"""Prepare candidate 2PM tensors with Dastan's documented residual-NaN policy.

The raw candidate is audited before imputation. Existing -1 snapshot-missing sentinels
are preserved; only residual NaN values are converted to 0.0, matching the pinned
Dastan model's feature-matrix preprocessing. This creates candidate tensors only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from build_2pm_dastan_sequence_dataset import (
    build_sequence_shards,
    load_schema,
    validate_input,
)


def prepare_candidate_tensors(
    input_path: Path,
    schema_path: Path,
    output_dir: Path,
    report_path: Path,
    *,
    shard_size: int = 10000,
    require_label: bool = True,
) -> dict[str, Any]:
    features, feature_hash = load_schema(schema_path)
    frame = pd.read_parquet(input_path)
    missing_columns = sorted(set(features) - set(frame.columns))
    if missing_columns:
        raise ValueError(f"Candidate frame is missing features: {missing_columns[:20]}")

    numeric = frame[features].apply(pd.to_numeric, errors="coerce")
    values = numeric.to_numpy(dtype=np.float64)
    infinite_count = int(np.isinf(values).sum())
    if infinite_count:
        raise ValueError(f"Candidate feature matrix contains {infinite_count} infinite values")

    nan_by_feature = {
        column: int(numeric[column].isna().sum())
        for column in features
        if numeric[column].isna().any()
    }
    residual_nan_count = int(numeric.isna().sum().sum())
    sentinel_count = int(numeric.eq(-1.0).sum().sum())
    genuine_zero_count = int(numeric.eq(0.0).sum().sum())

    prepared = frame.copy()
    prepared.loc[:, features] = numeric.fillna(0.0)
    if int(prepared[features].eq(-1.0).sum().sum()) != sentinel_count:
        raise RuntimeError("Residual-NaN imputation unexpectedly changed -1 sentinels")
    prepared = validate_input(prepared, features, fixture_column="fixture")

    sequence_report = build_sequence_shards(
        prepared,
        features,
        output_dir,
        shard_size=shard_size,
        require_label=require_label,
    )
    report = {
        "status": "CANDIDATE_TENSOR_PREPARATION_COMPLETE",
        "admission_status": "NOT_ADMITTED",
        "input_path_name": input_path.name,
        "feature_count": len(features),
        "feature_order_sha256": feature_hash,
        "raw_nonfinite_values": residual_nan_count + infinite_count,
        "raw_infinite_values": infinite_count,
        "residual_nan_values_imputed_to_zero": residual_nan_count,
        "residual_nan_imputation_policy": "0.0, matching pinned Dastan model.py feature-matrix fillna(0.0)",
        "raw_nan_counts_by_feature": nan_by_feature,
        "preserved_minus_one_snapshot_sentinels": sentinel_count,
        "raw_genuine_zero_values": genuine_zero_count,
        "tensor_output_dir": str(output_dir),
        "sequence_report": sequence_report,
        "limitations": [
            "The raw candidate frame is not modified; only the in-memory tensor preparation copy is imputed.",
            "Structural pre-2025/26 defensive-stat absence remains visible in the raw per-feature audit and is not admitted as observed zero.",
            "The 0.0 fill is a documented Dastan preprocessing adaptation, not evidence that every feature is historically available.",
            "No model training or forecast evaluation is performed.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=Path(__file__).parents[1] / "config" / "2pm_dastan_286_schema.json")
    parser.add_argument("--tensor-out-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--shard-size", type=int, default=10000)
    parser.add_argument("--allow-unlabelled", action="store_true")
    args = parser.parse_args()
    report = prepare_candidate_tensors(
        args.input,
        args.schema,
        args.tensor_out_dir,
        args.report,
        shard_size=args.shard_size,
        require_label=not args.allow_unlabelled,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
