#!/usr/bin/env python3
"""Fail-closed evaluation contract and deterministic FPL squad scorer.

The first release is exercised only with explicitly labelled synthetic fixtures.
It scores a frozen recommendation against a no-transfer hold baseline using
official realised player points/minutes and FPL-style autosub/captain rules.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

CONTRACT_VERSION = "0.1.0"
POSITIONS = ("GKP", "DEF", "MID", "FWD")
LEGAL_FORMATIONS = {
    f"{d}-{m}-{f}"
    for d in range(3, 6)
    for m in range(2, 6)
    for f in range(1, 4)
    if d + m + f == 10
}


class DecisionEvaluationError(ValueError):
    """Raised when evaluation evidence or a decision plan is invalid."""


def _fail(message: str) -> None:
    raise DecisionEvaluationError(message)


def _timestamp(value: Any, name: str) -> datetime:
    if not isinstance(value, str):
        _fail(f"{name} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DecisionEvaluationError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        _fail(f"{name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _finite_number(value: Any, name: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        _fail(f"{name} must be a finite number")
    result = float(value)
    if minimum is not None and result < minimum:
        _fail(f"{name} must be at least {minimum}")
    return result


def _positive_ids(values: Any, name: str, expected: int) -> list[int]:
    if not isinstance(values, list) or len(values) != expected:
        _fail(f"{name} must contain exactly {expected} player IDs")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in values):
        _fail(f"{name} must contain positive integer player IDs")
    if len(set(values)) != expected:
        _fail(f"{name} must contain unique player IDs")
    return list(values)


def _verify_source_archive(source: Mapping[str, Any], index: int) -> None:
    required = ("source_type", "source_url", "raw_snapshot_id", "raw_sha256",
                "captured_at_utc", "raw_payload_base64")
    missing = [key for key in required if key not in source]
    if missing:
        _fail(f"source_archives[{index}] missing fields: {', '.join(missing)}")
    if not all(isinstance(source[key], str) and source[key].strip() for key in required):
        _fail(f"source_archives[{index}] required fields must be non-empty strings")
    digest = source["raw_sha256"].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        _fail(f"source_archives[{index}].raw_sha256 must be SHA-256")
    try:
        raw = base64.b64decode(source["raw_payload_base64"], validate=True)
    except (ValueError, TypeError) as exc:
        raise DecisionEvaluationError(f"source_archives[{index}] raw payload is invalid base64") from exc
    if hashlib.sha256(raw).hexdigest() != digest:
        _fail(f"source_archives[{index}] raw payload SHA-256 mismatch")
    _timestamp(source["captured_at_utc"], f"source_archives[{index}].captured_at_utc")


def _validate_evidence(record: Mapping[str, Any]) -> None:
    required = ("evidence_class", "target_gameweek", "deadline_utc", "as_of_utc",
                "season", "provider_identity", "software_commit", "source_archives")
    missing = [key for key in required if key not in record]
    if missing:
        _fail("evaluation record missing fields: " + ", ".join(missing))
    if record["evidence_class"] not in {"SYNTHETIC_TEST", "REAL_CANDIDATE"}:
        _fail("evidence_class must be SYNTHETIC_TEST or REAL_CANDIDATE")
    if isinstance(record["target_gameweek"], bool) or not isinstance(record["target_gameweek"], int) or record["target_gameweek"] < 1:
        _fail("target_gameweek must be a positive integer")
    if not isinstance(record["season"], str) or not record["season"].strip():
        _fail("season must be a non-empty string")
    if not isinstance(record["software_commit"], str) or not re.fullmatch(r"[0-9a-f]{40,64}", record["software_commit"]):
        _fail("software_commit must be a full hexadecimal commit hash")
    if not isinstance(record["provider_identity"], Mapping):
        _fail("provider_identity must be an object")
    for key in ("name", "product", "variant"):
        if not isinstance(record["provider_identity"].get(key), str) or not record["provider_identity"][key].strip():
            _fail(f"provider_identity.{key} must be a non-empty string")

    deadline = _timestamp(record["deadline_utc"], "deadline_utc")
    as_of = _timestamp(record["as_of_utc"], "as_of_utc")
    if as_of >= deadline:
        _fail("decision as_of_utc must be strictly before the FPL deadline")

    archives = record["source_archives"]
    if not isinstance(archives, list) or len(archives) < 4:
        _fail("source_archives must include provider, player_metadata, manager_state and realised_points archives")
    by_type: dict[str, Mapping[str, Any]] = {}
    for index, source in enumerate(archives):
        if not isinstance(source, Mapping):
            _fail(f"source_archives[{index}] must be an object")
        _verify_source_archive(source, index)
        source_type = source["source_type"]
        if source_type in by_type:
            _fail(f"duplicate source archive type: {source_type}")
        by_type[source_type] = source
        captured = _timestamp(source["captured_at_utc"], f"{source_type}.captured_at_utc")
        if source_type == "realised_points":
            if captured <= deadline:
                _fail("realised_points archive must be captured after the FPL deadline")
        else:
            if captured >= deadline:
                _fail(f"{source_type} archive was captured at or after the deadline")
            if captured > as_of:
                _fail(f"{source_type} archive was captured after decision as_of_utc")
    for source_type in ("provider", "player_metadata", "manager_state", "realised_points"):
        if source_type not in by_type:
            _fail(f"missing {source_type} source archive")
    provider = by_type["provider"]
    if "generated_at_utc" not in provider:
        _fail("provider archive requires generated_at_utc")
    generated = _timestamp(provider["generated_at_utc"], "provider.generated_at_utc")
    captured = _timestamp(provider["captured_at_utc"], "provider.captured_at_utc")
    if generated >= deadline:
        _fail("provider generation must be strictly before deadline")
    if generated > captured:
        _fail("provider generation cannot be later than provider capture")


def _validate_roster(roster: Any, name: str) -> tuple[dict[int, Mapping[str, Any]], dict[str, int]]:
    if not isinstance(roster, list) or len(roster) != 15:
        _fail(f"{name} must contain exactly 15 player records")
    by_id: dict[int, Mapping[str, Any]] = {}
    counts = {position: 0 for position in POSITIONS}
    for index, player in enumerate(roster):
        if not isinstance(player, Mapping):
            _fail(f"{name}[{index}] must be an object")
        player_id = player.get("fpl_element_id")
        if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id < 1:
            _fail(f"{name}[{index}].fpl_element_id must be a positive integer")
        if player_id in by_id:
            _fail(f"{name} contains duplicate player ID {player_id}")
        position = player.get("position")
        if position not in POSITIONS:
            _fail(f"{name}[{index}].position is invalid")
        team_id = player.get("team_id")
        if isinstance(team_id, bool) or not isinstance(team_id, int) or team_id < 1:
            _fail(f"{name}[{index}].team_id must be a positive integer")
        for price_field in ("purchase_price", "current_price"):
            _finite_number(player.get(price_field), f"{name}[{index}].{price_field}", 0.1)
        counts[position] += 1
        by_id[player_id] = player
    expected = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
    if counts != expected:
        _fail(f"{name} must have FPL squad composition {expected}")
    team_counts: dict[int, int] = {}
    for player in roster:
        team_counts[player["team_id"]] = team_counts.get(player["team_id"], 0) + 1
    if any(count > 3 for count in team_counts.values()):
        _fail(f"{name} exceeds the three-player-per-club limit")
    return by_id, counts


def _validate_plan(plan: Any, roster_by_id: Mapping[int, Mapping[str, Any]], name: str) -> dict[str, Any]:
    if not isinstance(plan, Mapping):
        _fail(f"{name} must be an object")
    squad_ids = _positive_ids(plan.get("squad_ids"), f"{name}.squad_ids", 15)
    if set(squad_ids) != set(roster_by_id):
        _fail(f"{name}.squad_ids must exactly match the 15-player roster")
    xi = _positive_ids(plan.get("starting_xi"), f"{name}.starting_xi", 11)
    bench = _positive_ids(plan.get("bench_order"), f"{name}.bench_order", 3)
    reserve_gk = plan.get("reserve_goalkeeper_id")
    captain = plan.get("captain_id")
    vice = plan.get("vice_captain_id")
    for value, field in ((reserve_gk, "reserve_goalkeeper_id"), (captain, "captain_id"), (vice, "vice_captain_id")):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            _fail(f"{name}.{field} must be a positive integer")
    if set(xi) & set(bench) or set(xi) & {reserve_gk} or set(bench) & {reserve_gk}:
        _fail(f"{name} starting XI, bench and reserve goalkeeper must be disjoint")
    if set(xi) | set(bench) | {reserve_gk} != set(squad_ids):
        _fail(f"{name} must account for all 15 squad players exactly once")
    if roster_by_id[reserve_gk]["position"] != "GKP":
        _fail(f"{name}.reserve_goalkeeper_id must identify a goalkeeper")
    if sum(roster_by_id[player_id]["position"] == "GKP" for player_id in xi) != 1:
        _fail(f"{name}.starting_xi must contain exactly one goalkeeper")
    if any(roster_by_id[player_id]["position"] == "GKP" for player_id in bench):
        _fail(f"{name}.bench_order must contain outfield players only")
    if captain not in xi or vice not in xi or captain == vice:
        _fail(f"{name} captain and vice-captain must be distinct starting XI players")
    counts = {position: sum(roster_by_id[player_id]["position"] == position for player_id in xi)
              for position in ("DEF", "MID", "FWD")}
    formation = "-".join(str(counts[position]) for position in ("DEF", "MID", "FWD"))
    if formation not in LEGAL_FORMATIONS:
        _fail(f"{name}.starting_xi has an illegal FPL formation")
    if plan.get("formation") != formation:
        _fail(f"{name}.formation does not match its starting XI")
    return {
        "squad_ids": squad_ids, "starting_xi": xi, "bench_order": bench,
        "reserve_goalkeeper_id": reserve_gk, "captain_id": captain,
        "vice_captain_id": vice, "formation": formation,
    }


def _score_plan(plan: Mapping[str, Any], roster_by_id: Mapping[int, Mapping[str, Any]],
                realised: Mapping[int, Mapping[str, Any]]) -> dict[str, Any]:
    xi = list(plan["starting_xi"])
    on_pitch = list(xi)
    absent = [player_id for player_id in xi if realised[player_id]["minutes"] == 0]
    starting_gk = next(player_id for player_id in xi if roster_by_id[player_id]["position"] == "GKP")
    if starting_gk in absent:
        reserve_gk = plan["reserve_goalkeeper_id"]
        if realised[reserve_gk]["minutes"] > 0:
            on_pitch[on_pitch.index(starting_gk)] = reserve_gk
        absent.remove(starting_gk)

    substitutions: list[dict[str, int]] = []
    outfield_absent = [player_id for player_id in absent if roster_by_id[player_id]["position"] != "GKP"]
    for bench_id in plan["bench_order"]:
        if realised[bench_id]["minutes"] <= 0 or not outfield_absent:
            continue
        bench_position = roster_by_id[bench_id]["position"]
        chosen = None
        for missing_id in outfield_absent:
            trial = [player_id for player_id in on_pitch if player_id != missing_id] + [bench_id]
            trial_counts = {position: sum(roster_by_id[player_id]["position"] == position for player_id in trial)
                            for position in ("DEF", "MID", "FWD")}
            trial_formation = "-".join(str(trial_counts[position]) for position in ("DEF", "MID", "FWD"))
            if trial_formation in LEGAL_FORMATIONS:
                chosen = missing_id
                break
        if chosen is None:
            continue
        on_pitch[on_pitch.index(chosen)] = bench_id
        outfield_absent.remove(chosen)
        substitutions.append({"player_out_id": chosen, "player_in_id": bench_id})

    gross = sum(realised[player_id]["total_points"] for player_id in on_pitch)
    captain_id = plan["captain_id"]
    vice_id = plan["vice_captain_id"]
    effective_captain = captain_id if realised[captain_id]["minutes"] > 0 else (
        vice_id if realised[vice_id]["minutes"] > 0 else None
    )
    captain_bonus = realised[effective_captain]["total_points"] if effective_captain is not None else 0.0
    return {
        "gross_points": gross + captain_bonus,
        "starting_xi_ids": xi,
        "on_pitch_ids_after_substitutions": on_pitch,
        "outfield_substitutions": substitutions,
        "goalkeeper_substitution": (
            {"player_out_id": starting_gk, "player_in_id": plan["reserve_goalkeeper_id"]}
            if starting_gk not in on_pitch else None
        ),
        "effective_captain_id": effective_captain,
        "captain_bonus_points": captain_bonus,
    }


def evaluate_decision_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a frozen record and score recommended plan against hold baseline."""
    if not isinstance(record, Mapping):
        _fail("evaluation record must be an object")
    _validate_evidence(record)
    if record["evidence_class"] != "SYNTHETIC_TEST":
        _fail("REAL_CANDIDATE records are blocked until independent historical-evidence admission is implemented")
    manager = record.get("manager_state")
    if not isinstance(manager, Mapping):
        _fail("manager_state must be an object")
    for field in ("bank", "free_transfers"):
        if field not in manager:
            _fail(f"manager_state missing {field}")
    _finite_number(manager["bank"], "manager_state.bank", 0)
    if isinstance(manager["free_transfers"], bool) or not isinstance(manager["free_transfers"], int) or manager["free_transfers"] < 0:
        _fail("manager_state.free_transfers must be a non-negative integer")
    if manager.get("chip") not in (None, "NONE"):
        _fail("chip scoring is outside the initial M3 evaluation harness")
    manager_roster, _ = _validate_roster(manager.get("squad_snapshot"), "manager_state.squad_snapshot")
    manager_plan = _validate_plan(manager.get("hold_plan"), manager_roster, "manager_state.hold_plan")

    decision = record.get("frozen_decision")
    if not isinstance(decision, Mapping):
        _fail("frozen_decision must be an object")
    decision_body = {key: value for key, value in decision.items() if key != "decision_sha256"}
    expected_decision_hash = hashlib.sha256(
        json.dumps(decision_body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    if decision.get("decision_sha256") != expected_decision_hash:
        _fail("frozen_decision decision_sha256 mismatch")
    if decision.get("action") not in {"HOLD", "TRANSFER"}:
        _fail("frozen_decision.action must be HOLD or TRANSFER")
    plan = _validate_plan(decision.get("squad_plan"), manager_roster if decision["action"] == "HOLD" else
                          _post_transfer_roster(manager_roster, decision), "frozen_decision.squad_plan")
    hit_points = _finite_number(decision.get("transfer_hit_points"), "frozen_decision.transfer_hit_points", 0)
    if decision["action"] == "HOLD":
        if decision.get("transfer_out_id") is not None or decision.get("transfer_in_id") is not None:
            _fail("HOLD decision must not contain transfer player IDs")
        if hit_points != 0:
            _fail("HOLD decision cannot incur a transfer hit")
        if set(plan["squad_ids"]) != set(manager_roster):
            _fail("HOLD decision must preserve the manager's 15-player squad")
    else:
        out_id = decision.get("transfer_out_id")
        in_id = decision.get("transfer_in_id")
        if out_id not in manager_roster or in_id in manager_roster:
            _fail("TRANSFER must name one owned outgoing and one unowned incoming player")
        expected_hit = 0 if manager["free_transfers"] > 0 else 4
        if hit_points != expected_hit:
            _fail(f"one-transfer hit must be {expected_hit} under the captured free-transfer count")
        if decision.get("incoming_player") is None:
            _fail("TRANSFER requires incoming_player metadata")
        incoming = decision["incoming_player"]
        if not isinstance(incoming, Mapping) or incoming.get("fpl_element_id") != in_id:
            _fail("incoming_player metadata must match transfer_in_id")
        if incoming.get("position") != manager_roster[out_id]["position"]:
            _fail("transfer must preserve player position")
        if isinstance(incoming.get("team_id"), bool) or not isinstance(incoming.get("team_id"), int) or incoming.get("team_id") < 1:
            _fail("incoming player team metadata is invalid")
        for price_field in ("purchase_price", "current_price"):
            _finite_number(incoming.get(price_field), f"incoming_player.{price_field}", 0.1)
        if set(plan["squad_ids"]) != (set(manager_roster) - {out_id}) | {in_id}:
            _fail("post-transfer plan must replace exactly the outgoing player with the incoming player")
        if plan["reserve_goalkeeper_id"] != manager_plan["reserve_goalkeeper_id"]:
            _fail("the designated reserve goalkeeper cannot change in the initial manager strategy")
        if manager_roster[manager_plan["starting_xi"][0]]["position"] == "GKP":
            starting_gk = next(pid for pid in manager_plan["starting_xi"] if manager_roster[pid]["position"] == "GKP")
        else:
            starting_gk = next(pid for pid in manager_plan["starting_xi"] if manager_roster[pid]["position"] == "GKP")
        if starting_gk not in plan["starting_xi"]:
            _fail("the designated starting goalkeeper must remain in the post-transfer XI")
        if out_id in manager_plan["starting_xi"]:
            expected_xi = (set(manager_plan["starting_xi"]) - {out_id}) | {in_id}
            if set(plan["starting_xi"]) != expected_xi:
                _fail("a starter transfer must replace only the outgoing starter in the fixed XI")
        else:
            if in_id not in plan["starting_xi"]:
                _fail("a bench transfer must improve the starting XI by promoting the incoming player")
            removed = set(manager_plan["starting_xi"]) - set(plan["starting_xi"])
            expected_xi = (set(manager_plan["starting_xi"]) - removed) | {in_id}
            if len(removed) != 1 or set(plan["starting_xi"]) != expected_xi:
                _fail("a bench transfer must replace exactly one outfield starter")
            removed_id = next(iter(removed))
            if manager_roster[removed_id]["position"] != incoming["position"]:
                _fail("a bench transfer must replace a starter in the incoming player's position")
        combined = {**manager_roster, in_id: incoming}
        _validate_roster([combined[player_id] for player_id in plan["squad_ids"]], "post-transfer roster")
    if plan["reserve_goalkeeper_id"] != manager_plan["reserve_goalkeeper_id"]:
        _fail("reserve goalkeeper must remain fixed")
    if next(pid for pid in plan["starting_xi"] if (manager_roster.get(pid) or decision.get("incoming_player", {})).get("position") == "GKP") != next(
        pid for pid in manager_plan["starting_xi"] if manager_roster[pid]["position"] == "GKP"
    ):
        _fail("starting goalkeeper must remain fixed")

    realised_rows = record.get("realised_player_points")
    expected_row_count = 15 if decision["action"] == "HOLD" else 16
    if not isinstance(realised_rows, list) or len(realised_rows) != expected_row_count:
        _fail(f"realised_player_points must contain exactly {expected_row_count} player rows")
    realised: dict[int, dict[str, float]] = {}
    for index, row in enumerate(realised_rows):
        if not isinstance(row, Mapping):
            _fail(f"realised_player_points[{index}] must be an object")
        player_id = row.get("fpl_element_id")
        if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id < 1 or player_id in realised:
            _fail(f"realised_player_points[{index}] has invalid or duplicate player ID")
        points = _finite_number(row.get("total_points"), f"realised_player_points[{index}].total_points")
        minutes = _finite_number(row.get("minutes"), f"realised_player_points[{index}].minutes", 0)
        if minutes != int(minutes):
            _fail(f"realised_player_points[{index}].minutes must be an integer")
        realised[player_id] = {"total_points": points, "minutes": minutes}
    expected_ids = set(manager_roster) if decision["action"] == "HOLD" else (
        set(manager_roster) | {decision["transfer_in_id"]}
    )
    if set(realised) != expected_ids:
        _fail("realised points must cover the complete decision cohort (15 hold players or 16 transfer-comparison players)")

    hold_score = _score_plan(manager_plan, manager_roster, realised)
    if decision["action"] == "TRANSFER":
        scoring_roster = _post_transfer_roster(manager_roster, decision)
    else:
        scoring_roster = manager_roster
    recommendation_score = _score_plan(plan, scoring_roster, realised)
    net_recommended = recommendation_score["gross_points"] - hit_points
    net_hold = hold_score["gross_points"]
    return {
        "evaluation_contract_version": CONTRACT_VERSION,
        "evidence_class": "SYNTHETIC_TEST",
        "evaluation_status": "SYNTHETIC_ONLY_NOT_HISTORICAL_EVIDENCE",
        "target_gameweek": record["target_gameweek"],
        "provider_identity": dict(record["provider_identity"]),
        "recommended_action": decision["action"],
        "recommended": {**recommendation_score, "transfer_hit_points": hit_points, "net_points": net_recommended},
        "hold": {**hold_score, "transfer_hit_points": 0.0, "net_points": net_hold},
        "net_points_delta_vs_hold": net_recommended - net_hold,
        "historical_performance_validated": False,
    }


def _post_transfer_roster(roster_by_id: Mapping[int, Mapping[str, Any]], decision: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    out_id = decision.get("transfer_out_id")
    in_id = decision.get("transfer_in_id")
    incoming = decision.get("incoming_player")
    if out_id not in roster_by_id or isinstance(in_id, bool) or not isinstance(in_id, int) or in_id < 1:
        _fail("transfer player IDs are invalid")
    if not isinstance(incoming, Mapping) or incoming.get("fpl_element_id") != in_id:
        _fail("incoming_player metadata is missing or mismatched")
    result = dict(roster_by_id)
    del result[out_id]
    result[in_id] = incoming
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evaluation_record", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    record = json.loads(args.evaluation_record.read_text(encoding="utf-8"))
    result = evaluate_decision_record(record)
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
