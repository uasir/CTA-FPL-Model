#!/usr/bin/env python3
"""Exploratory chronological test of Wyscout threat features beyond FPL history."""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

import numpy as np

BASELINE_FEATURES = (
    "fpl_total_points_prior_3_avg",
    "fpl_total_points_prior_5_avg",
    "fpl_minutes_prior_3_avg",
    "fpl_minutes_prior_5_avg",
)
CTA_FEATURES = (
    "pass_attempts", "pass_completions", "key_pass_attempts",
    "smart_pass_attempts", "through_pass_attempts", "opportunity_pass_attempts",
    "progressive_pass_attempts", "progressive_pass_completions",
    "final_third_entry_pass_attempts", "danger_zone_entry_pass_attempts",
    "threat_creation_pass_attempts", "threat_creation_pass_completions",
    "progressive_carry_attempts", "shot_attempts", "accurate_shot_attempts",
    "shot_opportunity_attempts", "dangerous_ball_losses", "offside_events",
    "duel_events", "duels_won", "duels_lost",
)


def _number(value):
    if value in (None, ""):
        return np.nan
    try:
        number = float(value)
    except (TypeError, ValueError):
        return np.nan
    return number if np.isfinite(number) else np.nan


def _matrix(rows, columns, means=None, scales=None):
    matrix = np.array([[_number(row.get(column)) for column in columns] for row in rows], dtype=float)
    if means is None:
        means = np.nanmean(matrix, axis=0)
        means = np.where(np.isfinite(means), means, 0.0)
    matrix = np.where(np.isfinite(matrix), matrix, means)
    if scales is None:
        scales = np.std(matrix, axis=0)
        scales = np.where(scales > 1e-9, scales, 1.0)
    return (matrix - means) / scales, means, scales


def _fit_ridge(train_x, train_y, alpha=1.0):
    y_mean = float(np.mean(train_y))
    centered_y = train_y - y_mean
    gram = train_x.T @ train_x
    coefficients = np.linalg.solve(gram + alpha * np.eye(gram.shape[0]), train_x.T @ centered_y)
    return y_mean, coefficients


def _metrics(actual, predicted):
    error = predicted - actual
    return {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error ** 2))),
        "mean_actual_points": float(np.mean(actual)),
        "mean_predicted_points": float(np.mean(predicted)),
    }


def evaluate(rows, train_fraction=0.7, alpha=1.0):
    eligible = [
        row for row in rows
        if row.get("target_fpl_total_points") not in (None, "")
        and int(float(row.get("prior_matches_count") or 0)) > 0
        and row.get("kickoff_time_utc")
    ]
    eligible.sort(key=lambda row: (datetime.fromisoformat(row["kickoff_time_utc"].replace("Z", "+00:00")), int(row["fpl_element_id"]), int(row["fixture_id"])))
    unique_kickoffs = sorted({row["kickoff_time_utc"] for row in eligible})
    if len(unique_kickoffs) < 5:
        raise ValueError("At least five distinct target kickoff timestamps are required")
    split_index = max(1, min(len(unique_kickoffs) - 1, int(len(unique_kickoffs) * train_fraction)))
    cutoff = unique_kickoffs[split_index]
    train = [row for row in eligible if row["kickoff_time_utc"] < cutoff]
    test = [row for row in eligible if row["kickoff_time_utc"] >= cutoff]
    if len(train) < 30 or len(test) < 30:
        raise ValueError("Chronological split needs at least 30 training and 30 test rows")

    cta_candidates = [
        f"{feature}{suffix}_prior_{window}_avg"
        for feature in CTA_FEATURES
        for suffix in ("", "_per90")
        for window in (3, 5)
    ]
    cta_columns = [
        column for column in cta_candidates
        if any(np.isfinite(_number(row.get(column))) for row in train)
    ]
    baseline_columns = [
        column for column in BASELINE_FEATURES
        if any(np.isfinite(_number(row.get(column))) for row in train)
    ]
    if not baseline_columns:
        raise ValueError("No prior FPL baseline features are available")
    if not cta_columns:
        raise ValueError("No lagged Wyscout CTA features are available")

    y_train = np.array([float(row["target_fpl_total_points"]) for row in train])
    y_test = np.array([float(row["target_fpl_total_points"]) for row in test])
    baseline_train, b_means, b_scales = _matrix(train, baseline_columns)
    baseline_test, _, _ = _matrix(test, baseline_columns, b_means, b_scales)
    combined_columns = baseline_columns + cta_columns
    combined_train, c_means, c_scales = _matrix(train, combined_columns)
    combined_test, _, _ = _matrix(test, combined_columns, c_means, c_scales)

    base_mean, base_coef = _fit_ridge(baseline_train, y_train, alpha)
    cta_mean, cta_coef = _fit_ridge(combined_train, y_train, alpha)
    base_pred = base_mean + baseline_test @ base_coef
    cta_pred = cta_mean + combined_test @ cta_coef
    baseline_metrics = _metrics(y_test, base_pred)
    combined_metrics = _metrics(y_test, cta_pred)
    improvement = baseline_metrics["mae"] - combined_metrics["mae"]
    report = {
        "status": "PASS_EXPLORATORY_CHRONOLOGICAL_CTA_COMPARISON",
        "target": "historical FPL total_points",
        "provider": "Wyscout",
        "season": "2017/18",
        "train_rows": len(train),
        "test_rows": len(test),
        "train_unique_players": len({row["fpl_element_id"] for row in train}),
        "test_unique_players": len({row["fpl_element_id"] for row in test}),
        "train_latest_kickoff_utc": max(row["kickoff_time_utc"] for row in train),
        "test_earliest_kickoff_utc": min(row["kickoff_time_utc"] for row in test),
        "chronological_cutoff_utc": cutoff,
        "baseline_feature_count": len(baseline_columns),
        "cta_feature_count": len(cta_columns),
        "baseline_test_metrics": baseline_metrics,
        "baseline_plus_cta_test_metrics": combined_metrics,
        "mae_improvement_points": float(improvement),
        "mae_improvement_pct": float(improvement / baseline_metrics["mae"] * 100) if baseline_metrics["mae"] else None,
        "cta_incremental_value_status": (
            "POSITIVE_EXPLORATORY_SIGNAL" if improvement > 1e-9
            else "NO_POSITIVE_EXPLORATORY_SIGNAL"
        ),
        "decision_use_status": "RESEARCH_ONLY_NOT_IN_BASELINE",
        "validation_caveats": [
            "One historical EPL season and one chronological holdout only; not external validation.",
            "Historical FPL outcomes and features may include retrospective corrections; source snapshots are not point-in-time archived.",
            "Ridge coefficients are exploratory and not a calibrated production CTA composite.",
            "Wyscout event metrics are on-ball event-count/geometric proxies, not continuous tracking, receiver-aware xT or calibrated xG.",
            "No claim of causal impact or guaranteed FPL points uplift."
        ],
        "model_specification": {
            "baseline": "Ridge regression using prior 3/5-match FPL points and minutes averages.",
            "cta_augmented": "Same baseline plus prior 3/5-match Wyscout event-threat feature averages.",
            "alpha": alpha,
            "train_fraction_by_unique_kickoff": train_fraction,
            "missing_feature_policy": "Impute using training-set feature means only; standardize using training-set means and standard deviations.",
        },
    }
    return report


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lagged-features", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--train-fraction", type=float, default=0.7)
    parser.add_argument("--alpha", type=float, default=1.0)
    args = parser.parse_args()
    if not 0.5 <= args.train_fraction <= 0.9:
        parser.error("--train-fraction must be between 0.5 and 0.9")
    rows = read_csv(args.lagged_features)
    report = evaluate(rows, args.train_fraction, args.alpha)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "wyscout_cta_incremental_value_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
