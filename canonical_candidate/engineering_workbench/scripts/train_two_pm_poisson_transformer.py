"""Chronological experimental trainer for the independent 2PM Poisson-mixture Transformer.

This first trainer is deliberately Stage-A only: expanding-season folds through
2024-25, using the manifest's 259 common candidate features. It does not claim
point-in-time feature admission or production readiness. 2025-26 adaptation and
2026-27 OOT are deliberately excluded and handled by separate protocols.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset

from two_component_poisson_transformer import (
    build_model,
    forward_player_gameweek_batch,
    initialize_mixture_head_from_training_targets,
)
from two_pm_fold_preprocessing import (
    fit_fold_median_imputer,
    apply_fold_median_imputer,
)

SEASONS = ("2020-21", "2021-22", "2022-23", "2023-24", "2024-25")
VALIDATION_SEASONS = SEASONS[1:]
HISTORY_TOKEN_COUNT = 5


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def load_grouped_dataset(root: Path, schema_path: Path, manifest_path: Path):
    schema = json.loads(schema_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    feature_order = schema["feature_order"]
    if len(feature_order) != 286:
        raise ValueError("Expected the pinned 286-feature schema")
    common = manifest["feature_groups"]["common_candidate"]["feature_order"]
    defensive = manifest["feature_groups"]["defensive_regime_dependent"]["feature_order"]
    if len(common) != 259 or len(defensive) != 27:
        raise ValueError("Unexpected feature-group manifest counts")
    if set(common) & set(defensive) or set(common) | set(defensive) != set(feature_order):
        raise ValueError("Feature manifest does not partition the schema")
    indices = np.asarray([feature_order.index(name) for name in common], dtype=np.int64)

    # Enforce manifest-level source-vintage HOLD policies again at load time.
    # This protects already-built artifacts when a policy is tightened later;
    # a stale observed-value sidecar cannot override a current HOLD decision.
    policy_features: set[str] = set()
    for policy_name, policy in manifest.get("source_vintage_policies", {}).items():
        names = policy.get("feature_order", [])
        if not isinstance(names, list) or len(names) != len(set(names)):
            raise ValueError(f"Invalid or duplicate source-vintage feature list: {policy_name}")
        declared_count = policy.get("feature_count")
        if declared_count is not None and declared_count != len(names):
            raise ValueError(f"Source-vintage feature count mismatch: {policy_name}")
        unknown = set(names) - set(feature_order)
        if unknown:
            raise ValueError(f"Source-vintage policy references features outside schema: {sorted(unknown)}")
        overlap = policy_features.intersection(names)
        if overlap:
            raise ValueError(f"Overlapping source-vintage policies: {sorted(overlap)}")
        status = policy.get("status")
        action = policy.get("mask_action")
        if status != "HOLD" or action != "FORCE_UNOBSERVED":
            raise ValueError(
                f"Unsupported source-vintage policy {policy_name}: {status}/{action}; "
                "training loader only accepts HOLD/FORCE_UNOBSERVED until row-level masks are implemented."
            )
        policy_features.update(names)
    vintage_indices = np.asarray(
        [i for i, name in enumerate(feature_order) if name in policy_features],
        dtype=np.int64,
    )

    tensor_root = root / "postmatch-grouped-dataset" / "player_gameweek_tensors"
    samples: list[tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]] = []
    for metadata_path in sorted(tensor_root.glob("*_gw*/metadata_player_gw_*.csv")):
        with metadata_path.open(newline="") as handle:
            metadata = list(csv.DictReader(handle))
        stem = metadata_path.name.replace("metadata_player_gw_", "")
        x_path = metadata_path.with_name("X_player_gw_" + stem.replace(".csv", ".npy"))
        mask_path = metadata_path.with_name("fixture_mask_" + stem.replace(".csv", ".npy"))
        observed_path = metadata_path.with_name("observed_value_mask_" + stem.replace(".csv", ".npy"))
        availability_path = metadata_path.with_name("source_availability_state_" + stem.replace(".csv", ".npy"))
        y_path = metadata_path.with_name("y_player_gw_" + stem.replace(".csv", ".npy"))
        required_paths = (x_path, mask_path, observed_path, availability_path, y_path)
        missing_paths = [str(path) for path in required_paths if not path.exists()]
        if missing_paths:
            raise FileNotFoundError(
                "Training is blocked: shard lacks required provenance arrays: "
                + ", ".join(missing_paths)
            )
        x = np.load(x_path, allow_pickle=False)
        fixture_mask = np.load(mask_path, allow_pickle=False).astype(bool)
        observed_full = np.load(observed_path, allow_pickle=False)
        availability_full = np.load(availability_path, allow_pickle=False)
        y = np.load(y_path, allow_pickle=False).astype(np.float32).reshape(-1)
        if observed_full.shape != x.shape or availability_full.shape != x.shape:
            raise ValueError(f"Provenance-mask shape mismatch in {metadata_path}")
        if not np.isin(observed_full, [0, 1]).all():
            raise ValueError(f"Observed-value mask must be binary in {observed_path}")
        if not np.isin(availability_full, [0, 1, 2]).all():
            raise ValueError(f"Source availability must use 0/1/2 states in {availability_path}")
        if np.any((observed_full == 1) & (availability_full == 0)):
            raise ValueError(f"Structurally unavailable values marked observed in {metadata_path}")
        if np.any((observed_full == 1) & ~np.isfinite(x)):
            raise ValueError(f"Non-finite values marked observed in {metadata_path}")
        if vintage_indices.size:
            observed_full[..., vintage_indices] = 0
        if x.shape != (len(metadata), fixture_mask.shape[1], 6, 286):
            raise ValueError(f"Unexpected X shape in {x_path}: {x.shape}")
        if len(metadata) != len(y) or fixture_mask.shape[0] != len(y):
            raise ValueError(f"Shard row counts disagree: {metadata_path}")
        for i, row in enumerate(metadata):
            season = row["season"]
            if season not in SEASONS:
                continue
            # The first five tokens are historical post-match states. The last
            # token is the target fixture query. Values are kept as stored.
            values = x[i, :, :, :][:, :, indices].astype(np.float32, copy=True)
            # Use the builder's raw-source and source-vintage masks. Never infer
            # observation from finiteness: upstream pipelines may zero-fill.
            observed = observed_full[i][:, :, indices].astype(bool, copy=True)
            availability = availability_full[i][:, :, indices].astype(np.int64, copy=True)
            if np.any(observed & (availability == 0)):
                raise ValueError(f"Observed mask conflicts with unavailable source in {metadata_path}")
            # Padded fixture slots are not real queries and carry no observations.
            values[~fixture_mask[i]] = np.nan
            observed[~fixture_mask[i]] = False
            availability[~fixture_mask[i]] = 0
            samples.append((values, fixture_mask[i], observed, {
                **row,
                "target_points": float(y[i]),
                "season": season,
                "availability": availability,
            }))
    if not samples:
        raise ValueError(f"No grouped samples found under {tensor_root}")
    return samples, common


def fold_arrays(samples, indices, feature_count):
    selected = [samples[int(i)] for i in indices]
    max_fixtures = max(s[1].shape[0] for s in selected)
    x = np.full((len(selected), max_fixtures, 6, feature_count), np.nan, np.float32)
    mask = np.zeros((len(selected), max_fixtures), bool)
    observed = np.zeros_like(x, dtype=bool)
    availability = np.zeros_like(x, dtype=np.int64)
    y = np.zeros(len(selected), np.float32)
    regimes = np.zeros(len(selected), np.int64)
    rows = []
    for j, (values, fixture_mask, obs, meta) in enumerate(selected):
        n = len(fixture_mask)
        x[j, :n] = values
        mask[j, :n] = fixture_mask
        observed[j, :n] = obs
        availability[j, :n] = meta["availability"]
        y[j] = meta["target_points"]
        rows.append(meta)
    return x, mask, observed, availability, y, regimes, rows


def fit_scaler(train_x: np.ndarray, train_observed: np.ndarray, fixture_mask: np.ndarray):
    # Scaling is fitted only on the training fold. Shared history tokens are
    # deduplicated to avoid weighting double-gameweek samples twice.
    values = train_x.copy()
    selected = train_observed & fixture_mask[..., None, None]
    for i in range(len(values)):
        valid = np.flatnonzero(fixture_mask[i])
        for f in valid[1:]:
            selected[i, f, :HISTORY_TOKEN_COUNT] = False
    means, scales = [], []
    for j in range(values.shape[-1]):
        col = values[..., j][selected[..., j]]
        if not col.size:
            # No evidence in this fold: keep the feature neutral (mean 0,
            # scale 1). Its observed-value channel remains false, so the model
            # can distinguish unavailable input from a measured zero.
            means.append(0.0)
            scales.append(1.0)
            continue
        means.append(float(col.mean()))
        scale = float(col.std())
        scales.append(scale if scale > 1e-8 else 1.0)
    return np.asarray(means, np.float32), np.asarray(scales, np.float32)


def apply_scaler(x, means, scales, fixture_mask):
    result = (x - means.reshape(1, 1, 1, -1)) / scales.reshape(1, 1, 1, -1)
    result[~fixture_mask] = 0.0
    if not np.isfinite(result).all():
        raise ValueError("Non-finite scaled inputs")
    return result.astype(np.float32)


def batch_iter(arrays, batch_size, shuffle, seed):
    x, fm, obs, avail, y, regime = arrays
    ds = TensorDataset(
        torch.from_numpy(x), torch.from_numpy(fm), torch.from_numpy(obs),
        torch.from_numpy(avail), torch.from_numpy(y), torch.from_numpy(regime),
    )
    generator = torch.Generator().manual_seed(seed)
    return DataLoader(ds, batch_size=batch_size, shuffle=shuffle, generator=generator)


def run_fold(samples, feature_order, train_idx, valid_idx, args, fold_dir):
    feature_count = len(feature_order)
    tr = fold_arrays(samples, train_idx, feature_count)
    va = fold_arrays(samples, valid_idx, feature_count)
    tr_x, tr_mask, tr_obs, tr_avail, tr_y, tr_regime, _ = tr
    va_x, va_mask, va_obs, va_avail, va_y, va_regime, va_rows = va

    imputer = fit_fold_median_imputer(
        tr_x, tr_obs, feature_order, fixture_mask=tr_mask,
        history_token_count=HISTORY_TOKEN_COUNT,
    )
    tr_x = apply_fold_median_imputer(tr_x, tr_obs, imputer, feature_order, fixture_mask=tr_mask)
    va_x = apply_fold_median_imputer(va_x, va_obs, imputer, feature_order, fixture_mask=va_mask)
    means, scales = fit_scaler(tr_x, tr_obs, tr_mask)
    tr_x = apply_scaler(tr_x, means, scales, tr_mask)
    va_x = apply_scaler(va_x, means, scales, va_mask)

    # Only player-Gameweek labels are available in this artifact. The model
    # contract therefore prescribes the fixed conservative shift of 20;
    # do not estimate a fixture-level minimum from aggregated GW labels.
    support_shift = 20
    if (va_y < -support_shift * va_mask.sum(axis=1)).any():
        raise ValueError("Validation target falls below the training-only aggregate support")
    model = build_model(
        feature_count, sequence_length=6, num_layers=args.layers,
        d_model=args.d_model, nhead=args.heads,
        dim_feedforward=args.feedforward, dropout=args.dropout,
        support_shift=support_shift,
    ).to(args.device)
    init = initialize_mixture_head_from_training_targets(
        model, tr_y, max_iter=500,
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    train_loader = batch_iter((tr_x, tr_mask, tr_obs, tr_avail, tr_y, tr_regime), args.batch_size, True, args.seed)
    valid_loader = batch_iter((va_x, va_mask, va_obs, va_avail, va_y, va_regime), args.batch_size, False, args.seed)

    best_loss, best_epoch, stale = float("inf"), 0, 0
    best_state = None
    history = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        train_losses = []
        for bx, bm, bo, bav, by, br in train_loader:
            bx, bm = bx.to(args.device), bm.to(args.device)
            bo, bav, by, br = bo.to(args.device), bav.to(args.device), by.to(args.device), br.to(args.device)
            optimizer.zero_grad(set_to_none=True)
            out = forward_player_gameweek_batch(model, bx, bm, bo, bav, br, targets=by)
            loss = out["loss"]
            if not torch.isfinite(loss):
                raise FloatingPointError("Non-finite training NLL")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_losses.append(float(loss.detach().cpu()))
        model.eval()
        valid_losses, predictions, variances = [], [], []
        with torch.no_grad():
            for bx, bm, bo, bav, by, br in valid_loader:
                out = forward_player_gameweek_batch(
                    model, bx.to(args.device), bm.to(args.device),
                    bo.to(args.device), bav.to(args.device), br.to(args.device), targets=by.to(args.device),
                )
                valid_losses.extend(out["nll_per_player_gameweek"].cpu().tolist())
                predictions.extend(out["expected_points"].cpu().tolist())
                variances.extend(out["variance"].cpu().tolist())
        val_loss = float(np.mean(valid_losses))
        history.append({"epoch": epoch, "train_nll": float(np.mean(train_losses)), "validation_nll": val_loss})
        if val_loss < best_loss - args.min_delta:
            best_loss, best_epoch, stale = val_loss, epoch, 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            stale += 1
            if stale >= args.patience:
                break
    if best_state is None:
        raise RuntimeError("No valid checkpoint produced")
    model.load_state_dict(best_state)
    model.eval()
    predictions, variances, nll = [], [], []
    with torch.no_grad():
        for bx, bm, bo, bav, by, br in valid_loader:
            out = forward_player_gameweek_batch(
                model, bx.to(args.device), bm.to(args.device),
                bo.to(args.device), bav.to(args.device), br.to(args.device), targets=by.to(args.device),
            )
            predictions.extend(out["expected_points"].cpu().tolist())
            variances.extend(out["variance"].cpu().tolist())
            nll.extend(out["nll_per_player_gameweek"].cpu().tolist())

    fold_dir.mkdir(parents=True, exist_ok=True)
    torch.save(best_state, fold_dir / "best_model.pt")
    (fold_dir / "preprocessing.json").write_text(json.dumps({
        "feature_order": feature_order, "imputer": imputer,
        "scaler_mean": means.tolist(), "scaler_scale": scales.tolist(),
        "support_shift": support_shift, "initialization": init,
        "availability_policy": "UNKNOWN for all common candidate features; no feature source-vintage admission implied",
        "zero_coverage_features": imputer.get("zero_coverage_features", []),
    }, indent=2))
    with (fold_dir / "training_history.json").open("w") as f:
        json.dump(history, f, indent=2)
    pred_path = fold_dir / "oof_predictions.csv"
    with pred_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "season", "gameweek", "fpl_code", "fixture_ids",
            "actual_points", "predicted_points", "predicted_variance", "nll",
        ])
        writer.writeheader()
        for row, pred, var, loss in zip(va_rows, predictions, variances, nll):
            writer.writerow({
                "season": row["season"], "gameweek": row["gameweek"],
                "fpl_code": row["fpl_code"], "fixture_ids": row["fixture_ids"],
                "actual_points": row["target_points"], "predicted_points": pred,
                "predicted_variance": var, "nll": loss,
            })
    return {
        "validation_season": va_rows[0]["season"],
        "train_samples": len(train_idx), "validation_samples": len(valid_idx),
        "best_epoch": best_epoch, "best_validation_nll": best_loss,
        "mae": float(np.mean(np.abs(np.asarray(predictions) - va_y))),
        "rmse": float(np.sqrt(np.mean((np.asarray(predictions) - va_y) ** 2))),
        "fold_directory": str(fold_dir),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True,
                        help="Extracted corrected six-season 2pm-dastan-candidate directory; Run 83 artifacts are prohibited")
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-provisional-common-features", action="store_true",
                        help="Explicitly run research-only with 259 common candidate features; not production/admission")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--patience", type=int, default=4)
    parser.add_argument("--min-delta", type=float, default=1e-4)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--d-model", type=int, default=128)
    parser.add_argument("--heads", type=int, default=8)
    parser.add_argument("--feedforward", type=int, default=512)
    parser.add_argument("--dropout", type=float, default=0.22)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=20261127)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()
    if not args.allow_provisional_common_features:
        raise SystemExit("Feature source-vintage admission is pending. Pass --allow-provisional-common-features for an explicitly research-only experiment.")
    if args.epochs <= 0 or args.patience <= 0 or args.batch_size <= 0:
        raise SystemExit("epochs, patience and batch-size must be positive")
    seed_everything(args.seed)
    samples, feature_order = load_grouped_dataset(args.artifact_root, args.schema, args.manifest)
    manifest = json.loads(args.manifest.read_text())
    held_features = sorted({
        name
        for policy in manifest.get("source_vintage_policies", {}).values()
        if policy.get("status") == "HOLD" and policy.get("mask_action") == "FORCE_UNOBSERVED"
        for name in policy.get("feature_order", [])
    })
    seasons = np.asarray([s[3]["season"] for s in samples])
    results = []
    for validation_season in VALIDATION_SEASONS:
        train_idx = np.flatnonzero(np.isin(seasons, [s for s in SEASONS if s < validation_season]))
        valid_idx = np.flatnonzero(seasons == validation_season)
        if not len(train_idx) or not len(valid_idx):
            raise ValueError(f"Empty chronological fold for {validation_season}")
        result = run_fold(samples, feature_order, train_idx, valid_idx, args, args.output / validation_season)
        results.append(result)
        print(json.dumps(result, sort_keys=True), flush=True)
    summary = {
        "status": "EXPERIMENTAL_STAGE_A_OOF_COMPLETE",
        "admission_status": "NOT_ADMITTED",
        "production_eligible": False,
        "feature_policy": "259 common candidate features; manifest HOLD policies are enforced as unobserved at load time; remaining common features are provisional and source-vintage unresolved",
        "source_vintage_hold": {
            "forced_unobserved_feature_count": len(held_features),
            "forced_unobserved_feature_names": held_features,
            "enforcement": "applied by the training loader even when a stored tensor sidecar incorrectly marks a HOLD feature observed",
        },
        "excluded": {"2025-26": "reserved for separate scoring-regime Stage-B adaptation", "2026-27": "sealed OOT"},
        "folds": results,
        "seed": args.seed,
        "device": args.device,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
