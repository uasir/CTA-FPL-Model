#!/usr/bin/env python3
"""Capture a strictly pre-deadline, auditable external-forecast decision bundle.

The manager state is explicitly confirmed at dispatch. Purchase prices are
reconstructed only from archived official FPL season-history sources when the
target-Gameweek picks endpoint is not yet available; the independent auditor
replays that reconstruction before admission.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from capture_fpl_cat_snapshot import FPL_BOOTSTRAP_URL, FPL_CAT_URL, capture_fpl_cat_snapshot
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


def _selling_price_tenths(now_cost: Any, purchase_price: Any, player_id: int) -> int:
    if isinstance(now_cost, bool) or not isinstance(now_cost, int) or now_cost <= 0:
        raise DecisionCaptureError(f"Official current price missing/invalid for player {player_id}")
    if isinstance(purchase_price, bool) or not isinstance(purchase_price, (int, float)):
        raise DecisionCaptureError(f"Purchase price missing/invalid for player {player_id}")
    purchase_tenths = round(float(purchase_price) * 10)
    return (
        purchase_tenths + (now_cost - purchase_tenths) // 2
        if now_cost > purchase_tenths else now_cost
    )


def _validate_manager_state(state: Mapping[str, Any], team_id: int) -> dict[str, Any]:
    required = {
        "squad_15", "bank", "free_transfers", "formation", "starting_xi",
        "bench_order", "reserve_goalkeeper_id", "captain_id", "vice_captain_id",
        "chip_state",
    }
    missing = sorted(required - set(state))
    if missing:
        raise DecisionCaptureError(f"Manager state JSON missing fields: {', '.join(missing)}")
    squad = state["squad_15"]
    xi = state["starting_xi"]
    bench = state["bench_order"]
    if not isinstance(squad, list) or len(squad) != 15 or len(set(squad)) != 15:
        raise DecisionCaptureError("squad_15 must contain exactly 15 unique FPL element IDs")
    if not isinstance(xi, list) or len(xi) != 11 or len(set(xi)) != 11:
        raise DecisionCaptureError("starting_xi must contain exactly 11 unique FPL element IDs")
    if not isinstance(bench, list) or len(bench) != 3 or len(set(bench)) != 3:
        raise DecisionCaptureError("bench_order must contain exactly three ordered outfield IDs")
    ids = set(squad)
    reserve_gk = state["reserve_goalkeeper_id"]
    captain, vice = state["captain_id"], state["vice_captain_id"]
    if set(xi) | set(bench) | {reserve_gk} != ids:
        raise DecisionCaptureError("Starting XI, outfield bench and reserve goalkeeper must partition the 15-player squad")
    if set(xi) & set(bench) or reserve_gk in set(xi) | set(bench):
        raise DecisionCaptureError("Manager lineup contains duplicate player assignments")
    if captain not in ids or vice not in ids or captain == vice:
        raise DecisionCaptureError("Captain and vice-captain must be distinct squad players")
    if state["chip_state"] != "NONE":
        raise DecisionCaptureError("Only chip_state NONE is supported by the initial decision contract")
    if isinstance(state["bank"], bool) or not isinstance(state["bank"], (int, float)) or state["bank"] < 0:
        raise DecisionCaptureError("Manager bank must be a non-negative number")
    ft = state["free_transfers"]
    if isinstance(ft, bool) or not isinstance(ft, int) or not 0 <= ft <= 5:
        raise DecisionCaptureError("free_transfers must be an integer from 0 to 5")
    if state["formation"] not in {"3-4-3", "3-5-2", "4-3-3", "4-4-2", "4-5-1", "5-2-3", "5-3-2", "5-4-1"}:
        raise DecisionCaptureError("Unsupported FPL formation")
    if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0
           for value in ids | set(xi) | set(bench) | {reserve_gk, captain, vice}):
        raise DecisionCaptureError("All FPL element IDs must be positive integers")
    return {
        "squad_15": sorted(squad),
        "bank": float(state["bank"]),
        "free_transfers": ft,
        "formation": state["formation"],
        "starting_xi": list(xi),
        "bench_order": list(bench),
        "reserve_goalkeeper_id": reserve_gk,
        "captain_id": captain,
        "vice_captain_id": vice,
        "chip_state": "NONE",
    }


def capture_predeadline_decision_bundle(
    *,
    team_id: int,
    gameweek: int,
    season: str,
    manager_state: Mapping[str, Any],
    provider_capture: Mapping[str, Any] | None = None,
    clock: Callable[[], str] | None = None,
) -> dict[str, Any]:
    if team_id <= 0 or gameweek <= 0:
        raise DecisionCaptureError("team_id and gameweek must be positive integers")
    # Preserve the manager identity separately from player metadata club IDs.
    manager_id = team_id
    state = _validate_manager_state(manager_state, manager_id)
    expected_ids = set(state["squad_15"])
    starting_xi_ids = set(state["starting_xi"])

    # A caller may supply an independently captured provider envelope. The
    # default remains the established FPL Cat path; provider runs never mix.
    if provider_capture is None:
        provider_capture = capture_fpl_cat_snapshot(season=season)
    if not isinstance(provider_capture, Mapping):
        raise DecisionCaptureError("provider_capture must be a provider capture envelope")
    for required_key in ("provider_snapshot", "raw_archives", "player_metadata_provenance"):
        if required_key not in provider_capture:
            raise DecisionCaptureError(f"provider capture envelope missing {required_key}")
    provider = provider_capture["provider_snapshot"]
    provider_raw_b64 = provider_capture["raw_archives"]["provider_response_base64"]
    provider_raw, provider_payload = _decode_json(provider_raw_b64, "provider forecast")
    if provider.get("target_gameweek") != gameweek or provider_payload.get("gameweek") != gameweek:
        raise DecisionCaptureError(f"Provider did not return requested GW{gameweek}")
    deadline_text = provider.get("timing", {}).get("deadline_utc")
    deadline = _time(deadline_text, "official deadline")
    generated_text = provider.get("timing", {}).get("generated_at_utc")
    generated = _time(generated_text, "provider generation time")
    provider_captured = _time(provider.get("timing", {}).get("captured_at_utc"),
                              "provider capture time")
    if not generated < deadline or not provider_captured < deadline:
        raise DecisionCaptureError("Provider generation and capture must precede deadline")

    manager_capture = capture_manager_context(
        team_id,
        gameweek,
        expected_element_ids=expected_ids,
        expected_bank=state["bank"],
        free_transfers=state["free_transfers"],
        personal_risk_profile="aggressive",
        formation=state["formation"],
        starting_xi_ids=starting_xi_ids,
        allow_user_confirmed_fallback=True,
    )
    manager_provenance = manager_capture["manager_context_capture"]
    manager_context = manager_capture["manager_context"]
    manager_captured = _time(manager_provenance.get("captured_at_utc"),
                             "manager state capture time")
    if not manager_captured < deadline:
        raise DecisionCaptureError("Manager state capture must precede the official deadline")
    captured_bank = manager_context.get("bank")
    if captured_bank is None or abs(float(captured_bank) - state["bank"]) > 0.0001:
        raise DecisionCaptureError("Captured manager bank does not match confirmed manager state")

    manager_archive_raw, manager_archive = _decode_json(
        manager_provenance["raw_response_base64"], "manager source archive"
    )
    if hashlib.sha256(manager_archive_raw).hexdigest() != manager_provenance.get("raw_sha256"):
        raise DecisionCaptureError("Manager source archive hash does not match capture provenance")
    manager_archive_type = manager_archive.get("source_type")
    fallback = manager_archive_type in {
        "FPL_SEASON_HISTORY_RECONSTRUCTION", "PREVIOUS_GAMEWEEK_PICKS"
    }
    if fallback:
        history_archive_b64 = manager_provenance["raw_response_base64"]
        raw_manager_picks_b64 = None
        history_raw, history_payload = _decode_json(manager_archive["history"], "manager history")
        chips = history_payload.get("chips")
        if not isinstance(chips, list) or any(
            isinstance(chip, dict) and chip.get("event") == gameweek
            for chip in chips
        ):
            raise DecisionCaptureError("Manager history does not confirm a no-chip target Gameweek")
        if manager_archive_type == "FPL_SEASON_HISTORY_RECONSTRUCTION":
            required_archives = {
                "previous_gameweek_picks", "gw1_picks", "transfers", "history", "bootstrap"
            }
            if not required_archives.issubset(manager_archive):
                raise DecisionCaptureError("Official manager history archive is incomplete")
            metadata_raw_b64 = manager_archive["bootstrap"]
            metadata_raw, metadata_payload = _decode_json(metadata_raw_b64, "manager bootstrap")
            capture_method = "USER_CONFIRMED_WITH_OFFICIAL_HISTORY"
            metadata_captured_text = manager_captured.isoformat().replace("+00:00", "Z")
        else:
            if not {"previous_gameweek_picks", "history"}.issubset(manager_archive):
                raise DecisionCaptureError("Previous-Gameweek manager archive is incomplete")
            metadata_raw_b64 = provider_capture["raw_archives"]["fpl_bootstrap_response_base64"]
            metadata_raw, metadata_payload = _decode_json(metadata_raw_b64, "player metadata")
            capture_method = "USER_CONFIRMED_WITH_PREVIOUS_GW_PICKS"
            metadata_captured_text = provider_capture["player_metadata_provenance"]["captured_at_utc"]
    else:
        metadata_raw_b64 = provider_capture["raw_archives"]["fpl_bootstrap_response_base64"]
        metadata_raw, metadata_payload = _decode_json(metadata_raw_b64, "player metadata")
        history_payload = None
        capture_method = "OFFICIAL_TARGET_GAMEWEEK_PICKS"
        history_archive_b64 = None
        raw_manager_picks_b64 = manager_provenance["raw_response_base64"]
        metadata_captured_text = provider_capture["player_metadata_provenance"]["captured_at_utc"]

    elements = metadata_payload.get("elements")
    if not isinstance(elements, list):
        raise DecisionCaptureError("Official bootstrap metadata is missing elements")
    by_id = {row.get("id"): row for row in elements if isinstance(row, dict)}
    if any(player_id not in by_id for player_id in expected_ids):
        raise DecisionCaptureError("One or more manager players are absent from captured official metadata")
    element_types = {player_id: row.get("element_type") for player_id, row in by_id.items()}
    position_names = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
    provider_records = provider.get("records")
    if not isinstance(provider_records, list) or not provider_records:
        raise DecisionCaptureError("Provider snapshot has no player-gameweek forecast records")
    normalized_metadata = []
    for record in provider_records:
        player_id = record.get("fpl_element_id") if isinstance(record, dict) else None
        meta = by_id.get(player_id)
        if meta is None:
            raise DecisionCaptureError(f"Provider player {player_id} is missing from official metadata")
        position = position_names.get(meta.get("element_type"))
        player_team_id = meta.get("team")
        now_cost = meta.get("now_cost")
        if position is None or isinstance(player_team_id, bool) or not isinstance(player_team_id, int) or player_team_id < 1:
            raise DecisionCaptureError(f"Official metadata is incomplete for player {player_id}")
        if isinstance(now_cost, bool) or not isinstance(now_cost, int) or now_cost <= 0:
            raise DecisionCaptureError(f"Official current price is missing for player {player_id}")
        normalized_metadata.append({
            "fpl_element_id": player_id,
            "price": now_cost / 10,
            "position": position,
            "team_id": player_team_id,
        })

    starting_counts = {
        position: sum(element_types.get(player_id) == element_type
                      for player_id in state["starting_xi"])
        for element_type, position in ((1, "GKP"), (2, "DEF"), (3, "MID"), (4, "FWD"))
    }
    expected_counts = dict(zip(("DEF", "MID", "FWD"),
                               (int(value) for value in state["formation"].split("-"))))
    if starting_counts["GKP"] != 1 or any(
        starting_counts[position] != expected_counts[position]
        for position in ("DEF", "MID", "FWD")
    ):
        raise DecisionCaptureError("Confirmed starting XI does not match the requested formation")
    if element_types.get(state["reserve_goalkeeper_id"]) != 1:
        raise DecisionCaptureError("Confirmed reserve goalkeeper is not an FPL goalkeeper")
    if any(element_types.get(player_id) == 1 for player_id in state["bench_order"]):
        raise DecisionCaptureError("Outfield bench order must not contain a goalkeeper")

    purchase_prices = {
        str(row["fpl_element_id"]): float(row["purchase_price"])
        for row in manager_context["squad_snapshot"]
    }
    if set(map(int, purchase_prices)) != expected_ids or len(purchase_prices) != 15:
        raise DecisionCaptureError("Official purchase-price evidence does not cover the exact 15-player squad")
    if not fallback:
        if manager_archive.get("entry_history", {}).get("event") != gameweek:
            raise DecisionCaptureError("Official target picks payload identifies the wrong Gameweek")
        if manager_archive.get("active_chip") is not None:
            raise DecisionCaptureError("Official target picks show an active chip")
        picks = manager_archive.get("picks")
        if not isinstance(picks, list) or len(picks) != 15:
            raise DecisionCaptureError("Official target picks must contain exactly 15 players")
        picks_by_position = {row.get("position"): row for row in picks if isinstance(row, dict)}
        if set(picks_by_position) != set(range(1, 16)):
            raise DecisionCaptureError("Official target picks positions must be 1 through 15")
        if {row.get("element") for row in picks} != expected_ids:
            raise DecisionCaptureError("Official target picks do not match the confirmed 15-player squad")
        if {picks_by_position[pos]["element"] for pos in range(1, 12)} != set(state["starting_xi"]):
            raise DecisionCaptureError("Official target picks starting XI differs from confirmed lineup")
        direct_bench = [
            picks_by_position[pos]["element"] for pos in range(12, 16)
            if element_types.get(picks_by_position[pos]["element"]) != 1
        ]
        direct_gks = [
            picks_by_position[pos]["element"] for pos in range(12, 16)
            if element_types.get(picks_by_position[pos]["element"]) == 1
        ]
        if direct_bench != state["bench_order"] or direct_gks != [state["reserve_goalkeeper_id"]]:
            raise DecisionCaptureError("Official target picks bench order/reserve goalkeeper differs from confirmed state")
        direct_captains = [row["element"] for row in picks if row.get("is_captain") is True]
        direct_vice = [row["element"] for row in picks if row.get("is_vice_captain") is True]
        if direct_captains != [state["captain_id"]] or direct_vice != [state["vice_captain_id"]]:
            raise DecisionCaptureError("Official target picks captain/vice-captain differs from confirmed state")
        bank_raw = manager_archive.get("entry_history", {}).get("bank")
        if not isinstance(bank_raw, int) or isinstance(bank_raw, bool) or abs(bank_raw / 10 - state["bank"]) > 0.0001:
            raise DecisionCaptureError("Official target picks bank differs from confirmed manager state")
        official_purchase_prices = {
            str(row["element"]): row["purchase_price"] / 10
            for row in picks if isinstance(row, dict)
            and isinstance(row.get("purchase_price"), int)
            and not isinstance(row.get("purchase_price"), bool)
        }
        if official_purchase_prices != purchase_prices:
            raise DecisionCaptureError("Official target picks purchase prices differ from manager context")
    selling_prices = {}
    for player_id in expected_ids:
        now_cost = by_id[player_id].get("now_cost")
        selling_prices[str(player_id)] = _selling_price_tenths(
            now_cost, purchase_prices[str(player_id)], player_id
        ) / 10

    manager_url = f"https://fantasy.premierleague.com/entry/{manager_id}"
    manager_state_envelope = {
        "capture_kind": "USER_ATTESTED_PREDEADLINE_MANAGER_STATE",
        "capture_method": capture_method,
        "manager_team_id": manager_id,
        "target_gameweek": gameweek,
        "captured_at_utc": manager_provenance["captured_at_utc"],
        "source_urls": manager_provenance.get("source_urls", [manager_provenance["source_url"]]),
        "history_archive_base64": history_archive_b64,
        "raw_manager_picks_base64": raw_manager_picks_b64,
        "manager_state": {
            **state,
            "purchase_prices": purchase_prices,
            "selling_prices": selling_prices,
        },
    }
    manager_state_raw = json.dumps(
        manager_state_envelope, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    manager_state_b64 = base64.b64encode(manager_state_raw).decode("ascii")

    metadata_hash = hashlib.sha256(metadata_raw).hexdigest()
    provider_hash = hashlib.sha256(provider_raw).hexdigest()
    manager_hash = hashlib.sha256(manager_state_raw).hexdigest()
    if provider_hash != provider.get("source", {}).get("raw_sha256"):
        raise DecisionCaptureError("Provider raw archive hash does not match capture provenance")
    if fallback and manager_archive_type == "FPL_SEASON_HISTORY_RECONSTRUCTION":
        if metadata_hash != hashlib.sha256(metadata_raw).hexdigest():
            raise DecisionCaptureError("Manager bootstrap hash could not be verified")
    elif metadata_hash != provider_capture.get("player_metadata_provenance", {}).get("raw_sha256"):
        raise DecisionCaptureError("Player metadata raw archive hash does not match capture provenance")

    metadata_captured = _time(metadata_captured_text, "player metadata capture time")
    if not metadata_captured < deadline:
        raise DecisionCaptureError("Player metadata capture must precede deadline")
    if clock is None:
        decision_as_of = manager_captured
    else:
        decision_as_of = _time(clock(), "decision-as-of timestamp")
    if not decision_as_of < deadline or decision_as_of < max(provider_captured, metadata_captured, manager_captured):
        raise DecisionCaptureError("Decision-as-of timestamp must follow all captures and precede deadline")

    manifest = {
        "manager_team_id": manager_id,
        "season": provider["season"],
        "provider_snapshot": provider,
        "player_metadata": normalized_metadata,
        "player_metadata_provenance": {
            "source_url": FPL_BOOTSTRAP_URL,
            "raw_snapshot_id": f"sha256:{metadata_hash}",
            "raw_sha256": metadata_hash,
            "captured_at_utc": metadata_captured_text,
            "row_count": len(normalized_metadata),
        },
        "target_gameweek": gameweek,
        "deadline_utc": deadline_text,
        "decision_as_of_utc": decision_as_of.isoformat().replace("+00:00", "Z"),
        "evidence_is_point_in_time": True,
        "sources": [
            {
                "source_type": "provider_forecast",
                "provider_id": (
                    "fpl-cat" if provider.get("provider", {}).get("name") == "FPL Cat"
                    else "sideline-quant" if provider.get("provider", {}).get("name") == "Sideline Quant"
                    else "unregistered-provider"
                ),
                "provider_variant": provider.get("provider", {}).get("variant"),
                "raw_snapshot_id": f"sha256:{provider_hash}",
                "raw_sha256": provider_hash,
                "generated_at_utc": generated_text,
                "captured_at_utc": provider.get("timing", {}).get("captured_at_utc"),
                "source_url": provider.get("source", {}).get("url"),
                "raw_payload_base64": provider_raw_b64,
            },
            {
                "source_type": "player_metadata",
                "raw_snapshot_id": f"sha256:{metadata_hash}",
                "raw_sha256": metadata_hash,
                "captured_at_utc": metadata_captured_text,
                "source_url": FPL_BOOTSTRAP_URL,
                "raw_payload_base64": metadata_raw_b64,
            },
            {
                "source_type": "manager_deadline_state",
                "raw_snapshot_id": f"sha256:{manager_hash}",
                "raw_sha256": manager_hash,
                "captured_at_utc": manager_provenance["captured_at_utc"],
                "source_url": manager_url,
                "raw_payload_base64": manager_state_b64,
            },
        ],
        "manager_state": manager_state_envelope["manager_state"],
    }
    manager_source = next(
        source for source in manifest["sources"]
        if source["source_type"] == "manager_deadline_state"
    )
    if (
        manifest["manager_team_id"] != manager_id
        or manager_state_envelope["manager_team_id"] != manager_id
        or manager_source["source_url"] != f"https://fantasy.premierleague.com/entry/{manager_id}"
    ):
        raise DecisionCaptureError("Manager identity was not preserved across the decision evidence bundle")
    return {str(gameweek): manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team-id", type=int, required=True)
    parser.add_argument("--gameweek", type=int, required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument("--manager-state-json", required=True,
                        help="JSON manager state: squad_15, bank, free_transfers, formation, starting_xi, bench_order, reserve_goalkeeper_id, captain_id, vice_captain_id, chip_state")
    parser.add_argument("--provider-capture", type=Path,
                        help="Optional prebuilt provider envelope; defaults to live FPL Cat capture")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manager_state = json.loads(args.manager_state_json)
    except json.JSONDecodeError as exc:
        raise DecisionCaptureError("manager-state-json is not valid JSON") from exc
    if not isinstance(manager_state, dict):
        raise DecisionCaptureError("manager-state-json must be a JSON object")
    provider_capture = (
        json.loads(args.provider_capture.read_text(encoding="utf-8"))
        if args.provider_capture else None
    )
    result = capture_predeadline_decision_bundle(
        team_id=args.team_id,
        gameweek=args.gameweek,
        season=args.season,
        manager_state=manager_state,
        provider_capture=provider_capture,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = result[str(args.gameweek)]
    print(json.dumps({
        "manager_team_id": args.team_id,
        "gameweek": args.gameweek,
        "deadline_utc": manifest["deadline_utc"],
        "decision_as_of_utc": manifest["decision_as_of_utc"],
        "capture_method": json.loads(base64.b64decode(
            manifest["sources"][2]["raw_payload_base64"]
        ))["capture_method"],
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
