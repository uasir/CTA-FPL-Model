"""Paired comparison of ABC and standalone 2PM on exact manifest test keys."""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

from matched_fold_keys import canonical_key, load_partition_keys, sha_keys, verify_manifest_partition_hashes


def read_prediction_file(path, model):
    required = {"fold", "season", "fpl_element_id", "gameweek", "actual_points"}
    prediction_fields = {
        "abc": ("abc_calibrated_points", "abc_raw_points", "fpl_history_calibrated_points"),
        "two_pm": ("affine_calibrated_points", "predicted_points"),
    }[model]
    rows = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = (required | set(prediction_fields)) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{model} prediction file missing columns: {sorted(missing)}")
        for raw in reader:
            key = canonical_key(raw["season"], raw["fpl_element_id"], raw["gameweek"])
            if key in rows:
                raise ValueError(f"Duplicate {model} prediction key: {key}")
            rows[key] = {
                "fold": int(raw["fold"]),
                "actual": float(raw["actual_points"]),
                **{name: float(raw[name]) for name in prediction_fields},
            }
    if not rows:
        raise ValueError(f"{model} prediction file is empty")
    return rows


def validate_predictions(name, rows, partitions, manifest):
    expected = {}
    for fold, parts in partitions.items():
        for key in parts["test"]:
            if key in expected:
                raise ValueError(f"Test key appears in more than one fold: {key}")
            expected[key] = fold
    actual_keys = set(rows)
    expected_keys = set(expected)
    if actual_keys != expected_keys:
        missing = len(expected_keys - actual_keys)
        extra = len(actual_keys - expected_keys)
        raise ValueError(f"{name} prediction keys differ from manifest test cohort: missing={missing}, extra={extra}")
    per_fold = {}
    manifest_folds = {int(f["fold"]): f for f in manifest["folds"]}
    for fold, parts in partitions.items():
        fold_keys = sorted(key for key, assigned in expected.items() if assigned == fold)
        for key in fold_keys:
            if rows[key]["fold"] != fold:
                raise ValueError(f"{name} prediction fold label mismatch for {key}")
        digest = sha_keys(fold_keys)
        if digest != manifest_folds[fold]["test_key_sha256"]:
            raise ValueError(f"{name} fold {fold} prediction hash differs from manifest")
        per_fold[fold] = {"test_player_gameweeks": len(fold_keys), "test_key_sha256": digest}
    return per_fold


def forecast_metrics(records, prediction_key):
    errors = [r["actual"] - r[prediction_key] for r in records]
    absolute = [abs(x) for x in errors]
    squared = [x * x for x in errors]
    ordered = sorted(absolute)
    def quantile(q):
        if not ordered:
            return None
        pos = (len(ordered) - 1) * q
        lo, hi = math.floor(pos), math.ceil(pos)
        return ordered[lo] if lo == hi else ordered[lo] * (hi - pos) + ordered[hi] * (pos - lo)
    return {
        "n": len(records),
        "mae": statistics.mean(absolute),
        "rmse": math.sqrt(statistics.mean(squared)),
        "mean_signed_error_actual_minus_predicted": statistics.mean(errors),
        "absolute_error_p50": quantile(.50),
        "absolute_error_p90": quantile(.90),
        "absolute_error_p95": quantile(.95),
        "large_error_rate_ge_6": sum(x >= 6 for x in absolute) / len(absolute),
        "large_error_rate_ge_10": sum(x >= 10 for x in absolute) / len(absolute),
    }


def paired_player_cluster_bootstrap(records, candidate_key, comparator_key, n_boot=2000, seed=20261120):
    clusters = defaultdict(list)
    for row in records:
        clusters[(row["season"], row["player_id"])].append(row)
    names = sorted(clusters)
    if len(names) < 2:
        raise ValueError("Paired player-cluster bootstrap requires at least two player clusters")
    deltas_mae, deltas_mse, win_rates = [], [], []
    rng = random.Random(seed)
    for _ in range(n_boot):
        sampled = [rng.choice(names) for _ in names]
        candidate_abs, comparator_abs, candidate_sq, comparator_sq = [], [], [], []
        wins = []
        for cluster in sampled:
            for row in clusters[cluster]:
                ec = row["actual"] - row[candidate_key]
                eb = row["actual"] - row[comparator_key]
                candidate_abs.append(abs(ec))
                comparator_abs.append(abs(eb))
                candidate_sq.append(ec * ec)
                comparator_sq.append(eb * eb)
                wins.append(1.0 if abs(ec) < abs(eb) else 0.0 if abs(ec) > abs(eb) else 0.5)
        deltas_mae.append(statistics.mean(candidate_abs) - statistics.mean(comparator_abs))
        deltas_mse.append(statistics.mean(candidate_sq) - statistics.mean(comparator_sq))
        win_rates.append(statistics.mean(wins))
    def interval(values):
        values = sorted(values)
        return [values[int(.025 * (len(values) - 1))], values[int(.975 * (len(values) - 1))]]
    return {
        "method": "PAIRED_PLAYER_SEASON_CLUSTER_BOOTSTRAP",
        "clusters": len(names),
        "replicates": n_boot,
        "delta_definition": "candidate minus comparator; negative favours candidate",
        "mae_delta_ci95": interval(deltas_mae),
        "mse_delta_ci95": interval(deltas_mse),
        "candidate_absolute_error_win_rate_ci95": interval(win_rates),
    }


def average_ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[order[k]] = rank
        i = j
    return ranks


def pearson(x, y):
    mx, my = statistics.mean(x), statistics.mean(y)
    dx, dy = [v - mx for v in x], [v - my for v in y]
    denom = math.sqrt(sum(v*v for v in dx) * sum(v*v for v in dy))
    return sum(a*b for a, b in zip(dx, dy)) / denom if denom else 0.0


def deadline_metrics(rows, prediction_key, top_k=100):
    actual = [r["actual"] for r in rows]
    predicted = [r[prediction_key] for r in rows]
    ar, pr = average_ranks(actual), average_ranks(predicted)
    k = min(top_k, len(rows))
    selected = sorted(rows, key=lambda r: (-r[prediction_key], r["player_id"]))[:k]
    oracle = sorted(rows, key=lambda r: (-r["actual"], r["player_id"]))[:k]
    universe_mean = statistics.mean(actual)
    selected_mean = statistics.mean(r["actual"] for r in selected)
    oracle_mean = statistics.mean(r["actual"] for r in oracle)
    return {
        "n": len(rows),
        "top_k": k,
        "spearman": pearson(ar, pr),
        "selected_mean_points": selected_mean,
        "universe_mean_points": universe_mean,
        "oracle_top_k_mean_points": oracle_mean,
        "top_k_lift_over_universe": selected_mean - universe_mean,
        "top_k_regret_vs_oracle": oracle_mean - selected_mean,
    }


def ranking_report(records, prediction_key, top_k=100):
    by_deadline = defaultdict(list)
    for row in records:
        by_deadline[(row["season"], row["gameweek"])].append(row)
    deadlines = {key: deadline_metrics(rows, prediction_key, top_k) for key, rows in by_deadline.items()}
    return {
        "n_deadlines": len(deadlines),
        "top_k_per_deadline": top_k,
        "macro_spearman": statistics.mean(v["spearman"] for v in deadlines.values()),
        "macro_selected_mean_points": statistics.mean(v["selected_mean_points"] for v in deadlines.values()),
        "macro_top_k_lift_over_universe": statistics.mean(v["top_k_lift_over_universe"] for v in deadlines.values()),
        "macro_top_k_regret_vs_oracle": statistics.mean(v["top_k_regret_vs_oracle"] for v in deadlines.values()),
        "by_deadline": {f"{season}:GW{gw}": deadlines[(season, gw)] for season, gw in sorted(deadlines)},
        "_deadlines": deadlines,
    }


def paired_deadline_bootstrap(candidate_deadlines, comparator_deadlines, n_boot=2000, seed=20261121):
    if set(candidate_deadlines) != set(comparator_deadlines):
        raise ValueError("Paired ranking models do not cover identical deadlines")
    keys = sorted(candidate_deadlines)
    rng = random.Random(seed)
    deltas = {metric: [] for metric in ("spearman", "selected_mean_points", "top_k_lift_over_universe")}
    for _ in range(n_boot):
        sample = [rng.choice(keys) for _ in keys]
        for metric in deltas:
            deltas[metric].append(statistics.mean(
                candidate_deadlines[k][metric] - comparator_deadlines[k][metric] for k in sample
            ))
    def interval(values):
        values = sorted(values)
        return [values[int(.025 * (len(values) - 1))], values[int(.975 * (len(values) - 1))]]
    return {
        "method": "PAIRED_TEST_DEADLINE_CLUSTER_BOOTSTRAP",
        "deadline_clusters": len(keys),
        "replicates": n_boot,
        "caveat": "Only one historical season is represented; deadline resampling is descriptive uncertainty, not independent-season generalisation.",
        **{f"{metric}_candidate_minus_comparator_ci95": interval(values) for metric, values in deltas.items()},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--abc-predictions", type=Path, required=True)
    parser.add_argument("--two-pm-predictions", type=Path, required=True)
    parser.add_argument("--partition-keys", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bootstrap-replicates", type=int, default=2000)
    args = parser.parse_args()
    if args.bootstrap_replicates < 100:
        parser.error("--bootstrap-replicates must be at least 100")
    partitions = load_partition_keys(args.partition_keys)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    verify_manifest_partition_hashes(partitions, manifest)
    abc = read_prediction_file(args.abc_predictions, "abc")
    two_pm = read_prediction_file(args.two_pm_predictions, "two_pm")
    abc_hashes = validate_predictions("ABC", abc, partitions, manifest)
    two_pm_hashes = validate_predictions("2PM", two_pm, partitions, manifest)
    if set(abc) != set(two_pm):
        raise ValueError("ABC and 2PM prediction keys are not identical")
    records = []
    for key in sorted(abc):
        a, t = abc[key], two_pm[key]
        if a["fold"] != t["fold"]:
            raise ValueError(f"ABC and 2PM fold IDs differ for {key}")
        if abs(a["actual"] - t["actual"]) > 1e-9:
            raise ValueError(f"ABC and 2PM actual points differ for {key}")
        records.append({
            "season": key[0], "player_id": key[1], "gameweek": key[2],
            "actual": a["actual"],
            "abc_calibrated": a["abc_calibrated_points"],
            "abc_raw": a["abc_raw_points"],
            "fpl_history_calibrated": a["fpl_history_calibrated_points"],
            "two_pm_affine": t["affine_calibrated_points"],
            "two_pm_raw": t["predicted_points"],
        })

    models = {
        "ABC_calibrated": "abc_calibrated",
        "ABC_raw": "abc_raw",
        "ABC_FPL_history_reference": "fpl_history_calibrated",
        "2PM_Transformer_affine_calibrated": "two_pm_affine",
        "2PM_Transformer_raw": "two_pm_raw",
    }
    forecast = {name: forecast_metrics(records, key) for name, key in models.items()}
    pair_specs = {
        "ABC_calibrated_vs_2PM_affine_calibrated": ("abc_calibrated", "two_pm_affine"),
        "ABC_calibrated_vs_FPL_history_reference": ("abc_calibrated", "fpl_history_calibrated"),
        "2PM_affine_calibrated_vs_FPL_history_reference": ("two_pm_affine", "fpl_history_calibrated"),
    }
    paired = {}
    for index, (name, (candidate, comparator)) in enumerate(pair_specs.items()):
        paired[name] = paired_player_cluster_bootstrap(
            records, candidate, comparator, args.bootstrap_replicates, 20261120 + index
        )
    rankings = {}
    ranking_bootstraps = {}
    ranking_deadlines = {}
    for name, key in models.items():
        report = ranking_report(records, key)
        ranking_deadlines[name] = report.pop("_deadlines")
        rankings[name] = report
    for index, (name, (candidate, comparator)) in enumerate(pair_specs.items()):
        ranking_bootstraps[name] = paired_deadline_bootstrap(
            ranking_deadlines[candidate if candidate in ranking_deadlines else models[candidate]],
            ranking_deadlines[comparator if comparator in ranking_deadlines else models[comparator]],
            args.bootstrap_replicates, 20261130 + index,
        )

    per_fold = {}
    for fold in sorted(partitions):
        fold_rows = [r for r in records if two_pm[(r["season"], r["player_id"], r["gameweek"])]["fold"] == fold]
        per_fold[fold] = {
            "test_player_gameweeks": len(fold_rows),
            "ABC_calibrated": forecast_metrics(fold_rows, "abc_calibrated"),
            "2PM_affine_calibrated": forecast_metrics(fold_rows, "two_pm_affine"),
            "FPL_history_reference": forecast_metrics(fold_rows, "fpl_history_calibrated"),
        }
    report = {
        "status": "PASS_EXACT_MATCHED_PREDICTION_KEYS_RESEARCH_ONLY",
        "comparison": "ABC_ONLY_VS_STANDALONE_CONVENTIONAL_FPL_2PM_TRANSFORMER",
        "season": manifest.get("season"),
        "matched_test_player_gameweeks": len(records),
        "matched_unique_players": len({r["player_id"] for r in records}),
        "matched_deadlines": len({(r["season"], r["gameweek"]) for r in records}),
        "manifest_common_cohort_sha256": manifest.get("common_key_sha256"),
        "fold_test_key_hashes": {
            str(fold): {
                "manifest": manifest_hash,
                "abc_prediction": abc_hashes[fold]["test_key_sha256"] if "test_key_sha256" in abc_hashes[fold] else manifest_hash,
                "two_pm_prediction": two_pm_hashes[fold]["test_key_sha256"] if "test_key_sha256" in two_pm_hashes[fold] else manifest_hash,
            }
            for fold, manifest_hash in [
                (int(f["fold"]), f["test_key_sha256"]) for f in manifest["folds"]
            ]
        },
        "forecast_metrics": forecast,
        "paired_forecast_uncertainty": paired,
        "deadline_local_ranking": rankings,
        "paired_deadline_ranking_uncertainty": ranking_bootstraps,
        "per_fold_forecast_metrics": per_fold,
        "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_SOURCE_VINTAGES",
        "promotion_status": "RESEARCH_ONLY_DO_NOT_PROMOTE",
        "limitations": [
            "The cohort is the restricted 2017/18 verified Wyscout-FPL identity population, not a representative FPL universe.",
            "Only one historical season is available; player-cluster intervals do not establish cross-season generalisation.",
            "Deadline-cluster ranking intervals are descriptive because all deadlines belong to one season.",
            "Source vintages were not archived at the historical FPL deadlines.",
            "ABC and 2PM are compared as calibrated point forecasts; their internal model architectures and feature availability differ.",
            "No ABC+2PM or FPL+ABC hybrid is evaluated in this comparison.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
