#!/usr/bin/env python3
"""Run the complete imported Dastan xPts model as a separate benchmark.

The CTA-owned points model remains the primary candidate. This script preserves
Dastan's full expected-points output as an independently sourced comparator and
does not feed it into CTA recommendations or model training.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


IDENTITY = [
    "season", "gameweek", "fpl_code", "fpl_element_id", "fixture_id",
    "position", "team_name", "opponent_team_name", "kickoff_time",
]
PREDICTIONS = [
    "xpts", "multibucket", "direct", "p60", "p_any", "expected_minutes",
    "p_band0", "p_band1", "p_band2", "p_band3",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_input(frame: pd.DataFrame, features: list[str]) -> None:
    required = set(IDENTITY + features)
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"feature matrix is missing required columns: {missing[:20]}")
    key = ["season", "gameweek", "fpl_code", "fixture_id"]
    if frame.duplicated(key).any():
        raise ValueError("feature matrix contains duplicate player-fixture keys")
    if frame.empty:
        raise ValueError("feature matrix is empty")
    if not set(frame["position"].astype(str)).issubset({"GKP", "DEF", "MID", "FWD"}):
        raise ValueError("feature matrix contains an unsupported position")
    values = frame[features].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("feature matrix contains missing or non-finite Dastan features")


def validate_predictions(predicted: pd.DataFrame, input_frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(IDENTITY + PREDICTIONS) - set(predicted.columns))
    if missing:
        raise ValueError(f"Dastan predictor omitted required outputs: {missing}")
    if len(predicted) != len(input_frame):
        raise ValueError("Dastan predictor changed the number of fixture rows")
    key = ["season", "gameweek", "fpl_code", "fixture_id"]
    if predicted.duplicated(key).any():
        raise ValueError("Dastan predictions contain duplicate player-fixture keys")
    joined = input_frame[key].merge(predicted[key], on=key, how="outer", indicator=True)
    if not joined["_merge"].eq("both").all():
        raise ValueError("Dastan predictions do not cover the exact CTA fixture population")
    values = predicted[PREDICTIONS].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Dastan prediction outputs contain non-finite values")
    if (predicted["xpts"].astype(float) < 0).any():
        raise ValueError("Dastan expected points contains negative values")
    return predicted[IDENTITY + PREDICTIONS].copy()


def run(input_path: Path, schema_path: Path, dastan_root: Path, model_dir: Path,
        output_path: Path, report_path: Path) -> dict:
    sys.path.insert(0, str(dastan_root))
    from dastan.predictor import Dastan

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    features = schema.get("feature_order")
    if not isinstance(features, list) or len(features) != 286 or len(set(features)) != 286:
        raise ValueError("CTA schema is not the pinned ordered 286-feature contract")
    frame = pd.read_csv(input_path, low_memory=False)
    validate_input(frame, features)

    manifest_path = model_dir / "artifact_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    model = Dastan(model_dir=model_dir)
    if model.features != features:
        raise ValueError("Dastan model feature order differs from CTA feature schema")
    predicted = model.predict_frame(frame, with_parts=True)
    result = validate_predictions(predicted, frame)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False, lineterminator="\n")
    report = {
        "status": "PASS_DASTAN_FULL_MODEL_BENCHMARK",
        "model_version": manifest.get("public_version"),
        "production_source": manifest.get("production_source"),
        "source_commit": "758db9247e8b3a9a870c991064f74d8339d61cd0",
        "model_manifest_sha256": sha256(manifest_path),
        "rows": len(result),
        "feature_count": len(features),
        "target_gameweeks": sorted(pd.to_numeric(result["gameweek"]).astype(int).unique().tolist()),
        "outputs": PREDICTIONS,
        "role": "independent benchmark only; CTA-owned points model remains separate",
        "decision_weight": 0.0,
        "production_eligible": False,
        "input_sha256": sha256(input_path),
        "output_sha256": sha256(output_path),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--dastan-root", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    run(args.input, args.schema, args.dastan_root, args.model_dir, args.output, args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
