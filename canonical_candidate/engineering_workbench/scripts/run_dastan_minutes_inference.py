#!/usr/bin/env python3
"""Run only Dastan's released position-specific p60 heads and minutes calibration.

CTA adopts Dastan as a minutes component only. This script never loads or calls
Dastan's expected-points heads. The 286 ordered inputs and the exact p60/calibration
artifacts are hash-checked before inference.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import xgboost as xgb

POSITIONS = ("GKP", "DEF", "MID", "FWD")
IDENTITY = ("season", "gameweek", "fpl_code", "fpl_element_id", "fixture_id", "position")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_artifacts(model_dir: Path, manifest: dict) -> dict:
    files = manifest.get("files", {})
    required = ["feature_cols.json", "minutes_calibration.json"] + [
        f"p60_{position}.json" for position in POSITIONS
    ]
    checked = {}
    for name in required:
        entry = files.get(name)
        path = model_dir / name
        if not isinstance(entry, dict) or not path.is_file():
            raise ValueError(f"required Dastan minutes artifact missing: {name}")
        actual_size = path.stat().st_size
        actual_hash = sha256(path)
        if actual_size != int(entry.get("bytes", -1)) or actual_hash != entry.get("sha256"):
            raise ValueError(f"Dastan artifact integrity mismatch: {name}")
        checked[name] = {"bytes": actual_size, "sha256": actual_hash}
    if manifest.get("contract", {}).get("features") != 286:
        raise ValueError("Dastan artifact manifest does not declare 286 features")
    return checked


def apply_minutes_curve(p60: np.ndarray, curve: dict) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(curve["p60"], dtype=float)
    e_minutes = np.asarray(curve["e_minutes"], dtype=float)
    p_any_curve = np.asarray(curve["p_any"], dtype=float)
    if not (len(x) == len(e_minutes) == len(p_any_curve) and len(x) >= 2):
        raise ValueError("invalid Dastan minutes calibration curve")
    if not (np.isfinite(x).all() and np.isfinite(e_minutes).all() and np.isfinite(p_any_curve).all()):
        raise ValueError("non-finite calibration values")
    if np.any(np.diff(x) < 0) or np.any(np.diff(e_minutes) < -1e-9) or np.any(np.diff(p_any_curve) < -1e-9):
        raise ValueError("Dastan minutes calibration curve is not monotonic")
    minutes = np.clip(np.maximum(np.interp(p60, x, e_minutes), 60.0 * p60), 0.0, 90.0)
    p_any = np.clip(np.maximum.reduce([np.interp(p60, x, p_any_curve), p60, minutes / 90.0]), 0.0, 1.0)
    return minutes, p_any


def predict_rows(rows: list[dict], schema: dict, calibration: dict, predictors: dict) -> list[dict]:
    features = schema.get("feature_order")
    if not isinstance(features, list) or len(features) != 286 or len(set(features)) != 286:
        raise ValueError("invalid ordered 286-feature schema")
    required = set(features) | set(IDENTITY)
    if not rows:
        raise ValueError("feature input is empty")
    missing = sorted(required - set(rows[0]))
    if missing:
        raise ValueError(f"feature input missing columns: {missing[:20]}")
    seen = set()
    result = []
    for pos in POSITIONS:
        group = [row for row in rows if str(row["position"]).strip() == pos]
        if not group:
            continue
        matrix = np.empty((len(group), len(features)), dtype=np.float32)
        for i, row in enumerate(group):
            key = tuple(str(row.get(field, "")).strip() for field in IDENTITY[:-1]) + (pos,)
            if any(not value for value in key):
                raise ValueError(f"row has incomplete identity: {key}")
            if key in seen:
                raise ValueError(f"duplicate player-fixture identity: {key}")
            seen.add(key)
            for j, feature in enumerate(features):
                raw = row.get(feature)
                if raw is None or str(raw).strip() == "":
                    raise ValueError(f"{key}: missing feature {feature}")
                value = float(raw)
                if not math.isfinite(value):
                    raise ValueError(f"{key}: non-finite feature {feature}")
                matrix[i, j] = value
        probabilities = np.asarray(predictors[pos](matrix), dtype=float).reshape(-1)
        if len(probabilities) != len(group) or not np.isfinite(probabilities).all():
            raise ValueError(f"{pos}: p60 predictor returned invalid shape/values")
        if np.any((probabilities < 0.0) | (probabilities > 1.0)):
            raise ValueError(f"{pos}: p60 outside [0,1]")
        curve = calibration.get("curve", {}).get(pos)
        if not isinstance(curve, dict):
            raise ValueError(f"{pos}: minutes calibration curve missing")
        expected_minutes, p_any = apply_minutes_curve(probabilities, curve)
        for i, row in enumerate(group):
            result.append({
                **{field: row[field] for field in IDENTITY},
                "p60": float(probabilities[i]),
                "p_any": float(p_any[i]),
                "expected_minutes": float(expected_minutes[i]),
                "minutes_model": "Dastan 1.1.0 p60-only",
                "points_model_used": False,
            })
    result.sort(key=lambda row: (row["season"], int(row["gameweek"]), int(row["fpl_code"]), int(row["fixture_id"])))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="CSV with 286 ordered feature columns and identity")
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True, help="Dastan models/artifact_manifest.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    checked = verify_artifacts(args.model_dir, manifest)
    features = schema.get("feature_order")
    if features != json.loads((args.model_dir / "feature_cols.json").read_text(encoding="utf-8")):
        raise ValueError("CTA feature order differs from Dastan's packaged feature_cols.json")
    calibration = json.loads((args.model_dir / "minutes_calibration.json").read_text(encoding="utf-8"))
    predictors = {}
    for position in POSITIONS:
        model = xgb.XGBClassifier()
        model.load_model(str(args.model_dir / f"p60_{position}.json"))
        predictors[position] = lambda matrix, model=model: model.predict_proba(matrix)[:, 1]

    with args.input.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    predictions = predict_rows(rows, schema, calibration, predictors)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = [*IDENTITY, "p60", "p_any", "expected_minutes", "minutes_model", "points_model_used"]
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(predictions)
    report = {
        "status": "PASS_DASTAN_P60_ONLY_INFERENCE",
        "rows": len(predictions),
        "positions": {pos: sum(row["position"] == pos for row in predictions) for pos in POSITIONS},
        "feature_count": len(features),
        "model_version": manifest.get("public_version"),
        "production_artifact_source": manifest.get("production_source"),
        "verified_artifacts": checked,
        "scope": "minutes prediction only; no Dastan points heads loaded or called",
        "decision_weight": 0.0,
        "production_eligible": False,
        "eligibility_note": "Pending CTA M2 minutes validation and forecast integration gates",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
