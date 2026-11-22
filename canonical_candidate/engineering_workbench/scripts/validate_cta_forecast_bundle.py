#!/usr/bin/env python3
"""Validate snapshot consistency and fixture-to-player-GW-to-five-GW aggregation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def validate_bundle(forecast_dir: Path, output_path: Path) -> dict:
    fixture = pd.read_csv(forecast_dir / "fixture_forecasts.csv")
    gameweek = pd.read_csv(forecast_dir / "player_gameweek_forecasts.csv")
    horizon = pd.read_csv(forecast_dir / "player_five_gw_forecasts.csv")
    report = json.loads((forecast_dir / "forecast_report.json").read_text(encoding="utf-8"))
    snapshot = report.get("forecast_snapshot_id")
    if not snapshot or len(snapshot) != 64:
        raise ValueError("forecast report has no valid SHA-256 snapshot ID")
    for label, frame in (("fixture", fixture), ("player-GW", gameweek), ("five-GW", horizon)):
        if frame.empty:
            raise ValueError(f"{label} forecast table is empty")
        if "forecast_snapshot_id" not in frame or set(frame["forecast_snapshot_id"].astype(str)) != {snapshot}:
            raise ValueError(f"{label} rows do not share the report forecast_snapshot_id")
    if fixture.duplicated(["season", "gameweek", "fpl_code", "fixture_id"]).any():
        raise ValueError("fixture forecast has duplicate player-fixture keys")
    if gameweek.duplicated(["season", "gameweek", "fpl_code", "position"]).any():
        raise ValueError("player-GW forecast has duplicate player-gameweek keys")
    if horizon.duplicated(["season", "fpl_code", "position"]).any():
        raise ValueError("five-GW forecast has duplicate player horizon keys")
    gameweeks = sorted(pd.to_numeric(fixture["gameweek"], errors="raise").astype(int).unique().tolist())
    if len(gameweeks) != 5 or gameweeks != list(range(gameweeks[0], gameweeks[0] + 5)):
        raise ValueError(f"fixture forecasts do not cover five consecutive gameweeks: {gameweeks}")

    fixture_group = (
        fixture.groupby(["season", "gameweek", "fpl_code", "position"], as_index=False)
        .agg(
            expected_points=("cta_expected_points", "sum"),
            expected_minutes=("expected_minutes", "sum"),
            fixture_count=("fixture_id", "nunique"),
        )
    )
    joined_gw = fixture_group.merge(
        gameweek,
        on=["season", "gameweek", "fpl_code", "position"],
        how="outer", suffixes=("_fixture", "_published"), indicator=True,
        validate="one_to_one",
    )
    if not joined_gw["_merge"].eq("both").all():
        raise ValueError("player-GW aggregate keys do not match fixture-level source rows")
    for metric in ("expected_points", "expected_minutes", "fixture_count"):
        left = pd.to_numeric(joined_gw[f"{metric}_fixture"], errors="raise")
        right = pd.to_numeric(joined_gw[f"{metric}_published"], errors="raise")
        if not np.allclose(left, right, rtol=0, atol=1e-6):
            raise ValueError(f"player-GW {metric} is not the sum of fixture rows")

    horizon_group = (
        gameweek.groupby(["season", "fpl_code", "position"], as_index=False)
        .agg(
            expected_points_5gw=("expected_points", "sum"),
            expected_minutes_5gw=("expected_minutes", "sum"),
            fixture_count_5gw=("fixture_count", "sum"),
            gameweeks_with_fixtures=("gameweek", "nunique"),
        )
    )
    joined_horizon = horizon_group.merge(
        horizon,
        on=["season", "fpl_code", "position"],
        how="outer", suffixes=("_derived", "_published"), indicator=True,
        validate="one_to_one",
    )
    if not joined_horizon["_merge"].eq("both").all():
        raise ValueError("five-GW aggregate keys do not match player-GW source rows")
    for metric in ("expected_points_5gw", "expected_minutes_5gw",
                   "fixture_count_5gw", "gameweeks_with_fixtures"):
        left = pd.to_numeric(joined_horizon[f"{metric}_derived"], errors="raise")
        right = pd.to_numeric(joined_horizon[f"{metric}_published"], errors="raise")
        if not np.allclose(left, right, rtol=0, atol=1e-6):
            raise ValueError(f"five-GW {metric} is not the sum of player-GW rows")

    if fixture["production_eligible"].astype(bool).any() or gameweek["production_eligible"].astype(bool).any() or horizon["production_eligible"].astype(bool).any():
        raise ValueError("candidate forecast incorrectly marked production-eligible")
    if not np.allclose(pd.to_numeric(fixture["decision_weight"]), 0.0):
        raise ValueError("candidate forecast has non-zero decision weight")
    if fixture["covar_used"].astype(bool).any():
        raise ValueError("forecast unexpectedly used CoVar")
    if report.get("decision_safeguards", {}).get("production_eligible") is not False:
        raise ValueError("forecast report does not preserve the production gate")

    result = {
        "status": "PASS_CTA_FORECAST_BUNDLE_INTEGRITY",
        "forecast_snapshot_id": snapshot,
        "gameweeks": gameweeks,
        "fixture_rows": len(fixture),
        "player_gameweek_rows": len(gameweek),
        "five_gameweek_player_rows": len(horizon),
        "aggregation_checks": [
            "fixture -> player-GW expected points",
            "fixture -> player-GW expected minutes",
            "fixture -> player-GW fixture count",
            "player-GW -> five-GW expected points",
            "player-GW -> five-GW expected minutes",
            "player-GW -> five-GW fixture count and GW coverage",
        ],
        "production_eligible": False,
        "decision_weight": 0.0,
        "covar_used": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forecast-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate_bundle(args.forecast_dir, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
