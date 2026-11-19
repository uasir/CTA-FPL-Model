#!/usr/bin/env python3
"""Paired comparison of base and position-aware 2PM walk-forward predictions."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path

from evaluate_fpl_decision_quality import evaluate_forecast
from evaluate_fpl_walk_forward import cluster_bootstrap_paired_errors

KEY_FIELDS = ("season", "fpl_element_id", "gameweek")


def load_predictions(path: Path) -> dict:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    result = {}
    for row in rows:
        key = tuple(str(row[field]) for field in KEY_FIELDS)
        if key in result:
            raise ValueError(f"Duplicate player-gameweek prediction key: {key}")
        result[key] = {
            "actual": float(row["actual_points"]),
            "raw": float(row["predicted_points"]),
            "calibrated": float(row["affine_calibrated_points"]),
        }
    return result


def compare_predictions(base: dict, position: dict) -> dict:
    if set(base) != set(position):
        raise ValueError("Base and position models must have identical player-gameweek keys")
    keys = sorted(base)
    for key in keys:
        if abs(base[key]["actual"] - position[key]["actual"]) > 1e-9:
            raise ValueError(f"Actual points differ for matched key {key}")
    actual = [base[key]["actual"] for key in keys]
    base_raw = [base[key]["raw"] for key in keys]
    position_raw = [position[key]["raw"] for key in keys]
    base_cal = [base[key]["calibrated"] for key in keys]
    position_cal = [position[key]["calibrated"] for key in keys]
    clusters = [f"{season}:{player}" for season, player, _ in keys]
    return {
        "status": "RESEARCH_ONLY_PAIRED_FEATURE_ABLATION",
        "comparison": "POSITION_AWARE_2PM_MINUS_BASE_2PM",
        "matched_player_gameweeks": len(keys),
        "matched_seasons": sorted({key[0] for key in keys}),
        "matched_gameweeks": sorted({int(key[2]) for key in keys}),
        "raw_expected_points": {
            "base": evaluate_forecast(actual, base_raw, ranking_score=base_raw, top_k=100),
            "position": evaluate_forecast(actual, position_raw, ranking_score=position_raw, top_k=100),
            "paired_player_season_cluster_bootstrap_position_minus_base": cluster_bootstrap_paired_errors(
                actual, position_raw, base_raw, clusters, n_boot=2000, seed=20261119,
            ),
        },
        "affine_calibrated_expected_points": {
            "base": evaluate_forecast(actual, base_cal, ranking_score=base_cal, top_k=100),
            "position": evaluate_forecast(actual, position_cal, ranking_score=position_cal, top_k=100),
            "paired_player_season_cluster_bootstrap_position_minus_base": cluster_bootstrap_paired_errors(
                actual, position_cal, base_cal, clusters, n_boot=2000, seed=20261120,
            ),
        },
        "interpretation_rule": "Negative MAE and MSE deltas favor position features; ranking is evaluated separately. No model promotion follows from this single retrospective ablation.",
        "limitations": [
            "Historical source vintages are retrospective, not archived pre-deadline snapshots.",
            "Position labels may reflect retrospective season exports rather than a fully archived deadline-time position state.",
            "Player-season clustered intervals quantify player dependence but do not replace gameweek-level robustness checks.",
            "This experiment changes only the conventional FPL position feature set; it does not add CTA features.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-predictions", type=Path, required=True)
    parser.add_argument("--position-predictions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = compare_predictions(load_predictions(args.base_predictions), load_predictions(args.position_predictions))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()