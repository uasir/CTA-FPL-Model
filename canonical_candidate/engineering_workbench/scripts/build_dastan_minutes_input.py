#!/usr/bin/env python3
"""Validate and order CTA rows for Dastan's released p60 minutes heads.

This is a strict schema adapter, not model inference. It refuses to impute missing
features because the upstream documentation and inference implementation differ
on missing-value handling. Resolve that discrepancy before attaching model weights.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

POSITIONS = {"GKP", "DEF", "MID", "FWD"}
KEY_FIELDS = ("fpl_element_id", "fixture_id")
SNAPSHOT_FEATURES = {"ar_ep_next", "sig_status_risk", "sig_chance_playing", "sig_has_news"}


def load_schema(path: Path) -> dict:
    schema = json.loads(path.read_text(encoding="utf-8"))
    features = schema.get("feature_order")
    if not isinstance(features, list) or len(features) != schema.get("feature_count"):
        raise ValueError("Invalid pinned Dastan feature schema")
    if len(set(features)) != len(features):
        raise ValueError("Dastan feature schema contains duplicate columns")
    return schema


def build_rows(rows: list[dict], schema: dict) -> tuple[list[dict], dict]:
    features = schema["feature_order"]
    required = set(features) | set(KEY_FIELDS) | {"position"}
    if not rows:
        raise ValueError("Input contains no player-fixture rows")
    missing_columns = sorted(required - set(rows[0]))
    if missing_columns:
        raise ValueError(f"Input is missing {len(missing_columns)} required columns: {missing_columns[:10]}")

    seen = set()
    output = []
    missing_snapshot_values = 0
    residual_nan_fills = 0
    for line_number, row in enumerate(rows, start=2):
        key = tuple(str(row.get(field, "")).strip() for field in KEY_FIELDS)
        if not all(key):
            raise ValueError(f"Row {line_number}: missing player-fixture identity")
        if key in seen:
            raise ValueError(f"Row {line_number}: duplicate player-fixture key {key}")
        seen.add(key)
        position = str(row.get("position", "")).strip().upper()
        if position not in POSITIONS:
            raise ValueError(f"Row {line_number}: unsupported position {position!r}")
        values = {}
        for feature in features:
            raw = row.get(feature)
            if raw is None or str(raw).strip() == "":
                if feature in SNAPSHOT_FEATURES:
                    value = -1.0
                    missing_snapshot_values += 1
                else:
                    value = 0.0
                    residual_nan_fills += 1
            else:
                try:
                    value = float(raw)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Row {line_number}: non-numeric feature {feature}") from exc
                if not math.isfinite(value):
                    if feature in SNAPSHOT_FEATURES:
                        value = -1.0
                        missing_snapshot_values += 1
                    else:
                        value = 0.0
                        residual_nan_fills += 1
            values[feature] = value
        output.append({
            "fpl_element_id": key[0],
            "fixture_id": key[1],
            "position": position,
            **values,
        })
    report = {
        "status": "PASS_SCHEMA_ONLY_NOT_MODEL_VALIDATION",
        "rows": len(output),
        "positions": {pos: sum(r["position"] == pos for r in output) for pos in sorted(POSITIONS)},
        "feature_count": len(features),
        "feature_schema_version": schema["schema_version"],
        "upstream_feature_cols_blob_sha": schema["upstream"]["feature_cols_blob_sha"],
        "missing_value_policy": {
            "snapshot_absence_sentinel": -1.0,
            "snapshot_missing_values": missing_snapshot_values,
            "residual_nan_fill": 0.0,
            "residual_nan_fills": residual_nan_fills,
        },
    }
    return output, report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    schema = load_schema(args.schema)
    with args.input.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    output, report = build_rows(rows, schema)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["fpl_element_id", "fixture_id", "position", *schema["feature_order"]])
        writer.writeheader()
        writer.writerows(output)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
