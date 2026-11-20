#!/usr/bin/env python3
"""Fail-closed acceptance contract for the initial conventional M5 product."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


class M5DeliveryContractError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise M5DeliveryContractError("decision payload is not canonical JSON") from exc


def _utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise M5DeliveryContractError(f"{label} is required")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise M5DeliveryContractError(f"{label} must be ISO-8601") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise M5DeliveryContractError(f"{label} must include a timezone")
    return result


def _ids(values: Any, label: str, expected: int) -> list[int]:
    if not isinstance(values, list) or len(values) != expected:
        raise M5DeliveryContractError(f"{label} must contain exactly {expected} player IDs")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in values):
        raise M5DeliveryContractError(f"{label} contains an invalid player ID")
    if len(set(values)) != len(values):
        raise M5DeliveryContractError(f"{label} contains duplicate player IDs")
    return values


def validate_conventional_m5_output(output: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an M3 frozen decision for conventional-only M5 presentation.

    This checks delivery integrity, not recommendation quality or release
    eligibility. The existing M3 engine remains the source of decision logic.
    """
    if not isinstance(output, Mapping):
        raise M5DeliveryContractError("M3 output must be an object")
    if output.get("run_type") != "M3_CONVENTIONAL_PERSONAL_SQUAD_RECOMMENDATION":
        raise M5DeliveryContractError("only the conventional personal-squad M3 product is admitted")
    if output.get("release_eligible") is not False:
        raise M5DeliveryContractError("M3 output must retain its explicit non-release-eligible status")
    if output.get("recommendation_status") != "EXPLORATORY_ONLY":
        raise M5DeliveryContractError("conventional benchmark status must remain EXPLORATORY_ONLY")
    for key in ("manager_team_id", "target_gameweek", "decision_as_of_utc", "deadline_utc",
                "provider_identity", "provider_snapshot_id", "recommendation",
                "frozen_decision", "evaluation_candidate", "release_blockers"):
        if key not in output:
            raise M5DeliveryContractError(f"M3 output missing required field: {key}")

    if isinstance(output["manager_team_id"], bool) or not isinstance(output["manager_team_id"], int):
        raise M5DeliveryContractError("manager_team_id must be an integer")
    if isinstance(output["target_gameweek"], bool) or not isinstance(output["target_gameweek"], int):
        raise M5DeliveryContractError("target_gameweek must be an integer")
    decision_at = _utc(output["decision_as_of_utc"], "decision_as_of_utc")
    deadline = _utc(output["deadline_utc"], "deadline_utc")
    if not decision_at < deadline:
        raise M5DeliveryContractError("decision timestamp must be strictly before deadline")

    provider = output["provider_identity"]
    if not isinstance(provider, Mapping) or any(
        not isinstance(provider.get(key), str) or not provider[key].strip()
        for key in ("name", "product", "variant")
    ):
        raise M5DeliveryContractError("provider identity must preserve name, product and variant")
    if not isinstance(output["provider_snapshot_id"], str) or not output["provider_snapshot_id"]:
        raise M5DeliveryContractError("provider_snapshot_id must be non-empty")

    recommendation = output["recommendation"]
    if not isinstance(recommendation, Mapping):
        raise M5DeliveryContractError("recommendation must be an object")
    transfer = recommendation.get("transfer_recommendation")
    if not isinstance(transfer, Mapping):
        raise M5DeliveryContractError("transfer_recommendation is missing")
    if transfer.get("alternatives_suppressed") is not True or "alternatives" in transfer:
        raise M5DeliveryContractError("M5 presentation must suppress alternatives and expose only the frozen best action")
    decision = output["frozen_decision"]
    candidate = output["evaluation_candidate"]
    if not isinstance(decision, Mapping) or not isinstance(candidate, Mapping):
        raise M5DeliveryContractError("frozen decision and evaluation candidate must be objects")
    digest = decision.get("decision_sha256")
    body = {key: value for key, value in decision.items() if key != "decision_sha256"}
    expected_digest = hashlib.sha256(_canonical(body)).hexdigest()
    if digest != expected_digest:
        raise M5DeliveryContractError("frozen decision SHA-256 does not match its content")
    if _canonical(candidate.get("frozen_decision")) != _canonical(dict(decision)):
        raise M5DeliveryContractError("evaluation candidate is detached from the frozen decision")
    for key, expected in (
        ("manager_team_id", output["manager_team_id"]),
        ("target_gameweek", output["target_gameweek"]),
        ("deadline_utc", output["deadline_utc"]),
        ("as_of_utc", output["decision_as_of_utc"]),
    ):
        if candidate.get(key) != expected:
            raise M5DeliveryContractError(f"evaluation candidate {key} differs from top-level M3 output")

    manager_state = candidate.get("manager_state")
    if not isinstance(manager_state, Mapping):
        raise M5DeliveryContractError("evaluation candidate manager_state is missing")
    roster = manager_state.get("squad_snapshot")
    if not isinstance(roster, list) or len(roster) != 15:
        raise M5DeliveryContractError("original manager squad snapshot must contain 15 players")
    roster_by_id = {}
    for row in roster:
        if not isinstance(row, Mapping):
            raise M5DeliveryContractError("manager squad rows must be objects")
        player_id = row.get("fpl_element_id")
        if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id in roster_by_id:
            raise M5DeliveryContractError("manager squad has invalid or duplicate player IDs")
        roster_by_id[player_id] = row
        if row.get("purchase_price") is None or row.get("current_price") is None:
            raise M5DeliveryContractError(f"manager player {player_id} lacks purchase/current price")

    action = decision.get("action")
    if action not in {"HOLD", "TRANSFER"} or transfer.get("action") != action:
        raise M5DeliveryContractError("recommendation action differs from frozen HOLD/TRANSFER decision")
    original_ids = set(roster_by_id)
    if action == "HOLD":
        if decision.get("transfer_out_id") is not None or decision.get("transfer_in_id") is not None:
            raise M5DeliveryContractError("HOLD must not contain transfer player IDs")
        if decision.get("incoming_player") is not None:
            raise M5DeliveryContractError("HOLD must not contain an incoming player")
        expected_squad = original_ids
    else:
        outgoing, incoming = decision.get("transfer_out_id"), decision.get("transfer_in_id")
        if outgoing not in original_ids or isinstance(incoming, bool) or not isinstance(incoming, int) or incoming in original_ids:
            raise M5DeliveryContractError("TRANSFER must sell one owned player and buy one non-owned player")
        incoming_player = decision.get("incoming_player")
        if not isinstance(incoming_player, Mapping) or incoming_player.get("fpl_element_id") != incoming:
            raise M5DeliveryContractError("incoming player metadata does not match transfer_in_id")
        expected_squad = (original_ids - {outgoing}) | {incoming}

    plan = decision.get("squad_plan")
    if not isinstance(plan, Mapping):
        raise M5DeliveryContractError("frozen decision squad_plan is missing")
    squad_ids = set(_ids(plan.get("squad_ids"), "post-decision squad_ids", 15))
    if squad_ids != expected_squad:
        raise M5DeliveryContractError("post-decision 15-player squad does not match frozen transfer action")
    xi = _ids(plan.get("starting_xi"), "starting_xi", 11)
    bench = _ids(plan.get("bench_order"), "bench_order", 3)
    reserve_gk = plan.get("reserve_goalkeeper_id")
    captain, vice = plan.get("captain_id"), plan.get("vice_captain_id")
    if set(xi) & set(bench) or set(xi) & {reserve_gk} or set(bench) & {reserve_gk}:
        raise M5DeliveryContractError("XI, outfield bench and reserve goalkeeper must be disjoint")
    if set(xi) | set(bench) | {reserve_gk} != squad_ids:
        raise M5DeliveryContractError("XI, bench and reserve goalkeeper must cover the full 15-player squad")
    if reserve_gk not in squad_ids or captain not in xi or vice not in xi or captain == vice:
        raise M5DeliveryContractError("reserve goalkeeper/captain/vice-captain plan is invalid")
    formation = plan.get("formation")
    if not isinstance(formation, str) or formation not in {
        "3-4-3", "3-5-2", "4-3-3", "4-4-2", "4-5-1",
        "5-2-3", "5-3-2", "5-4-1",
    }:
        raise M5DeliveryContractError("formation is not a supported legal FPL formation")
    if plan.get("squad_ids") != sorted(squad_ids):
        raise M5DeliveryContractError("squad_ids must be sorted for deterministic output")

    blockers = output["release_blockers"]
    if not isinstance(blockers, list) or not blockers or any(not isinstance(item, str) or not item for item in blockers):
        raise M5DeliveryContractError("release blockers must remain explicit")
    return {
        "status": "PASS_CONVENTIONAL_M5_DELIVERY_CONTRACT",
        "manager_team_id": output["manager_team_id"],
        "target_gameweek": output["target_gameweek"],
        "provider": dict(provider),
        "action": action,
        "decision_sha256": digest,
        "squad_player_count": len(squad_ids),
        "starting_xi_count": len(xi),
        "bench_count": len(bench),
        "formation": formation,
        "captain_id": captain,
        "vice_captain_id": vice,
        "release_eligible": False,
        "release_blockers": list(blockers),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.input.read_text(encoding="utf-8"))
    result = validate_conventional_m5_output(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
                           encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
