#!/usr/bin/env python3
"""Expanding-gameweek walk-forward evaluation of independent A/B/C variants.

The split unit is the FPL gameweek, never an individual kickoff or fixture.
All player-fixture predictions are aggregated to player-gameweek before scoring,
so double-gameweeks are compared at the same target grain as the 2PM model.
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
from evaluate_fpl_walk_forward import cluster_bootstrap_paired_errors
from train_fpl_exploratory_ridge import fit_ridge, predict

BASELINE_FEATURES = (
    "fpl_total_points_prior_3_avg",
    "fpl_total_points_prior_5_avg",
    "fpl_minutes_prior_3_avg",
    "fpl_minutes_prior_5_avg",
)
LAYERS = (
    "A_temporal_football_value",
    "B_risk_defensive_intelligence",
    "C_player_intelligence",
)


def number(value):
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def truth(value):
    return str(value).strip().lower() in {"true", "1", "yes"}


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def available_features(rows, candidates):
    return [name for name in candidates if any(number(r.get(name)) is not None for r in rows)]


def aggregate_player_gameweek(rows, predictions):
    grouped = {}
    for row, prediction in zip(rows, predictions):
        key = (str(row["fpl_element_id"]), int(float(row["gameweek"])))
        item = grouped.setdefault(key, {"actual": 0.0, "predicted": 0.0, "fixture_rows": 0})
        item["actual"] += float(row["target_fpl_total_points"])
        item["predicted"] += float(prediction)
        item["fixture_rows"] += 1
    result = []
    for (player_id, gameweek), values in sorted(grouped.items(), key=lambda x: (x[0][1], x[0][0])):
        result.append({
            "player_id": player_id,
            "gameweek": gameweek,
            "actual": values["actual"],
            "predicted": values["predicted"],
            "fixture_rows": values["fixture_rows"],
        })
    return result


def metrics(records, top_k=20):
    actual = [r["actual"] for r in records]
    predicted = [r["predicted"] for r in records]
    report = evaluate_forecast(actual, predicted, ranking_score=predicted, top_k=top_k)
    errors = [abs(p - y) for p, y in zip(predicted, actual)]
    signed = [p - y for p, y in zip(predicted, actual)]
    ordered = sorted(errors)
    def quantile(q):
        if not ordered:
            return None
        return ordered[min(len(ordered) - 1, int(math.ceil(q * len(ordered)) - 1))]
    return {
        "forecast": report,
        "n_player_gameweeks": len(records),
        "n_unique_players": len({r["player_id"] for r in records}),
        "mean_signed_error_predicted_minus_actual": sum(signed) / len(signed) if signed else None,
        "absolute_error_p50": quantile(0.50),
        "absolute_error_p90": quantile(0.90),
        "absolute_error_p95": quantile(0.95),
        "large_error_rate_ge_6": sum(e >= 6 for e in errors) / len(errors) if errors else None,
        "large_error_rate_ge_10": sum(e >= 10 for e in errors) / len(errors) if errors else None,
        "top_k": top_k,
    }


def candidate_sets():
    layer_features = {
        layer: [f"abc_{name}" for name in LAYER_FEATURES[layer]]
        for layer in LAYERS
    }
    a, b, c = (layer_features[layer] for layer in LAYERS)
    return {
        "FPL_HISTORY_ONLY": list(BASELINE_FEATURES),
        "ABC_ONLY_A": a,
        "ABC_ONLY_B": b,
        "ABC_ONLY_C": c,
        "ABC_ONLY_AB": a + b,
        "ABC_ONLY_AC": a + c,
        "ABC_ONLY_BC": b + c,
        "ABC_ONLY_ABC": a + b + c,
        "FPL_PLUS_A": list(BASELINE_FEATURES) + a,
        "FPL_PLUS_B": list(BASELINE_FEATURES) + b,
        "FPL_PLUS_C": list(BASELINE_FEATURES) + c,
        "FPL_PLUS_AB": list(BASELINE_FEATURES) + a + b,
        "FPL_PLUS_AC": list(BASELINE_FEATURES) + a + c,
        "FPL_PLUS_BC": list(BASELINE_FEATURES) + b + c,
        "FPL_PLUS_ABC": list(BASELINE_FEATURES) + a + b + c,
    }


def build_folds(gameweeks, min_train_gameweeks=18, test_window=4):
    if len(gameweeks) <= min_train_gameweeks:
        raise ValueError("Not enough distinct gameweeks for expanding walk-forward evaluation")
    first_test = max(min_train_gameweeks, len(gameweeks) // 2)
    remaining = gameweeks[first_test:]
    blocks = [remaining[i:i + test_window] for i in range(0, len(remaining), test_window)]
    return [
        {"train_gameweeks": gameweeks[:first_test + i * test_window],
         "test_gameweeks": block}
        for i, block in enumerate(blocks) if block
    ]


def evaluate(rows, source_report, ridge_lambda=1.0, n_boot=1000,
             min_train_gameweeks=18, test_window=4):
    eligible = [
        row for row in rows
        if truth(row.get("research_eligible_for_analysis"))
        and number(row.get("target_fpl_total_points")) is not None
        and number(row.get("gameweek")) is not None
        and row.get("fpl_element_id") not in (None, "")
    ]
    if not eligible:
        raise ValueError("No verified, conservative-cutoff player-fixture rows are eligible")
    eligible.sort(key=lambda r: (int(float(r["gameweek"])), str(r["kickoff_time_utc"]), str(r["fpl_element_id"])))
    gameweeks = sorted({int(float(r["gameweek"])) for r in eligible})
    folds = build_folds(gameweeks, min_train_gameweeks, test_window)
    candidates = candidate_sets()
    pooled = defaultdict(list)
    unavailable_in_any_fold = set()
    fold_reports = []
    model_features = {}
    for fold_index, fold in enumerate(folds):
        train_gws = set(fold["train_gameweeks"])
        test_gws = set(fold["test_gameweeks"])
        train = [r for r in eligible if int(float(r["gameweek"])) in train_gws]
        test = [r for r in eligible if int(float(r["gameweek"])) in test_gws]
        if len(train) < 50 or len(test) < 30:
            continue
        actual_by_model = None
        this_fold = {
            "fold": fold_index + 1,
            "train_gameweeks": fold["train_gameweeks"],
            "test_gameweeks": fold["test_gameweeks"],
            "train_fixture_rows": len(train),
            "test_fixture_rows": len(test),
            "models": {},
        }
        for name, feature_candidates in candidates.items():
            features = available_features(train, feature_candidates)
            if not features:
                unavailable_in_any_fold.add(name)
                this_fold["models"][name] = {"status": "UNAVAILABLE_NO_OBSERVED_FEATURES"}
                continue
            if name == "FPL_HISTORY_ONLY" and not all(f in features for f in BASELINE_FEATURES):
                raise ValueError("Conventional FPL baseline feature coverage is incomplete")
            model = fit_ridge(train, "target_fpl_total_points", features, ridge_lambda)
            fixture_predictions = [predict(model, row) for row in test]
            player_gw = aggregate_player_gameweek(test, fixture_predictions)
            if actual_by_model is None:
                actual_by_model = [(r["player_id"], r["gameweek"], r["actual"]) for r in player_gw]
            elif [(r["player_id"], r["gameweek"], r["actual"]) for r in player_gw] != actual_by_model:
                raise AssertionError("Model player-gameweek cohorts diverged within a fold")
            pooled[name].extend(player_gw)
            model_features[name] = sorted(set(model_features.get(name, [])) | set(features))
            this_fold["models"][name] = {
                "status": "EVALUATED",
                "feature_count": len(features),
                "features_used": features,
                "metrics": metrics(player_gw),
            }
        fold_reports.append(this_fold)

    if not fold_reports:
        raise ValueError("No valid walk-forward folds were produced")
    # Only pool models that produced forecasts on every fold; otherwise their
    # player-GW cohort would silently differ from the conventional comparator.
    for name in unavailable_in_any_fold:
        pooled.pop(name, None)
    pooled_reports = {name: metrics(records) for name, records in pooled.items()}
    baseline = pooled.get("FPL_HISTORY_ONLY")
    paired = {}
    if baseline:
        base_actual = [r["actual"] for r in baseline]
        base_pred = [r["predicted"] for r in baseline]
        cluster_ids = [f"2017/18:{r['player_id']}" for r in baseline]
        for name, records in pooled.items():
            if name == "FPL_HISTORY_ONLY":
                continue
            if [(r["player_id"], r["gameweek"]) for r in records] != [
                (r["player_id"], r["gameweek"]) for r in baseline
            ]:
                raise AssertionError(f"Common cohort mismatch for {name}")
            paired[name] = cluster_bootstrap_paired_errors(
                base_actual, [r["predicted"] for r in records], base_pred,
                cluster_ids, n_boot=n_boot, seed=20261119 + len(paired),
            )

    return {
        "status": "PASS_EXPLORATORY_EXPANDING_GAMEWEEK_ABC_WALK_FORWARD",
        "model_track": "INDEPENDENT_INTEGRATED_ABC",
        "target": "official historical FPL player-gameweek total_points",
        "provider": "Wyscout + independently corroborated 11footy identity",
        "season": "2017/18",
        "eligible_fixture_rows": len(eligible),
        "eligible_player_gameweeks": len({(r["fpl_element_id"], int(float(r["gameweek"]))) for r in eligible}),
        "unique_players": len({str(r["fpl_element_id"]) for r in eligible}),
        "gameweeks_available": gameweeks,
        "fold_count": len(fold_reports),
        "split_policy": "Expanding chronological folds split only at whole FPL gameweek boundaries; all fixtures in a player-GW are aggregated before scoring.",
        "folds": fold_reports,
        "pooled_models": pooled_reports,
        "paired_player_cluster_bootstrap_vs_fpl_history": paired,
        "features_used_across_folds": model_features,
        "ridge_lambda": ridge_lambda,
        "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_SOURCE_VINTAGES",
        "promotion_status": "RESEARCH_ONLY_DO_NOT_PROMOTE",
        "limitations": [
            "One historical EPL season and one event-data provider; this is not external-season validation.",
            "Historical Wyscout and FPL source vintages are retrospective, not archived at each FPL deadline.",
            "The Wyscout identity bridge covers a small, survivorship-biased subset of FPL players.",
            "Unsupported receiver identity, xG, pressure and role features remain null and are not zero-filled.",
            "Ridge is a transparent first candidate, not a final architecture; model-family and regularisation selection require nested chronological validation.",
            "All player-fixture predictions are summed to player-gameweek before evaluation, including double gameweeks.",
        ],
        "source_hashes": source_report.get("source_hashes", {}),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--abc-panel", type=Path, required=True)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ridge-lambda", type=float, default=1.0)
    parser.add_argument("--bootstrap-replicates", type=int, default=1000)
    parser.add_argument("--min-train-gameweeks", type=int, default=18)
    parser.add_argument("--test-window", type=int, default=4)
    args = parser.parse_args()
    if args.ridge_lambda <= 0:
        parser.error("--ridge-lambda must be positive")
    if args.bootstrap_replicates < 100:
        parser.error("--bootstrap-replicates must be at least 100")
    source_report = json.loads(args.source_report.read_text(encoding="utf-8"))
    report = evaluate(
        read_csv(args.abc_panel), source_report,
        args.ridge_lambda, args.bootstrap_replicates,
        args.min_train_gameweeks, args.test_window,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
