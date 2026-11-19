#!/usr/bin/env python3
"""Chronological exploratory evaluation of the standalone Wyscout A/B/C predictor.

Compares FPL-history-only Ridge against A, B, C and their combinations on the
same held-out player-fixture cohort. All imputations/scaling are fitted on the
training block; no validation outcomes select features or weights.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

from cta_four_layer_pipeline import LAYER_FEATURES
from evaluate_fpl_decision_quality import evaluate_forecast
from evaluate_fpl_walk_forward import paired_error_comparison, cluster_bootstrap_paired_errors
from train_fpl_exploratory_ridge import fit_ridge, predict

BASELINE_FEATURES = (
    "fpl_total_points_prior_3_avg",
    "fpl_total_points_prior_5_avg",
    "fpl_minutes_prior_3_avg",
    "fpl_minutes_prior_5_avg",
)
LAYER_NAMES = (
    "A_temporal_football_value",
    "B_risk_defensive_intelligence",
    "C_player_intelligence",
)


def number(value):
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def truth(value):
    return str(value).strip().lower() in {"true", "1", "yes"}


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def available_features(rows, candidates):
    return [
        name for name in candidates
        if any(number(row.get(name)) is not None for row in rows)
    ]


def split_chronologically(rows, train_fraction):
    ordered_times = sorted({str(row["kickoff_time_utc"]) for row in rows})
    if len(ordered_times) < 5:
        raise ValueError("At least five unique target kickoffs are required")
    split = max(1, min(len(ordered_times) - 1, int(len(ordered_times) * train_fraction)))
    cutoff = ordered_times[split]
    train = [row for row in rows if str(row["kickoff_time_utc"]) < cutoff]
    test = [row for row in rows if str(row["kickoff_time_utc"]) >= cutoff]
    if len(train) < 50 or len(test) < 30:
        raise ValueError("Insufficient chronological training or test rows")
    return train, test, cutoff


def evaluate(rows, source_report, train_fraction=0.7, ridge_lambda=1.0, n_boot=1000):
    eligible = [
        row for row in rows
        if truth(row.get("research_eligible_for_analysis"))
        and number(row.get("target_fpl_total_points")) is not None
    ]
    if not eligible:
        raise ValueError("No verified, conservative-cutoff player-fixture rows are eligible")
    eligible.sort(key=lambda row: (str(row["kickoff_time_utc"]), str(row["fpl_element_id"])))
    train, test, cutoff = split_chronologically(eligible, train_fraction)
    actual = [float(row["target_fpl_total_points"]) for row in test]
    cluster_ids = [str(row["fpl_element_id"]) for row in test]

    layer_features = {
        layer: [f"abc_{name}" for name in LAYER_FEATURES[layer]]
        for layer in LAYER_NAMES
    }
    candidates = {
        "FPL_HISTORY_ONLY": list(BASELINE_FEATURES),
        "FPL_PLUS_A": list(BASELINE_FEATURES) + layer_features[LAYER_NAMES[0]],
        "FPL_PLUS_B": list(BASELINE_FEATURES) + layer_features[LAYER_NAMES[1]],
        "FPL_PLUS_C": list(BASELINE_FEATURES) + layer_features[LAYER_NAMES[2]],
        "FPL_PLUS_AB": list(BASELINE_FEATURES) + layer_features[LAYER_NAMES[0]] + layer_features[LAYER_NAMES[1]],
        "FPL_PLUS_AC": list(BASELINE_FEATURES) + layer_features[LAYER_NAMES[0]] + layer_features[LAYER_NAMES[2]],
        "FPL_PLUS_BC": list(BASELINE_FEATURES) + layer_features[LAYER_NAMES[1]] + layer_features[LAYER_NAMES[2]],
        "FPL_PLUS_ABC": list(BASELINE_FEATURES) + layer_features[LAYER_NAMES[0]] + layer_features[LAYER_NAMES[1]] + layer_features[LAYER_NAMES[2]],
    }
    predictions = {}
    models = {}
    for name, feature_candidates in candidates.items():
        features = available_features(train, feature_candidates)
        if name == "FPL_HISTORY_ONLY" and not all(x in features for x in BASELINE_FEATURES):
            raise ValueError("Conventional FPL baseline feature coverage is incomplete")
        model = fit_ridge(train, "target_fpl_total_points", features, ridge_lambda)
        predictions[name] = [predict(model, row) for row in test]
        models[name] = {
            "feature_count": len(features),
            "features_used": features,
            "missing_feature_policy": model["missing_value_policy"],
        }

    baseline_predictions = predictions["FPL_HISTORY_ONLY"]
    reports = {}
    comparisons = {}
    for name, forecast in predictions.items():
        reports[name] = {
            "forecast": evaluate_forecast(
                actual, forecast, ranking_score=forecast, top_k=20,
            ),
            "mean_signed_error": sum(p - y for p, y in zip(forecast, actual)) / len(actual),
            "overprediction_rate": sum(p > y for p, y in zip(forecast, actual)) / len(actual),
            **models[name],
        }
        if name == "FPL_HISTORY_ONLY":
            continue
        comparisons[name] = {
            "paired": paired_error_comparison(actual, forecast, baseline_predictions),
            "player_cluster_bootstrap_vs_fpl_history": cluster_bootstrap_paired_errors(
                actual, forecast, baseline_predictions, cluster_ids,
                n_boot=n_boot, seed=20261119 + len(comparisons),
            ),
        }

    return {
        "status": "PASS_EXPLORATORY_CHRONOLOGICAL_ABC_COMPARISON",
        "target": "historical FPL total_points",
        "season": "2017/18",
        "provider": "Wyscout + independently corroborated 11footy identity",
        "eligible_rows": len(eligible),
        "train_rows": len(train),
        "test_rows": len(test),
        "train_unique_players": len({str(row["fpl_element_id"]) for row in train}),
        "test_unique_players": len({str(row["fpl_element_id"]) for row in test}),
        "train_latest_kickoff_utc": max(str(row["kickoff_time_utc"]) for row in train),
        "test_earliest_kickoff_utc": min(str(row["kickoff_time_utc"]) for row in test),
        "chronological_cutoff_utc": cutoff,
        "split_policy": "Whole unique target kickoffs; no fixture/player rows split across train and test.",
        "models": reports,
        "paired_comparisons_vs_conventional": comparisons,
        "source_hashes": source_report.get("source_hashes", {}),
        "point_in_time_status": "NOT_VERIFIED",
        "validation_caveats": [
            "One historical EPL season and one chronological holdout only; not external validation.",
            "Historical FPL and Wyscout source vintages are retrospective, not archived at each FPL deadline.",
            "Same-gameweek leakage is conservatively blocked by the earliest kickoff in each FPL round, but this does not prove source-vintage availability.",
            "Wyscout has no receiver IDs, xG, pressure events or tracking; unsupported A/B/C features remain missing.",
            "The model is an exploratory standalone A/B/C points predictor; it is not the 2PM-Transformer and is not promoted.",
            "All held-out outcomes, including exceptional hauls, remain in evaluation; RMSE is reported but is not the sole promotion criterion.",
        ],
        "promotion_status": "RESEARCH_ONLY_DO_NOT_PROMOTE",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--abc-panel", type=Path, required=True)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--train-fraction", type=float, default=0.7)
    parser.add_argument("--ridge-lambda", type=float, default=1.0)
    parser.add_argument("--bootstrap-replicates", type=int, default=1000)
    args = parser.parse_args()
    if not 0.5 <= args.train_fraction <= 0.9:
        parser.error("--train-fraction must be between 0.5 and 0.9")
    source_report = json.loads(args.source_report.read_text(encoding="utf-8"))
    report = evaluate(
        read_csv(args.abc_panel), source_report,
        args.train_fraction, args.ridge_lambda, args.bootstrap_replicates,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
