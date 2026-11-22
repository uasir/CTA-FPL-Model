#!/usr/bin/env python3
"""Train CTA-owned position-specific FPL points models on historical 286-feature rows.

This is a candidate points model. It does not load Dastan points heads. The
historical frame is sourced from Dastan's verified data release, but CTA trains
against the observed FPL points target (not any Dastan prediction). M2 evaluation
remains deferred, so saved weights are explicitly non-production and have zero
recommendation decision weight until the separate validation gate is cleared.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from feature_availability import (
    FPL_NATIVE_MODE, mask_unavailable_features, unavailable_feature_names,
)

POSITIONS = ("GKP", "DEF", "MID", "FWD")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def with_training_target(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert observed FPL points into an appearance-conditional points/90 target.

    Dastan's published training frame names the observed FPL label `target_points`
    and its playing-time field `minutes`. CTA consumes those observed labels only;
    it never consumes Dastan's predicted points or model outputs.
    """
    if "target_points_per_90" in frame.columns:
        return frame
    points_column = next(
        (name for name in ("target_points", "total_points", "fpl_points") if name in frame.columns),
        None,
    )
    minutes_column = next(
        (name for name in ("minutes", "minutes_played") if name in frame.columns),
        None,
    )
    if points_column is None or minutes_column is None:
        raise ValueError(
            "Training frame requires target_points_per_90 or an observed FPL "
            "points field (target_points/total_points/fpl_points) plus "
            f"minutes; available candidates missing: "
            f"points={points_column is None}, minutes={minutes_column is None}"
        )
    out = frame.copy()
    points = pd.to_numeric(out[points_column], errors="coerce")
    minutes = pd.to_numeric(out[minutes_column], errors="coerce")
    # FPL awards one appearance point for 1-59 minutes and two for 60+.
    # Remove those points because the forecast layer adds expected appearance
    # points from Dastan's p_any and p60 probabilities.
    appearance_points = np.where(
        minutes.ge(60), 2.0, np.where(minutes.gt(0), 1.0, 0.0),
    )
    non_appearance_points = points - appearance_points
    eligible = minutes.ge(30) & non_appearance_points.notna()
    out["target_points_per_90"] = np.nan
    out.loc[eligible, "target_points_per_90"] = (
        non_appearance_points.loc[eligible] * 90.0 / minutes.loc[eligible]
    )
    return out


def train_models(frame: pd.DataFrame, features: list[str], output_dir: Path,
                 source_path: Path, feature_source_mode: str = FPL_NATIVE_MODE) -> dict:
    frame = with_training_target(frame)
    required = set(features) | {"season", "gameweek", "fixture", "fpl_code", "position", "target_points_per_90"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Training frame missing required fields: {missing[:20]}")
    if len(features) != 286 or len(set(features)) != 286:
        raise ValueError("CTA points model requires the pinned ordered 286-feature schema")
    if frame.duplicated(["season", "gameweek", "fixture", "fpl_code"]).any():
        raise ValueError("Training frame has duplicate player-fixture keys")
    output_dir.mkdir(parents=True, exist_ok=True)
    masked_features = unavailable_feature_names(features, feature_source_mode)
    report_positions = {}
    for position in POSITIONS:
        rows = frame[frame["position"].astype(str).eq(position)].copy()
        rows["target_points_per_90"] = pd.to_numeric(rows["target_points_per_90"], errors="coerce")
        rows = rows[rows["target_points_per_90"].notna()]
        if len(rows) < 500:
            raise ValueError(f"{position}: insufficient training rows ({len(rows)})")
        train_features, applied_mask = mask_unavailable_features(rows[features], features, feature_source_mode)
        if applied_mask != masked_features:
            raise RuntimeError("Unavailable feature mask changed between position partitions")
        X = train_features.apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy(dtype=np.float32)
        y = rows["target_points_per_90"].to_numpy(dtype=np.float32)
        if not np.isfinite(X).all() or not np.isfinite(y).all():
            raise ValueError(f"{position}: non-finite training matrix or target")
        model = xgb.XGBRegressor(
            objective="reg:squarederror",
            eval_metric="rmse",
            n_estimators=700,
            max_depth=4,
            learning_rate=0.025,
            min_child_weight=10,
            subsample=0.85,
            colsample_bytree=0.85,
            reg_alpha=0.1,
            reg_lambda=10.0,
            tree_method="hist",
            n_jobs=4,
            random_state=42,
        )
        model.fit(X, y, verbose=False)
        path = output_dir / f"cta_points_{position}.json"
        model.save_model(str(path))
        report_positions[position] = {
            "training_rows": len(rows),
            "seasons": sorted(rows["season"].astype(str).unique().tolist()),
            "gameweeks": sorted(pd.to_numeric(rows["gameweek"], errors="coerce").dropna().astype(int).unique().tolist()),
            "target_source_column": next(
                (name for name in ("target_points", "total_points", "fpl_points") if name in frame.columns),
                "target_points_per_90",
            ),
            "target_minutes_column": next(
                (name for name in ("minutes", "minutes_played") if name in frame.columns),
                "minutes",
            ),
            "target_points_basis": "observed FPL points less 1 point for 1-59 minutes or 2 points for 60+ minutes, scaled to 90 minutes; training appearances >=30 minutes",
            "target_mean": float(np.mean(y)),
            "target_std": float(np.std(y)),
            "model_path": str(path),
            "model_sha256": sha256(path),
        }
    report = {
        "status": "CANDIDATE_TRAINED_M2_VALIDATION_PENDING",
        "model_family": "CTA-owned position-specific XGBoost conditional non-appearance points-per-90 regression; multiplied by Dastan expected minutes at scoring",
        "feature_count": len(features),
        "feature_source_mode": feature_source_mode,
        "masked_unavailable_feature_count": len(masked_features),
        "masked_unavailable_features": masked_features,
        "feature_order_sha256": hashlib.sha256("\n".join(features).encode()).hexdigest(),
        "training_source": str(source_path),
        "training_source_sha256": sha256(source_path),
        "training_label_source": "observed historical FPL points in the verified feature frame; no Dastan points predictions or heads",
        "positions": report_positions,
        "validation": {
            "status": "NOT_RUN_M2_DEFERRED",
            "reason": "M2 model evaluation remains deferred until the agreed official Gameweek scores are available",
        },
        "dastan_points_heads_used": False,
        "dastan_role": "historical feature definitions and minutes prediction only; no Dastan points head loaded",
        "decision_weight": 0.0,
        "production_eligible": False,
    }
    report_path = output_dir / "cta_points_model_manifest.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-frame", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--source-report", type=Path, required=True)
    args = parser.parse_args()
    frame = pd.read_parquet(args.training_frame)
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    report = train_models(
        frame, schema["feature_order"], args.model_dir, args.training_frame,
        json.loads(args.source_report.read_text(encoding="utf-8"))["feature_source_mode"],
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
