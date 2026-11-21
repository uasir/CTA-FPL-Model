#!/usr/bin/env python3
"""Capture an immutable raw Sideline Quant Gameweek JSON feed.

This first-stage collector deliberately does not normalize forecast rows. The
publisher's complete raw schema is retained for inspection before a parser is
approved, avoiding guessed row keys or silent fixture-to-Gameweek aggregation.
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

SIDELINE_URL = "https://sidelinequant.com/data/gw/{gameweek}/projections.json"
FPL_BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"


class CaptureError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise CaptureError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CaptureError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise CaptureError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "CTA-FPL-Model/1.0 (benchmark research)"})
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise CaptureError(f"GET {url} returned HTTP {response.status}")
        content_type = response.headers.get("Content-Type", "")
        if "json" not in content_type.lower():
            raise CaptureError(f"GET {url} returned non-JSON content type: {content_type}")
        return response.read()


def capture_sideline_quant_raw(
    *,
    gameweek: int,
    season: str,
    fetch: Callable[[str], bytes] = fetch_bytes,
    clock: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    if isinstance(gameweek, bool) or not isinstance(gameweek, int) or gameweek < 1:
        raise CaptureError("gameweek must be a positive integer")
    url = SIDELINE_URL.format(gameweek=gameweek)
    provider_raw = fetch(url)
    provider_captured_at = clock()
    bootstrap_raw = fetch(FPL_BOOTSTRAP_URL)
    bootstrap_captured_at = clock()

    try:
        provider = json.loads(provider_raw)
        bootstrap = json.loads(bootstrap_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError("provider or official FPL response is not valid JSON") from exc
    if not isinstance(provider, dict):
        raise CaptureError("Sideline Quant payload must be a JSON object")
    if not isinstance(bootstrap, dict) or not isinstance(bootstrap.get("events"), list):
        raise CaptureError("official FPL bootstrap must contain an events array")

    if provider.get("gameweek") != gameweek:
        raise CaptureError("Sideline Quant payload Gameweek does not match requested Gameweek")
    generated = parse_utc(provider.get("generated_at"), "Sideline Quant generated_at")
    deadline = parse_utc(provider.get("deadline"), "Sideline Quant deadline")
    captured = parse_utc(provider_captured_at, "provider capture time")
    bootstrap_captured = parse_utc(bootstrap_captured_at, "FPL bootstrap capture time")
    if generated > captured:
        raise CaptureError("Sideline Quant generated_at is later than retrieval time")
    if captured >= deadline:
        raise CaptureError("Sideline Quant snapshot was retrieved at or after its deadline")
    if bootstrap_captured >= deadline:
        raise CaptureError("official FPL metadata was retrieved at or after the deadline")

    events = [event for event in bootstrap["events"] if event.get("id") == gameweek]
    if len(events) != 1:
        raise CaptureError("official FPL bootstrap does not contain exactly one target event")
    official_deadline = parse_utc(events[0].get("deadline_time"), "official FPL deadline")
    if official_deadline != deadline:
        raise CaptureError("Sideline Quant deadline does not match official FPL deadline")

    for field in ("n_players", "n_rows"):
        value = provider.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise CaptureError(f"Sideline Quant {field} must be a positive integer")

    provider_hash = hashlib.sha256(provider_raw).hexdigest()
    bootstrap_hash = hashlib.sha256(bootstrap_raw).hexdigest()
    token = captured.strftime("%Y%m%dT%H%M%S%fZ")
    return {
        "capture_id": f"sidelinequant-gw{gameweek}-{token}",
        "provider": {
            "name": "Sideline Quant",
            "product": "public next-Gameweek projections",
            "variant": "fixture-grain JSON feed",
            "schema_version": provider.get("schema_version"),
            "produced_by": provider.get("produced_by"),
            "licence": provider.get("licence"),
        },
        "season": season,
        "target_gameweek": gameweek,
        "timing": {
            "generated_at_utc": generated.isoformat().replace("+00:00", "Z"),
            "captured_at_utc": captured.isoformat().replace("+00:00", "Z"),
            "deadline_utc": deadline.isoformat().replace("+00:00", "Z"),
            "official_metadata_captured_at_utc": bootstrap_captured.isoformat().replace("+00:00", "Z"),
            "point_in_time_status": "PROVIDER_GENERATED_AND_CAPTURED_BEFORE_DEADLINE",
        },
        "source": {
            "url": url,
            "raw_sha256": provider_hash,
            "raw_snapshot_id": f"sha256:{provider_hash}",
            "content_type": "application/json",
        },
        "coverage": {
            "declared_player_count": provider["n_players"],
            "declared_row_count": provider["n_rows"],
            "grain": "player_fixture",
        },
        "schema_inspection": {
            "top_level_keys": sorted(provider.keys()),
            "row_parser_status": "PENDING_RAW_PAYLOAD_SCHEMA_INSPECTION",
            "normalization_status": "NOT_NORMALIZED",
        },
        "raw_archives": {
            "provider_response_base64": base64.b64encode(provider_raw).decode("ascii"),
            "official_fpl_bootstrap_base64": base64.b64encode(bootstrap_raw).decode("ascii"),
        },
        "official_metadata_provenance": {
            "source_url": FPL_BOOTSTRAP_URL,
            "raw_sha256": bootstrap_hash,
            "raw_snapshot_id": f"sha256:{bootstrap_hash}",
            "captured_at_utc": bootstrap_captured.isoformat().replace("+00:00", "Z"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", required=True)
    parser.add_argument("--gameweek", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = capture_sideline_quant_raw(
        season=args.season,
        gameweek=args.gameweek,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "capture_id": result["capture_id"],
        "gameweek": result["target_gameweek"],
        "declared_players": result["coverage"]["declared_player_count"],
        "declared_rows": result["coverage"]["declared_row_count"],
        "raw_sha256": result["source"]["raw_sha256"],
        "row_parser_status": result["schema_inspection"]["row_parser_status"],
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
