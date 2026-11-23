"""Audit the structural quality of a rebuilt 2PM Dastan 286 candidate frame.

This audit reports schema, coverage, sentinel, snapshot-timestamp and same-player/GW
invariance diagnostics. It cannot certify historical source vintages or independently
reconstruct all feature values at the official deadline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ANCHOR_PREFIXES = ("player_", "team_", "p_any_", "p60_", "e_minutes_")
FIXTURE_CONTEXT_FEATURES = (
    "ar_opp_dc_allowed_3", "ar_opp_dc_allowed_5", "ar_opp_dc_allowed_10",
    "ar_opp_tackles_allowed_5", "ar_rest_days", "ar_team_matches_14d",
    "is_home_num",
)
DEFENSIVE_PREFIXES = (
    "ar_defensive_contribution_", "ar_cbit_", "ar_recoveries_", "ar_tackles_",
    "ar_dc_", "ar_opp_dc_allowed_", "ar_opp_tackles_allowed_",
)
MARKET_FEATURES = ("value", "selected", "transfers_balance")


def audit_frame(frame: pd.DataFrame, features: list[str]) -> dict[str, Any]:
    if len(features) != 286 or len(set(features)) != 286:
        raise ValueError("Expected exactly 286 unique ordered feature names")
    required = {"season", "gameweek", "fixture", "fpl_code", "deadline_time", *features}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Candidate frame missing columns: {missing[:20]}")
    key = ["season", "gameweek", "fixture", "fpl_code"]
    duplicate_count = int(frame.duplicated(key).sum())
    if duplicate_count:
        raise ValueError(f"Candidate contains {duplicate_count} duplicate player-fixture keys")
    observed_order = [column for column in frame.columns if column in set(features)]
    if observed_order != features:
        raise ValueError("Candidate feature columns do not preserve pinned Dastan order")

    numeric = frame[features].apply(pd.to_numeric, errors="coerce")
    values = numeric.to_numpy(dtype=float)
    nonfinite_count = int((~np.isfinite(values)).sum())
    family_counts = {
        "player_": sum(column.startswith("player_") for column in features),
        "team_": sum(column.startswith("team_") for column in features),
        "opp_": sum(column.startswith("opp_") for column in features),
        "availability": sum(column.startswith(("p_any_", "p60_", "e_minutes_")) for column in features),
        "ar_": sum(column.startswith("ar_") and column != "ar_ep_next" for column in features),
        "snapshots": sum(column.startswith("sig_") for column in features) + int("ar_ep_next" in features),
        "flat_context": sum(column in {"is_home_num", "status_league_rank", *MARKET_FEATURES} for column in features),
    }

    season_coverage = {}
    for season, rows in frame.groupby("season", sort=True):
        season_values = numeric.loc[rows.index]
        season_coverage[str(season)] = {
            "rows": int(len(rows)),
            "finite_feature_values": int(np.isfinite(season_values.to_numpy(dtype=float)).sum()),
            "total_feature_values": int(season_values.size),
            "nan_values": int(season_values.isna().sum().sum()),
            "negative_one_sentinels": int(season_values.eq(-1.0).sum().sum()),
            "genuine_zero_values": int(season_values.eq(0.0).sum().sum()),
        }

    anchor_features = [
        column for column in features
        if column.startswith(ANCHOR_PREFIXES)
        or column == "status_league_rank"
        or (
            column.startswith("ar_")
            and column not in FIXTURE_CONTEXT_FEATURES
        )
    ]
    fixture_context_features = [
        column for column in features
        if column.startswith("opp_")
        or column in FIXTURE_CONTEXT_FEATURES
    ]
    duplicate_players = frame[frame.duplicated(["season", "gameweek", "fpl_code"], keep=False)]
    groups_affected = 0
    columns_affected: set[str] = set()
    if not duplicate_players.empty and anchor_features:
        for _, group in duplicate_players.groupby(
            ["season", "gameweek", "fpl_code"], sort=False
        ):
            counts = group[anchor_features].nunique(dropna=False)
            differing = counts[counts > 1].index.tolist()
            if differing:
                groups_affected += 1
                columns_affected.update(differing)

    context_flattening = {
        "groups_with_multiple_fixtures": 0,
        "groups_where_all_context_features_are_constant": 0,
        "constant_feature_group_counts": {column: 0 for column in fixture_context_features},
        "checked_feature_count": len(fixture_context_features),
        "interpretation": "Diagnostic only: fixture-specific opponent/venue/rest/congestion context may legitimately vary within one player/Gameweek. Constant values can indicate upstream deadline anchoring flattened context that should be rebuilt per target fixture.",
    }
    if not duplicate_players.empty and fixture_context_features:
        for _, group in duplicate_players.groupby(
            ["season", "gameweek", "fpl_code"], sort=False
        ):
            context_flattening["groups_with_multiple_fixtures"] += 1
            counts = group[fixture_context_features].nunique(dropna=False)
            for column in fixture_context_features:
                if counts[column] <= 1:
                    context_flattening["constant_feature_group_counts"][column] += 1
            if counts.le(1).all():
                context_flattening["groups_where_all_context_features_are_constant"] += 1

    snapshot_report = {}
    if "deadline_time" in frame:
        deadline = pd.to_datetime(frame["deadline_time"], utc=True, errors="coerce")
        for column in ("ep_next_snapshot_at", "signals_snapshot_at", "market_snapshot_at"):
            if column not in frame:
                continue
            captured = pd.to_datetime(frame[column], utc=True, errors="coerce")
            present = captured.notna()
            post_deadline = present & captured.ge(deadline)
            age = (deadline[present] - captured[present]).dt.total_seconds() / 3600
            snapshot_report[column] = {
                "rows_present": int(present.sum()),
                "rows_missing": int((~present).sum()),
                "post_deadline_rows": int(post_deadline.sum()),
                "median_age_hours": float(age.median()) if len(age) else None,
                "min_age_hours": float(age.min()) if len(age) else None,
                "max_age_hours": float(age.max()) if len(age) else None,
                "rows_under_5m_buffer": int(age.lt(5 / 60.0).sum()),
            }

    defensive_coverage = {}
    defensive = [column for column in features if column.startswith(DEFENSIVE_PREFIXES)]
    for season, rows in frame.groupby("season", sort=True):
        block = numeric.loc[rows.index, defensive] if defensive else pd.DataFrame(index=rows.index)
        defensive_coverage[str(season)] = {
            "rows": int(len(rows)),
            "columns": len(defensive),
            "finite_values": int(np.isfinite(block.to_numpy(dtype=float)).sum()) if defensive else 0,
            "all_zero_columns": [
                column for column in defensive
                if len(block) and block[column].notna().all() and block[column].eq(0).all()
            ],
        }

    return {
        "status": "CANDIDATE_STRUCTURAL_AUDIT",
        "admission_status": "NOT_ADMITTED",
        "rows": int(len(frame)),
        "feature_count": len(features),
        "feature_order_sha256": hashlib.sha256("\n".join(features).encode()).hexdigest(),
        "duplicate_player_fixture_keys": duplicate_count,
        "nonfinite_feature_values": nonfinite_count,
        "feature_family_counts": family_counts,
        "season_coverage": season_coverage,
        "defensive_feature_coverage": defensive_coverage,
        "snapshot_timestamps": snapshot_report,
        "same_player_gameweek_upstream_anchor_check": {
            "groups_with_differences": groups_affected,
            "columns_with_differences": sorted(columns_affected),
            "checked_feature_count": len(anchor_features),
            "scope": "player/team/availability history and non-fixture ar_ history only; not a full 286-feature deadline proof",
        },
        "fixture_context_flattening_check": context_flattening,
        "known_unresolved_scopes": {
            "opponent_rolling_features": "not independently deadline-reconstructed",
            "fixture_specific_ar_context": "ar_ opponent allowance, rest, team congestion and venue context may be flattened by the upstream ar_ deadline anchor and must be rebuilt per target fixture",
            "direct_league_rank_features": "not independently deadline-reconstructed",
            "market_fields": "value/selected/transfers_balance timestamp provenance not verified",
            "source_vintage": "retrospective provider revisions not verified",
            "defensive_features": "pre-2025/26 structural absence versus observed zero requires source-level audit",
        },
        "market_fields": {
            column: {
                "present": column in numeric,
                "finite_rows": int(np.isfinite(numeric[column].to_numpy(dtype=float)).sum()) if column in numeric else 0,
            }
            for column in MARKET_FEATURES
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="features_286_candidate.parquet")
    parser.add_argument("--schema", type=Path, default=Path(__file__).parents[1] / "config" / "2pm_dastan_286_schema.json")
    parser.add_argument("--out", type=Path, required=True, help="JSON audit report")
    args = parser.parse_args()
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    features = schema["feature_order"]
    frame = pd.read_parquet(args.input)
    report = audit_frame(frame, features)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
