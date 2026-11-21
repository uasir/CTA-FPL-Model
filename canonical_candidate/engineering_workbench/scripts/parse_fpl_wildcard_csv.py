#!/usr/bin/env python3
"""Parse a privately obtained FPL Wildcard projection CSV.

This parser performs no network access and does not archive or publish provider
rows. Keep input CSV, metadata and output in private, access-controlled storage.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping

from canonical_provider_forecast_contract import normalize_provider_snapshot


REQUIRED_COLUMNS = {
    "rank", "gameweek", "player", "profile_url", "club", "position",
    "price_m", "xpts", "xmins",
}
OPTIONAL_COLUMNS = {
    "ownership_pct", "fixture", "start_pct", "appearance_pct",
    "sixty_plus_pct", "blank_pct", "haul_pct",
}
PROVIDER = "FPL Wildcard"


class FPLWildcardParseError(ValueError):
    pass


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _number(value: str, field: str, *, minimum: float | None = None,
            maximum: float | None = None, optional: bool = False) -> float | None:
    if value is None or value.strip() == "":
        if optional:
            return None
        raise FPLWildcardParseError(f"{field} is required")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise FPLWildcardParseError(f"{field} must be numeric") from exc
    if not math.isfinite(result):
        raise FPLWildcardParseError(f"{field} must be finite")
    if minimum is not None and result < minimum:
        raise FPLWildcardParseError(f"{field} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise FPLWildcardParseError(f"{field} must be <= {maximum}")
    return result


def parse_fpl_wildcard_csv(csv_text: str, metadata: Mapping[str, Any],
                           bootstrap: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize documented player-Gameweek rows using exact name+club identity."""
    try:
        reader = csv.DictReader(io.StringIO(csv_text))
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)):
            raise FPLWildcardParseError("CSV contains duplicate headers")
        missing = REQUIRED_COLUMNS - set(headers)
        unknown = set(headers) - REQUIRED_COLUMNS - OPTIONAL_COLUMNS
        if missing:
            raise FPLWildcardParseError(f"CSV missing required columns: {sorted(missing)}")
        if unknown:
            raise FPLWildcardParseError(f"CSV contains undocumented columns: {sorted(unknown)}")
        rows = list(reader)
    except csv.Error as exc:
        raise FPLWildcardParseError("invalid CSV payload") from exc

    gameweek = metadata.get("target_gameweek")
    if isinstance(gameweek, bool) or not isinstance(gameweek, int) or gameweek < 1:
        raise FPLWildcardParseError("metadata target_gameweek must be a positive integer")
    if not rows:
        raise FPLWildcardParseError("CSV contains no player rows")

    teams = {
        item.get("id"): _key(item.get("short_name"))
        for item in bootstrap.get("teams", [])
        if isinstance(item, dict) and isinstance(item.get("id"), int)
    }
    identity: dict[tuple[str, str], set[int]] = {}
    for item in bootstrap.get("elements", []):
        if not isinstance(item, dict) or not isinstance(item.get("id"), int):
            continue
        team_key = teams.get(item.get("team"))
        if team_key:
            identity.setdefault((_key(item.get("web_name")), team_key), set()).add(item["id"])
            identity.setdefault((_key(item.get("first_name") + " " + item.get("second_name")), team_key), set()).add(item["id"])

    seen: set[int] = set()
    normalized, native = [], []
    for index, row in enumerate(rows, start=2):
        if row.get("gameweek", "").strip() != str(gameweek):
            raise FPLWildcardParseError(f"row {index} Gameweek differs from requested Gameweek")
        club_key = _key(row.get("club"))
        player_key = _key(row.get("player"))
        matches = identity.get((player_key, club_key), set())
        if len(matches) != 1:
            raise FPLWildcardParseError(f"row {index} player+club identity is not uniquely mapped")
        element_id = next(iter(matches))
        if element_id in seen:
            raise FPLWildcardParseError(f"duplicate player-Gameweek key: {element_id}")
        seen.add(element_id)

        record = {
            "fpl_element_id": element_id,
            "expected_points": _number(row.get("xpts", ""), f"row {index} xpts"),
            "expected_minutes": _number(row.get("xmins", ""), f"row {index} xmins", minimum=0),
        }
        probability_fields = {
            "start_probability": "start_pct",
            "appearance_probability": "appearance_pct",
            "sixty_plus_probability": "sixty_plus_pct",
            "blank_probability": "blank_pct",
            "haul_probability": "haul_pct",
        }
        for target, source in probability_fields.items():
            if source in headers:
                value = _number(row.get(source, ""), f"row {index} {source}",
                                minimum=0, maximum=100, optional=True)
                if value is not None:
                    record[target] = value / 100.0
        normalized.append(record)
        native.append(dict(row))

    raw_bytes = csv_text.encode("utf-8")
    digest = hashlib.sha256(raw_bytes).hexdigest()
    if metadata.get("raw_sha256") and metadata["raw_sha256"] != digest:
        raise FPLWildcardParseError("CSV SHA-256 does not match capture metadata")

    snapshot = {
        "snapshot_id": metadata["capture_id"],
        "season": metadata["season"],
        "target_gameweek": gameweek,
        "provider": {
            "name": PROVIDER,
            "product": "projection_csv",
            "variant": "provider_native_xpts",
            "version": metadata.get("model_version"),
        },
        "timing": {
            "generated_at_utc": None,
            "captured_at_utc": metadata["captured_at_utc"],
            "deadline_utc": metadata["deadline_utc"],
        },
        "source": {
            "url": metadata["source_url"],
            "raw_snapshot_id": metadata["capture_id"],
            "raw_sha256": digest,
        },
        "grain": "player_gameweek",
        "records": normalized,
        "coverage": {
            "row_count": len(normalized),
            "expected_player_universe": len(bootstrap.get("elements", [])),
            "identity_mapped_count": len(normalized),
            "identity_resolution_status": "UNVERIFIED_NAME_CLUB_MATCH",
        },
    }
    canonical = normalize_provider_snapshot(snapshot)
    return {
        "canonical_snapshot": canonical,
        "provider_native_rows": native,
        "source_metadata": {
            "projection_updated_at_utc": metadata.get("projection_updated_at_utc"),
            "model_version": metadata.get("model_version"),
            "csv_headers": headers,
            "csv_row_count": len(rows),
            "raw_sha256": digest,
            "storage_policy": "PRIVATE_RESTRICTED_NO_REDISTRIBUTION",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--bootstrap", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = parse_fpl_wildcard_csv(
        args.csv.read_text(encoding="utf-8-sig"),
        json.loads(args.metadata.read_text(encoding="utf-8")),
        json.loads(args.bootstrap.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "provider": PROVIDER,
        "gameweek": result["canonical_snapshot"]["target_gameweek"],
        "rows": len(result["canonical_snapshot"]["records"]),
        "decision_eligible": result["canonical_snapshot"]["decision_eligible"],
        "eligibility_reason": result["canonical_snapshot"].get("eligibility_reason"),
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
