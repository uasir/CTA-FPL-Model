#!/usr/bin/env python3
"""Capture a strictly pre-deadline, auditable external-forecast decision bundle.

This command intentionally requires the live target-Gameweek manager picks
endpoint to return the exact confirmed 15-player squad. It does not reconstruct
prices or backdate state for decision-backtest admission.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from capture_fpl_cat_snapshot import (
    FPL_BOOTSTRAP_URL,
    FPL_CAT_URL,
    capture_fpl_cat_snapshot,
)
from capture_fpl_manager_context import capture_manager_context


class DecisionCaptureError(ValueError):
    pass


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise DecisionCaptureError(f"{label} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DecisionCaptureError(f"{label} is not ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DecisionCaptureError(f"{label} must be timezone-aware")
    return parsed


def _decode_json(encoded: str, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = base64.b64decode(encoded, validate=True)
        payload = json.loads(raw)
    except Exception as exc:
        raise DecisionCaptureError(f"{label} raw archive is not valid base64 JSON") from exc
    if not isinstance(payload, dict):
        raise DecisionCaptureError(f"{label} payload must be a JSON object")
    return raw, payload


def capture_predeadline_decision_bundle(
    *,
    team_id: int,
    gameweek: int,
    season: str,
    expected_element_ids: set[int],
    free_transfers: int,
    formation: str = "4-3-3",
    chip_state: str = "NONE",
    clock: Callable[[], str] | None = None,
) -> dict[str, Any]:
    if team_id <= 0 or gameweek <= 0:
        raise DecisionCaptureError("team_id and gameweek must be positive integers")
    if len(expected_element_ids) != 15 or any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in expected_element_ids
    ):
        raise DecisionCaptureError("expected_element_ids must contain exactly 15 unique positive IDs")
    if isinstance(free_transfers, bool) or not isinstance(free_transfers, int) or not 0 <= free_transfers <= 5:
        raise DecisionCaptureError("free_transfers must be an integer from 0 to 5")
    if chip_state != "NONE":
        raise DecisionCaptureError("Only chip_state NONE is supported by the initial decision contract")
    if formation not in {"3-4-3", "3-5-2", "4-3-3", "4-4-2", "4-5-1", "5-2-3", "5-3-2", "5-4-1"}:
        raise DecisionCaptureError("Unsupported FPL formation")

    provider_capture = capture_fpl_cat_snapshot(season=season)
    provider = provider_capture["provider_snapshot"]
    provider_raw_b64 = provider_capture["raw_archives"]["provider_response_base64"]
    metadata_raw_b64 = provider_capture["raw_archives"]["fpl_bootstrap_response_base64"]
    provider_raw, provider_payload = _decode_json(provider_raw_b64, "provider forecast")
    metadata_raw, metadata_payload = _decode_json(metadata_raw_b64, "player metadata")

    if provider.get("target_gameweek") != gameweek:
        raise DecisionCaptureError(
            f"Provider returned GW{provider.get('target_gameweek')}, not requested GW{gameweek}"
        )
    deadline_text = provider.get("timing", {}).get("deadline_utc")
    deadline = _time(deadline_text, "official deadline")
    provider_generated = provider.get("timing", {}).get("generated_at_utc")
    generated = _time(provider_generated, "provider generation time")
    provider_captured = _time(provider.get("timing", {}).get("captured_at_utc"),
                              "provider capture time")
    metadata_captured = _time(
        provider_capture.get("player_metadata_provenance", {}).get("captured_at_utc"),
        "player metadata capture time",
    )
    if not generated < deadline or not provider_captured < deadline or not metadata_captured < deadline:
        raise DecisionCaptureError("Provider generation/capture and metadata capture must all precede deadline")

    manager_capture = capture_manager_context(
        team_id,
        gameweek,
        expected_element_ids=expected_element_ids,
        free_transfers=free_transfers,
        personal_risk_profile="aggressive",
        formation=formation,
        allow_user_confirmed_fallback=False,
    )
    manager_provenance = manager_capture["manager_context_capture"]
    manager_context = manager_capture["manager_context"]
    manager_raw, manager_payload = _decode_json(
        manager_provenance["raw_response_base64"], "manager deadline state"
    )
    manager_captured = _time(manager_provenance.get("captured_at_utc"),
                             "manager deadline-state capture time")
    if not manager_captured < deadline:
        raise DecisionCaptureError("Manager deadline-state capture must precede the official deadline")
    if manager_payload.get("entry_history", {}).get("event") != gameweek:
        raise DecisionCaptureError("Manager raw payload does not identify the requested Gameweek")

    picks = manager_payload.get("picks")
    if not isinstance(picks, list) or len(picks) != 15:
        raise DecisionCaptureError("Manager raw payload must contain exactly 15 picks")
    picks_by_position = {}
    for pick in picks:
        position = pick.get("position") if isinstance(pick, dict) else None
        element = pick.get("element") if isinstance(pick, dict) else None
        if (isinstance(position, bool) or not isinstance(position, int) or not 1 <= position <= 15
                or position in picks_by_position or isinstance(element, bool)
                or not isinstance(element, int) or element <= 0):
            raise DecisionCaptureError("Manager picks contain invalid or duplicate position/player data")
        picks_by_position[position] = pick
    if set(picks_by_position) != set(range(1, 16)):
        raise DecisionCaptureError("Manager picks must contain positions 1 through 15")
    pick_ids = {pick["element"] for pick in picks_by_position.values()}
    if pick_ids != expected_element_ids:
        raise DecisionCaptureError("Live manager picks do not match the user-confirmed 15-player squad")

    elements = metadata_payload.get("elements")
    if not isinstance(elements, list):
        raise DecisionCaptureError("Official bootstrap metadata is missing elements")
    element_types = {
        row.get("id"): row.get("element_type")
        for row in elements if isinstance(row, dict)
    }
    if any(player_id not in element_types for player_id in pick_ids):
        raise DecisionCaptureError("One or more manager players are absent from captured official metadata")

    starting_xi = [picks_by_position[pos]["element"] for pos in range(1, 12)]
    bench_picks = [picks_by_position[pos] for pos in range(12, 16)]
    reserve_gks = [pick["element"] for pick in bench_picks
                   if element_types.get(pick["element"]) == 1]
    outfield_bench = [pick["element"] for pick in bench_picks
                      if element_types.get(pick["element"]) != 1]
    if len(reserve_gks) != 1 or len(outfield_bench) != 3:
        raise DecisionCaptureError("Bench must contain exactly one reserve goalkeeper and three outfield substitutes")

    captains = [pick["element"] for pick in picks if pick.get("is_captain") is True]
    vice_captains = [pick["element"] for pick in picks if pick.get("is_vice_captain") is True]
    if len(captains) != 1 or len(vice_captains) != 1 or captains[0] == vice_captains[0]:
        raise DecisionCaptureError("Manager picks must identify one distinct captain and vice-captain")

    purchase_prices = {
        str(row["fpl_element_id"]): row["purchase_price"]
        for row in manager_context["squad_snapshot"]
    }
    selling_prices = {}
    for player_id, pick in ((pick["element"], pick) for pick in picks):
        price = pick.get("selling_price")
        if isinstance(price, bool) or not isinstance(price, int) or price <= 0:
            raise DecisionCaptureError(f"Official selling_price missing/invalid for player {player_id}")
        selling_prices[str(player_id)] = price / 10
    if len(purchase_prices) != 15 or len(selling_prices) != 15:
        raise DecisionCaptureError("Purchase and selling prices must cover all 15 players")

    bank = manager_context.get("bank")
    if not isinstance(bank, (int, float)) or isinstance(bank, bool) or bank < 0:
        raise DecisionCaptureError("Official manager bank is missing or invalid")
    if clock is None:
        decision_as_of = manager_captured
    else:
        decision_as_of = _time(clock(), "decision-as-of timestamp")
    if not decision_as_of < deadline:
        raise DecisionCaptureError("Decision-as-of timestamp must precede deadline")
    if decision_as_of < max(provider_captured, metadata_captured, manager_captured):
        raise DecisionCaptureError("Decision-as-of timestamp cannot precede one of its source captures")

    # Independently bind the exact bytes to the hashes returned by the capture layers.
    provider_hash = hashlib.sha256(provider_raw).hexdigest()
    metadata_hash = hashlib.sha256(metadata_raw).hexdigest()
    manager_hash = hashlib.sha256(manager_raw).hexdigest()
    if provider_hash != provider.get("source", {}).get("raw_sha256"):
        raise DecisionCaptureError("Provider raw archive hash does not match capture provenance")
    if metadata_hash != provider_capture.get("player_metadata_provenance", {}).get("raw_sha256"):
        raise DecisionCaptureError("Player metadata raw archive hash does not match capture provenance")
    if manager_hash != manager_provenance.get("raw_sha256"):
        raise DecisionCaptureError("Manager raw archive hash does not match capture provenance")
    if "active_chip" not in manager_payload or manager_payload.get("active_chip") is not None:
        raise DecisionCaptureError("Manager picks must explicitly confirm no active chip")
    element_position = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
    actual_counts = {
        position: sum(element_types.get(player_id) == element_type
                      for player_id in starting_xi)
        for element_type, position in element_position.items()
    }
    expected_counts = dict(zip(("DEF", "MID", "FWD"),
                               (int(value) for value in formation.split("-"))))
    if actual_counts["GKP"] != 1 or any(
        actual_counts[position] != expected_counts[position]
        for position in ("DEF", "MID", "FWD")
    ):
        raise DecisionCaptureError("Live starting XI does not match the requested formation")
    manager_url = manager_provenance["source_url"]
    manifest = {
        "target_gameweek": gameweek,
        "deadline_utc": deadline_text,
        "decision_as_of_utc": decision_as_of.isoformat().replace("+00:00", "Z"),
        "evidence_is_point_in_time": True,
        "sources": [
            {
                "source_type": "provider_forecast",
                "provider_id": "fpl-cat",
                "provider_variant": "public-xp",
                "raw_snapshot_id": f"sha256:{provider_hash}",
                "raw_sha256": provider_hash,
                "generated_at_utc": provider_generated,
                "captured_at_utc": provider.get("timing", {}).get("captured_at_utc"),
                "source_url": FPL_CAT_URL,
                "raw_payload_base64": provider_raw_b64,
            },
            {
                "source_type": "player_metadata",
                "raw_snapshot_id": f"sha256:{metadata_hash}",
                "raw_sha256": metadata_hash,
                "captured_at_utc": provider_capture["player_metadata_provenance"]["captured_at_utc"],
                "source_url": FPL_BOOTSTRAP_URL,
                "raw_payload_base64": metadata_raw_b64,
            },
            {
                "source_type": "manager_deadline_state",
                "raw_snapshot_id": f"sha256:{manager_hash}",
                "raw_sha256": manager_hash,
                "captured_at_utc": manager_provenance["captured_at_utc"],
                "source_url": manager_url,
                "raw_payload_base64": manager_provenance["raw_response_base64"],
            },
        ],
        "manager_state": {
            "squad_15": sorted(pick_ids),
            "bank": bank,
            "free_transfers": free_transfers,
            "purchase_prices": purchase_prices,
            "selling_prices": selling_prices,
            "chip_state": chip_state,
            "starting_xi": starting_xi,
            "bench_order": outfield_bench,
            "reserve_goalkeeper_id": reserve_gks[0],
            "captain_id": captains[0],
            "vice_captain_id": vice_captains[0],
            "formation": formation,
        },
    }
    return {str(gameweek): manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team-id", type=int, required=True)
    parser.add_argument("--gameweek", type=int, required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument("--expected-element-ids", required=True,
                        help="Comma-separated exact 15 FPL element IDs confirmed by the manager")
    parser.add_argument("--free-transfers", type=int, required=True,
                        help="Manager-confirmed free transfers available before the deadline")
    parser.add_argument("--formation", default="4-3-3")
    parser.add_argument("--chip-state", default="NONE")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ids = {int(value.strip()) for value in args.expected_element_ids.split(",") if value.strip()}
    result = capture_predeadline_decision_bundle(
        team_id=args.team_id,
        gameweek=args.gameweek,
        season=args.season,
        expected_element_ids=ids,
        free_transfers=args.free_transfers,
        formation=args.formation,
        chip_state=args.chip_state,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = result[str(args.gameweek)]
    print(json.dumps({
        "manager_team_id": args.team_id,
        "gameweek": args.gameweek,
        "deadline_utc": manifest["deadline_utc"],
        "decision_as_of_utc": manifest["decision_as_of_utc"],
        "sources": [
            {"source_type": row["source_type"], "raw_sha256": row["raw_sha256"],
             "captured_at_utc": row["captured_at_utc"]}
            for row in manifest["sources"]
        ],
        "output": str(args.output),
        "historical_evidence_admitted": False,
        "note": "Capture only; admission occurs after finalized official scoring reconciliation and independent audit.",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
