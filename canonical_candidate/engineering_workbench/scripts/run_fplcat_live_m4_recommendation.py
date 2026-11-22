#!/usr/bin/env python3
"""Run a point-in-time FPL Cat M3/M4 recommendation for a public manager.

The previous official Gameweek picks are carried forward as the initial
lineup/bench/captaincy baseline. The script refuses to guess bank when
target-Gameweek transfers have already been made.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

from build_conventional_squad_product import build_personal_squad_product
from capture_predeadline_decision_bundle import capture_predeadline_decision_bundle
from run_external_benchmark_personal_squad import run_external_benchmark_personal_squad
from run_predeadline_m3_decision import run_predeadline_m3_decision


class LiveM4ReplayError(ValueError):
    pass


def derive_free_transfers(history: Mapping[str, Any], target_gameweek: int) -> int:
    """Reconstruct FTs from official event transfer counts and chip history."""
    current_rows = history.get("current")
    chips = history.get("chips")
    if not isinstance(current_rows, list) or not isinstance(chips, list):
        raise LiveM4ReplayError("official manager history is missing current events or chips")
    by_event = {
        row.get("event"): row for row in current_rows
        if isinstance(row, dict) and isinstance(row.get("event"), int)
    }
    chip_events = {
        row.get("event"): row.get("name")
        for row in chips
        if isinstance(row, dict) and row.get("name") in {"wildcard", "freehit"}
    }
    # One free transfer is available after GW1 for GW2.
    free_transfers = 1
    for event in range(2, target_gameweek):
        row = by_event.get(event)
        if not isinstance(row, dict):
            raise LiveM4ReplayError(f"official manager history is missing GW{event}")
        if chip_events.get(event) in {"wildcard", "freehit"}:
            # The new FT for this Gameweek is consumed by activating the chip;
            # banked transfers remain available next Gameweek.
            continue
        transfer_count = row.get("event_transfers")
        hit_cost = row.get("event_transfers_cost")
        if (
            isinstance(transfer_count, bool) or not isinstance(transfer_count, int)
            or transfer_count < 0 or isinstance(hit_cost, bool)
            or not isinstance(hit_cost, int) or hit_cost < 0 or hit_cost % 4
        ):
            raise LiveM4ReplayError(f"invalid official transfer accounting for GW{event}")
        hit_transfers = hit_cost // 4
        free_used = transfer_count - hit_transfers
        if free_used < 0 or free_used > free_transfers:
            raise LiveM4ReplayError(
                f"GW{event} transfer history is inconsistent with reconstructed free transfers"
            )
        free_transfers = min(5, free_transfers - free_used + 1)
    return free_transfers


def build_manager_state(
    manager_snapshot: Mapping[str, Any],
    history: Mapping[str, Any],
    *,
    chip_state: str,
) -> dict[str, Any]:
    if manager_snapshot.get("capture_type") != "PUBLIC_FPL_MANAGER_STATE_REVIEW_NOT_DECISION_EVIDENCE":
        raise LiveM4ReplayError("manager snapshot is not the expected public FPL capture")
    activity = manager_snapshot.get("target_gameweek_transfer_activity")
    previous = manager_snapshot.get("previous_gameweek_state")
    if not isinstance(activity, Mapping) or not isinstance(previous, Mapping):
        raise LiveM4ReplayError("manager snapshot is missing squad or transfer activity")
    if activity.get("transfers_reported") != 0:
        raise LiveM4ReplayError(
            "target-Gameweek transfers exist; refresh the bank and manager state before recommendation"
        )
    squad = previous.get("squad_ids")
    xi = previous.get("starting_xi_ids")
    bench = previous.get("outfield_bench_ids")
    reserve_gk = previous.get("reserve_goalkeeper_id")
    if not isinstance(squad, list) or len(squad) != 15:
        raise LiveM4ReplayError("official previous-Gameweek squad does not contain 15 players")
    if not isinstance(xi, list) or len(xi) != 11 or not isinstance(bench, list) or len(bench) != 3:
        raise LiveM4ReplayError("official previous-Gameweek lineup is incomplete")
    if not isinstance(reserve_gk, int):
        raise LiveM4ReplayError("official previous-Gameweek reserve goalkeeper is missing")
    bank = previous.get("bank_at_previous_deadline")
    if isinstance(bank, bool) or not isinstance(bank, (int, float)) or bank < 0:
        raise LiveM4ReplayError("official previous-Gameweek bank is invalid")
    formation_counts = {"DEF": 0, "MID": 0, "FWD": 0}
    starting_goalkeepers = 0
    rows = previous.get("players_in_official_pick_order")
    if not isinstance(rows, list):
        raise LiveM4ReplayError("official player metadata is missing")
    by_id = {row.get("fpl_element_id"): row for row in rows if isinstance(row, dict)}
    for player_id in xi:
        element_type = by_id.get(player_id, {}).get("element_type")
        if element_type == 1:
            starting_goalkeepers += 1
            continue
        position = {2: "DEF", 3: "MID", 4: "FWD"}.get(element_type)
        if position is None:
            raise LiveM4ReplayError("official starting XI has an invalid position")
        formation_counts[position] += 1
    if starting_goalkeepers != 1 or sum(formation_counts.values()) != 10 or min(formation_counts.values()) < 1:
        raise LiveM4ReplayError("official starting XI does not form a legal FPL formation")
    captain = previous.get("captain_id")
    vice = previous.get("vice_captain_id")
    if not isinstance(captain, int) or not isinstance(vice, int) or captain == vice:
        raise LiveM4ReplayError("official captain/vice-captain state is incomplete")
    if chip_state != "NONE":
        raise LiveM4ReplayError("the initial M3/M4 contract currently supports chip_state NONE only")
    return {
        "squad_15": list(squad),
        "bank": float(bank),
        "free_transfers": derive_free_transfers(history, int(manager_snapshot["target_gameweek"])),
        "formation": f"{formation_counts['DEF']}-{formation_counts['MID']}-{formation_counts['FWD']}",
        "starting_xi": list(xi),
        "bench_order": list(bench),
        "reserve_goalkeeper_id": reserve_gk,
        "captain_id": captain,
        "vice_captain_id": vice,
        "chip_state": chip_state,
    }


def run_live_fplcat_m4(
    *,
    capture: Mapping[str, Any],
    manager_snapshot: Mapping[str, Any],
    chip_state: str = "NONE",
    software_commit: str | None = None,
) -> dict[str, Any]:
    archives = manager_snapshot.get("source_archives")
    if not isinstance(archives, Mapping) or not isinstance(archives.get("history"), Mapping):
        raise LiveM4ReplayError("manager snapshot does not include official history archive")
    history = json.loads(archives["history"]["raw_json"])
    target_gameweek = int(manager_snapshot["target_gameweek"])
    manager_state = build_manager_state(manager_snapshot, history, chip_state=chip_state)

    captured = capture_predeadline_decision_bundle(
        team_id=int(manager_snapshot["manager_team_id"]),
        gameweek=target_gameweek,
        season=str(capture.get("provider_snapshot", {}).get("season", "")),
        manager_state=manager_state,
        provider_capture_override=capture,
    )
    manifest = captured[str(target_gameweek)]
    if manifest["manager_state"]["free_transfers"] != manager_state["free_transfers"]:
        raise LiveM4ReplayError("manager FT state changed during capture")
    if set(manifest["manager_state"]["squad_15"]) != set(manager_state["squad_15"]):
        raise LiveM4ReplayError("manager squad changed during capture")

    m3 = run_predeadline_m3_decision(
        captured,
        software_commit=software_commit or os.environ.get("GITHUB_SHA", "unavailable"),
    )
    state = manifest["manager_state"]
    squad_snapshot = [
        {
            "fpl_element_id": player_id,
            "purchase_price": state["purchase_prices"][str(player_id)],
        }
        for player_id in state["squad_15"]
    ]
    engine_payload = {
        "provider_snapshot": manifest["provider_snapshot"],
        "player_metadata": manifest["player_metadata"],
        "player_metadata_provenance": manifest["player_metadata_provenance"],
        "manager_context": {
            "squad_snapshot": squad_snapshot,
            "bank": state["bank"],
            "free_transfers": state["free_transfers"],
            "personal_risk_profile": "aggressive",
            "formation": state["formation"],
            "starting_xi": state["starting_xi"],
            "bench_order": state["bench_order"],
            "personal_preferences": {},
        },
        "as_of_utc": manifest["decision_as_of_utc"],
    }
    engine_run = run_external_benchmark_personal_squad(engine_payload)
    product = build_personal_squad_product(engine_run)

    m3_transfer = m3["recommendation"]["transfer_recommendation"]
    m4_transfer = product["decision"]
    m3_candidate = m3_transfer.get("best_candidate")
    m4_candidate = m4_transfer.get("best_transfer")
    if m3_transfer["action"] != m4_transfer["action"]:
        raise LiveM4ReplayError("M3 frozen action and M4 product action differ")
    if (m3_candidate or {}).get("transfer_in_id") != (m4_candidate or {}).get("transfer_in_id"):
        raise LiveM4ReplayError("M3 and M4 incoming transfer candidates differ")
    if (m3_candidate or {}).get("transfer_out_id") != (m4_candidate or {}).get("transfer_out_id"):
        raise LiveM4ReplayError("M3 and M4 outgoing transfer candidates differ")

    return {
        "replay_contract_version": "1.0.0",
        "replay_status": "LIVE_MANAGER_M3_M4_CONVENTIONAL_RECOMMENDATION_PASSED",
        "manager_state_basis": {
            "manager_team_id": manager_snapshot["manager_team_id"],
            "target_gameweek": target_gameweek,
            "squad_ids": state["squad_15"],
            "bank": state["bank"],
            "free_transfers": state["free_transfers"],
            "formation_baseline": state["formation"],
            "lineup_baseline_source": f"OFFICIAL_GW{target_gameweek - 1}_PICKS_CARRIED_FORWARD",
            "target_gameweek_transfers_at_snapshot": 0,
            "chip_state": chip_state,
            "chip_state_note": "NONE is an explicit workflow assumption; public previous-GW picks cannot expose an unsaved upcoming chip selection.",
        },
        "m3_frozen_recommendation": m3,
        "m4_conventional_product": product,
        "m3_m4_action_consistent": True,
        "limitations": [
            "The starting XI, bench order and captaincy baseline are carried forward from the previous official Gameweek picks; the M4 engine may recommend changes.",
            "A chip selection not yet saved/confirmed in the public FPL API cannot be independently observed.",
            "M2 forecast validation and M4 outcome evaluation remain pending.",
            "The product remains exploratory and is not release-eligible.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--manager-snapshot", type=Path, required=True)
    parser.add_argument("--chip-state", choices=["NONE"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    capture = json.loads(args.capture.read_text(encoding="utf-8"))
    manager_snapshot = json.loads(args.manager_snapshot.read_text(encoding="utf-8"))
    result = run_live_fplcat_m4(
        capture=capture,
        manager_snapshot=manager_snapshot,
        chip_state=args.chip_state,
        software_commit=os.environ.get("GITHUB_SHA"),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    m4 = result["m4_conventional_product"]
    transfer = m4["decision"]
    candidate = transfer.get("best_transfer") or {}
    print(json.dumps({
        "replay_status": result["replay_status"],
        "manager_team_id": result["manager_state_basis"]["manager_team_id"],
        "target_gameweek": result["manager_state_basis"]["target_gameweek"],
        "bank": result["manager_state_basis"]["bank"],
        "free_transfers": result["manager_state_basis"]["free_transfers"],
        "action": transfer["action"],
        "transfer_out_id": candidate.get("transfer_out_id"),
        "transfer_in_id": candidate.get("transfer_in_id"),
        "product_id": m4["product_id"],
        "decision_basis": transfer["basis"],
        "release_eligible": m4["release_eligible"],
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
