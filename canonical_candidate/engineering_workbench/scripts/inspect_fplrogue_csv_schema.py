#!/usr/bin/env python3
"""Inspect FPLRogue raw CSV structure without assigning forecast semantics.

This is deliberately a schema-inspection utility, not a forecast normalizer.
It reports exact headers, row widths, sample values and conservative lexical
type hints. Column-to-field mapping requires separate documented evidence.
"""
from __future__ import annotations

import base64
import csv
import io
from collections import Counter
from typing import Any, Mapping


class FPLRogueSchemaInspectionError(ValueError):
    pass


def _lexical_type(value: str) -> str:
    token = value.strip()
    if not token:
        return "empty"
    try:
        float(token)
    except ValueError:
        return "text"
    return "numeric_lexeme"


def inspect_fplrogue_csv_schema(
    capture: Mapping[str, Any], *, sample_limit: int = 5
) -> dict[str, Any]:
    if isinstance(sample_limit, bool) or not isinstance(sample_limit, int) or sample_limit < 1:
        raise FPLRogueSchemaInspectionError("sample_limit must be a positive integer")
    try:
        encoded = capture["raw_archives"]["csv_base64"]
        raw = base64.b64decode(encoded, validate=True)
        reader = csv.reader(io.StringIO(raw.decode("utf-8-sig")))
        headers = next(reader)
        rows = list(reader)
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, StopIteration, csv.Error) as exc:
        raise FPLRogueSchemaInspectionError("capture does not contain a valid raw FPLRogue CSV") from exc
    if not headers or any(not header.strip() for header in headers):
        raise FPLRogueSchemaInspectionError("CSV contains empty headers")
    if len(set(headers)) != len(headers):
        raise FPLRogueSchemaInspectionError("CSV contains duplicate headers")
    if any(len(row) != len(headers) for row in rows):
        raise FPLRogueSchemaInspectionError("CSV contains ragged rows")

    columns = []
    for index, name in enumerate(headers):
        values = [row[index] for row in rows]
        hints = Counter(_lexical_type(value) for value in values)
        columns.append({
            "index": index,
            "header": name,
            "non_empty_count": sum(bool(value.strip()) for value in values),
            "lexical_type_counts": dict(sorted(hints.items())),
            "sample_values": values[:sample_limit],
            "semantic_mapping": None,
            "mapping_status": "UNMAPPED_PENDING_SOURCE_DOCUMENTATION",
        })
    return {
        "provider": "FPLRogue",
        "capture_id": capture.get("capture_id"),
        "target_gameweek": capture.get("target_gameweek"),
        "csv_sha256": capture.get("source", {}).get("csv_raw_sha256"),
        "row_count": len(rows),
        "column_count": len(headers),
        "columns": columns,
        "normalization_status": "SCHEMA_INSPECTED_MAPPING_NOT_APPROVED",
    }
