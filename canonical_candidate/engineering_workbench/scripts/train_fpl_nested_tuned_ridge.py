#!/usr/bin/env python3
"""Nested rolling-origin ridge experiment with training-only alpha selection.

The final four gameweeks are held out once. Ridge alpha is selected only from
an earlier internal split inside the outer training window. This is exploratory
and is never promoted automatically.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from train_fpl_exploratory_ridge import (
    FEATURES, fit_ridge, aggregate_predictions, metrics, number, optional_number, bool_number,
)

ALPHA_GRID = (0.1, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0)


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def normalize_rows(rows):
    fixture_counts = defaultdict(int)
    for row in rows:
        key = (str(row.get("fpl_element_id", "")), int(number(row.get("gameweek"), -1)))
        if key[0] and key[1] > 0:
            fixture_counts[key] += 1
    normalized = []
    for row in rows:
        key = (str(row.get("fpl_element_id", "")), int(number(row.get("gameweek"), -1)))
        count = fixture_counts.get(key, 0)
        if count < 1:
            continue
        item = dict(row)
        item["fixture_count"] = float(count)
        for feature in FEATURES:
            if feature == "fixture_count":
                continue
            value = optional_number(row.get(feature))
            if feature == "was_home":
                value = bool_number(row.get(feature))
            elif feature in {"team_difficulty_snapshot", "opponent_difficulty_snapshot"}:
                value = value / 5.0 if value is not None else None
            item[feature] = value
        item["target_total_points"] = optional_number(row.get("target_total_points"))
        item["target_minutes"] = optional_number(row.get("target_minutes"))
        if item["target_total_points"] is None or item["target_minutes"] is None:
            raise ValueError("Missing/non-finite FPL target; refusing to encode target as zero")
        normalized.append(item)
    return normalized


def _inner_tune(train_rows, validation_rows, target_key, metric_key):
    scores = []
    for alpha in ALPHA_GRID:
        model = fit_ridge(train_rows, target_key, ridge_lambda=alpha)
        if target_key == "target_total_points":
            records = aggregate_predictions(validation_rows, model, model)
            actual_key, predicted_key, baseline_key = (
                "actual_points", "predicted_points", "baseline_last5_points"
            )
        else:
            records = aggregate_predictions(validation_rows, model, model)
            actual_key, predicted_key, baseline_key = (
                "actual_minutes", "predicted_minutes", "baseline_last_gw_minutes"
            )
        report = metrics(records, actual_key, predicted_key, baseline_key)
        scores.append({
            "alpha": alpha,
            "mae": report["model_mae"],
            "rmse": report["model_rmse"],
            "baseline_mae": report["baseline_mae"],
        })
    selected = min(scores, key=lambda x: (x["mae"], x["rmse"], x["alpha"]))
    return selected["alpha"], scores


def evaluate(rows):
    normalized = normalize_rows(rows)
    gameweeks = sorted({int(row["gameweek"]) for row in normalized})
    if len(gameweeks) < 8:
        raise ValueError("At least eight gameweeks are required for nested rolling-origin validation")
    outer_validation_gws = gameweeks[-4:]
    outer_training_gws = gameweeks[:-4]
    inner_validation_gws = outer_training_gws[-2:]
    inner_training_gws = outer_training_gws[:-2]

    outer_train = [
        row for row in normalized
        if int(row["gameweek"]) in outer_training_gws
        and number(row.get("prior_gameweeks_count")) >= 1
    ]
    outer_valid = [row for row in normalized if int(row["gameweek"]) in outer_validation_gws]
    inner_train = [
        row for row in normalized
        if int(row["gameweek"]) in inner_training_gws
        and number(row.get("prior_gameweeks_count")) >= 1
    ]
    inner_valid = [row for row in normalized if int(row["gameweek"]) in inner_validation_gws]
    if len(inner_train) < len(FEATURES) + 2 or not inner_valid:
        raise ValueError("Insufficient rows for inner alpha selection")
    if len(outer_train) < len(FEATURES) + 2 or not outer_valid:
        raise ValueError("Insufficient rows for outer temporal holdout")

    points_alpha, points_grid = _inner_tune(
        inner_train, inner_valid, "target_total_points", "points"
    )
    minutes_alpha, minutes_grid = _inner_tune(
        inner_train, inner_valid, "target_minutes", "minutes"
    )

    fixed_points = fit_ridge(outer_train, "target_total_points", ridge_lambda=10.0)
    fixed_minutes = fit_ridge(outer_train, "target_minutes", ridge_lambda=10.0)
    tuned_points = fit_ridge(outer_train, "target_total_points", ridge_lambda=points_alpha)
    tuned_minutes = fit_ridge(outer_train, "target_minutes", ridge_lambda=minutes_alpha)

    fixed_records = aggregate_predictions(outer_valid, fixed_points, fixed_minutes)
    tuned_records = aggregate_predictions(outer_valid, tuned_points, tuned_minutes)
    fixed_points_metrics = metrics(fixed_records, "actual_points", "predicted_points", "baseline_last5_points")
    tuned_points_metrics = metrics(tuned_records, "actual_points", "predicted_points", "baseline_last5_points")
    fixed_minutes_metrics = metrics(fixed_records, "actual_minutes", "predicted_minutes", "baseline_last_gw_minutes")
    tuned_minutes_metrics = metrics(tuned_records, "actual_minutes", "predicted_minutes", "baseline_last_gw_minutes")

    report = {
        "status": "EXPLORATORY_ONLY",
        "decision": "DO_NOT_PROMOTE",
        "point_in_time_status": "NOT_VERIFIED",
        "training_gameweeks": outer_training_gws,
        "validation_gameweeks": outer_validation_gws,
        "inner_training_gameweeks": inner_training_gws,
        "inner_validation_gameweeks": inner_validation_gws,
        "outer_training_fixture_rows": len(outer_train),
        "outer_validation_fixture_rows": len(outer_valid),
        "inner_training_fixture_rows": len(inner_train),
        "inner_validation_fixture_rows": len(inner_valid),
        "ridge_alpha_grid": list(ALPHA_GRID),
        "inner_alpha_selection": {
            "points": {"selected_alpha": points_alpha, "scores": points_grid},
            "minutes": {"selected_alpha": minutes_alpha, "scores": minutes_grid},
        },
        "outer_holdout_metrics": {
            "fixed_alpha_10": {
                "points": fixed_points_metrics,
                "minutes": fixed_minutes_metrics,
            },
            "nested_tuned_alpha": {
                "points": tuned_points_metrics,
                "minutes": tuned_minutes_metrics,
            },
            "tuned_minus_fixed": {
                "points_mae": round(tuned_points_metrics["model_mae"] - fixed_points_metrics["model_mae"], 6),
                "points_rmse": round(tuned_points_metrics["model_rmse"] - fixed_points_metrics["model_rmse"], 6),
                "minutes_mae": round(tuned_minutes_metrics["model_mae"] - fixed_minutes_metrics["model_mae"], 6),
                "minutes_rmse": round(tuned_minutes_metrics["model_rmse"] - fixed_minutes_metrics["model_rmse"], 6),
            },
        },
        "features": list(FEATURES),
        "missing_feature_policy": "Training-only median imputation with explicit missingness indicators; observed zero remains distinct from missing.",
        "outer_training_missing_feature_counts": {
            name: sum(1 for row in outer_train if row.get(name) is None)
            for name in FEATURES
        },
        "limitations": [
            "One current season and one four-gameweek outer holdout.",
            "Hyperparameter selection uses only an earlier internal split within the outer training window.",
            "Historical source vintages are not verified; this is not a strict point-in-time backtest.",
            "No feature selection is performed; the feature set is held fixed.",
            "The model is not connected to either recommendation engine.",
            "The decision remains DO_NOT_PROMOTE regardless of one holdout result.",
        ],
    }
    model = {
        "fixed_alpha_10": {"points_model": fixed_points, "minutes_model": fixed_minutes},
        "nested_tuned": {
            "points_model": tuned_points, "minutes_model": tuned_minutes,
            "points_alpha": points_alpha, "minutes_alpha": minutes_alpha,
        },
        "outer_validation_predictions_fixed": fixed_records,
        "outer_validation_predictions_tuned": tuned_records,
    }
    return model, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    model, report = evaluate(read_csv(args.input))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "fpl_nested_tuned_ridge_model.json").write_text(json.dumps(model, indent=2))
    (args.out_dir / "fpl_nested_tuned_ridge_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
