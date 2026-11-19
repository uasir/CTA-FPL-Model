#!/usr/bin/env python3
"""Expanding-season evaluation of the standalone conventional-FPL 2PM Transformer.

The model sees only lagged conventional FPL features. A/B/C features are
intentionally excluded. Calibration is fitted on a later pre-validation
chronological slice; all folds retain the common last-five-baseline cohort.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path

import numpy as np

from evaluate_fpl_two_part_model import FEATURES, fit_platt, calibrated_probability, group_player_gameweeks
from evaluate_fpl_walk_forward import (
    cluster_bootstrap_paired_errors, minutes_band, points_band,
    POINTS_BAND_FALLBACK_REPRESENTATIVES,
)
from evaluate_fpl_decision_quality import evaluate_forecast
from train_fpl_exploratory_ridge import fit_ridge, predict

# Include the recent xG/xA aggregates available in the multi-season FPL panel.
# The existing published baseline feature set remains unchanged; matched Ridge
# and two-part comparators below use this same expanded conventional feature set.
TRANSFORMER_FEATURES = tuple(FEATURES) + ("prior3_gw_xg_avg", "prior3_gw_xa_avg")

MAX_LENGTH = 6
EPOCHS = 8
BATCH_SIZE = 1024
WIDTH = 32
HEADS = 4
LAYERS = 1
SEED = 20261119


def build_history_index(rows):
    index = defaultdict(list)
    for row in rows:
        index[(row["season"], str(row["fpl_element_id"]))].append(row)
    for key in index:
        index[key].sort(key=lambda row: int(row["gameweek"]))
    return index


def make_windows(target_rows, history_index, max_length=MAX_LENGTH):
    """Return chronological histories ending at each target deadline snapshot."""
    windows = []
    for target in target_rows:
        key = (target["season"], str(target["fpl_element_id"]))
        history = history_index.get(key, [])
        prior = [row for row in history if int(row["gameweek"]) <= int(target["gameweek"])]
        windows.append(prior[-max_length:])
    return windows


def available_features(fit_rows):
    """Use a feature only when the current fold's fitting block observes it."""
    return tuple(
        feature for feature in TRANSFORMER_FEATURES
        if any(number(row.get(feature)) is not None for row in fit_rows)
    )


def fit_preprocessor(fit_rows, feature_names=None):
    feature_names = tuple(feature_names or available_features(fit_rows))
    if not feature_names:
        raise ValueError("No conventional FPL features are observed in this fold's training data")
    medians = []
    means = []
    scales = []
    for feature in feature_names:
        values = [number(row.get(feature)) for row in fit_rows]
        observed = [value for value in values if value is not None]
        if not observed:
            raise ValueError("No training observations for conventional feature " + feature)
        medians.append(float(np.median(observed)))
    encoded = []
    for row in fit_rows:
        values = [number(row.get(feature)) for feature in feature_names]
        imputed = [medians[i] if value is None else value for i, value in enumerate(values)]
        missing = [1.0 if value is None else 0.0 for value in values]
        encoded.append(imputed + missing)
    matrix = np.asarray(encoded, dtype=np.float32)
    means = matrix.mean(axis=0)
    scales = matrix.std(axis=0)
    scales[scales < 1e-8] = 1.0
    return {"feature_names": list(feature_names), "medians": medians, "means": means, "scales": scales}


def number(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def encode_windows(windows, preprocessor, max_length=MAX_LENGTH):
    feature_names = tuple(preprocessor["feature_names"])
    width = len(feature_names) * 2
    values = np.zeros((len(windows), max_length, width), dtype=np.float32)
    masks = np.ones((len(windows), max_length), dtype=bool)
    for i, window in enumerate(windows):
        encoded = []
        for row in window:
            raw = [number(row.get(feature)) for feature in feature_names]
            imputed = [preprocessor["medians"][j] if v is None else v for j, v in enumerate(raw)]
            missing = [1.0 if v is None else 0.0 for v in raw]
            vector = np.asarray(imputed + missing, dtype=np.float32)
            vector = (vector - preprocessor["means"]) / preprocessor["scales"]
            encoded.append(vector)
        if encoded:
            # Valid timesteps are left-aligned and padding is on the right.
            # TwoPMTransformer pools at valid_count - 1, so this preserves the
            # final observed snapshot rather than pooling a padded position.
            values[i, :len(encoded)] = np.stack(encoded)
            masks[i, :len(encoded)] = False
    return values, masks


def fit_temperature(logits, labels, torch):
    if len(labels) < 10:
        return 1.0
    candidates = np.arange(0.50, 2.51, 0.05)
    best = (float("inf"), 1.0)
    labels_t = torch.as_tensor(labels, dtype=torch.long)
    logits_t = torch.as_tensor(logits, dtype=torch.float32)
    for temperature in candidates:
        loss = float(torch.nn.functional.cross_entropy(logits_t / float(temperature), labels_t).item())
        if loss < best[0]:
            best = (loss, float(temperature))
    return best[1]


def points_representatives(rows):
    groups = [[] for _ in range(6)]
    for row in rows:
        if row["appeared"] == 1.0:
            groups[points_band(row["actual_points"])].append(float(row["actual_points"]))
    return np.asarray([
        float(np.mean(values)) if values else float(POINTS_BAND_FALLBACK_REPRESENTATIVES[i])
        for i, values in enumerate(groups)
    ], dtype=np.float32)


def within_band_eight_plus_share(rows):
    band_rows = [r for r in rows if r["appeared"] == 1.0 and points_band(r["actual_points"]) == 4]
    return (
        sum(float(r["actual_points"]) >= 8.0 for r in band_rows) / len(band_rows)
        if band_rows else 0.5
    )


def train_transformer(fit_rows, fit_windows, preprocessor, torch):
    from torch.utils.data import DataLoader, TensorDataset
    from two_pm_transformer import TwoPMTransformer

    x, mask = encode_windows(fit_windows, preprocessor)
    y_minutes = np.asarray([minutes_band(r["actual_minutes"]) for r in fit_rows], dtype=np.int64)
    y_points = np.asarray([points_band(r["actual_points"]) for r in fit_rows], dtype=np.int64)
    appeared = np.asarray([r["appeared"] == 1.0 for r in fit_rows], dtype=bool)

    dataset = TensorDataset(
        torch.as_tensor(x), torch.as_tensor(mask),
        torch.as_tensor(y_minutes), torch.as_tensor(y_points),
        torch.as_tensor(appeared),
    )
    generator = torch.Generator().manual_seed(SEED)
    loader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True, generator=generator)
    model = TwoPMTransformer(feature_count=x.shape[-1], width=WIDTH, heads=HEADS,
                             layers=LAYERS, dropout=0.10, max_length=MAX_LENGTH)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=0.0001)
    model.train()
    for _ in range(EPOCHS):
        for xb, mb, ym, yp, appeared_batch in loader:
            optimizer.zero_grad()
            output = model(xb, mb)
            loss_minutes = torch.nn.functional.cross_entropy(output["minutes_logits"], ym)
            if appeared_batch.any():
                loss_points = torch.nn.functional.cross_entropy(
                    output["conditional_points_logits"][appeared_batch],
                    yp[appeared_batch],
                )
                loss = loss_minutes + loss_points
            else:
                loss = loss_minutes
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
    return model


def model_logits(model, rows, windows, preprocessor, torch):
    x, mask = encode_windows(windows, preprocessor)
    model.eval()
    outputs = []
    with torch.no_grad():
        for start in range(0, len(rows), BATCH_SIZE):
            xb = torch.as_tensor(x[start:start+BATCH_SIZE])
            mb = torch.as_tensor(mask[start:start+BATCH_SIZE])
            out = model(xb, mb)
            outputs.append((
                out["minutes_logits"].cpu().numpy(),
                out["conditional_points_logits"].cpu().numpy(),
            ))
    return np.concatenate([x[0] for x in outputs]), np.concatenate([x[1] for x in outputs])


def probabilities_from_logits(minutes_logits, points_logits, minutes_temp, points_temp,
                               representatives, eight_plus_share):
    def softmax(values):
        shifted = values - values.max(axis=1, keepdims=True)
        exp = np.exp(shifted)
        return exp / exp.sum(axis=1, keepdims=True)
    minutes = softmax(minutes_logits / minutes_temp)
    conditional = softmax(points_logits / points_temp)
    appearance = 1.0 - minutes[:, 0]
    unconditional = conditional * appearance[:, None]
    unconditional[:, 1] += 1.0 - appearance
    unconditional /= unconditional.sum(axis=1, keepdims=True)
    expected = unconditional @ representatives
    haul = {
        6: unconditional[:, 4] + unconditional[:, 5],
        8: unconditional[:, 5] + unconditional[:, 4] * eight_plus_share,
        10: unconditional[:, 5],
    }
    return expected.tolist(), {key: value.tolist() for key, value in haul.items()}


def fit_affine_expected_points_calibrator(calibration_predictions, calibration_actual):
    """Fit a two-parameter expected-points map on a held-out calibration block."""
    x = np.asarray(calibration_predictions, dtype=np.float64)
    y = np.asarray(calibration_actual, dtype=np.float64)
    if len(x) != len(y) or len(x) < 2 or float(np.var(x)) <= 1e-10:
        return 1.0, 0.0
    slope, _ = np.polyfit(x, y, 1)
    # Expected-points calibration must not reverse the model's ranking.
    slope = max(0.0, float(slope))
    intercept = float(np.mean(y) - slope * np.mean(x))
    return slope, intercept


def apply_affine_expected_points_calibrator(predictions, slope, intercept):
    """Apply the frozen calibration map; expected points cannot be negative."""
    values = np.asarray(predictions, dtype=np.float64)
    return np.maximum(0.0, intercept + slope * values).tolist()


def evaluate_fold(all_rows, season, torch, seed_offset=0):
    train = [r for r in all_rows if r["season"] < season]
    valid = [r for r in all_rows if r["season"] == season]
    train_keys = sorted({(r["season"], r["gameweek"]) for r in train})
    if len(train_keys) < 10:
        raise ValueError("Insufficient prior gameweeks for transformer calibration")
    calibration_count = max(1, math.ceil(len(train_keys) * 0.20))
    calibration_keys = set(train_keys[-calibration_count:])
    fit_rows = [r for r in train if (r["season"], r["gameweek"]) not in calibration_keys]
    calibration_rows = [r for r in train if (r["season"], r["gameweek"]) in calibration_keys]
    fold_features = available_features(fit_rows)
    if len(fit_rows) < len(fold_features) + 10:
        raise ValueError("Insufficient transformer fitting rows or usable features")
    # The same pre-validation chronological split is used for the neural model
    # and its conventional two-part baseline.
    history_index = build_history_index(all_rows)
    fit_windows = make_windows(fit_rows, history_index)
    calibration_windows = make_windows(calibration_rows, history_index)
    validation_rows = [r for r in valid if r["last5_baseline_points"] is not None]
    validation_windows = make_windows(validation_rows, history_index)

    preprocessor = fit_preprocessor(fit_rows, fold_features)
    random.seed(SEED + seed_offset)
    np.random.seed(SEED + seed_offset)
    torch.manual_seed(SEED + seed_offset)
    torch.set_num_threads(1)
    model = train_transformer(fit_rows, fit_windows, preprocessor, torch)
    cal_minutes_logits, cal_points_logits = model_logits(
        model, calibration_rows, calibration_windows, preprocessor, torch
    )
    cal_minute_labels = [minutes_band(r["actual_minutes"]) for r in calibration_rows]
    appeared_cal = [i for i, r in enumerate(calibration_rows) if r["appeared"] == 1.0]
    minutes_temp = fit_temperature(cal_minutes_logits, cal_minute_labels, torch)
    points_temp = fit_temperature(
        cal_points_logits[appeared_cal],
        [points_band(calibration_rows[i]["actual_points"]) for i in appeared_cal],
        torch,
    )
    val_minutes_logits, val_points_logits = model_logits(
        model, validation_rows, validation_windows, preprocessor, torch
    )
    representatives = points_representatives(fit_rows)
    eight_share = within_band_eight_plus_share(fit_rows)
    transformer_prediction, transformer_haul_probs = probabilities_from_logits(
        val_minutes_logits, val_points_logits, minutes_temp, points_temp,
        representatives, eight_share,
    )
    # Expected-points affine calibration is fitted only on the held-out,
    # pre-validation calibration block; the validation season is untouched.
    calibration_prediction, _ = probabilities_from_logits(
        cal_minutes_logits, cal_points_logits, minutes_temp, points_temp,
        representatives, eight_share,
    )
    calibration_y = [r["actual_points"] for r in calibration_rows]
    affine_slope, affine_intercept = fit_affine_expected_points_calibrator(
        calibration_prediction, calibration_y
    )
    transformer_affine_prediction = apply_affine_expected_points_calibrator(
        transformer_prediction, affine_slope, affine_intercept
    )

    appearance_model = fit_ridge(fit_rows, "appeared", fold_features, 10.0)
    calibration_scores = [appearance_model_prediction(appearance_model, r) for r in calibration_rows]
    calibrator = fit_platt(calibration_scores, [r["appeared"] for r in calibration_rows])
    positive_fit = [r for r in fit_rows if r["appeared"] == 1.0]
    conditional_model = fit_ridge(positive_fit, "actual_points", fold_features, 10.0)
    direct_model = fit_ridge(fit_rows, "actual_points", fold_features, 10.0)
    baseline_raw = []
    baseline_calibrated = []
    baseline_direct = []
    baseline_last5 = []
    for row in validation_rows:
        score = appearance_model_prediction(appearance_model, row)
        conditional = max(0.0, predict(conditional_model, row))
        baseline_raw.append(min(1.0, max(0.0, score)) * conditional)
        baseline_calibrated.append(calibrated_probability(calibrator, score) * conditional)
        baseline_direct.append(predict(direct_model, row))
        baseline_last5.append(float(row["last5_baseline_points"]))

    actual = [r["actual_points"] for r in validation_rows]
    transformer_report = evaluate_forecast(
        actual, transformer_prediction, transformer_haul_probs,
        ranking_score=transformer_prediction, top_k=100,
    )
    transformer_affine_report = evaluate_forecast(
        actual, transformer_affine_prediction, transformer_haul_probs,
        ranking_score=transformer_affine_prediction, top_k=100,
    )
    raw_report = evaluate_forecast(actual, baseline_raw, ranking_score=baseline_raw, top_k=100)
    calibrated_report = evaluate_forecast(actual, baseline_calibrated, ranking_score=baseline_calibrated, top_k=100)
    direct_report = evaluate_forecast(actual, baseline_direct, ranking_score=baseline_direct, top_k=100)
    last5_report = evaluate_forecast(actual, baseline_last5, ranking_score=baseline_last5, top_k=100)
    cluster_ids = [f"{r['season']}:{r['fpl_element_id']}" for r in validation_rows]
    bootstrap = cluster_bootstrap_paired_errors(
        actual, transformer_prediction, baseline_calibrated, cluster_ids,
        n_boot=1000, seed=SEED + seed_offset,
    )
    direct_bootstrap = cluster_bootstrap_paired_errors(
        actual, transformer_prediction, baseline_direct, cluster_ids,
        n_boot=1000, seed=SEED + 50 + seed_offset,
    )
    return {
        "season": season,
        "features_used": list(fold_features),
        "fit_player_gameweeks": len(fit_rows),
        "calibration_player_gameweeks": len(calibration_rows),
        "validation_player_gameweeks": len(validation_rows),
        "minutes_temperature": minutes_temp,
        "conditional_points_temperature": points_temp,
        "transformer": transformer_report,
        "transformer_expected_points_affine_calibrated": transformer_affine_report,
        "transformer_expected_points_affine_calibration": {
            "fit_source": "held-out latest 20% of prior training gameweeks only",
            "slope": float(affine_slope),
            "intercept": float(affine_intercept),
        },
        "conventional_two_part_raw": raw_report,
        "conventional_two_part_calibrated": calibrated_report,
        "direct_ridge": direct_report,
        "last5_points_persistence": last5_report,
        "paired_transformer_vs_calibrated_two_part_cluster_bootstrap": bootstrap,
        "paired_transformer_vs_direct_ridge_cluster_bootstrap": direct_bootstrap,
        "_aggregate": {
            "actual": actual,
            "transformer": transformer_prediction,
            "transformer_affine_calibrated": transformer_affine_prediction,
            "transformer_haul_probabilities": transformer_haul_probs,
            "two_part_calibrated": baseline_calibrated,
            "direct_ridge": baseline_direct,
            "last5": baseline_last5,
            "keys": [
                {"season": str(r["season"]), "fpl_element_id": str(r["fpl_element_id"]), "gameweek": int(r["gameweek"])}
                for r in validation_rows
            ],
        },
    }


def appearance_model_prediction(model, row):
    from train_fpl_exploratory_ridge import predict
    return predict(model, row)


def evaluate(rows):
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("Install the optional PyTorch dependency to run this experiment") from exc
    grouped = group_player_gameweeks(rows)
    raw_by_key = {}
    for row in rows:
        raw_by_key.setdefault(
            (str(row["season"]), str(row["fpl_element_id"]), int(row["gameweek"])),
            row,
        )
    for record in grouped:
        raw = raw_by_key[(record["season"], record["fpl_element_id"], record["gameweek"])]
        record["prior3_gw_xg_avg"] = number(raw.get("prior3_gw_xg_avg"))
        record["prior3_gw_xa_avg"] = number(raw.get("prior3_gw_xa_avg"))
    grouped = [r for r in grouped if r["gameweek"] > 1]
    seasons = sorted({r["season"] for r in grouped})
    folds = []
    pooled_actual, pooled_transformer, pooled_transformer_affine, pooled_baseline, pooled_direct, pooled_last5, pooled_clusters = [], [], [], [], [], [], []
    pooled_haul = {6: [], 8: [], 10: []}
    for index, season in enumerate(seasons):
        if index == 0:
            continue
        fold = evaluate_fold(grouped, season, torch, index)
        aggregate = fold.pop("_aggregate")
        folds.append(fold)
        pooled_actual.extend(aggregate["actual"])
        pooled_transformer.extend(aggregate["transformer"])
        pooled_transformer_affine.extend(aggregate["transformer_affine_calibrated"])
        pooled_baseline.extend(aggregate["two_part_calibrated"])
        pooled_direct.extend(aggregate["direct_ridge"])
        pooled_last5.extend(aggregate["last5"])
        for threshold in pooled_haul:
            pooled_haul[threshold].extend(aggregate["transformer_haul_probabilities"][threshold])
        # Validation fold is one season; player-season clusters are unique within it.
        pooled_clusters.extend([
            f"{season}:{r['fpl_element_id']}"
            for r in grouped
            if r["season"] == season and r["last5_baseline_points"] is not None
        ])
    if not folds:
        raise ValueError("No expanding-season Transformer folds available")
    pooled_report = evaluate_forecast(
        pooled_actual, pooled_transformer, pooled_haul,
        ranking_score=pooled_transformer, top_k=100,
    )
    pooled_transformer_affine_report = evaluate_forecast(
        pooled_actual, pooled_transformer_affine,
        ranking_score=pooled_transformer_affine, top_k=100,
    )
    pooled_baseline_report = evaluate_forecast(
        pooled_actual, pooled_baseline,
        ranking_score=pooled_baseline, top_k=100,
    )
    pooled_direct_report = evaluate_forecast(
        pooled_actual, pooled_direct,
        ranking_score=pooled_direct, top_k=100,
    )
    pooled_last5_report = evaluate_forecast(
        pooled_actual, pooled_last5,
        ranking_score=pooled_last5, top_k=100,
    )
    bootstrap = cluster_bootstrap_paired_errors(
        pooled_actual, pooled_transformer, pooled_baseline, pooled_clusters,
        n_boot=1000, seed=SEED + 100,
    )
    direct_bootstrap = cluster_bootstrap_paired_errors(
        pooled_actual, pooled_transformer, pooled_direct, pooled_clusters,
        n_boot=1000, seed=SEED + 200,
    )
    affine_bootstrap = cluster_bootstrap_paired_errors(
        pooled_actual, pooled_transformer_affine, pooled_baseline, pooled_clusters,
        n_boot=1000, seed=SEED + 300,
    )
    return {
        "status": "RESEARCH_ONLY",
        "decision": "DO_NOT_PROMOTE",
        "model_track": "STANDALONE_CONVENTIONAL_FPL_2PM_TRANSFORMER",
        "feature_set": list(TRANSFORMER_FEATURES),
        "sequence_length": MAX_LENGTH,
        "training": {
            "epochs": EPOCHS, "batch_size": BATCH_SIZE, "width": WIDTH,
            "attention_heads": HEADS, "encoder_layers": LAYERS,
            "optimizer": "AdamW", "seed": SEED,
        },
        "validation_design": "Expanding-season walk-forward; each validation season is trained only on earlier seasons. The latest 20% of prior training gameweeks is held out for calibration. Earlier validation-season outcomes enter only through lagged feature snapshots for later deadlines.",
        "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_SOURCE_VINTAGES",
        "fold_count": len(folds),
        "folds": folds,
        "pooled_transformer": pooled_report,
        "pooled_transformer_expected_points_affine_calibrated": pooled_transformer_affine_report,
        "pooled_conventional_two_part_calibrated": pooled_baseline_report,
        "pooled_direct_ridge": pooled_direct_report,
        "pooled_last5_points_persistence": pooled_last5_report,
        "paired_transformer_vs_conventional_two_part_cluster_bootstrap": bootstrap,
        "paired_transformer_affine_vs_conventional_two_part_cluster_bootstrap": affine_bootstrap,
        "paired_transformer_vs_direct_ridge_cluster_bootstrap": direct_bootstrap,
        "limitations": [
            "Historical FPL source vintages are retrospective, not archived pre-deadline snapshots.",
            "The 8+ probability is estimated by the training-only share of 8+ outcomes within the 6-9 points band.",
            "Hyperparameters are predeclared rather than tuned on validation seasons.",
            "The model is standalone and contains no A/B/C or provider-derived CTA features.",
            "This is a research evaluation, not a live recommendation model.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    with args.input.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    report = evaluate(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
