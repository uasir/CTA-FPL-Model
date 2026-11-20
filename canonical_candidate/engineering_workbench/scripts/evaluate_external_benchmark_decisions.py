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
    required = ("evidence_class", "manager_team_id", "target_gameweek", "deadline_utc", "as_of_utc",
                "season", "provider_snapshot_id", "provider_identity",
                "decision_contract_version", "software_commit", "source_archives")
    missing = [key for key in required if key not in record]
    if missing:
        _fail("evaluation record missing fields: " + ", ".join(missing))
    if not isinstance(record["evidence_class"], str) or record["evidence_class"] not in {"SYNTHETIC_TEST", "REAL_CANDIDATE"}:
        _fail("evidence_class must be SYNTHETIC_TEST or REAL_CANDIDATE")
    if isinstance(record["target_gameweek"], bool) or not isinstance(record["target_gameweek"], int) or record["target_gameweek"] < 1:
        _fail("target_gameweek must be a positive integer")
    if isinstance(record["manager_team_id"], bool) or not isinstance(record["manager_team_id"], int) or record["manager_team_id"] < 1:
        _fail("manager_team_id must be a positive integer")
    for field in ("provider_snapshot_id", "decision_contract_version"):
        if not isinstance(record[field], str) or not record[field].strip():
            _fail(f"{field} must be a non-empty string")
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
        if source_type not in {"provider", "player_metadata", "manager_state", "realised_points"}:
            _fail(f"unsupported source archive type: {source_type}")
        if source_type in by_type:
            _fail(f"duplicate source archive type: {source_type}")
        by_type[source_type] = source
        captured = _timestamp(source["captured_at_utc"], f"{source_type}.captured_at_utc")
        if source_type == "realised_points":
            if captured <= deadline:
                _fail("realised_points archive must be captured after the FPL deadline")
            if "finalized_at_utc" not in source:
                _fail("realised_points archive requires finalized_at_utc")
            finalized = _timestamp(source["finalized_at_utc"], "realised_points.finalized_at_utc")
            if finalized <= deadline or captured < finalized:
                _fail("realised_points archive must be captured after gameweek finalization")
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


def _selling_price(current_price: float, purchase_price: float) -> float:
    current_tenths = int(round(current_price * 10))
    purchase_tenths = int(round(purchase_price * 10))
    if current_tenths <= purchase_tenths:
        return current_tenths / 10.0
    return (purchase_tenths + (current_tenths - purchase_tenths) // 2) / 10.0


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


def _played(row: Mapping[str, Any]) -> bool:
    # FPL counts a player as having played if they appeared or received a card.
    return row["minutes"] > 0 or row["yellow_cards"] > 0 or row["red_cards"] > 0


def _score_plan(plan: Mapping[str, Any], roster_by_id: Mapping[int, Mapping[str, Any]],
                realised: Mapping[int, Mapping[str, Any]]) -> dict[str, Any]:
    xi = list(plan["starting_xi"])
    on_pitch = list(xi)
    absent = [player_id for player_id in xi if not _played(realised[player_id])]
    starting_gk = next(player_id for player_id in xi if roster_by_id[player_id]["position"] == "GKP")
    if starting_gk in absent:
        reserve_gk = plan["reserve_goalkeeper_id"]
        if _played(realised[reserve_gk]):
            on_pitch[on_pitch.index(starting_gk)] = reserve_gk
        absent.remove(starting_gk)

    substitutions: list[dict[str, int]] = []
    outfield_absent = [player_id for player_id in absent if roster_by_id[player_id]["position"] != "GKP"]
    for bench_id in plan["bench_order"]:
        if not _played(realised[bench_id]) or not outfield_absent:
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
    effective_captain = captain_id if _played(realised[captain_id]) else (
        vice_id if _played(realised[vice_id]) else None
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


def _verify_real_admission(record: Mapping[str, Any], admission_report: Any,
                           audit_report: Any, batch: Any) -> None:
    """Bind a real scoring record to the independent archive/admission chain."""
    manager_id = record.get("manager_team_id")
    gameweek = record.get("target_gameweek")
    if not isinstance(admission_report, Mapping) or not isinstance(audit_report, Mapping) or not isinstance(batch, Mapping):
        _fail("REAL_CANDIDATE requires admission report, independent audit report and official batch")
    if admission_report.get("manager_team_id") != manager_id:
        _fail("admission report manager identity mismatch")
    if audit_report.get("status") != "PASSED" or audit_report.get("manager_team_id") != manager_id:
        _fail("independent archive audit is missing, failed or belongs to another manager")
    if batch.get("manager_team_id") != manager_id or batch.get("historical_evidence_admitted") is not False:
        _fail("official reconciliation batch identity or non-admission invariant mismatch")

    admission_events = admission_report.get("events")
    admitted = next((row for row in admission_events if isinstance(row, Mapping)
                     and row.get("gameweek") == gameweek), None) if isinstance(admission_events, list) else None
    if (not isinstance(admitted, Mapping)
            or admitted.get("classification") != "DECISION_BACKTEST_ELIGIBLE"
            or admitted.get("historical_evidence_admitted") is not True
            or admitted.get("official_score_reconciled") is not True):
        _fail("target Gameweek is not independently classified DECISION_BACKTEST_ELIGIBLE")

    audit_events = audit_report.get("events")
    audited = next((row for row in audit_events if isinstance(row, Mapping)
                    and row.get("gameweek") == gameweek), None) if isinstance(audit_events, list) else None
    if not isinstance(audited, Mapping) or audited.get("status") != "RECONCILED":
        _fail("target Gameweek has no independently audited official scoring reconciliation")
    recommendation = audited.get("predeadline_recommendation")
    decision = record.get("frozen_decision")
    if not isinstance(recommendation, Mapping) or not isinstance(decision, Mapping):
        _fail("frozen recommendation audit or decision is missing")
    if (recommendation.get("status") != "VERIFIED"
            or recommendation.get("execution_match") not in {"HOLD_BASELINE_MATCHED", "RECOMMENDATION_MATCHED"}
            or recommendation.get("action") != decision.get("action")
            or recommendation.get("decision_sha256") != decision.get("decision_sha256")):
        _fail("frozen decision hash/action/execution does not match the independent post-Gameweek audit")
    replay = audited.get("predeadline_replay")
    if (not isinstance(replay, Mapping)
            or replay.get("status") != "VERIFIED"
            or replay.get("replay_type") != "DETERMINISTIC_RAW_AND_CANONICAL_INPUT_REEXECUTION"
            or replay.get("decision_sha256") != decision.get("decision_sha256")
            or replay.get("raw_archive_hashes_verified") is not True
            or replay.get("software_commit") != record.get("software_commit")):
        _fail("independent audit did not verify the deterministic replay of this exact frozen decision")

    # Bind the three point-in-time inputs used by the decision to the exact raw
    # archives independently hashed by the post-Gameweek auditor. A valid hash
    # on an unrelated archive is not sufficient evidence for this decision.
    audited_sources = audited.get("decision_sources")
    if not isinstance(audited_sources, list):
        _fail("independent audit is missing point-in-time decision source archives")
    audit_by_type = {
        row.get("source_type"): row for row in audited_sources
        if isinstance(row, Mapping)
    }
    record_by_type = {
        row.get("source_type"): row for row in record.get("source_archives", [])
        if isinstance(row, Mapping)
    }
    source_type_map = {
        "provider": "provider_forecast",
        "player_metadata": "player_metadata",
        "manager_state": "manager_deadline_state",
    }
    for record_type, audit_type in source_type_map.items():
        source = record_by_type.get(record_type)
        audited_source = audit_by_type.get(audit_type)
        if not isinstance(source, Mapping) or not isinstance(audited_source, Mapping):
            _fail(f"{record_type} archive is not bound to an independently audited decision source")
        for field in ("raw_snapshot_id", "raw_sha256", "captured_at_utc", "source_url"):
            if source.get(field) != audited_source.get(field):
                _fail(f"{record_type} archive {field} does not match the independent decision-source audit")
        if record_type == "provider":
            for field in ("generated_at_utc",):
                if source.get(field) != audited_source.get(field):
                    _fail(f"provider archive {field} does not match the independent decision-source audit")
    # Bind roster and incoming-player attributes to the exact independently
    # audited official bootstrap archive, not merely to a matching archive hash.
    metadata_source = record_by_type.get("player_metadata")
    try:
        metadata_raw = base64.b64decode(metadata_source["raw_payload_base64"], validate=True)
        metadata_payload = json.loads(metadata_raw)
    except (TypeError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise DecisionEvaluationError("player-metadata archive is not valid official bootstrap JSON") from exc
    metadata_elements = metadata_payload.get("elements") if isinstance(metadata_payload, Mapping) else None
    if not isinstance(metadata_elements, list):
        _fail("player-metadata archive must contain official bootstrap elements")
    official_metadata = {}
    for index, element in enumerate(metadata_elements):
        if not isinstance(element, Mapping):
            _fail(f"official bootstrap elements[{index}] must be an object")
        player_id = element.get("id")
        if (isinstance(player_id, bool) or not isinstance(player_id, int)
                or player_id < 1 or player_id in official_metadata):
            _fail("official bootstrap archive contains invalid or duplicate player IDs")
        official_metadata[player_id] = element
    position_by_element_type = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
    evaluated_manager = record.get("manager_state")
    roster_for_metadata = evaluated_manager.get("squad_snapshot") if isinstance(evaluated_manager, Mapping) else None
    if not isinstance(roster_for_metadata, list):
        _fail("evaluation manager roster is missing for official metadata binding")
    metadata_cohort = list(roster_for_metadata)
    if decision.get("action") == "TRANSFER":
        incoming_for_metadata = decision.get("incoming_player")
        if not isinstance(incoming_for_metadata, Mapping):
            _fail("incoming player metadata is missing for official metadata binding")
        metadata_cohort.append(incoming_for_metadata)
    seen_metadata_ids = set()
    for player in metadata_cohort:
        if not isinstance(player, Mapping):
            _fail("evaluation metadata cohort contains a malformed player record")
        player_id = player.get("fpl_element_id")
        if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id < 1 or player_id in seen_metadata_ids:
            _fail("evaluation metadata cohort contains an invalid or duplicate player ID")
        seen_metadata_ids.add(player_id)
        official = official_metadata.get(player_id)
        if not isinstance(official, Mapping):
            _fail(f"player {player_id} is absent from the audited official bootstrap metadata")
        element_type = official.get("element_type")
        official_position = position_by_element_type.get(element_type)
        team_id = official.get("team")
        now_cost = official.get("now_cost")
        if (official_position is None or isinstance(team_id, bool) or not isinstance(team_id, int)
                or team_id < 1 or isinstance(now_cost, bool) or not isinstance(now_cost, int)
                or now_cost < 1):
            _fail(f"official bootstrap metadata is incomplete for player {player_id}")
        current_price = _finite_number(
            player.get("current_price"), f"evaluation current price for player {player_id}", 0.1
        )
        if (player.get("position") != official_position or player.get("team_id") != team_id
                or not math.isclose(current_price, now_cost / 10.0, abs_tol=1e-9)):
            _fail(f"evaluation position, club or current price for player {player_id} does not match official bootstrap metadata")

    # The evaluation record's hold baseline must be the exact manager state
    # sealed into the independently audited pre-deadline manager archive. Matching
    # archive hashes alone does not prevent a detached scoring roster or lineup.
    manager_source = record_by_type.get("manager_state")
    try:
        manager_raw = base64.b64decode(manager_source["raw_payload_base64"], validate=True)
        manager_envelope = json.loads(manager_raw)
    except (TypeError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise DecisionEvaluationError("manager-state archive is not valid captured JSON") from exc
    if not isinstance(manager_envelope, Mapping):
        _fail("manager-state archive envelope must be an object")
    if (manager_envelope.get("capture_kind") != "USER_ATTESTED_PREDEADLINE_MANAGER_STATE"
            or manager_envelope.get("manager_team_id") != manager_id
            or manager_envelope.get("target_gameweek") != gameweek
            or manager_envelope.get("captured_at_utc") != manager_source.get("captured_at_utc")):
        _fail("manager-state archive envelope identity or capture timestamp mismatch")
    archived_state = manager_envelope.get("manager_state")
    evaluated_state = record.get("manager_state")
    if not isinstance(archived_state, Mapping) or not isinstance(evaluated_state, Mapping):
        _fail("manager-state archive or evaluation manager_state is missing")
    roster_rows = evaluated_state.get("squad_snapshot")
    if not isinstance(roster_rows, list) or len(roster_rows) != 15 or any(
        not isinstance(row, Mapping) for row in roster_rows
    ):
        _fail("evaluation manager roster must contain 15 player records")
    roster_by_id = {}
    for row in roster_rows:
        player_id = row.get("fpl_element_id")
        if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id < 1 or player_id in roster_by_id:
            _fail("evaluation manager roster contains an invalid or duplicate player ID")
        roster_by_id[player_id] = row
    archived_squad = _positive_ids(archived_state.get("squad_15"), "archived manager squad_15", 15)
    if set(archived_squad) != set(roster_by_id):
        _fail("evaluation manager roster does not match the archived 15-player deadline squad")
    archived_bank = _finite_number(archived_state.get("bank"), "archived manager bank", 0)
    evaluated_bank = _finite_number(evaluated_state.get("bank"), "evaluation manager bank", 0)
    if not math.isclose(evaluated_bank, archived_bank, abs_tol=1e-9):
        _fail("evaluation manager_state bank does not match the archived deadline state")
    archived_ft = archived_state.get("free_transfers")
    evaluated_ft = evaluated_state.get("free_transfers")
    if (isinstance(archived_ft, bool) or not isinstance(archived_ft, int)
            or archived_ft != evaluated_ft):
        _fail("evaluation manager_state free_transfers does not match the archived deadline state")
    if (not isinstance(archived_state.get("formation"), str)
            or evaluated_state.get("formation") != archived_state.get("formation")):
        _fail("evaluation manager_state formation does not match the archived deadline state")
    if archived_state.get("chip_state") != "NONE" or evaluated_state.get("chip") not in (None, "NONE"):
        _fail("manager-state archive or evaluation record is outside the no-chip contract")
    hold_plan = evaluated_state.get("hold_plan")
    if not isinstance(hold_plan, Mapping):
        _fail("evaluation hold plan is missing")
    plan_bindings = {
        "starting_xi": "starting_xi",
        "bench_order": "bench_order",
        "reserve_goalkeeper_id": "reserve_goalkeeper_id",
        "captain_id": "captain_id",
        "vice_captain_id": "vice_captain_id",
        "formation": "formation",
    }
    for evaluation_field, archive_field in plan_bindings.items():
        if hold_plan.get(evaluation_field) != archived_state.get(archive_field):
            _fail(f"evaluation hold-plan {evaluation_field} does not match the archived deadline state")
    if set(hold_plan.get("squad_ids", [])) != set(archived_squad):
        _fail("evaluation hold-plan squad does not match the archived deadline squad")
    for price_field in ("purchase_prices", "selling_prices"):
        prices = archived_state.get(price_field)
        if not isinstance(prices, Mapping) or {str(key) for key in prices} != {str(pid) for pid in archived_squad}:
            _fail(f"archived manager {price_field} must cover exactly the 15 deadline players")
    for player_id, player in roster_by_id.items():
        purchase = _finite_number(
            archived_state["purchase_prices"].get(str(player_id), archived_state["purchase_prices"].get(player_id)),
            f"archived purchase price for player {player_id}", 0.1
        )
        selling = _finite_number(
            archived_state["selling_prices"].get(str(player_id), archived_state["selling_prices"].get(player_id)),
            f"archived selling price for player {player_id}", 0.1
        )
        evaluated_purchase = _finite_number(
            player.get("purchase_price"), f"evaluation purchase price for player {player_id}", 0.1
        )
        current_price = _finite_number(
            player.get("current_price"), f"evaluation current price for player {player_id}", 0.1
        )
        if not math.isclose(evaluated_purchase, purchase, abs_tol=1e-9):
            _fail(f"evaluation purchase price for player {player_id} does not match archived manager state")
        expected_selling = _selling_price(current_price, purchase)
        if not math.isclose(selling, expected_selling, abs_tol=1e-9):
            _fail(f"archived selling price for player {player_id} does not match official FPL price rules")

    # Bind the realised-points rows to the exact finalized official event-live
    # archive independently hashed by the auditor, then derive the comparison
    # values from that raw payload rather than trusting a detached points table.
    realised_source = record_by_type.get("realised_points")
    audited_archives = audited.get("archives")
    if not isinstance(realised_source, Mapping) or not isinstance(audited_archives, list):
        _fail("realised-points archive is not bound to independently audited official scoring evidence")
    official_live = next((row for row in audited_archives
                          if isinstance(row, Mapping) and row.get("source_type") == "event_live"), None)
    if not isinstance(official_live, Mapping):
        _fail("independent audit is missing the official event-live scoring archive")
    for field in ("raw_snapshot_id", "raw_sha256", "captured_at_utc", "source_url"):
        if realised_source.get(field) != official_live.get(field):
            _fail(f"realised_points archive {field} does not match the audited official event-live archive")
    try:
        realised_raw = base64.b64decode(realised_source["raw_payload_base64"], validate=True)
        realised_payload = json.loads(realised_raw)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise DecisionEvaluationError("realised-points archive is not valid official event-live JSON") from exc
    live_elements = realised_payload.get("elements") if isinstance(realised_payload, Mapping) else None
    if not isinstance(live_elements, list):
        _fail("realised-points archive must contain official event-live elements")
    official_points: dict[int, dict[str, int]] = {}
    for index, element in enumerate(live_elements):
        if not isinstance(element, Mapping):
            _fail(f"official event-live elements[{index}] must be an object")
        player_id = element.get("id")
        stats = element.get("stats")
        if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id < 1 or player_id in official_points:
            _fail("official event-live archive contains invalid or duplicate player IDs")
        if not isinstance(stats, Mapping):
            _fail(f"official event-live stats missing for player {player_id}")
        values = {}
        for field in ("minutes", "yellow_cards", "red_cards", "total_points"):
            value = stats.get(field)
            if isinstance(value, bool) or not isinstance(value, int):
                _fail(f"official event-live {field} missing or invalid for player {player_id}")
            values[field] = value
        official_points[player_id] = values
    realised_rows = record.get("realised_player_points")
    if not isinstance(realised_rows, list):
        _fail("realised_player_points must be a list")
    for row in realised_rows:
        player_id = row.get("fpl_element_id") if isinstance(row, Mapping) else None
        if player_id not in official_points:
            _fail(f"realised player {player_id} is absent from the official event-live archive")
        expected = official_points[player_id]
        for field in ("minutes", "yellow_cards", "red_cards", "total_points"):
            if row.get(field) != expected[field]:
                _fail(f"realised player {player_id} {field} does not match official event-live scoring")

    batch_rows = batch.get("results")
    batch_event = next((row for row in batch_rows if isinstance(row, Mapping)
                        and row.get("gameweek") == gameweek), None) if isinstance(batch_rows, list) else None
    source_record = batch_event.get("result") if isinstance(batch_event, Mapping) else None
    if (not isinstance(batch_event, Mapping) or batch_event.get("status") != "RECONCILED"
            or not isinstance(source_record, Mapping)
            or source_record.get("manager_team_id") != manager_id
            or source_record.get("target_gameweek") != gameweek
            or source_record.get("event_finalized") is not True
            or source_record.get("historical_evidence_admitted") is not False
            or source_record.get("active_chip") not in (None, "")):
        _fail("official batch does not contain the matching finalized, no-chip, non-admitted source event")


def evaluate_decision_record(record: Mapping[str, Any], *, admission_report: Any = None,
                             audit_report: Any = None, batch: Any = None) -> dict[str, Any]:
    """Validate a frozen record and score recommended plan against hold baseline."""
    if not isinstance(record, Mapping):
        _fail("evaluation record must be an object")
    _validate_evidence(record)
    if record["evidence_class"] == "REAL_CANDIDATE":
        _verify_real_admission(record, admission_report, audit_report, batch)
    manager = record.get("manager_state")
    if not isinstance(manager, Mapping):
        _fail("manager_state must be an object")
    for field in ("bank", "free_transfers", "personal_risk_profile", "formation"):
        if field not in manager:
            _fail(f"manager_state missing {field}")
    if not isinstance(manager["personal_risk_profile"], str) or manager["personal_risk_profile"] not in {"conservative", "balanced", "aggressive"}:
        _fail("manager_state.personal_risk_profile is invalid")
    if not isinstance(manager["formation"], str) or manager["formation"] not in LEGAL_FORMATIONS:
        _fail("manager_state.formation must be a legal FPL formation")
    _finite_number(manager["bank"], "manager_state.bank", 0)
    if isinstance(manager["free_transfers"], bool) or not isinstance(manager["free_transfers"], int) or manager["free_transfers"] < 0:
        _fail("manager_state.free_transfers must be a non-negative integer")
    if manager.get("chip") not in (None, "NONE"):
        _fail("chip scoring is outside the initial M3 evaluation harness")
    manager_roster, _ = _validate_roster(manager.get("squad_snapshot"), "manager_state.squad_snapshot")
    manager_plan = _validate_plan(manager.get("hold_plan"), manager_roster, "manager_state.hold_plan")
    if manager_plan["formation"] != manager["formation"]:
        _fail("manager_state.formation does not match the confirmed hold-plan starting XI")

    decision = record.get("frozen_decision")
    if not isinstance(decision, Mapping):
        _fail("frozen_decision must be an object")
    decision_body = {key: value for key, value in decision.items() if key != "decision_sha256"}
    expected_decision_hash = hashlib.sha256(
        json.dumps(decision_body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    if decision.get("decision_sha256") != expected_decision_hash:
        _fail("frozen_decision decision_sha256 mismatch")
    if not isinstance(decision.get("action"), str) or decision["action"] not in {"HOLD", "TRANSFER"}:
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
        outgoing_player = manager_roster[out_id]
        if outgoing_player["position"] == "GKP":
            _fail("goalkeeper transfers are excluded by the manager strategy contract")
        expected_hit = 0 if manager["free_transfers"] > 0 else 4
        if hit_points != expected_hit:
            _fail(f"one-transfer hit must be {expected_hit} under the captured free-transfer count")
        if decision.get("incoming_player") is None:
            _fail("TRANSFER requires incoming_player metadata")
        incoming = decision["incoming_player"]
        if not isinstance(incoming, Mapping) or incoming.get("fpl_element_id") != in_id:
            _fail("incoming_player metadata must match transfer_in_id")
        if incoming.get("position") != outgoing_player["position"]:
            _fail("transfer must preserve player position")
        if isinstance(incoming.get("team_id"), bool) or not isinstance(incoming.get("team_id"), int) or incoming.get("team_id") < 1:
            _fail("incoming player team metadata is invalid")
        for price_field in ("purchase_price", "current_price"):
            _finite_number(incoming.get(price_field), f"incoming_player.{price_field}", 0.1)
        sale_price = _selling_price(outgoing_player["current_price"], outgoing_player["purchase_price"])
        bank_after = manager["bank"] + sale_price - incoming["current_price"]
        if bank_after < -1e-9:
            _fail("transfer is unaffordable using captured bank and FPL selling-price rules")
        if set(plan["squad_ids"]) != (set(manager_roster) - {out_id}) | {in_id}:
            _fail("post-transfer plan must replace exactly the outgoing player with the incoming player")
        if plan["reserve_goalkeeper_id"] != manager_plan["reserve_goalkeeper_id"]:
            _fail("the designated reserve goalkeeper cannot change in the initial manager strategy")
        starting_gk = next(
            pid for pid in manager_plan["starting_xi"]
            if manager_roster[pid]["position"] == "GKP"
        )
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
        points = row.get("total_points")
        if isinstance(points, bool) or not isinstance(points, int):
            _fail(f"realised_player_points[{index}].total_points must be an integer")
        minutes = _finite_number(row.get("minutes"), f"realised_player_points[{index}].minutes", 0)
        if minutes != int(minutes):
            _fail(f"realised_player_points[{index}].minutes must be an integer")
        cards = {}
        for card_field in ("yellow_cards", "red_cards"):
            card_count = row.get(card_field)
            if isinstance(card_count, bool) or not isinstance(card_count, int) or card_count < 0:
                _fail(f"realised_player_points[{index}].{card_field} must be a non-negative integer")
            cards[card_field] = card_count
        realised[player_id] = {"total_points": points, "minutes": int(minutes), **cards}
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
    input_sha256 = hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    archive_provenance = [
        {
            "source_type": source["source_type"],
            "raw_snapshot_id": source["raw_snapshot_id"],
            "raw_sha256": source["raw_sha256"],
            "captured_at_utc": source["captured_at_utc"],
            **({"finalized_at_utc": source["finalized_at_utc"]} if source["source_type"] == "realised_points" else {}),
        }
        for source in record["source_archives"]
    ]
    return {
        "evaluation_contract_version": CONTRACT_VERSION,
        "evidence_class": record["evidence_class"],
        "evaluation_status": ("SYNTHETIC_ONLY_NOT_HISTORICAL_EVIDENCE"
                              if record["evidence_class"] == "SYNTHETIC_TEST"
                              else "REAL_DECISION_BACKTEST_EVENT_SCORED_NOT_PROMOTION_EVIDENCE"),
        "manager_team_id": record["manager_team_id"],
        "target_gameweek": record["target_gameweek"],
        "provider_snapshot_id": record["provider_snapshot_id"],
        "provider_identity": dict(record["provider_identity"]),
        "personal_risk_profile": manager["personal_risk_profile"],
        "risk_profile_applied": False,
        "software_commit": record["software_commit"],
        "evaluation_input_sha256": input_sha256,
        "frozen_decision_sha256": decision["decision_sha256"],
        "source_provenance": archive_provenance,
        "recommended_action": decision["action"],
        "transfer_financials": (
            {
                "outgoing_selling_price": sale_price,
                "incoming_price": incoming["current_price"],
                "bank_after_transfer": bank_after,
            } if decision["action"] == "TRANSFER" else None
        ),
        "recommended": {**recommendation_score, "transfer_hit_points": hit_points, "net_points": net_recommended},
        "hold": {**hold_score, "transfer_hit_points": 0.0, "net_points": net_hold},
        "net_points_delta_vs_hold": net_recommended - net_hold,
        "historical_performance_validated": False,
    }


def _post_transfer_roster(roster_by_id: Mapping[int, Mapping[str, Any]], decision: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    out_id = decision.get("transfer_out_id")
    in_id = decision.get("transfer_in_id")
    incoming = decision.get("incoming_player")
    if isinstance(out_id, bool) or not isinstance(out_id, int) or out_id < 1 or out_id not in roster_by_id:
        _fail("transfer_out_id must identify an owned player")
    if isinstance(in_id, bool) or not isinstance(in_id, int) or in_id < 1 or in_id in roster_by_id:
        _fail("transfer_in_id must identify a positive unowned player")
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
    parser.add_argument("--admission-report", type=Path)
    parser.add_argument("--audit-report", type=Path)
    parser.add_argument("--batch", type=Path)
    args = parser.parse_args()
    record = json.loads(args.evaluation_record.read_text(encoding="utf-8"))
    admission = json.loads(args.admission_report.read_text(encoding="utf-8")) if args.admission_report else None
    audit = json.loads(args.audit_report.read_text(encoding="utf-8")) if args.audit_report else None
    batch = json.loads(args.batch.read_text(encoding="utf-8")) if args.batch else None
    result = evaluate_decision_record(record, admission_report=admission, audit_report=audit, batch=batch)
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
