#!/usr/bin/env python3
"""Build deadline-safe 286-feature rows for upcoming FPL fixtures.

The historical rolling feature definitions are executed from the pinned MIT Dastan
reconstruction package. CTA owns the target-fixture assembly, feature contract,
snapshot policy, and all downstream points modelling. Only the p60 head is imported
from Dastan; this script does not invoke any Dastan points head.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from feature_availability import mask_unavailable_features, unavailable_feature_names

POSITIONS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
STATUS_RISK = {"a": 0, "d": 1, "s": 2, "i": 3, "u": 4, "n": 4}
BASE_MATCH_STATS = (
    "minutes", "total_points", "influence", "creativity", "threat", "goals_scored",
    "penalties_missed", "assists", "goals_conceded", "own_goals", "saves",
    "penalties_saved", "yellow_cards", "red_cards", "bps", "bonus", "value",
    "selected", "transfers_balance", "team_h_score", "team_a_score",
    "us_team_xG", "us_team_xGA", "us_deep", "us_deep_allowed",
    "expected_points_pre_deadline",
)
DEFENSIVE_STATS = (
    "starts", "clearances_blocks_interceptions", "defensive_contribution",
    "recoveries", "tackles",
)


def _float(value, default=0.0):
    if value in (None, ""):
        return float(default)
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float(default)
    return result if math.isfinite(result) else float(default)


def exact_fixture_opponent_lookup(team_matches: pd.DataFrame) -> pd.DataFrame:
    """Preserve FPL fixture-linked opponents instead of inferring them by scoreline.

    Multiple EPL matches can share a kickoff and scoreline. The Dastan generic
    Understat matcher can then pair the wrong clubs when xG is unavailable.
    CTA's FPL fixture ID and reciprocal opponent mapping are exact identifiers.
    """
    required = {"season", "fixture", "understat_team", "opponent"}
    missing = sorted(required - set(team_matches.columns))
    if missing:
        raise ValueError(
            f"FPL-native team matches require exact fixture/opponent keys: {missing}"
        )
    out = team_matches.copy()
    keys = ["season", "fixture"]
    if out.duplicated(keys + ["understat_team"]).any():
        raise ValueError("duplicate team row within an FPL fixture")
    for (season, fixture), group in out.groupby(keys, sort=False):
        if len(group) != 2 or group["understat_team"].nunique() != 2:
            raise ValueError(
                f"{season} fixture {fixture} must contain exactly two distinct teams"
            )
        mapping = dict(zip(group["understat_team"].astype(str),
                           group["opponent"].astype(str)))
        if any(mapping.get(team) != opponent or mapping.get(opponent) != team
               for team, opponent in mapping.items()):
            raise ValueError(
                f"{season} fixture {fixture} has non-reciprocal opponent mapping: {mapping}"
            )
    return out


def build_future_rows(bootstrap: dict, fixtures: list[dict], player_map: dict, club_map: dict,
                      season: str, gameweeks: list[int]) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    teams = {int(team["id"]): str(team["name"]) for team in bootstrap.get("teams", [])}
    players = []
    for item in bootstrap.get("elements", []):
        position = POSITIONS.get(int(item.get("element_type", 0)))
        if position is None:
            continue
        players.append(item)
    if not players:
        raise ValueError("FPL bootstrap contains no outfield/goalkeeper player records")
    missing_clubs = sorted({name for name in teams.values() if name not in club_map})
    unmapped_clubs = sorted(name for name in teams.values()
                            if name in club_map and (
            not club_map[name].get("understat_name")
            or str(club_map[name].get("mapping_status", "mapped")).lower() != "mapped"
        ))
    if missing_clubs or unmapped_clubs:
        raise ValueError(f"Understat club mapping incomplete: missing={missing_clubs}, unmapped={unmapped_clubs}")

    selected_fixtures = [
        f for f in fixtures
        if f.get("event") is not None and int(f["event"]) in set(gameweeks)
        and not f.get("finished") and not f.get("finished_provisional")
        and f.get("kickoff_time") and f.get("team_h") and f.get("team_a")
    ]
    if not selected_fixtures:
        raise ValueError("No scheduled fixtures found in requested five-GW horizon")

    player_rows, team_rows = [], []
    fixture_metadata = []
    mapping_seen = set()
    for fixture in selected_fixtures:
        fixture_id = int(fixture["id"])
        gw = int(fixture["event"])
        home_id, away_id = int(fixture["team_h"]), int(fixture["team_a"])
        home_fpl, away_fpl = teams[home_id], teams[away_id]
        home_us = str(club_map[home_fpl]["understat_name"])
        away_us = str(club_map[away_fpl]["understat_name"])
        kickoff = pd.to_datetime(fixture["kickoff_time"], utc=True, errors="raise")
        fixture_metadata.append({
            "season": season, "gameweek": gw, "fixture_id": fixture_id,
            "kickoff_time": kickoff.isoformat(), "team_h_id": home_id,
            "team_h_name": home_fpl, "team_a_id": away_id, "team_a_name": away_fpl,
        })
        for team_id, own_us, opp_us, is_home in (
            (home_id, home_us, away_us, True), (away_id, away_us, home_us, False)
        ):
            team_rows.append({
                "season": season, "fixture": fixture_id, "date": kickoff,
                "understat_team": own_us, "opponent": opp_us,
                "is_home": float(is_home), "scored": 0.0, "missed": 0.0,
                "xG": float(fixture_id * 2 + (0 if is_home else 1)),
                "xGA": float(fixture_id * 2 + (1 if is_home else 0)),
                "deep": 0.0, "deep_allowed": 0.0,
                "ppda_att": 0.0, "ppda_def": 0.0,
                "ppda_allowed_att": 0.0, "ppda_allowed_def": 0.0, "pts": 0.0,
            })
        for player in players:
            own_team_id = int(player["team"])
            if own_team_id not in (home_id, away_id):
                continue
            is_home = own_team_id == home_id
            own_fpl = home_fpl if is_home else away_fpl
            opp_fpl = away_fpl if is_home else home_fpl
            own_us = home_us if is_home else away_us
            opp_us = away_us if is_home else home_us
            code = int(player["code"])
            mapped = player_map.get(code)
            understat_id = mapped.get("understat_id") if mapped else None
            if mapped and mapped.get("mapping_status") == "shared_understat_id":
                understat_id = None
            if understat_id:
                mapping_seen.add(code)
            row = {
                "season": season, "gameweek": gw, "fixture": fixture_id,
                "fpl_code": code, "element": int(player["id"]),
                "player_name": str(player.get("web_name", "")),
                "position": POSITIONS[int(player["element_type"])],
                # Use Understat's canonical club names consistently throughout this
                # feature build; retain FPL names separately in output metadata.
                "team_name": own_fpl, "opponent_team_name": opp_fpl,
                "us_opponent": opp_us, "kickoff_time": kickoff,
                "match_date": kickoff.date().isoformat(), "is_home": is_home,
                "understat_id": float(understat_id) if understat_id else np.nan,
                "minutes": 0.0, "total_points": 0.0,
                "expected_points_pre_deadline": 0.0,
                "value": _float(player.get("now_cost")),
                "selected": _float(player.get("selected_by_percent")),
                "transfers_balance": _float(player.get("transfers_balance")),
                "team_h_score": 0.0, "team_a_score": 0.0,
                "us_team_xG": 0.0, "us_team_xGA": 0.0,
                "us_deep": 0.0, "us_deep_allowed": 0.0,
            }
            for field in BASE_MATCH_STATS:
                row.setdefault(field, 0.0)
            for field in DEFENSIVE_STATS:
                row[field] = np.nan
            player_rows.append(row)

    player_frame = pd.DataFrame(player_rows)
    team_frame = pd.DataFrame(team_rows)
    if player_frame.empty or team_frame.empty:
        raise ValueError("No player/team fixture rows generated")
    if player_frame.duplicated(["season", "gameweek", "fixture", "fpl_code"]).any():
        raise ValueError("duplicate future player-fixture rows")
    report = {
        "scheduled_fixtures": len(fixture_metadata),
        "target_player_fixture_rows": len(player_frame),
        "target_team_fixture_rows": len(team_frame),
        "roster_players": len(players),
        "understat_mapped_target_players": len(mapping_seen),
        "understat_unmapped_target_players": len(set(player_frame["fpl_code"]) - mapping_seen),
        "understat_player_mapping_coverage_pct": round(100.0 * len(mapping_seen) / len(set(player_frame["fpl_code"])), 3),
        "team_mapping_coverage": "100% required; fail-closed",
        "fixture_metadata": fixture_metadata,
    }
    return player_frame, team_frame, report


def add_live_snapshot_features(frame: pd.DataFrame, bootstrap: dict, first_gameweek: int) -> pd.DataFrame:
    elements = {int(row["code"]): row for row in bootstrap.get("elements", [])}
    out = frame.copy()
    for col in ("ar_ep_next", "sig_status_risk", "sig_chance_playing", "sig_has_news"):
        out[col] = -1.0
    mask = pd.to_numeric(out["gameweek"], errors="coerce").eq(first_gameweek)
    for index in out.index[mask]:
        code = int(out.at[index, "fpl_code"])
        player = elements.get(code)
        if not player:
            continue
        ep = player.get("ep_next")
        chance = player.get("chance_of_playing_next_round")
        status = str(player.get("status") or "a")
        out.at[index, "ar_ep_next"] = -1.0 if ep in (None, "") else _float(ep, -1.0)
        out.at[index, "sig_status_risk"] = float(STATUS_RISK.get(status, 4))
        out.at[index, "sig_chance_playing"] = -1.0 if chance is None else _float(chance, -1.0)
        out.at[index, "sig_has_news"] = float(bool(str(player.get("news") or "").strip()))
    return out


def anchor_team_features_to_deadline(target: pd.DataFrame) -> pd.DataFrame:
    """Prevent earlier target-GW dummy fixtures contaminating later DGW rows.

    Player/own-team history is anchored by Dastan's deadline routine. Opponent
    columns are intentionally not flattened there, so rebuild them from each
    opponent's earliest target-GW row, whose shifted team history contains only
    completed matches before the deadline.
    """
    out = target.copy()
    team_columns = [c for c in out.columns if c.startswith("team_") and pd.api.types.is_numeric_dtype(out[c])]
    status_columns = [c for c in ("status_league_rank", "status_opp_league_rank") if c in out]
    if not team_columns and not status_columns:
        return out
    sort_columns = ["kickoff_time"] + (["fixture"] if "fixture" in out.columns else [])
    if "fpl_code" in out.columns:
        sort_columns.append("fpl_code")
    ordered = out.sort_values(sort_columns, kind="mergesort")
    earliest = ordered.drop_duplicates("team_name", keep="first").set_index("team_name")
    for index, row in out.iterrows():
        own = earliest.loc[row["team_name"]]
        for column in team_columns + status_columns:
            out.at[index, column] = own[column]
        opponent = earliest.loc[row["opponent_team_name"]]
        for column in team_columns:
            target_column = column.replace("team_", "opp_", 1)
            if target_column in out.columns:
                out.at[index, target_column] = opponent[column]
        if "opp_status_league_rank" in out.columns and "status_league_rank" in opponent:
            out.at[index, "opp_status_league_rank"] = opponent["status_league_rank"]
        if "opp_status_opp_league_rank" in out.columns and "status_opp_league_rank" in opponent:
            out.at[index, "opp_status_opp_league_rank"] = opponent["status_opp_league_rank"]
    return out


def anchor_player_features_to_deadline(target: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """Give every same-GW fixture for a player the same pre-deadline player history.

    Dastan's rolling builder shifts rows, so a player with two target fixtures in
    one GW can otherwise have the earlier dummy target row enter the later row's
    player rolling features. Anchor player-history and availability families to
    that player's earliest target row. Keep date/opponent-dependent ar_* features
    fixture-specific.
    """
    out = target.copy()
    dynamic_ar = {"ar_rest_days", "ar_team_matches_14d"}
    anchored = [
        feature for feature in features
        if feature.startswith(("player_", "p_any_", "p60_", "e_minutes_"))
        or (
            feature.startswith("ar_")
            and feature not in dynamic_ar
            and not feature.startswith("ar_opp_")
        )
    ]
    if not anchored or "fpl_code" not in out:
        return out
    ordered = out.sort_values(
        ["kickoff_time", "fixture"], kind="mergesort"
    ).drop_duplicates("fpl_code", keep="first").set_index("fpl_code")
    for index, row in out.iterrows():
        code = row["fpl_code"]
        for feature in anchored:
            if feature in out.columns:
                out.at[index, feature] = ordered.at[code, feature]
    return out


def anchor_opponent_features_to_deadline(target: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """Keep opponent-history features fixed to each opponent's pre-deadline state."""
    out = target.copy()
    anchored = [feature for feature in features if feature.startswith("ar_opp_")]
    if not anchored or "opponent_team_name" not in out:
        return out
    ordered = out.sort_values(
        ["kickoff_time", "fixture"], kind="mergesort"
    ).drop_duplicates("opponent_team_name", keep="first").set_index("opponent_team_name")
    for index, row in out.iterrows():
        opponent = row["opponent_team_name"]
        for feature in anchored:
            if feature in out.columns:
                out.at[index, feature] = ordered.at[opponent, feature]
    return out


def validate_bootstrap_snapshot(bootstrap: dict, first_gameweek: int, deadline: pd.Timestamp) -> dict:
    metadata = bootstrap.get("_cta_snapshot")
    if not isinstance(metadata, dict):
        raise ValueError("bootstrap snapshot is missing CTA capture-time provenance")
    if int(metadata.get("gameweek", -1)) != int(first_gameweek):
        raise ValueError("bootstrap snapshot metadata targets a different Gameweek")
    captured = pd.to_datetime(metadata.get("captured_at_utc"), utc=True, errors="coerce")
    stated_deadline = pd.to_datetime(metadata.get("deadline_time"), utc=True, errors="coerce")
    if pd.isna(captured) or pd.isna(stated_deadline):
        raise ValueError("bootstrap snapshot metadata has invalid timestamps")
    if abs((stated_deadline - deadline).total_seconds()) > 1:
        raise ValueError("bootstrap snapshot deadline metadata does not match FPL event")
    safety_minutes = int(metadata.get("safety_buffer_minutes", 0))
    if safety_minutes < 5:
        raise ValueError("bootstrap snapshot safety buffer is below five minutes")
    if captured > deadline - pd.Timedelta(minutes=safety_minutes):
        raise ValueError("bootstrap snapshot was captured inside the deadline safety buffer")
    return {
        "captured_at_utc": captured.isoformat(),
        "deadline_time": deadline.isoformat(),
        "safety_buffer_minutes": safety_minutes,
    }


def build_matrix(dastan_root: Path, canonical_player_path: Path,
                 canonical_team_path: Path, player_mapping_path: Path,
                 bootstrap_path: Path, fixtures_path: Path, schema_path: Path,
                 output: Path, report_path: Path, target_gameweeks: list[int]) -> dict:
    sys.path.insert(0, str(dastan_root))
    from dastan.rebuild import features as dastan_features
    build_feature_frame = dastan_features.build_feature_frame
    # FPL fixture IDs provide exact opponent pairing even when same-kickoff
    # fixtures share identical scorelines and Understat xG is unavailable.
    dastan_features.build_opponent_lookup = exact_fixture_opponent_lookup

    bootstrap = json.loads(bootstrap_path.read_text(encoding="utf-8"))
    fixtures = json.loads(fixtures_path.read_text(encoding="utf-8"))
    player_history = pd.read_parquet(canonical_player_path)
    team_history = pd.read_parquet(canonical_team_path)
    if player_history.empty or team_history.empty:
        raise ValueError("Canonical player/team match inputs must be non-empty")
    events = bootstrap.get("events", [])
    next_events = [int(event["id"]) for event in events if event.get("is_next")]
    if len(next_events) != 1:
        raise ValueError(f"Expected exactly one is_next FPL event, found {next_events}")
    first_gw = next_events[0]
    if target_gameweeks != list(range(first_gw, first_gw + 5)):
        raise ValueError("Target horizon must be the next five consecutive gameweek IDs")

    deadlines = [pd.to_datetime(event["deadline_time"], utc=True) for event in events if int(event["id"]) == first_gw]
    if not deadlines:
        raise ValueError("next event is missing deadline_time")
    deadline = deadlines[0]
    snapshot_metadata = validate_bootstrap_snapshot(bootstrap, first_gw, deadline)
    season_start = int(deadline.year) if deadline.month >= 6 else int(deadline.year) - 1
    season = f"{season_start}-{str(season_start + 1)[-2:]}"

    players_map = pd.read_csv(player_mapping_path, keep_default_na=False)
    if not {"fpl_code", "understat_player_id", "mapping_status"}.issubset(players_map.columns):
        raise ValueError("Safe current-player mapping is missing required columns")
    players_map["understat_player_id"] = pd.to_numeric(players_map["understat_player_id"], errors="coerce")
    mapped = players_map.dropna(subset=["understat_player_id"])
    shared_ids = set(mapped.groupby("understat_player_id")["fpl_code"].nunique().loc[lambda x: x > 1].index.astype(int))
    player_map = {}
    for row in players_map.to_dict("records"):
        code = int(row["fpl_code"])
        raw_id = row.get("understat_player_id")
        understat_id = int(float(raw_id)) if raw_id not in (None, "") and pd.notna(raw_id) else None
        if understat_id in shared_ids:
            understat_id = None
        player_map[code] = {"understat_id": understat_id, "mapping_status": str(row.get("mapping_status", ""))}
    club_path = dastan_root / "data" / "mappings" / "current_fpl_understat_clubs.csv"
    clubs_map = pd.read_csv(club_path, keep_default_na=False)
    club_map = {str(row["club_name"]): row for row in clubs_map.to_dict("records")}
    # Extend Dastan's FPL->Understat alias map from the exact operational club map.
    dastan_features.FPL_TO_UNDERSTAT.update({
        str(row["club_name"]): str(row["understat_name"])
        for row in clubs_map.to_dict("records")
        if row.get("understat_name")
    })

    future_players, future_teams, coverage = build_future_rows(
        bootstrap, fixtures, player_map, club_map, season, target_gameweeks
    )

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    features = schema.get("feature_order")
    if not isinstance(features, list) or len(features) != 286:
        raise ValueError("CTA Dastan feature schema is not 286 features")

    matrices = []
    for gw in target_gameweeks:
        gw_players = future_players[future_players["gameweek"].eq(gw)].copy()
        if gw_players.empty:
            continue
        fixture_ids = set(gw_players["fixture"].astype(int))
        gw_teams = future_teams[future_teams["date"].isin(gw_players["kickoff_time"].unique())].copy()
        # Historical rows remain untouched; only this target GW's unplayed fixtures
        # are appended, preventing future dummy rows contaminating later horizons.
        combined_players = pd.concat([player_history, gw_players], ignore_index=True, sort=False)
        combined_teams = pd.concat([team_history, gw_teams], ignore_index=True, sort=False)
        built = build_feature_frame(combined_players, combined_teams)
        target = built[
            built["season"].astype(str).eq(season)
            & pd.to_numeric(built["gameweek"], errors="coerce").eq(gw)
            & pd.to_numeric(built["fixture"], errors="coerce").isin(fixture_ids)
        ].copy()
        target = anchor_team_features_to_deadline(target)
        target = anchor_player_features_to_deadline(target, features)
        target = anchor_opponent_features_to_deadline(target, features)
        target = add_live_snapshot_features(target, bootstrap, first_gw)
        metadata = gw_players[[
            "season", "gameweek", "fixture", "fpl_code", "element", "position",
            "team_name", "opponent_team_name", "kickoff_time", "is_home", "understat_id",
        ]].drop_duplicates(["season", "gameweek", "fixture", "fpl_code"])
        target = target.merge(
            metadata,
            on=["season", "gameweek", "fixture", "fpl_code"],
            how="left", suffixes=("", "_target"), validate="one_to_one"
        )
        if len(target) != len(gw_players):
            raise RuntimeError(f"GW{gw}: feature builder row coverage {len(target)} != target rows {len(gw_players)}")
        missing = [feature for feature in features if feature not in target]
        if missing:
            raise RuntimeError(f"GW{gw}: feature builder missing schema fields: {missing}")
        for feature in features:
            values = pd.to_numeric(target[feature], errors="coerce")
            # Dastan's two-stage inference contract: snapshot absence is already
            # -1.0; only residual NaNs are filled with 0.0.
            target[feature] = values.fillna(0.0).astype(float)
        # Keep current FPL-native inference aligned with CTA training: the
        # Understat-derived feature family is unavailable in this source mode.
        target, _masked = mask_unavailable_features(target, features)
        element_column = "element_target" if "element_target" in target.columns else "element"
        if element_column not in target.columns:
            raise RuntimeError(f"GW{gw}: feature builder lost FPL element identity")
        target["fpl_element_id"] = target[element_column]
        target["fixture_id"] = target["fixture"]
        target["kickoff_time"] = pd.to_datetime(target["kickoff_time"], utc=True).astype(str)
        matrices.append(target[[
            "season", "gameweek", "fpl_code", "fpl_element_id", "fixture_id",
            "position", "team_name", "opponent_team_name", "kickoff_time", *features
        ]])

    if not matrices:
        raise ValueError("No five-GW feature rows were built")
    result = pd.concat(matrices, ignore_index=True)
    if result.duplicated(["season", "gameweek", "fpl_code", "fixture_id"]).any():
        raise RuntimeError("final feature matrix has duplicate player-fixture keys")
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False, lineterminator="\n")
    report = {
        "status": "PASS_CTA_FIVE_GW_FEATURE_MATRIX",
        "season": season,
        "target_gameweeks": target_gameweeks,
        "rows": len(result),
        "feature_count": len(features),
        "masked_unavailable_features": unavailable_feature_names(features),
        "feature_schema": schema.get("schema_version"),
        "deadline": deadline.isoformat(),
        "bootstrap_snapshot": snapshot_metadata,
        "snapshot_policy": "live bootstrap ep_next/status/chance/news only for next GW; later GWs use -1 sentinel; all snapshots must precede deadline by at least five minutes",
        "rolling_history_policy": "player rolling/availability history and team history are anchored to the pre-deadline state across every fixture in each GW; date/opponent-dependent context remains fixture-specific",
        "dastan_role": "historical feature definitions and minutes component only; no Dastan points heads used",
        "mapping_coverage": coverage,
        "input_artifacts": {
            "bootstrap_sha256": __import__("hashlib").sha256(bootstrap_path.read_bytes()).hexdigest(),
            "fixtures_sha256": __import__("hashlib").sha256(fixtures_path.read_bytes()).hexdigest(),
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "mapping_coverage"}, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dastan-root", type=Path, required=True)
    parser.add_argument("--canonical-player-matches", type=Path, required=True)
    parser.add_argument("--canonical-team-matches", type=Path, required=True)
    parser.add_argument("--player-mapping", type=Path, required=True)
    parser.add_argument("--bootstrap", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--target-gameweeks", required=True, help="five comma-separated consecutive GW IDs")
    args = parser.parse_args()
    gameweeks = [int(value.strip()) for value in args.target_gameweeks.split(",") if value.strip()]
    if len(gameweeks) != 5:
        parser.error("--target-gameweeks must contain exactly five gameweek IDs")
    build_matrix(args.dastan_root, args.canonical_player_matches,
                 args.canonical_team_matches, args.player_mapping, args.bootstrap,
                 args.fixtures, args.schema, args.output, args.report, gameweeks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
