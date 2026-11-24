"""Build deterministic, schema-derived baseline/enhanced feature-arm manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFENSIVE_PREFIXES = (
    "ar_defensive_contribution_",
    "ar_cbit_",
    "ar_recoveries_",
    "ar_tackles_",
    "ar_dc_hit_rate_",
    "ar_dc_near_rate_",
    "ar_dc_ppg_",
    "ar_opp_dc_allowed_",
    "ar_opp_tackles_allowed_",
)
EXPECTED_SCHEMA_FEATURES = 286
EXPECTED_DEFENSIVE_FEATURES = 27


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_manifest(schema: dict[str, Any], schema_bytes: bytes) -> dict[str, Any]:
    feature_order = schema.get("feature_order")
    if not isinstance(feature_order, list) or not all(isinstance(x, str) for x in feature_order):
        raise ValueError("schema.feature_order must be a list of feature-name strings")
    if len(feature_order) != len(set(feature_order)):
        raise ValueError("schema.feature_order contains duplicate feature names")
    declared_count = schema.get("feature_count")
    if declared_count != EXPECTED_SCHEMA_FEATURES or len(feature_order) != EXPECTED_SCHEMA_FEATURES:
        raise ValueError(
            f"Expected exactly {EXPECTED_SCHEMA_FEATURES} schema features; "
            f"declared={declared_count}, actual={len(feature_order)}"
        )

    defensive = [
        name for name in feature_order
        if any(name.startswith(prefix) for prefix in DEFENSIVE_PREFIXES)
    ]
    if len(defensive) != EXPECTED_DEFENSIVE_FEATURES:
        raise ValueError(
            f"Expected exactly {EXPECTED_DEFENSIVE_FEATURES} defensive features; "
            f"derived={len(defensive)}"
        )
    defensive_set = set(defensive)
    baseline = [name for name in feature_order if name not in defensive_set]
    if len(baseline) != EXPECTED_SCHEMA_FEATURES - EXPECTED_DEFENSIVE_FEATURES:
        raise AssertionError("Baseline feature count does not reconcile")

    feature_order_bytes = json.dumps(
        feature_order, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return {
        "manifest_version": "1.0.0",
        "schema_component": schema.get("component"),
        "schema_upstream_commit": schema.get("upstream_commit"),
        "schema_feature_count": len(feature_order),
        "schema_file_sha256": sha256_bytes(schema_bytes),
        "feature_order_sha256": sha256_bytes(feature_order_bytes),
        "defensive_feature_count": len(defensive),
        "defensive_features_in_schema_order": defensive,
        "arms": {
            "baseline": {
                "feature_count": len(baseline),
                "features_in_schema_order": baseline,
            },
            "defensive_enhanced": {
                "feature_count": len(feature_order),
                "features_in_schema_order": feature_order,
            },
        },
        "comparison_contract": {
            "same_base_schema": True,
            "same_feature_order_for_shared_features": True,
            "baseline_excludes_only_defensive_block": True,
            "sample_intersection_required": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    schema_bytes = args.schema.read_bytes()
    schema = json.loads(schema_bytes)
    manifest = build_manifest(schema, schema_bytes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
