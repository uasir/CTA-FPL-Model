#!/usr/bin/env python3
"""Compare independent ABC and conventional 2PM on an exact player-GW cohort.

The 2PM fold is trained only on the prior 2016/17 season and predicts 2017/18.
ABC uses the expanding whole-GW folds built from the Wyscout-matched 2017/18
cohort. Both are scored only on the intersection of player-GWs with forecasts
from both tracks. Raw player-level predictions remain runner-local.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from evaluate_cta_abc_walk_forward import evaluate as evaluate_abc, read_csv, metrics
from evaluate_fpl_two_part_model import group_player_gameweeks
from evaluate_fpl_walk_forward import cluster_bootstrap_paired_errors
from evaluate_two_pm_transformer_walk_forward import evaluate_fold


def number(value):
    if value in (None, ""):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value == value and abs(value) != float("inf") else None


def load_two_pm_panel(path):
    rows = read_csv(path)
    grouped = group_player_gameweeks(rows)
    raw = {
        (str(r["season"]), str(r["fpl_element_id"]), int(r["gameweek"])): r
        for r in rows
    }
    for row in grouped:
        source = raw[(str(row["season"]), str(row["fpl_element_id"]), int(row["gameweek"]))]
        row["prior3_gw_xg_avg"] = number(source.get("prior3_gw_xg_avg"))
        row["prior3_gw_xa_avg"] = number(source.get("prior3_gw_xa_avg"))
    return [r for r in grouped if int(r["gameweek"]) > 1]


def key(player_id, gameweek):
    return (str(player_id), int(gameweek))


def evaluate(abc_panel_path, source_report_path, fpl_panel_path, n_boot=1000):
    import torch

    source_report = json.loads(source_report_path.read_text(encoding="utf-8"))
    abc_report = evaluate_abc(
        read_csv(abc_panel_path), source_report,
        n_boot=n_boot, min_train_gameweeks=18, test_window=4,
        return_predictions=True,
    )
    abc_predictions = abc_report.pop("_pooled_predictions")
    fpl_rows = load_two_pm_panel(fpl_panel_path)
    transformer_fold = evaluate_fold(fpl_rows, "2017-18", torch, seed_offset=17)
    transformer = transformer_fold["_aggregate"]
    keys = [key(x["fpl_element_id"], x["gameweek"]) for x in transformer["keys"]]
    if not (len(keys) == len(transformer["actual"]) == len(transformer["transformer"]) == len(transformer["transformer_affine_calibrated"])):
        raise AssertionError("2PM validation key and prediction lengths do not match")
    transformer_actual = {k: float(v) for k, v in zip(keys, transformer["actual"])}
    transformer_raw = {k: float(v) for k, v in zip(keys, transformer["transformer"])}
    transformer_affine = {k: float(v) for k, v in zip(keys, transformer["transformer_affine_calibrated"])}

    if "FPL_HISTORY_ONLY" not in abc_predictions:
        raise ValueError("ABC evaluation did not produce its conventional history baseline")
    abc_maps = {
        name: {key(r["player_id"], r["gameweek"]): r for r in records}
        for name, records in abc_predictions.items()
    }
    common = set(abc_maps["FPL_HISTORY_ONLY"]) & set(transformer_raw)
    for name, records in abc_maps.items():
        common &= set(records)
    candidate_common_keys = sorted(common, key=lambda k: (k[1], k[0]))
    actual_mismatch_by_gameweek = {}
    common_keys = []
    for k in candidate_common_keys:
        abc_actual = float(abc_maps["FPL_HISTORY_ONLY"][k]["actual"])
        two_pm_actual = transformer_actual[k]
        if abs(abc_actual - two_pm_actual) <= 1e-9:
            common_keys.append(k)
        else:
            actual_mismatch_by_gameweek[k[1]] = actual_mismatch_by_gameweek.get(k[1], 0) + 1
    excluded_actual_mismatch_rows = len(candidate_common_keys) - len(common_keys)
    if len(common_keys) < 30:
        raise ValueError(
            f"Insufficient exact-actual common player-GW cohort after excluding "
            f"{excluded_actual_mismatch_rows} source/fixture-coverage mismatches: {len(common_keys)}"
        )
    actual = [float(abc_maps["FPL_HISTORY_ONLY"][k]["actual"]) for k in common_keys]
    cluster_ids = [f"2017-18:{player_id}" for player_id, _ in common_keys]

    model_predictions = {
        name: [float(records[k]["predicted"]) for k in common_keys]
        for name, records in abc_maps.items()
    }
    model_predictions["2PM_TRANSFORMER"] = [transformer_raw[k] for k in common_keys]
    model_predictions["2PM_TRANSFORMER_AFFINE_CALIBRATED"] = [transformer_affine[k] for k in common_keys]
    records_by_model = {
        name: [
            {"player_id": player_id, "gameweek": gw, "actual": y, "predicted": p}
            for (player_id, gw), y, p in zip(common_keys, actual, prediction)
        ]
        for name, prediction in model_predictions.items()
    }
    reports = {name: metrics(records) for name, records in records_by_model.items()}

    paired_vs_2pm = {}
    for name, prediction in model_predictions.items():
        if name.startswith("2PM_"):
            continue
        paired_vs_2pm[name] = {
            "vs_2pm_raw": cluster_bootstrap_paired_errors(
                actual, prediction, model_predictions["2PM_TRANSFORMER"],
                cluster_ids, n_boot=n_boot, seed=20261119 + len(paired_vs_2pm),
            ),
            "vs_2pm_affine_calibrated": cluster_bootstrap_paired_errors(
                actual, prediction, model_predictions["2PM_TRANSFORMER_AFFINE_CALIBRATED"],
                cluster_ids, n_boot=n_boot, seed=20261219 + len(paired_vs_2pm),
            ),
        }

    return {
        "status": "PASS_EXPLORATORY_SAME_COHORT_ABC_VS_2PM",
        "cohort": {
            "season": "2017/18",
            "player_gameweeks": len(common_keys),
            "candidate_common_player_gameweeks_before_actual_match": len(candidate_common_keys),
            "excluded_actual_mismatch_player_gameweeks": excluded_actual_mismatch_rows,
            "excluded_actual_mismatch_counts_by_gameweek": actual_mismatch_by_gameweek,
            "unique_players": len({p for p, _ in common_keys}),
            "gameweeks": sorted({gw for _, gw in common_keys}),
            "grain": "player_gameweek",
            "common_cohort_rule": "Exact FPL element ID and gameweek intersection, with equal official target points from the ABC fixture panel and conventional player-GW panel; only rows with forecasts from every reported model.",
        },
        "abc_track": "Independent A/B/C predictor; expanding whole-gameweek folds; Wyscout/11footy matched cohort.",
        "2pm_track": "Standalone conventional 2PM-Transformer; trained on 2016/17 only and validated on 2017/18; no ABC inputs.",
        "2pm_fit_player_gameweeks": transformer_fold["fit_player_gameweeks"],
        "2pm_calibration_player_gameweeks": transformer_fold["calibration_player_gameweeks"],
        "models": reports,
        "paired_player_cluster_bootstrap_vs_2pm": paired_vs_2pm,
        "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_SOURCE_VINTAGES",
        "promotion_status": "RESEARCH_ONLY_DO_NOT_PROMOTE",
        "limitations": [
            "One historical season and one small, survivorship-biased Wyscout/11footy player subset.",
            "Wyscout and FPL historical data are retrospective vintages, not verified pre-deadline snapshots.",
            "The 2PM model trains on all eligible FPL players in 2016/17; ABC is trained only on the verified Wyscout-matched cohort in 2017/18.",
            "Both models are scored on the exact same player-GW intersection; rows with a source/fixture-coverage target mismatch are explicitly excluded, not reconciled by imputation.",
            "Their available training histories differ: the conventional model has all FPL players in the prior season, while ABC has only the verified Wyscout-matched cohort.",
            "This is a first matched-cohort comparison, not evidence of general superiority or prospective accuracy.",
        ],
        "abc_walk_forward_summary": {
            "fold_count": abc_report["fold_count"],
            "folds": [
                {"fold": f["fold"], "train_gameweeks": f["train_gameweeks"], "test_gameweeks": f["test_gameweeks"]}
                for f in abc_report["folds"]
            ],
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--abc-panel", type=Path, required=True)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--fpl-multiseason-panel", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bootstrap-replicates", type=int, default=1000)
    args = parser.parse_args()
    if args.bootstrap_replicates < 100:
        parser.error("--bootstrap-replicates must be at least 100")
    report = evaluate(
        args.abc_panel, args.source_report, args.fpl_multiseason_panel,
        args.bootstrap_replicates,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
