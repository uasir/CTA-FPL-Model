"""Audit defensive rolling-window history depth for 2025/26 targets.

Reads only defensive source fields, fixture availability, and non-label target
metadata. It never reads target_points, total_points, xP, or any 2026/27 labels.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PLAYER_FIELDS = {
    "ar_defensive_contribution": "defensive_contribution",
    "ar_cbit": "clearances_blocks_interceptions",
    "ar_recoveries": "recoveries",
    "ar_tackles": "tackles",
}
PLAYER_WINDOWS = (3, 5, 10, 38)
RATE_FEATURES = {
    "ar_dc_hit_rate": (3, 5, 10),
    "ar_dc_near_rate": (3, 5, 10),
    "ar_dc_ppg": (5,),
}
OPPONENT_FEATURES = {
    "ar_opp_dc_allowed": (3, 5, 10),
    "ar_opp_tackles_allowed": (5,),
}
META_COLUMNS = ("season", "gameweek", "fpl_code", "target_deadline_time", "fixture_ids")
SOURCE_COLUMNS = (
    "fixture", "element", "team", "opponent_team", "kickoff_time",
    "defensive_contribution", "clearances_blocks_interceptions", "recoveries", "tackles",
)
FIXTURE_COLUMNS = ("id", "kickoff_time", "finished")


def _depth_record(
    *,
    season: str,
    gameweek: int,
    fpl_code: int,
    fixture: str | None,
    feature: str,
    window: int,
    selected_rows: int,
    finite_observations: int,
) -> dict[str, Any]:
    return {
        "season": season,
        "gameweek": gameweek,
        "fpl_code": fpl_code,
        "fixture": fixture,
        "feature": feature,
        "window": window,
        "selected_match_rows": selected_rows,
        "finite_observations": finite_observations,
        "missing_observations": selected_rows - finite_observations,
        "full_window_depth": finite_observations == window,
    }


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {"rows": 0}
    frame = pd.DataFrame(records)
    finite = pd.to_numeric(frame["finite_observations"], errors="raise")
    selected = pd.to_numeric(frame["selected_match_rows"], errors="raise")
    full = frame["full_window_depth"].astype(bool)
    return {
        "rows": int(len(frame)),
        "full_window_rows": int(full.sum()),
        "partial_or_shallow_rows": int((~full & finite.gt(0)).sum()),
        "zero_observation_rows": int(finite.eq(0).sum()),
        "min_finite_observations": int(finite.min()),
        "median_finite_observations": float(finite.median()),
        "p10_finite_observations": float(finite.quantile(0.10)),
        "p90_finite_observations": float(finite.quantile(0.90)),
        "max_finite_observations": int(finite.max()),
        "min_selected_match_rows": int(selected.min()),
        "max_selected_match_rows": int(selected.max()),
    }


def _load_metadata(metadata_dir: Path) -> pd.DataFrame:
    paths = sorted(metadata_dir.rglob("metadata_player_gw_*.csv"))
    if not paths:
        raise FileNotFoundError(f"No metadata_player_gw_*.csv files under {metadata_dir}")
    frames = [pd.read_csv(path, usecols=list(META_COLUMNS)) for path in paths]
    data = pd.concat(frames, ignore_index=True)
    data["season"] = data["season"].astype(str)
    if set(data["season"].unique()) != {"2025-26"}:
        raise ValueError("History-depth audit accepts 2025/26 metadata only")
    data["gameweek"] = pd.to_numeric(data["gameweek"], errors="raise").astype(int)
    data["fpl_code"] = pd.to_numeric(data["fpl_code"], errors="raise").astype(int)
    data["target_deadline_time"] = pd.to_datetime(
        data["target_deadline_time"], utc=True, errors="coerce"
    )
    if data["target_deadline_time"].isna().any():
        raise ValueError("Target metadata has invalid deadline timestamps")
    if data.duplicated(["season", "gameweek", "fpl_code"]).any():
        raise ValueError("Duplicate player-Gameweek metadata rows")
    return data


def audit_history_depth(
    source_path: Path,
    fixtures_path: Path,
    metadata_dir: Path,
    players_raw_path: Path,
) -> tuple[dict[str, Any], pd.DataFrame]:
    metadata = _load_metadata(metadata_dir)

    crosswalk = pd.read_csv(players_raw_path, usecols=["id", "code"]).rename(
        columns={"id": "element", "code": "fpl_code"}
    )
    crosswalk["fpl_code"] = pd.to_numeric(crosswalk["fpl_code"], errors="raise").astype(int)
    crosswalk["element"] = pd.to_numeric(crosswalk["element"], errors="raise").astype(int)
    if crosswalk["fpl_code"].duplicated().any() or crosswalk["element"].duplicated().any():
        raise ValueError("Identity crosswalk must be one-to-one for 2025/26")

    source = pd.read_csv(source_path, usecols=list(SOURCE_COLUMNS))
    source["fixture"] = source["fixture"].astype(str)
    source["element"] = pd.to_numeric(source["element"], errors="raise").astype(int)
    source["fpl_code"] = source["element"].map(crosswalk.set_index("element")["fpl_code"])
    source["team"] = pd.to_numeric(source["team"], errors="coerce")
    source["opponent_team"] = pd.to_numeric(source["opponent_team"], errors="coerce")
    source["kickoff_time"] = pd.to_datetime(source["kickoff_time"], utc=True, errors="coerce")
    if source["kickoff_time"].isna().any():
        raise ValueError("Defensive source contains invalid kickoff timestamps")

    fixtures = pd.read_csv(fixtures_path, usecols=list(FIXTURE_COLUMNS))
    fixtures["fixture"] = fixtures["id"].astype(str)
    fixtures["kickoff_time"] = pd.to_datetime(
        fixtures["kickoff_time"], utc=True, errors="coerce"
    )
    if fixtures["kickoff_time"].isna().any():
        raise ValueError("Fixture calendar contains invalid kickoff timestamps")
    finished = fixtures["finished"].astype(str).str.lower().eq("true")
    fixtures["match_available_at"] = fixtures["kickoff_time"] + pd.Timedelta(hours=24)
    fixtures.loc[~finished, "match_available_at"] = pd.NaT
    calendar = fixtures[["fixture", "match_available_at"]]
    if calendar.duplicated(["fixture"]).any():
        raise ValueError("Fixture calendar contains duplicate fixture IDs")
    source = source.merge(calendar, on="fixture", how="left", validate="many_to_one")
    if source["match_available_at"].isna().any():
        # Unfinished fixtures may legitimately be NaT, but their fixture IDs must
        # still have matched the official calendar.
        known = set(calendar["fixture"])
        missing_ids = sorted(set(source.loc[source["match_available_at"].isna(), "fixture"]) - known)
        if missing_ids:
            raise ValueError(f"Source fixture IDs missing from fixture calendar: {missing_ids[:10]}")
    source = source.sort_values(
        ["fpl_code", "kickoff_time", "fixture"], kind="mergesort"
    ).reset_index(drop=True)

    # Player-history depth: the same 2025/26 player fixture rows used by the
    # candidate source, including non-appearance rows where source values are zero.
    player_groups = {
        int(code): group.sort_values(
            ["match_available_at", "kickoff_time", "fixture"], kind="mergesort"
        ).reset_index(drop=True)
        for code, group in source.groupby("fpl_code", sort=False)
    }

    # Opponent-allowed depth: sum each playing team's defensive contribution and
    # tackles, attribute the totals to the opponent that conceded them, and require
    # complete player-row coverage exactly as the feature builder does.
    dc = pd.to_numeric(source["defensive_contribution"], errors="coerce")
    tackles = pd.to_numeric(source["tackles"], errors="coerce")
    stat_source = source.assign(_dc=dc, _tackles=tackles)
    allowed = (
        stat_source.groupby(
            ["fixture", "opponent_team", "kickoff_time", "match_available_at"],
            as_index=False,
            sort=False,
        )
        .agg(
            dc_sum=("_dc", "sum"),
            dc_rows=("_dc", "count"),
            tackle_sum=("_tackles", "sum"),
            tackle_rows=("_tackles", "count"),
            player_rows=("_dc", "size"),
        )
        .rename(columns={"opponent_team": "conceding_team"})
    )
    allowed.loc[allowed["dc_rows"].ne(allowed["player_rows"]), "dc_sum"] = np.nan
    allowed.loc[
        allowed["tackle_rows"].ne(allowed["player_rows"]), "tackle_sum"
    ] = np.nan
    allowed_groups = {
        float(team): group.sort_values(
            ["match_available_at", "kickoff_time", "fixture"], kind="mergesort"
        ).reset_index(drop=True)
        for team, group in allowed.groupby("conceding_team", sort=False)
        if pd.notna(team)
    }

    records: list[dict[str, Any]] = []
    for row in metadata.itertuples(index=False):
        code = int(row.fpl_code)
        deadline = row.target_deadline_time
        history = player_groups.get(code)
        if history is None:
            raise ValueError(f"No 2025/26 source history for FPL code {code}")
        eligible = history.loc[
            history["match_available_at"].notna()
            & history["match_available_at"].lt(deadline)
        ].sort_values(["match_available_at", "kickoff_time", "fixture"], kind="mergesort")

        for feature, source_field in PLAYER_FIELDS.items():
            values = pd.to_numeric(eligible[source_field], errors="coerce")
            for window in PLAYER_WINDOWS:
                selected = values.tail(window)
                records.append(_depth_record(
                    season="2025-26", gameweek=int(row.gameweek), fpl_code=code,
                    fixture=None, feature=f"{feature}_{window}", window=window,
                    selected_rows=len(selected), finite_observations=int(selected.notna().sum()),
                ))
        dc_values = pd.to_numeric(eligible["defensive_contribution"], errors="coerce")
        for feature, windows in RATE_FEATURES.items():
            for window in windows:
                selected = dc_values.tail(window)
                records.append(_depth_record(
                    season="2025-26", gameweek=int(row.gameweek), fpl_code=code,
                    fixture=None, feature=f"{feature}_{window}", window=window,
                    selected_rows=len(selected), finite_observations=int(selected.notna().sum()),
                ))

        try:
            fixture_ids = json.loads(str(row.fixture_ids))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid fixture_ids JSON for player {code}, GW{row.gameweek}") from exc
        if not isinstance(fixture_ids, list) or not fixture_ids:
            raise ValueError(f"Missing target fixture IDs for player {code}, GW{row.gameweek}")
        for fixture_id in fixture_ids:
            fixture_id = str(fixture_id)
            target_rows = source.loc[
                source["fixture"].eq(fixture_id) & source["fpl_code"].eq(code)
            ]
            if len(target_rows) != 1:
                raise ValueError(
                    f"Expected one target player-fixture row for {code}/{fixture_id}, found {len(target_rows)}"
                )
            opponent = target_rows["opponent_team"].iloc[0]
            if pd.isna(opponent):
                raise ValueError(f"Target opponent missing for player {code}/{fixture_id}")
            opponent_history = allowed_groups.get(float(opponent))
            if opponent_history is None:
                opponent_history = allowed.iloc[0:0].copy()
            opponent_eligible = opponent_history.loc[
                opponent_history["match_available_at"].notna()
                & opponent_history["match_available_at"].lt(deadline)
            ].sort_values(
                ["match_available_at", "kickoff_time", "fixture"], kind="mergesort"
            )
            for feature, windows in OPPONENT_FEATURES.items():
                source_field = "dc_sum" if feature == "ar_opp_dc_allowed" else "tackle_sum"
                for window in windows:
                    selected = pd.to_numeric(
                        opponent_eligible[source_field], errors="coerce"
                    ).tail(window)
                    records.append(_depth_record(
                        season="2025-26", gameweek=int(row.gameweek), fpl_code=code,
                        fixture=fixture_id, feature=f"{feature}_{window}", window=window,
                        selected_rows=len(selected), finite_observations=int(selected.notna().sum()),
                    ))

    detail = pd.DataFrame(records)
    by_feature: dict[str, Any] = {}
    for feature, group in detail.groupby("feature", sort=True):
        by_feature[feature] = _summarize(group.to_dict("records"))
    by_gw: dict[str, Any] = {}
    for gw, group in detail.groupby("gameweek", sort=True):
        by_gw[str(int(gw))] = {
            feature: _summarize(subgroup.to_dict("records"))
            for feature, subgroup in group.groupby("feature", sort=True)
        }
    report = {
        "status": "DEFENSIVE_HISTORY_DEPTH_AUDIT_COMPLETE",
        "season": "2025-26",
        "player_gameweek_samples": int(len(metadata)),
        "target_fixture_queries": int(detail.loc[detail["fixture"].notna(), ["fpl_code", "fixture"]].drop_duplicates().shape[0]),
        "depth_records": int(len(detail)),
        "player_feature_windows": "last 3/5/10/38 available player fixture rows; finite observations counted separately from selected rows",
        "opponent_feature_windows": "last 3/5/10 opponent-conceded fixture totals and last 5 tackle totals; complete fixture totals required",
        "availability_rule": "official fixture kickoff + 24 hours for finished fixtures; strict match_available_at < target deadline",
        "label_isolation": {
            "target_points_loaded": False,
            "total_points_loaded": False,
            "oot_labels_read": False,
        },
        "feature_depth": by_feature,
        "gameweek_depth": by_gw,
        "training_authorized": False,
    }
    return report, detail


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--metadata-dir", type=Path, required=True)
    parser.add_argument("--players-raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--detail-output", type=Path, required=True)
    args = parser.parse_args()
    report, detail = audit_history_depth(args.source, args.fixtures, args.metadata_dir, args.players_raw)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.detail_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    detail.to_csv(args.detail_output, index=False)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
