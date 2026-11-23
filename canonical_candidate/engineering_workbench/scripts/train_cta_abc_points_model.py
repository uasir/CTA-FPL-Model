#!/usr/bin/env python3
"""Package the evaluated ABC + conventional-FPL Ridge candidate as a reusable points model.

This is a research candidate, not a production promotion. It preserves the
existing ABC A/B/C feature contract and predicts observed FPL total points.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from cta_four_layer_pipeline import LAYER_FEATURES
from train_fpl_exploratory_ridge import fit_ridge

BASELINE_FEATURES = (
    "fpl_total_points_prior_3_avg",
    "fpl_total_points_prior_5_avg",
    "fpl_minutes_prior_3_avg",
    "fpl_minutes_prior_5_avg",
)
ABC_FEATURES = tuple(
    f"abc_{name}" for names in LAYER_FEATURES.values() for name in names
)
FEATURE_CANDIDATES = BASELINE_FEATURES + ABC_FEATURES
MODEL_VERSION = "abc-points-ridge-v1"


def number(value):
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def truth(value):
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def available_features(rows, candidates):
    return [
        name for name in candidates
        if any(number(row.get(name)) is not None for row in rows)
    ]


def training_rows(rows):
    eligible = [
        row for row in rows
        if truth(row.get("research_eligible_for_analysis"))
        and number(row.get("target_fpl_total_points")) is not None
    ]
    if not eligible:
        raise ValueError("No verified research-eligible rows with observed FPL points")
    eligible.sort(key=lambda row: (
        str(row.get("kickoff_time_utc") or ""),
        str(row.get("fpl_element_id") or ""),
        str(row.get("fpl_fixture_id") or row.get("fixture_id") or ""),
    ))
    keys = []
    for row in eligible:
        player = str(row.get("fpl_element_id") or "").strip()
        fixture = str(row.get("fpl_fixture_id") or row.get("fixture_id") or "").strip()
        if not player or not fixture:
            raise ValueError("Training rows require FPL player and fixture identities")
        keys.append((player, fixture))
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate verified player-fixture keys in ABC training frame")
    return eligible


def train_model(rows, source_report, source_path: Path, out_dir: Path,
                ridge_lambda: float = 1.0) -> dict:
    eligible = training_rows(rows)
    features = available_features(eligible, FEATURE_CANDIDATES)
    missing_baseline = [name for name in BASELINE_FEATURES if name not in features]
    if missing_baseline:
        raise ValueError(f"Conventional FPL baseline coverage incomplete: {missing_baseline}")
    if len(eligible) < len(features) + 2:
        raise ValueError("Insufficient eligible player-fixture rows for ABC points training")

    model = fit_ridge(
        eligible,
        target_key="target_fpl_total_points",
        feature_names=features,
        ridge_lambda=ridge_lambda,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / "abc_points_model.json"
    model_payload = {
        "schema_version": "1.0",
        "model_version": MODEL_VERSION,
        "model_family": "Ridge regression with training-median imputation and missingness indicators",
        "target": "observed FPL total points per player-fixture",
        "feature_order": features,
        "model": model,
    }
    model_path.write_text(
        json.dumps(model_payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    report = {
        "status": "CANDIDATE_TRAINED_RESEARCH_ONLY",
        "model_version": MODEL_VERSION,
        "model_family": model_payload["model_family"],
        "target": model_payload["target"],
        "training_rows": len(eligible),
        "unique_players": len({str(row["fpl_element_id"]) for row in eligible}),
        "unique_fixtures": len({
            str(row.get("fpl_fixture_id") or row.get("fixture_id")) for row in eligible
        }),
        "seasons": sorted({str(row.get("season") or "") for row in eligible}),
        "gameweeks": sorted({
            int(float(row["gameweek"])) for row in eligible
            if number(row.get("gameweek")) is not None
        }),
        "feature_count": len(features),
        "feature_order": features,
        "ridge_lambda": ridge_lambda,
        "missing_value_policy": model["missing_value_policy"],
        "training_source": str(source_path),
        "training_source_sha256": sha256(source_path),
        "source_report": source_report,
        "model_path": str(model_path),
        "model_sha256": sha256(model_path),
        "evaluation_status": "SEPARATE_CHRONOLOGICAL_AND_MATCHED_EVALUATION_REQUIRED",
        "point_in_time_status": source_report.get("point_in_time_status", "NOT_VERIFIED"),
        "decision_weight": 0.0,
        "production_eligible": False,
        "promotion_status": "RESEARCH_ONLY_DO_NOT_PROMOTE",
    }
    manifest_path = out_dir / "abc_points_model_manifest.json"
    manifest_path.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return report


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--abc-panel", type=Path, required=True)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--ridge-lambda", type=float, default=1.0)
    args = parser.parse_args()
    report = train_model(
        read_csv(args.abc_panel),
        json.loads(args.source_report.read_text(encoding="utf-8")),
        args.abc_panel,
        args.out_dir,
        args.ridge_lambda,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
