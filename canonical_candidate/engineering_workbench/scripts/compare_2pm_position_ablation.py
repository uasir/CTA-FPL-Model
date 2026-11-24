#!/usr/bin/env python3
"""Paired, deadline-matched comparison of base and position-aware 2PM forecasts."""
from __future__ import annotations
import argparse
import csv
import json
import random
from collections import defaultdict
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


def average_rank(values):
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        rank = (cursor + 1 + end) / 2.0
        for offset in range(cursor, end):
            ranks[order[offset]] = rank
        cursor = end
    return ranks


def spearman(actual, predicted):
    if len(actual) < 2:
        return None
    left, right = average_rank(actual), average_rank(predicted)
    mean_left = sum(left) / len(left)
    mean_right = sum(right) / len(right)
    covariance = sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right))
    variance_left = sum((a - mean_left) ** 2 for a in left)
    variance_right = sum((b - mean_right) ** 2 for b in right)
    denominator = (variance_left * variance_right) ** 0.5
    return covariance / denominator if denominator else 0.0


def rank_by_deadline(rows, prediction_key, top_k=100):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["season"], int(row["gameweek"]))].append(row)
    deadline_rows = {}
    for key, group in sorted(groups.items()):
        actual = [row["actual"] for row in group]
        predicted = [row[prediction_key] for row in group]
        k = min(top_k, len(group))
        result = evaluate_forecast(actual, predicted, ranking_score=predicted, top_k=k)["ranking"]
        deadline_rows[key] = {
            "n": len(group),
            "spearman": spearman(actual, predicted),
            "selected_mean_points": result["selected_mean_points"],
            "oracle_top_k_mean_points": result["oracle_top_k_mean_points"],
            "top_k_lift_over_universe": result["top_k_lift_over_universe"],
            "top_k_regret_vs_oracle": result["top_k_regret_vs_oracle"],
        }
    by_season = defaultdict(list)
    for (season, _), values in deadline_rows.items():
        by_season[season].append(values)
    season_summary = {}
    for season, values in sorted(by_season.items()):
        season_summary[season] = {
            metric: sum(row[metric] for row in values) / len(values)
            for metric in ("spearman", "selected_mean_points", "oracle_top_k_mean_points",
                           "top_k_lift_over_universe", "top_k_regret_vs_oracle")
        }
    summary = {
        "n_deadlines": len(deadline_rows),
        "n_seasons": len(by_season),
        "top_k_per_deadline": top_k,
        "macro_spearman": sum(row["spearman"] for row in deadline_rows.values()) / len(deadline_rows),
        "macro_selected_mean_points": sum(row["selected_mean_points"] for row in deadline_rows.values()) / len(deadline_rows),
        "macro_oracle_top_k_mean_points": sum(row["oracle_top_k_mean_points"] for row in deadline_rows.values()) / len(deadline_rows),
        "macro_top_k_lift_over_universe": sum(row["top_k_lift_over_universe"] for row in deadline_rows.values()) / len(deadline_rows),
        "macro_top_k_regret_vs_oracle": sum(row["top_k_regret_vs_oracle"] for row in deadline_rows.values()) / len(deadline_rows),
        "by_season": season_summary,
    }
    return summary, deadline_rows


def paired_deadline_ranking_bootstrap(base_deadlines, position_deadlines, seed=20261121, n_boot=2000):
    if set(base_deadlines) != set(position_deadlines):
        raise ValueError("Base and position ranking must cover identical season-gameweek deadlines")
    seasons = sorted({season for season, _ in base_deadlines})
    deltas = {key: {
        "selected_mean_points": position_deadlines[key]["selected_mean_points"] - base_deadlines[key]["selected_mean_points"],
        "spearman": position_deadlines[key]["spearman"] - base_deadlines[key]["spearman"],
    } for key in base_deadlines}
    def mean_for(sampled_seasons, metric):
        values = [deltas[key][metric] for season in sampled_seasons for key in deltas if key[0] == season]
        return sum(values) / len(values) if values else 0.0
    rng = random.Random(seed)
    boot_selected, boot_spearman = [], []
    for _ in range(n_boot):
        sampled = [rng.choice(seasons) for _ in seasons]
        boot_selected.append(mean_for(sampled, "selected_mean_points"))
        boot_spearman.append(mean_for(sampled, "spearman"))
    def interval(values):
        values = sorted(values)
        return [values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))]]
    return {
        "method": "SEASON_CLUSTER_BOOTSTRAP_OF_WITHIN_DEADLINE_RANKING_DELTAS",
        "season_clusters": len(seasons), "deadline_clusters": len(deltas), "replicates": n_boot,
        "position_minus_base_macro_selected_mean_points": sum(value["selected_mean_points"] for value in deltas.values()) / len(deltas),
        "selected_mean_points_delta_ci95": interval(boot_selected),
        "position_minus_base_macro_spearman": sum(value["spearman"] for value in deltas.values()) / len(deltas),
        "spearman_delta_ci95": interval(boot_spearman),
    }


def compare_predictions(base: dict, position: dict) -> dict:
    if set(base) != set(position):
        raise ValueError("Base and position models must have identical player-gameweek keys")
    keys = sorted(base)
    for key in keys:
        if abs(base[key]["actual"] - position[key]["actual"]) > 1e-9:
            raise ValueError(f"Actual points differ for matched key {key}")
    rows = [{
        "season": key[0], "gameweek": int(key[2]), "actual": base[key]["actual"],
        "base_raw": base[key]["raw"], "position_raw": position[key]["raw"],
        "base_calibrated": base[key]["calibrated"], "position_calibrated": position[key]["calibrated"],
    } for key in keys]
    actual = [row["actual"] for row in rows]
    base_raw = [row["base_raw"] for row in rows]
    position_raw = [row["position_raw"] for row in rows]
    base_cal = [row["base_calibrated"] for row in rows]
    position_cal = [row["position_calibrated"] for row in rows]
    clusters = [f"{key[0]}:{key[1]}" for key in keys]
    raw_base_ranking, raw_base_deadlines = rank_by_deadline(rows, "base_raw")
    raw_position_ranking, raw_position_deadlines = rank_by_deadline(rows, "position_raw")
    cal_base_ranking, cal_base_deadlines = rank_by_deadline(rows, "base_calibrated")
    cal_position_ranking, cal_position_deadlines = rank_by_deadline(rows, "position_calibrated")
    return {
        "status": "RESEARCH_ONLY_PAIRED_FEATURE_ABLATION",
        "comparison": "POSITION_AWARE_2PM_MINUS_BASE_2PM",
        "matched_player_gameweeks": len(keys),
        "matched_seasons": sorted({key[0] for key in keys}),
        "matched_deadlines": len(raw_base_deadlines),
        "raw_expected_points": {
            "base_point_errors": evaluate_forecast(actual, base_raw)["point_errors"],
            "position_point_errors": evaluate_forecast(actual, position_raw)["point_errors"],
            "paired_player_season_cluster_bootstrap_position_minus_base": cluster_bootstrap_paired_errors(
                actual, position_raw, base_raw, clusters, n_boot=2000, seed=20261119,
            ),
            "ranking": {
                "base": raw_base_ranking, "position": raw_position_ranking,
                "paired_season_cluster_bootstrap_position_minus_base": paired_deadline_ranking_bootstrap(
                    raw_base_deadlines, raw_position_deadlines, seed=20261121,
                ),
            },
        },
        "affine_calibrated_expected_points": {
            "base_point_errors": evaluate_forecast(actual, base_cal)["point_errors"],
            "position_point_errors": evaluate_forecast(actual, position_cal)["point_errors"],
            "paired_player_season_cluster_bootstrap_position_minus_base": cluster_bootstrap_paired_errors(
                actual, position_cal, base_cal, clusters, n_boot=2000, seed=20261120,
            ),
            "ranking": {
                "base": cal_base_ranking, "position": cal_position_ranking,
                "paired_season_cluster_bootstrap_position_minus_base": paired_deadline_ranking_bootstrap(
                    cal_base_deadlines, cal_position_deadlines, seed=20261122,
                ),
            },
        },
        "interpretation_rule": "Negative MAE/MSE deltas favor position features. Ranking is calculated within each season-gameweek deadline and reported separately. No model promotion follows from this single retrospective ablation.",
        "limitations": [
            "Historical source vintages are retrospective, not archived pre-deadline snapshots.",
            "Position labels may reflect retrospective season exports rather than a fully archived deadline-time position state.",
            "Player-season clustered forecast intervals and season-clustered ranking intervals quantify different dependence structures.",
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