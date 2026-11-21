#!/usr/bin/env python3
"""Capture the public FPL Cat next-GW xP feed with matching FPL metadata.

The raw provider and bootstrap responses are hashed independently. The script
does not backdate capture time or treat a missing provider computed_at as
deadline-eligible.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

FPL_CAT_URL = "https://fplcat.com/api/v1/projections"
FPL_BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"


class CaptureError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise CaptureError(f"{field} is missing or invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CaptureError(f"{field} is not ISO-8601") from exc
    if parsed.tzinfo is None:
        raise CaptureError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)


def _fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "CTA-FPL-Model/1.0 (benchmark research)"})
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise CaptureError(f"GET {url} returned HTTP {response.status}")
        return response.read()


def capture_fpl_cat_snapshot(
    *,
    season: str,
    fetch_bytes: Callable[[str], bytes] = _fetch,
    clock: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    provider_raw = fetch_bytes(FPL_CAT_URL)
    provider_captured_at = clock()
    bootstrap_raw = fetch_bytes(FPL_BOOTSTRAP_URL)
    bootstrap_captured_at = clock()

    try:
        provider_data = json.loads(provider_raw)
        bootstrap = json.loads(bootstrap_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError("provider or FPL bootstrap response is not valid JSON") from exc

    if not isinstance(provider_data, dict) or not isinstance(provider_data.get("players"), list):
        raise CaptureError("FPL Cat response must contain a players array")
    if not isinstance(bootstrap, dict) or not isinstance(bootstrap.get("elements"), list):
        raise CaptureError("FPL bootstrap response must contain an elements array")

    gw = provider_data.get("gameweek")
    if isinstance(gw, bool) or not isinstance(gw, int) or gw < 1:
        raise CaptureError("FPL Cat gameweek must be a positive integer")
    provider_deadline = _parse_utc(provider_data.get("deadline"), "FPL Cat deadline")
    generated_raw = provider_data.get("computed_at")
    generated = (
        _parse_utc(generated_raw, "FPL Cat computed_at")
        if generated_raw is not None and generated_raw != ""
        else None
    )
    provider_captured = _parse_utc(provider_captured_at, "provider capture time")
    bootstrap_captured = _parse_utc(bootstrap_captured_at, "bootstrap capture time")
    if generated is not None and generated > provider_captured:
        raise CaptureError("FPL Cat computed_at is later than retrieval time")
    if provider_captured >= provider_deadline:
        raise CaptureError("FPL Cat snapshot was retrieved at or after its deadline")
    if bootstrap_captured >= provider_deadline:
        raise CaptureError("FPL bootstrap metadata was retrieved at or after its deadline")

    events = bootstrap.get("events", [])
    matching_events = [event for event in events if event.get("id") == gw]
    if len(matching_events) != 1:
        raise CaptureError(f"FPL bootstrap does not contain exactly one event for GW{gw}")
    bootstrap_deadline = _parse_utc(matching_events[0].get("deadline_time"), "FPL bootstrap deadline")
    if bootstrap_deadline != provider_deadline:
        raise CaptureError("FPL Cat deadline does not match the official FPL bootstrap deadline")

    element_types = {row["id"]: row["singular_name_short"] for row in bootstrap.get("element_types", [])}
    metadata_by_id = {}
    for element in bootstrap["elements"]:
        element_id = element.get("id")
        position = element_types.get(element.get("element_type"))
        if isinstance(element_id, int) and position:
            metadata_by_id[element_id] = {
                "fpl_element_id": element_id,
                "price": element.get("now_cost", 0) / 10,
                "position": position,
                "team_id": element.get("team"),
            }

    records = []
    metadata = []
    seen = set()
    for index, player in enumerate(provider_data["players"]):
        if not isinstance(player, dict):
            raise CaptureError(f"FPL Cat players[{index}] is not an object")
        element_id = player.get("id")
        xp = player.get("xp")
        expected_minutes = player.get("expected_minutes")
        if isinstance(element_id, bool) or not isinstance(element_id, int) or element_id < 1:
            raise CaptureError(f"FPL Cat players[{index}].id is invalid")
        if element_id in seen:
            raise CaptureError(f"FPL Cat returned duplicate player ID {element_id}")
        seen.add(element_id)
        if isinstance(xp, bool) or not isinstance(xp, (int, float)):
            raise CaptureError(f"FPL Cat player {element_id} has invalid xp")
        if isinstance(expected_minutes, bool) or not isinstance(expected_minutes, (int, float)):
            raise CaptureError(f"FPL Cat player {element_id} has no usable expected_minutes")
        if element_id not in metadata_by_id:
            raise CaptureError(f"FPL Cat player {element_id} is absent from FPL bootstrap")
        records.append({
            "fpl_element_id": element_id,
            "expected_points": xp,
            "expected_minutes": expected_minutes,
        })
        metadata.append(metadata_by_id[element_id])

    provider_hash = hashlib.sha256(provider_raw).hexdigest()
    bootstrap_hash = hashlib.sha256(bootstrap_raw).hexdigest()
    capture_token = provider_captured.strftime("%Y%m%dT%H%M%S%fZ")
    return {
        "provider_snapshot": {
            "snapshot_id": f"fplcat-gw{gw}-{capture_token}",
            "season": season,
            "target_gameweek": gw,
            "provider": {
                "name": "FPL Cat",
                "product": "published xP",
                "variant": "public next-gameweek JSON API",
                "version": "api/v1",
            },
            "timing": {
                "generated_at_utc": (
                    generated.isoformat().replace("+00:00", "Z") if generated else None
                ),
                "captured_at_utc": provider_captured.isoformat().replace("+00:00", "Z"),
                "deadline_utc": provider_deadline.isoformat().replace("+00:00", "Z"),
            },
            "source": {
                "url": FPL_CAT_URL,
                "raw_snapshot_id": f"sha256:{provider_hash}",
                "raw_sha256": provider_hash,
            },
            "grain": "player_gameweek",
            "records": records,
            "coverage": {
                "row_count": len(records),
                "expected_player_universe": len(bootstrap["elements"]),
                "identity_mapped_count": len(records),
                "identity_resolution_status": "VERIFIED",
                "identity_resolution_method": "PROVIDER_PLAYER_ID_EQUALS_OFFICIAL_FPL_ELEMENT_ID",
            },
        },
        "player_metadata": metadata,
        "raw_archives": {
            "provider_response_base64": base64.b64encode(provider_raw).decode("ascii"),
            "fpl_bootstrap_response_base64": base64.b64encode(bootstrap_raw).decode("ascii"),
        },
        "player_metadata_provenance": {
            "source_url": FPL_BOOTSTRAP_URL,
            "raw_snapshot_id": f"sha256:{bootstrap_hash}",
            "raw_sha256": bootstrap_hash,
            "captured_at_utc": bootstrap_captured.isoformat().replace("+00:00", "Z"),
            "row_count": len(metadata),
        },
        "capture_status": {
            "provider_capture_before_deadline": True,
            "provider_generated_before_capture": generated is not None,
            "provider_generation_time_status": (
                "VERIFIED" if generated is not None else "NOT_DISCLOSED_DIAGNOSTIC_ONLY"
            ),
            "bootstrap_capture_at_utc": bootstrap_captured.isoformat().replace("+00:00", "Z"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", required=True, help="FPL season label, e.g. 2026-27")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = capture_fpl_cat_snapshot(season=args.season)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "snapshot_id": result["provider_snapshot"]["snapshot_id"],
        "target_gameweek": result["provider_snapshot"]["target_gameweek"],
        "provider_rows": len(result["provider_snapshot"]["records"]),
        "metadata_rows": len(result["player_metadata"]),
        "provider_sha256": result["provider_snapshot"]["source"]["raw_sha256"],
        "bootstrap_sha256": result["player_metadata_provenance"]["raw_sha256"],
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
