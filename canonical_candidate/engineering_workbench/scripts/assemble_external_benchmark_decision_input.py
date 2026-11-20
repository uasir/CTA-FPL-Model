#!/usr/bin/env python3
"""Assemble immutable provider and manager captures into one M3 decision input."""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


class DecisionInputError(ValueError):
    pass


def _parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise DecisionInputError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DecisionInputError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise DecisionInputError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def assemble_decision_input(
    provider_capture: dict[str, Any],
    manager_capture: dict[str, Any],
    *,
    as_of_utc: str | None = None,
) -> dict[str, Any]:
    if not isinstance(provider_capture, dict) or not isinstance(manager_capture, dict):
        raise DecisionInputError("both capture documents must be JSON objects")
    for key in ("provider_snapshot", "player_metadata", "player_metadata_provenance"):
        if key not in provider_capture:
            raise DecisionInputError(f"provider capture missing {key}")
    for key in ("manager_context_capture", "manager_context"):
        if key not in manager_capture:
            raise DecisionInputError(f"manager capture missing {key}")

    provider = provider_capture["provider_snapshot"]
    manager_provenance = manager_capture["manager_context_capture"]
    manager = manager_capture["manager_context"]
    if not isinstance(provider, dict) or not isinstance(manager_provenance, dict) or not isinstance(manager, dict):
        raise DecisionInputError("capture sections must be JSON objects")

    provider_gw = provider.get("target_gameweek")
    manager_gw = manager_provenance.get("gameweek")
    if provider_gw != manager_gw:
        raise DecisionInputError(f"provider GW{provider_gw} does not match manager GW{manager_gw}")
    if manager_provenance.get("identity_verified") is not True:
        raise DecisionInputError("manager squad identity was not verified")
    if manager_provenance.get("row_count") != 15:
        raise DecisionInputError("manager capture provenance must report exactly 15 rows")
    manager_hash = manager_provenance.get("raw_sha256")
    if (
        not isinstance(manager_hash, str) or len(manager_hash) != 64
        or any(char not in "0123456789abcdef" for char in manager_hash.lower())
    ):
        raise DecisionInputError("manager capture raw_sha256 must be a 64-character SHA-256")
    raw_b64 = manager_provenance.get("raw_response_base64")
    if not isinstance(raw_b64, str) or not raw_b64:
        raise DecisionInputError("manager capture raw_response_base64 is missing")
    try:
        raw_manager = base64.b64decode(raw_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DecisionInputError("manager capture raw_response_base64 is invalid") from exc
    if hashlib.sha256(raw_manager).hexdigest() != manager_hash.lower():
        raise DecisionInputError("manager capture raw response SHA-256 mismatch")
    squad = manager.get("squad_snapshot")
    if not isinstance(squad, list) or len(squad) != 15:
        raise DecisionInputError("manager squad snapshot must contain exactly 15 players")
    ids = [row.get("fpl_element_id") for row in squad if isinstance(row, dict)]
    if len(ids) != 15 or len(set(ids)) != 15:
        raise DecisionInputError("manager squad must contain 15 unique FPL element IDs")

    provider_ids = {
        row.get("fpl_element_id") for row in provider_capture["player_metadata"]
        if isinstance(row, dict)
    }
    missing = sorted(set(ids) - provider_ids)
    if missing:
        raise DecisionInputError(f"manager squad IDs missing from FPL metadata: {missing}")
    enriched_squad = []
    for row in squad:
        enriched = dict(row)
        purchase_price = enriched.get("purchase_price")
        if (
            isinstance(purchase_price, bool)
            or not isinstance(purchase_price, (int, float))
            or purchase_price <= 0
        ):
            raise DecisionInputError(
                f"manager purchase_price is missing or invalid for FPL ID {enriched['fpl_element_id']}"
            )
        enriched_squad.append(enriched)

    captured_at = _parse_utc(manager_provenance.get("captured_at_utc"), "manager capture timestamp")
    deadline = _parse_utc(provider.get("timing", {}).get("deadline_utc"), "FPL deadline")
    provider_capture_at = _parse_utc(provider.get("timing", {}).get("captured_at_utc"), "provider capture timestamp")
    as_of = _parse_utc(as_of_utc or datetime.now(timezone.utc).isoformat(), "as_of_utc")
    if captured_at > as_of or provider_capture_at > as_of:
        raise DecisionInputError("as_of_utc cannot precede either capture")
    if captured_at >= deadline or provider_capture_at >= deadline or as_of >= deadline:
        raise DecisionInputError("both captures and decision as_of_utc must be strictly before deadline")

    metadata_provenance = provider_capture["player_metadata_provenance"]
    if metadata_provenance.get("row_count") != len(provider_capture["player_metadata"]):
        raise DecisionInputError("FPL metadata provenance row_count mismatch")

    required_manager = ("bank", "free_transfers", "personal_risk_profile", "formation")
    missing_manager = [key for key in required_manager if key not in manager]
    if missing_manager:
        raise DecisionInputError("manager context missing: " + ", ".join(missing_manager))

    return {
        "provider_snapshot": provider,
        "player_metadata": provider_capture["player_metadata"],
        "player_metadata_provenance": metadata_provenance,
        "manager_context": {
            "squad_snapshot": enriched_squad,
            "bank": manager["bank"],
            "free_transfers": manager["free_transfers"],
            "personal_risk_profile": manager["personal_risk_profile"],
            "formation": manager["formation"],
            **({"purchase_price_source": manager["purchase_price_source"]}
               if "purchase_price_source" in manager else {}),
        },
        "manager_context_provenance": manager_provenance,
        "as_of_utc": as_of.isoformat().replace("+00:00", "Z"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-capture", type=Path, required=True)
    parser.add_argument("--manager-capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of-utc")
    args = parser.parse_args()
    provider = json.loads(args.provider_capture.read_text(encoding="utf-8"))
    manager = json.loads(args.manager_capture.read_text(encoding="utf-8"))
    result = assemble_decision_input(provider, manager, as_of_utc=args.as_of_utc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "target_gameweek": result["provider_snapshot"]["target_gameweek"],
        "provider_rows": len(result["provider_snapshot"]["records"]),
        "metadata_rows": len(result["player_metadata"]),
        "manager_players": len(result["manager_context"]["squad_snapshot"]),
        "free_transfers": result["manager_context"]["free_transfers"],
        "as_of_utc": result["as_of_utc"],
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
