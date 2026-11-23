"""Build current-season 286-feature player-fixture history and target query rows.

This creates an inference-ready candidate frame for an upcoming, not-yet-started
Gameweek. It uses the official pre-deadline FPL cache snapshot for the target roster
and joins the same Dastan-derived feature definitions used by the historical rebuild.
No model is trained and no feature is promoted by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from build_2pm_predeadline_market_snapshot import build_market_artifact
from rebuild_2pm_dastan_286_candidate import (
    attach_match_availability_bounds,
    attach_official_deadlines,
    load_dastan_package,
    sha256,
    validate_reconstruction_coverage,
)
from rebuild_2pm_fixture_context import (
    rebuild_deadline_team_context,
    rebuild_fixture_context,
    rebuild_player_history_features,
)

KEY = ["season", "gameweek", "fpl_code"]
MARKET_FIELDS = ["value", "selected", "transfers_balance"]
POSITION_BY_ELEMENT_TYPE = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def build_fixture_player_rows(
    fixtures: pd.DataFrame,
    elements: list[dict[str, Any]],
    teams: pd.DataFrame,
    assignments: pd.DataFrame,
    *,
    season: str,
    gameweek: int,
    deadline: pd.Timestamp,
    now: pd.Timestamp,
    features_module,
) -> pd.DataFrame:
    """Create one pre-match player row for every active player/target fixture."""
    fixture_frame = fixtures.copy()
    fixture_frame["event"] = pd.to_numeric(fixture_frame["event"], errors="coerce")
    fixture_frame["kickoff_time"] = pd.to_datetime(
        fixture_frame["kickoff_time"], utc=True, errors="coerce"
    )
    selected = fixture_frame[fixture_frame["event"].eq(int(gameweek))].copy()
    if selected.empty:
        raise ValueError(f"No fixtures found for {season} GW{gameweek}")
    if selected["kickoff_time"].isna().any():
        raise ValueError("Target Gameweek contains fixtures without kickoff timestamps")
    finished = selected["finished"].astype(str).str.lower().eq("true")
    if finished.any() or selected["kickoff_time"].le(now).any():
        raise ValueError(
            "Target Gameweek has already started; deadline-safe current query build refused"
        )
    if selected["kickoff_time"].le(deadline).any():
        raise ValueError("A target fixture kickoff is not after its official deadline")

    team_names = teams.set_index("id")["name"].astype(str).to_dict()
    players = pd.DataFrame(elements)
    required = {"id", "code", "team", "element_type"}
    missing = sorted(required - set(players.columns))
    if missing:
        raise ValueError(f"FPL target snapshot lacks player fields: {missing}")
    players = players.dropna(subset=["id", "code", "team", "element_type"]).copy()
    players["id"] = pd.to_numeric(players["id"], errors="raise").astype(int)
    players["code"] = pd.to_numeric(players["code"], errors="raise").astype(int)
    players["team"] = pd.to_numeric(players["team"], errors="raise").astype(int)
    players["element_type"] = pd.to_numeric(
        players["element_type"], errors="raise"
    ).astype(int)
    if players["code"].duplicated().any():
        raise ValueError("FPL target snapshot contains duplicate stable player codes")

    identity = assignments[assignments["season"].astype(str).eq(str(season))][
        ["fpl_code", "understat_id"]
    ].drop_duplicates("fpl_code")
    players = players.merge(
        identity, left_on="code", right_on="fpl_code", how="left", validate="one_to_one"
    )
    output = []
    for fixture in selected.itertuples(index=False):
        for team_id, opponent_id, is_home in (
            (int(fixture.team_h), int(fixture.team_a), 1),
            (int(fixture.team_a), int(fixture.team_h), 0),
        ):
            team_name = team_names.get(team_id)
            opponent_name = team_names.get(opponent_id)
            if not team_name or not opponent_name:
                raise ValueError(
                    f"Fixture {fixture.id} references unknown team IDs {team_id}/{opponent_id}"
                )
            roster = players[players["team"].eq(team_id)]
            for player in roster.itertuples(index=False):
                position = POSITION_BY_ELEMENT_TYPE.get(int(player.element_type))
                if position is None:
                    raise ValueError(f"Unknown FPL element_type {player.element_type}")
                output.append(
                    {
                        "season": str(season),
                        "gameweek": int(gameweek),
                        "fixture": int(fixture.id),
                        "fpl_code": int(player.code),
                        "element": int(player.id),
                        "position": position,
                        "team_name": team_name,
                        "opponent_team_name": opponent_name,
                        "us_opponent": features_module.fpl_to_understat(opponent_name),
                        "kickoff_time": pd.Timestamp(fixture.kickoff_time),
                        "minutes": 0.0,
                        "total_points": 0.0,
                        "is_home": bool(is_home),
                        "understat_id": (
                            int(player.understat_id)
                            if pd.notna(player.understat_id)
                            else np.nan
                        ),
                        "expected_points_pre_deadline": 0.0,
                        "starts": np.nan,
                        "clearances_blocks_interceptions": np.nan,
                        "defensive_contribution": np.nan,
                        "recoveries": np.nan,
                        "tackles": np.nan,
                    }
                )
    result = pd.DataFrame(output)
    if result.empty:
        raise ValueError("No target player rows were produced")
    if result.duplicated(["season", "gameweek", "fixture", "fpl_code"]).any():
        raise ValueError("Target player-fixture rows contain duplicate keys")
    return result


def attach_snapshot_features(
    frame: pd.DataFrame,
    output_dir: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Join pre-deadline EP, availability and market snapshots with -1 sentinels."""
    result = frame.drop(
        columns=[*MARKET_FIELDS, "ar_ep_next", "sig_status_risk",
                 "sig_chance_playing", "sig_has_news"],
        errors="ignore",
    ).copy()
    ep = pd.read_parquet(output_dir / "pre_deadline_ep_next.parquet")
    signals = pd.read_parquet(output_dir / "pre_deadline_signals.parquet")
    market = pd.read_parquet(output_dir / "pre_deadline_market.parquet")
    ep = ep[KEY + ["ep_next", "snapshot_at"]].rename(
        columns={"snapshot_at": "ep_next_snapshot_at"}
    )
    signals = signals[
        KEY + ["sig_status_risk", "sig_chance_playing", "sig_has_news", "snapshot_at"]
    ].rename(columns={"snapshot_at": "signals_snapshot_at"})
    market = market[KEY + MARKET_FIELDS + ["snapshot_at"]].rename(
        columns={"snapshot_at": "market_snapshot_at"}
    )
    result = result.merge(ep, on=KEY, how="left", validate="many_to_one")
    result = result.merge(signals, on=KEY, how="left", validate="many_to_one")
    result = result.merge(market, on=KEY, how="left", validate="many_to_one")
    result["ar_ep_next"] = pd.to_numeric(result["ep_next"], errors="coerce").fillna(-1.0)
    for column in ["sig_status_risk", "sig_chance_playing", "sig_has_news", *MARKET_FIELDS]:
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(-1.0)
    snapshot_columns = [
        "ep_next_snapshot_at", "signals_snapshot_at", "market_snapshot_at"
    ]
    for column in snapshot_columns:
        result[column] = pd.to_datetime(result[column], utc=True, errors="coerce")
        present = result[column].notna()
        if present.any():
            age = result.loc[present, "deadline_time"] - result.loc[present, column]
            if age.lt(pd.Timedelta(minutes=5)).any():
                raise RuntimeError(f"{column} contains a snapshot inside the five-minute safety buffer")
            if age.le(pd.Timedelta(0)).any():
                raise RuntimeError(f"{column} contains a post-deadline snapshot")
    return result, {
        "rows": int(len(result)),
        "snapshot_coverage": {
            column: int(result[column].notna().sum()) for column in snapshot_columns
        },
    }



def build_future_fixture_schedule_rows(
    fixtures: pd.DataFrame,
    teams: pd.DataFrame,
    *,
    season: str,
    now: pd.Timestamp,
) -> pd.DataFrame:
    """Create schedule-only team/fixture rows for upcoming fixtures.

    These rows have no player identity or match results and a NaT availability
    timestamp. They are used only for fixture-count context, never as history.
    """
    team_names = teams.set_index("id")["name"].to_dict()
    now = pd.Timestamp(now)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    rows = []
    for fixture in fixtures.to_dict("records"):
        kickoff = pd.to_datetime(fixture.get("kickoff_time"), utc=True, errors="coerce")
        if pd.isna(kickoff) or kickoff <= now:
            continue
        home = team_names.get(int(fixture["team_h"]))
        away = team_names.get(int(fixture["team_a"]))
        if not home or not away:
            raise ValueError(f"Future fixture {fixture.get('id')} has unmapped FPL teams")
        for team_name, opponent_name, is_home in (
            (home, away, True),
            (away, home, False),
        ):
            rows.append(
                {
                    "season": str(season),
                    "fixture": str(fixture["id"]),
                    "fpl_code": -1,
                    "element": -1,
                    "understat_id": np.nan,
                    "position": "MID",
                    "is_home": is_home,
                    "team_name": team_name,
                    "opponent_team_name": opponent_name,
                    "kickoff_time": kickoff,
                    "match_available_at": pd.NaT,
                    "minutes": 0.0,
                    "total_points": 0.0,
                    "defensive_contribution": np.nan,
                    "clearances_blocks_interceptions": np.nan,
                    "recoveries": np.nan,
                    "tackles": np.nan,
                    "starts": np.nan,
                }
            )
    return pd.DataFrame(rows)

def build_active_target_candidate(
    dastan_root: Path,
    raw_dir: Path,
    output_dir: Path,
    season: str,
    gameweek: int,
    *,
    workers: int = 12,
    now: pd.Timestamp | None = None,
) -> dict[str, Any]:
    data, mappings, features, fplcache, sources = load_dastan_package(dastan_root)
    registry = json.loads((data.DATA / "season_registry.json").read_text())
    if season in set(map(str, registry["completed_seasons"])):
        raise ValueError(f"{season} is a completed season, not the active target season")
    mappings.assert_operational_clubs_ready(season)
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Downloading current-season FPL/Understat histories", flush=True)
    sources.download_sources(raw_dir, [season], workers=workers, force=False)
    player_matches, team_matches, _ = sources.build_canonical_matches(raw_dir, [season])

    fixture_path = raw_dir / "vaastav" / season / "fixtures.csv"
    if not fixture_path.exists() or fixture_path.stat().st_size == 0:
        sources._download(
            sources.VAASTAV_RAW + f"data/{season}/fixtures.csv", fixture_path
        )
    fixtures = pd.read_csv(fixture_path)
    deadlines = fplcache.season_deadlines(
        raw_dir, fplcache.load_index(raw_dir), season
    )
    if int(gameweek) not in deadlines:
        raise ValueError(f"No official FPL deadline for {season} GW{gameweek}")
    deadline = pd.Timestamp(deadlines[int(gameweek)])
    deadline = deadline.tz_localize("UTC") if deadline.tzinfo is None else deadline.tz_convert("UTC")
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")

    index = fplcache.load_index(raw_dir)
    selected_snapshot = fplcache.pick_snapshot(index, deadline.to_pydatetime())
    if selected_snapshot is None:
        raise RuntimeError("No FPL cache snapshot exists before the target deadline")
    captured_at, source_path = selected_snapshot
    age_hours = (deadline.to_pydatetime() - captured_at).total_seconds() / 3600
    if age_hours > 30 or age_hours < 5 / 60:
        raise RuntimeError(
            f"Target snapshot age {age_hours:.2f}h is outside the 5m–30h safety window"
        )
    payload = fplcache.fetch_snapshot(raw_dir, source_path)
    if not fplcache._accepted_event(payload, int(gameweek), deadline.to_pydatetime()):
        raise RuntimeError("Selected FPL snapshot does not mark the target GW as is_next")

    print("Rebuilding current-season pre-deadline snapshot artifacts", flush=True)
    fplcache.build_predeadline_artifacts(raw_dir, output_dir, [season])
    ep_safety = __import__(
        "rebuild_2pm_dastan_286_candidate", fromlist=["enforce_snapshot_safety_buffer"]
    ).enforce_snapshot_safety_buffer(
        output_dir / "pre_deadline_ep_next.parquet", minutes=5
    )
    signal_safety = __import__(
        "rebuild_2pm_dastan_286_candidate", fromlist=["enforce_snapshot_safety_buffer"]
    ).enforce_snapshot_safety_buffer(
        output_dir / "pre_deadline_signals.parquet", minutes=5
    )
    market_path, market_report = build_market_artifact(
        raw_dir, output_dir, [season], fplcache, safety_buffer_minutes=5
    )
    if market_path.name != "pre_deadline_market.parquet":
        raise RuntimeError("Unexpected market artifact path")

    # The history frame contains only completed player fixtures from the current season.
    history = features.build_feature_frame(player_matches, team_matches)
    history = attach_official_deadlines(history, raw_dir, fplcache, [season])
    history = attach_match_availability_bounds(history, raw_dir, sources, [season])
    history["feature_cutoff_time"] = history["deadline_time"]
    history["source_vintage_status"] = "ACTIVE_SEASON_HISTORY_VINTAGE_NOT_ARCHIVED_AT_ORIGINAL_DEADLINES"
    history, history_snapshot_report = attach_snapshot_features(history, output_dir)

    teams = pd.read_csv(raw_dir / "vaastav" / season / "teams.csv")
    assignments = mappings.assignments_for_seasons([season])
    target_fixture_rows = build_fixture_player_rows(
        fixtures,
        payload.get("elements", []),
        teams,
        assignments,
        season=season,
        gameweek=int(gameweek),
        deadline=deadline,
        now=now,
        features_module=features,
    )

    query_parts = []
    for fixture_id, fixture_players in target_fixture_rows.groupby("fixture", sort=True):
        print(f"Building target fixture query {fixture_id}", flush=True)
        combined = pd.concat(
            [player_matches, fixture_players], ignore_index=True, sort=False
        )
        feature_frame = features.build_feature_frame(combined, team_matches)
        query = feature_frame[
            feature_frame["fixture"].astype(int).eq(int(fixture_id))
            & feature_frame["gameweek"].astype(int).eq(int(gameweek))
        ].copy()
        query = attach_official_deadlines(query, raw_dir, fplcache, [season])
        query = attach_match_availability_bounds(query, raw_dir, sources, [season])
        query["feature_cutoff_time"] = query["deadline_time"]
        query["source_vintage_status"] = "CURRENT_TARGET_QUERY_FROM_PREDEADLINE_SNAPSHOT"
        query["target_points"] = np.nan
        query, _ = attach_snapshot_features(query, output_dir)
        query_parts.append(query)

    queries = pd.concat(query_parts, ignore_index=True)
    if queries.duplicated(["season", "gameweek", "fixture", "fpl_code"]).any():
        raise RuntimeError("Current target queries contain duplicate player-fixture rows")
    queries["row_role"] = "TARGET_QUERY"
    history["row_role"] = "HISTORICAL_FIXTURE"
    ordered_features = data.shipped_features(history)
    if len(ordered_features) != 286:
        raise RuntimeError(f"Expected 286 model features, got {len(ordered_features)}")

    # Reconstruct the complete 286 frame with the same deadline-safe adapters as
    # the completed-season pipeline. Include target roster rows in the source
    # calendar with NOT_FINISHED/NaT availability; they contribute schedule
    # context and identity, never historical match results.
    source_player_matches = pd.concat(
        [player_matches, target_fixture_rows],
        ignore_index=True,
        sort=False,
    )
    source_player_matches = attach_match_availability_bounds(
        source_player_matches, raw_dir, sources, [season]
    )
    schedule_rows = build_future_fixture_schedule_rows(
        fixtures, teams, season=season, now=now
    )
    if not schedule_rows.empty:
        source_player_matches = pd.concat(
            [source_player_matches, schedule_rows],
            ignore_index=True,
            sort=False,
        )
    combined = pd.concat([history, queries], ignore_index=True, sort=False)
    for key_frame in (combined, source_player_matches):
        key_frame["season"] = key_frame["season"].astype(str)
        key_frame["fixture"] = key_frame["fixture"].astype(str)
        key_frame["fpl_code"] = pd.to_numeric(
            key_frame["fpl_code"], errors="raise"
        ).astype("int64")
    combined, player_history_report = rebuild_player_history_features(
        combined, source_player_matches, features
    )
    combined, team_context_report = rebuild_deadline_team_context(
        combined, team_matches, features
    )
    combined, fixture_context_report = rebuild_fixture_context(
        combined, source_player_matches
    )
    reconstruction_coverage = validate_reconstruction_coverage(
        ordered_features,
        player_history_report,
        team_context_report,
        fixture_context_report,
        combined,
    )

    metadata = [
        "season", "gameweek", "fixture", "fpl_code", "position", "team_name",
        "opponent_team_name", "kickoff_time", "deadline_time", "feature_cutoff_time", "match_available_at",
        "completion_time_quality", "source_vintage_status", "minutes",
        "target_points", "ep_next_snapshot_at", "signals_snapshot_at",
        "market_snapshot_at", "row_role",
    ]
    absent = [column for column in metadata + ordered_features if column not in combined]
    if absent:
        raise RuntimeError(f"Active candidate frame missing required columns: {absent[:20]}")
    candidate = combined[metadata + ordered_features].copy()
    # Persist the full current-season match/schedule context so the selected
    # post-match sequence path can rebuild played-fixture states separately
    # from the pre-deadline TARGET_QUERY rows.
    player_matches_path = output_dir / "player_matches_with_availability.parquet"
    team_matches_path = output_dir / "team_matches.parquet"
    source_player_matches.to_parquet(player_matches_path, index=False)
    team_matches.to_parquet(team_matches_path, index=False)
    candidate["admission_status"] = "NOT_ADMITTED"
    candidate["feature_order_sha256"] = hashlib.sha256(
        "\n".join(ordered_features).encode()
    ).hexdigest()
    path = output_dir / f"2pm_{season}_gw{int(gameweek)}_active_candidate.parquet"
    candidate.to_parquet(path, index=False)
    sources.write_download_manifest(raw_dir, [season])
    report = {
        "status": "ACTIVE_SEASON_TARGET_QUERY_CANDIDATE_BUILT",
        "admission_status": "NOT_ADMITTED",
        "season": season,
        "gameweek": int(gameweek),
        "deadline_time": deadline.isoformat(),
        "target_snapshot_at": captured_at.isoformat(),
        "target_snapshot_age_hours": age_hours,
        "target_snapshot_path": source_path,
        "historical_player_fixture_rows": int(len(history)),
        "target_query_player_fixture_rows": int(len(queries)),
        "target_fixture_count": int(queries["fixture"].nunique()),
        "feature_count": len(ordered_features),
        "reconstruction_coverage": reconstruction_coverage,
        "player_history_reconstruction": player_history_report,
        "deadline_team_context_reconstruction": team_context_report,
        "fixture_context_reconstruction": fixture_context_report,
        "future_fixture_schedule_rows": int(len(schedule_rows)),
        "feature_order_sha256": candidate["feature_order_sha256"].iat[0],
        "player_matches_with_availability": player_matches_path.name,
        "player_match_context_rows": int(len(source_player_matches)),
        "team_matches_path": team_matches_path.name,
        "team_match_rows": int(len(team_matches)),
        "source_manifest_sha256": sha256(raw_dir / "downloads.json"),
        "snapshot_coverage": {
            "history": history_snapshot_report,
            "target": {
                "ep_next_rows": int(queries["ep_next_snapshot_at"].notna().sum()),
                "signals_rows": int(queries["signals_snapshot_at"].notna().sum()),
                "market_rows": int(queries["market_snapshot_at"].notna().sum()),
            },
        },
        "snapshot_safety_buffer": {
            "ep_next": ep_safety,
            "signals": signal_safety,
            "market": market_report.get("safety_buffer"),
        },
        "identity_mapping_coverage": {
            "target_players": int(queries["fpl_code"].nunique()),
            "understat_mapped_players": int(
                queries.loc[queries["understat_id"].notna(), "fpl_code"].nunique()
            ),
        },
        "limitations": [
            "Candidate only; all 286 feature source-vintage and value-parity admission gates remain open.",
            "All 286 feature families are independently reconstructed or joined from accepted deadline snapshots, but current-season historical source vintages are not archived at their original deadlines.",
            "Historical active-season rows are rebuilt from current archived sources, not exact historical source vintages.",
            "Target queries are refused once any fixture in the target Gameweek has started.",
            "Target-specific queries are built one fixture at a time to avoid flattening distinct Double Gameweek opponent context.",
            "This script does not train or evaluate the 2PM model.",
        ],
        "artifact": str(path),
    }
    (output_dir / "active_target_query_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dastan-root", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument("--gameweek", type=int, required=True)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    report = build_active_target_candidate(
        args.dastan_root, args.raw_dir, args.output_dir,
        args.season, args.gameweek, workers=args.workers,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
