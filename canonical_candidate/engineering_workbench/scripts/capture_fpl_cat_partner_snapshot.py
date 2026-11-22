#!/usr/bin/env python3
"""Capture FPL Cat's licensed six-Gameweek player-Gameweek projections.

This adapter preserves the provider's native player_gameweek grain. It never
splits double-Gameweek totals into invented fixture-level predictions.
The partner API key is read only from FPLCAT_PARTNER_API_KEY.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.request import Request, urlopen

FPL_CAT_PARTNER_URL = "https://fplcat.com/api/v1/partner/projections"
FPL_BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
PROVIDER = {
    "name": "FPL Cat",
    "product": "partner_projections",
    "variant": "provider_native_xp",
    "version": "partner-api-v1",
}


class PartnerCaptureError(ValueError):
    """Raised when licensed FPL Cat data is missing or inconsistent."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise PartnerCaptureError(f"{field} is missing or invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PartnerCaptureError(f"{field} is not ISO-8601") from exc
    if parsed.tzinfo is None:
        raise PartnerCaptureError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)


def _fetch(url: str, headers: Mapping[str, str] | None = None) -> bytes:
    request = Request(url, headers={
        "User-Agent": "CTA-FPL-Model/1.0 (licensed forecast research)",
        **dict(headers or {}),
    })
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise PartnerCaptureError(f"GET {url} returned HTTP {response.status}")
        return response.read()


def _finite_nonnegative(value: Any, field: str, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PartnerCaptureError(f"{field} must be numeric" + (" or null" if nullable else ""))
    if value < 0 or not __import__("math").isfinite(float(value)):
        raise PartnerCaptureError(f"{field} must be finite and non-negative")
    return float(value)


def capture_fpl_cat_partner_snapshot(
    *,
    season: str,
    api_key: str | None = None,
    fetch_bytes: Callable[..., bytes] = _fetch,
    clock: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    key = api_key or os.environ.get("FPLCAT_PARTNER_API_KEY")
    if not isinstance(key, str) or not key.strip():
        raise PartnerCaptureError("FPLCAT_PARTNER_API_KEY is required; public one-GW access is not a five-GW fallback")
    provider_raw = fetch_bytes(FPL_CAT_PARTNER_URL, {"Authorization": f"Bearer {key.strip()}"})
    provider_captured_at = clock()
    bootstrap_raw = fetch_bytes(FPL_BOOTSTRAP_URL, {})
    bootstrap_captured_at = clock()
    try:
        data = json.loads(provider_raw)
        bootstrap = json.loads(bootstrap_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PartnerCaptureError("partner or FPL bootstrap response is not valid JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("players"), list):
        raise PartnerCaptureError("partner response must contain a players array")
    gameweeks = data.get("gameweeks")
    if not isinstance(gameweeks, list) or len(gameweeks) < 5:
        raise PartnerCaptureError("partner response must contain at least five explicit Gameweeks")
    if not isinstance(bootstrap, dict) or not isinstance(bootstrap.get("elements"), list):
        raise PartnerCaptureError("FPL bootstrap response must contain an elements array")

    gw_ids = [row.get("gameweek") if isinstance(row, dict) else row for row in gameweeks]
    if any(isinstance(gw, bool) or not isinstance(gw, int) or gw < 1 for gw in gw_ids):
        raise PartnerCaptureError("partner gameweek identifiers must be positive integers")
    if gw_ids != list(range(gw_ids[0], gw_ids[0] + len(gw_ids))):
        raise PartnerCaptureError("partner Gameweeks must be consecutive and ordered")
    computed = _parse_utc(data.get("computed_at"), "partner computed_at")
    captured = _parse_utc(provider_captured_at, "partner capture time")
    bootstrap_captured = _parse_utc(bootstrap_captured_at, "bootstrap capture time")
    if computed > captured:
        raise PartnerCaptureError("partner computed_at is later than retrieval time")

    events = {row.get("id"): row for row in bootstrap.get("events", []) if isinstance(row, dict)}
    deadlines = {}
    for gw in gw_ids:
        event = events.get(gw)
        if not event:
            raise PartnerCaptureError(f"official FPL bootstrap is missing GW{gw}")
        deadlines[gw] = _parse_utc(event.get("deadline_time"), f"official GW{gw} deadline")
    first_deadline = _parse_utc(data.get("deadline"), "partner first deadline")
    if deadlines[gw_ids[0]] != first_deadline:
        raise PartnerCaptureError("partner first deadline does not match official FPL bootstrap")
    if captured >= first_deadline or bootstrap_captured >= first_deadline:
        raise PartnerCaptureError("capture occurred at or after the first Gameweek deadline")

    element_types = {row["id"]: row["singular_name_short"] for row in bootstrap.get("element_types", [])}
    metadata_by_id = {}
    for element in bootstrap["elements"]:
        pid = element.get("id")
        position = element_types.get(element.get("element_type"))
        if isinstance(pid, int) and position:
            metadata_by_id[pid] = {
                "fpl_element_id": pid,
                "team_id": element.get("team"),
                "position": position,
                "official_price": element.get("now_cost", 0) / 10,
            }

    rows = []
    seen_players = set()
    for index, player in enumerate(data["players"]):
        if not isinstance(player, dict):
            raise PartnerCaptureError(f"players[{index}] is not an object")
        pid = player.get("id")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1 or pid in seen_players:
            raise PartnerCaptureError(f"players[{index}] has an invalid or duplicate FPL element ID")
        seen_players.add(pid)
        if pid not in metadata_by_id:
            raise PartnerCaptureError(f"FPL Cat player {pid} is absent from official bootstrap")
        player_weeks = player.get("gameweeks")
        if not isinstance(player_weeks, list) or [x.get("gameweek") for x in player_weeks if isinstance(x, dict)] != gw_ids:
            raise PartnerCaptureError(f"player {pid} does not have the complete ordered six-GW panel")
        for week in player_weeks:
            gw = week["gameweek"]
            fixtures = week.get("fixtures")
            opponents = week.get("opponents")
            if isinstance(fixtures, bool) or not isinstance(fixtures, int) or fixtures < 0:
                raise PartnerCaptureError(f"player {pid} GW{gw} has invalid fixture count")
            if not isinstance(opponents, list) or len(opponents) != fixtures:
                raise PartnerCaptureError(f"player {pid} GW{gw} opponent list does not match fixture count")
            row = {
                **metadata_by_id[pid],
                "gameweek": gw,
                "expected_points": _finite_nonnegative(week.get("xp"), f"player {pid} GW{gw} xp"),
                "expected_minutes": _finite_nonnegative(week.get("expected_minutes"), f"player {pid} GW{gw} expected_minutes"),
                "fixtures_count": fixtures,
                "opponents": opponents,
                "play_chance": _finite_nonnegative(week.get("play_chance"), f"player {pid} GW{gw} play_chance", nullable=True),
                "p_return": _finite_nonnegative(week.get("p_return"), f"player {pid} GW{gw} p_return", nullable=True),
                "p_haul": _finite_nonnegative(week.get("p_haul"), f"player {pid} GW{gw} p_haul", nullable=True),
                "p_blank": _finite_nonnegative(week.get("p_blank"), f"player {pid} GW{gw} p_blank", nullable=True),
                "xp_q10": _finite_nonnegative(week.get("xp_q10"), f"player {pid} GW{gw} xp_q10", nullable=True),
                "xp_q90": _finite_nonnegative(week.get("xp_q90"), f"player {pid} GW{gw} xp_q90", nullable=True),
                "breakdown": week.get("breakdown"),
            }
            rows.append(row)

    expected_rows = len(seen_players) * len(gw_ids)
    if len(rows) != expected_rows:
        raise PartnerCaptureError("partner player-Gameweek panel is incomplete")
    provider_hash = hashlib.sha256(provider_raw).hexdigest()
    bootstrap_hash = hashlib.sha256(bootstrap_raw).hexdigest()
    snapshot_id = f"fplcat-partner-{provider_hash}"
    return {
        "provider_source_id": "fpl_cat_partner_projections",
        "provider_snapshot": {
            "snapshot_id": snapshot_id,
            "season": season,
            "provider": PROVIDER,
            "grain": "player_gameweek",
            "model_version": "provider_model_version_not_disclosed",
            "gameweeks": gw_ids,
            "decision_eligible": True,
            "timing": {
                "generated_at_utc": computed.isoformat().replace("+00:00", "Z"),
                "captured_at_utc": captured.isoformat().replace("+00:00", "Z"),
                "first_deadline_utc": first_deadline.isoformat().replace("+00:00", "Z"),
                "gameweek_deadlines_utc": {str(gw): deadlines[gw].isoformat().replace("+00:00", "Z") for gw in gw_ids},
                "bootstrap_captured_at_utc": bootstrap_captured.isoformat().replace("+00:00", "Z"),
            },
            "records": rows,
            "source": {
                "url": FPL_CAT_PARTNER_URL,
                "raw_sha256": provider_hash,
                "raw_snapshot_id": f"sha256:{provider_hash}",
                "row_count": len(rows),
            },
        },
        "raw_archives": {
            "provider_response_base64": base64.b64encode(provider_raw).decode("ascii"),
            "fpl_bootstrap_response_base64": base64.b64encode(bootstrap_raw).decode("ascii"),
        },
        "player_metadata_provenance": {
            "source_url": FPL_BOOTSTRAP_URL,
            "raw_sha256": bootstrap_hash,
            "raw_snapshot_id": f"sha256:{bootstrap_hash}",
            "captured_at_utc": bootstrap_captured.isoformat().replace("+00:00", "Z"),
        },
        "capture_status": {
            "capture_grain": "player_gameweek",
            "fixture_level_xp_available": False,
            "double_gameweek_xp_preserved_as_provider_total": True,
            "provider_model_version_disclosed": False,
            "horizon_gameweeks": gw_ids,
            "player_count": len(seen_players),
            "row_count": len(rows),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", required=True, help="FPL season label, e.g. 2026-27")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = capture_fpl_cat_partner_snapshot(season=args.season)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "snapshot_id": result["provider_snapshot"]["snapshot_id"],
        "horizon_gameweeks": result["provider_snapshot"]["gameweeks"],
        "provider_rows": result["capture_status"]["row_count"],
        "provider_sha256": result["provider_snapshot"]["source"]["raw_sha256"],
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
