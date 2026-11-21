#!/usr/bin/env python3
"""Inspect FPL Lucho CSV structure without exposing forecast row values.

The report is schema-only: it records exact headers, lexical type counts and
Gameweek-like header tokens, but never emits player names or sample values.
It does not assign canonical forecast semantics.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import re
from collections import Counter
from typing import Any, Mapping


class FPLLuchoSchemaInspectionError(ValueError):
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


def inspect_fpl_lucho_csv_schema(capture: Mapping[str, Any]) -> dict[str, Any]:
    try:
        provider = capture["provider"]
        encoded = capture["raw_archives"]["csv_base64"]
        raw = base64.b64decode(encoded, validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise FPLLuchoSchemaInspectionError(
            "capture does not contain a valid raw FPL Lucho CSV"
        ) from exc

    if (
        provider.get("name") != "FPL Lucho"
        or provider.get("product") != "forecast_csv"
        or provider.get("variant") != "served_odds_anchored_xp"
    ):
        raise FPLLuchoSchemaInspectionError(
            "capture provider identity does not match the registered served FPL Lucho CSV"
        )

    digest = hashlib.sha256(raw).hexdigest()
    expected_digest = capture.get("source", {}).get("sha256", {}).get("csv")
    if not expected_digest or digest != expected_digest:
        raise FPLLuchoSchemaInspectionError("raw CSV SHA-256 does not match capture metadata")

    try:
        reader = csv.reader(io.StringIO(raw.decode("utf-8-sig")))
        headers = next(reader)
        rows = list(reader)
    except (UnicodeDecodeError, StopIteration, csv.Error) as exc:
        raise FPLLuchoSchemaInspectionError("raw FPL Lucho CSV is empty or invalid") from exc

    normalized = [header.strip() for header in headers]
    if not headers or any(not header for header in normalized):
        raise FPLLuchoSchemaInspectionError("CSV contains empty headers")
    if len(set(normalized)) != len(normalized):
        raise FPLLuchoSchemaInspectionError("CSV contains duplicate headers after whitespace normalization")
    if any(len(row) != len(headers) for row in rows):
        raise FPLLuchoSchemaInspectionError("CSV contains rows with inconsistent column counts")
    if not rows:
        raise FPLLuchoSchemaInspectionError("CSV contains no forecast rows")

    columns = []
    gameweek_tokens: set[int] = set()
    for index, header in enumerate(headers):
        values = [row[index] for row in rows]
        type_counts = Counter(_lexical_type(value) for value in values)
        tokens = [int(value) for value in re.findall(r"(?i)(?:^|\\b)GW\\s*0*(\\d+)\\b", header)]
        gameweek_tokens.update(tokens)
        columns.append({
            "index": index,
            "header": header,
            "non_empty_count": sum(bool(value.strip()) for value in values),
            "lexical_type_counts": dict(sorted(type_counts.items())),
            "gameweek_tokens": tokens,
            "semantic_mapping": None,
            "mapping_status": "UNMAPPED_PENDING_ACTUAL_SCHEMA_AND_SOURCE_DOCUMENTATION",
        })

    return {
        "provider": "FPL Lucho",
        "product": "forecast_csv",
        "variant": "served_odds_anchored_xp",
        "capture_id": capture.get("capture_id"),
        "target_gameweek": capture.get("target_gameweek"),
        "csv_sha256": digest,
        "row_count": len(rows),
        "column_count": len(headers),
        "gameweek_tokens_in_headers": sorted(gameweek_tokens),
        "columns": columns,
        "normalization_status": "SCHEMA_INSPECTED_MAPPING_NOT_APPROVED",
        "privacy": "NO_PLAYER_ROW_VALUES_EMITTED",
    }
