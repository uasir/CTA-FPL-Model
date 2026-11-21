#!/usr/bin/env python3
"""Exploratory temporal holdout: does lagged Opta team context add FPL points signal? (v0.1.0)

This is deliberately a paired baseline-vs-augmented experiment. It never
promotes the model: provider source-vintage status is not point-in-time verified.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from train_fpl_exploratory_ridge import (
    FEATURES, RIDGE_LAMBDA, fit_ridge, predict, number, optional_number, bool_number, mae, rmse,
)

OPTA_FEATURES = (
    "opta_prior_matches_count",
    "opta_prior3_expectedGoals_avg",
    "opta_prior3_expectedAssists_avg",
    "opta_prior3_accuratePass_avg",
    "opta_prior3_possessionPercentage_avg",
    "opta_prior3_finalThirdEntries_avg",
    "opta_prior3_attemptsIbox_avg",
    "opta_prior3_ballRecovery_avg",
    "opta_prior3_interception_avg",
    "opta_prior3_duelWon_avg",
    "opta_prior3_touches_avg",
)


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def prepare_rows(fpl_rows, opta_rows):
    opta_by_key = {}
    for row in opta_rows:
        key = (str(row.get("fpl_element_id", "")), str(row.get("fixture_id", "")))
        if key in opta_by_key:
            raise ValueError(f"Duplicate Opta sidecar key: {key}")
        opta_by_key[key] = row
    fixture_counts = defaultdict(int)
    for row in fpl_rows:
        key = (str(row.get("fpl_element_id", "")), int(number(row.get("gameweek"), -1)))
        if key[0] and key[1] > 0:
            fixture_counts[key] += 1

    joined, missing = [], []
    for row in fpl_rows:
        key = (str(row.get("fpl_element_id", "")), str(row.get("fixture_id", "")))
        opta = opta_by_key.get(key)
        if opta is None:
            missing.append(key)
            continue
        item = dict(row)
        count = fixture_counts[(str(row.get("fpl_element_id", "")), int(number(row.get("gameweek"), -1)))]
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
        for feature in OPTA_FEATURES:
            item[feature] = optional_number(opta.get(feature))
        item["target_total_points"] = optional_number(row.get("target_total_points"))
        if item["target_total_points"] is None:
            raise ValueError("Missing/non-finite FPL target; refusing to encode target as zero")
        joined.append(item)
    if missing:
        raise ValueError(f"Missing Opta context for {len(missing)} FPL player-fixture rows")
    return joined, {
        "fpl_player_fixture_rows": len(fpl_rows),
        "opta_player_fixture_rows": len(opta_rows),
        "joined_rows": len(joined),
        "missing_rows": len(missing),
        "opta_feature_names": list(OPTA_FEATURES),
    }


def _aggregate(rows, model, feature_names):
    groups = defaultdict(list)
    for row in rows:
        groups[(str(row["fpl_element_id"]), int(row["gameweek"]))].append(row)
    output = []
    for (player_id, gameweek), items in sorted(groups.items(), key=lambda x: (int(x[0][0]), x[0][1])):
        output.append({
            "fpl_element_id": player_id,
            "gameweek": gameweek,
            "actual_points": sum(number(row.get("target_total_points")) for row in items),
            "predicted_points": sum(predict(model, row) for row in items),
            "baseline_last5_points": optional_number(items[0].get("prior5_gw_points_avg")),
        })
    return output


def _score(records):
    scored = [r for r in records if r["baseline_last5_points"] is not None]
    if not scored:
        raise ValueError("No complete rows available for Opta baseline comparison")
    actual = [r["actual_points"] for r in scored]
    predicted = [r["predicted_points"] for r in scored]
    naive = [r["baseline_last5_points"] for r in scored]
    return {
        "player_gameweek_rows": len(scored),
        "candidate_player_gameweek_rows": len(records),
        "rows_excluded_for_missing_baseline": len(records) - len(scored),
        "model_mae": round(mae(actual, predicted), 6),
        "model_rmse": round(rmse(actual, predicted), 6),
        "naive_last5_mae": round(mae(actual, naive), 6),
        "naive_last5_rmse": round(rmse(actual, naive), 6),
    }


def evaluate(fpl_rows, opta_rows):
    rows, join_report = prepare_rows(fpl_rows, opta_rows)
    gameweeks = sorted({int(row["gameweek"]) for row in rows})
    if len(gameweeks) < 7:
        raise ValueError("At least seven gameweeks are required for a four-GW temporal holdout")
    validation_gws = gameweeks[-4:]
    training_gws = gameweeks[:-4]
    train = [r for r in rows if int(r["gameweek"]) in training_gws and number(r.get("prior_gameweeks_count")) >= 1]
    valid = [r for r in rows if int(r["gameweek"]) in validation_gws]
    if len(train) < len(FEATURES) + len(OPTA_FEATURES) + 2 or not valid:
        raise ValueError("Insufficient rows for paired temporal ridge evaluation")

    baseline_model = fit_ridge(train, "target_total_points", feature_names=FEATURES, ridge_lambda=RIDGE_LAMBDA)
    augmented_features = FEATURES + OPTA_FEATURES
    augmented_model = fit_ridge(train, "target_total_points", feature_names=augmented_features, ridge_lambda=RIDGE_LAMBDA)
    baseline_records = _aggregate(valid, baseline_model, FEATURES)
    augmented_records = _aggregate(valid, augmented_model, augmented_features)
    baseline_score = _score(baseline_records)
    augmented_score = _score(augmented_records)
    delta_mae = round(augmented_score["model_mae"] - baseline_score["model_mae"], 6)
    delta_rmse = round(augmented_score["model_rmse"] - baseline_score["model_rmse"], 6)
    report = {
        "status": "EXPLORATORY_ONLY",
        "decision": "DO_NOT_PROMOTE",
        "point_in_time_status": "NOT_VERIFIED",
        "training_gameweeks": training_gws,
        "validation_gameweeks": validation_gws,
        "training_fixture_rows": len(train),
        "validation_fixture_rows": len(valid),
        "ridge_lambda": RIDGE_LAMBDA,
        "join": join_report,
        "baseline_player_form_model": baseline_score,
        "player_form_plus_lagged_opta_team_context": augmented_score,
        "augmented_minus_baseline_model": {
            "mae_delta": delta_mae,
            "rmse_delta": delta_rmse,
            "improved_mae": delta_mae < 0,
            "improved_rmse": delta_rmse < 0,
        },
        "features": {"baseline": list(FEATURES), "added_opta": list(OPTA_FEATURES)},
        "missing_feature_policy": "Training-only median imputation with explicit missingness indicators; observed zero remains distinct from missing.",
        "historical_form_normalization": "Prior gameweek totals and averages are retained; they are not divided by the target gameweek fixture count. Per-fixture forecasts are summed only after prediction.",
        "training_missing_feature_counts": {
            name: sum(1 for row in train if row.get(name) is None)
            for name in FEATURES + OPTA_FEATURES
        },
        "limitations": [
            "Only one 2026/27 season and one four-gameweek temporal holdout are evaluated.",
            "Provider source-vintage is not point-in-time verified; this is not a strict historical backtest.",
            "Opta inputs are team-match aggregates, not player-level per-match event features.",
            "Team-context features do not affect either recommendation engine.",
            "No hyperparameter tuning or feature selection is performed on the holdout.",
        ],
    }
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fpl-training", type=Path, required=True)
    parser.add_argument("--opta-features", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(read_csv(args.fpl_training), read_csv(args.opta_features))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "opta_team_context_evaluation.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
