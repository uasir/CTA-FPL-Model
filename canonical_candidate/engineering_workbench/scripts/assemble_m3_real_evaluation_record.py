#!/usr/bin/env python3
"""Assemble a real M3 evaluation record from frozen and independently audited evidence.

This command does not score or admit evidence. It only assembles the immutable
candidate and finalized official player points; the evaluator rechecks every
archive and admission gate before calculating hold-versus-transfer points.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class EvaluationAssemblyError(ValueError):
    """Raised when the required frozen or finalized evidence is incomplete."""


def _fail(message: str) -> None:
    raise EvaluationAssemblyError(message)


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        _fail(f"{label} must be a timezone-aware ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvaluationAssemblyError(
            f"{label} must be a timezone-aware ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _archive_payload(archive: Mapping[str, Any], label: str) -> tuple[bytes, dict[str, Any]]:
    required = ("source_url", "raw_snapshot_id", "raw_sha256", "captured_at_utc",
                "raw_payload_base64")
    for field in required:
        if not isinstance(archive.get(field), str) or not archive[field].strip():
            _fail(f"{label} archive is missing {field}")
    try:
        raw = base64.b64decode(archive["raw_payload_base64"], validate=True)
        payload = json.loads(raw)
    except Exception as exc:
        raise EvaluationAssemblyError(f"{label} archive is not valid base64 JSON") from exc
    if hashlib.sha256(raw).hexdigest() != archive["raw_sha256"]:
        _fail(f"{label} archive SHA-256 mismatch")
    if not isinstance(payload, dict):
        _fail(f"{label} archive payload must be a JSON object")
    _time(archive["captured_at_utc"], f"{label}.captured_at_utc")
    if not archive["source_url"].startswith("https://"):
        _fail(f"{label} source URL must use HTTPS")
    return raw, payload


def assemble_evaluation_record(
    recommendation: Mapping[str, Any],
    batch: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    admission_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a scorer-ready record only after independent admission and audit."""
    if recommendation.get("release_eligible") is not False:
        _fail("recommendation must remain explicitly non-release-eligible")
    candidate = recommendation.get("evaluation_candidate")
    decision = recommendation.get("frozen_decision")
    if not isinstance(candidate, Mapping) or not isinstance(decision, Mapping):
        _fail("frozen evaluation candidate or decision is missing")

    manager_id = recommendation.get("manager_team_id")
    gameweek = recommendation.get("target_gameweek")
    if (isinstance(manager_id, bool) or not isinstance(manager_id, int) or manager_id < 1
            or isinstance(gameweek, bool) or not isinstance(gameweek, int) or gameweek < 1):
        _fail("recommendation manager/Gameweek identity is invalid")
    if (candidate.get("manager_team_id") != manager_id
            or candidate.get("target_gameweek") != gameweek
            or candidate.get("software_commit") is None
            or candidate.get("frozen_decision") != decision):
        _fail("recommendation and evaluation candidate identity/decision do not match")
    if (batch.get("manager_team_id") != manager_id
            or batch.get("historical_evidence_admitted") is not False):
        _fail("official batch manager identity or non-admission invariant mismatch")
    if (audit_report.get("status") != "PASSED"
            or audit_report.get("manager_team_id") != manager_id
            or audit_report.get("historical_evidence_admitted") is not False):
        _fail("independent archive audit is missing, failed or belongs to another manager")
    if admission_report.get("manager_team_id") != manager_id:
        _fail("historical admission report manager identity mismatch")

    audit_events = audit_report.get("events")
    audited = next((row for row in audit_events if isinstance(row, Mapping)
                    and row.get("gameweek") == gameweek), None) if isinstance(audit_events, list) else None
    if not isinstance(audited, Mapping) or audited.get("status") != "RECONCILED":
        _fail("target Gameweek has no independently audited finalized scoring reconciliation")
    recommendation_audit = audited.get("predeadline_recommendation")
    replay_audit = audited.get("predeadline_replay")
    decision_hash = decision.get("decision_sha256")
    if (not isinstance(recommendation_audit, Mapping)
            or recommendation_audit.get("status") != "VERIFIED"
            or recommendation_audit.get("action") != decision.get("action")
            or recommendation_audit.get("decision_sha256") != decision_hash
            or recommendation_audit.get("execution_match") not in {
                "HOLD_BASELINE_MATCHED", "RECOMMENDATION_MATCHED"
            }):
        _fail("post-Gameweek audit did not verify the exact frozen decision execution")
    if (not isinstance(replay_audit, Mapping)
            or replay_audit.get("status") != "VERIFIED"
            or replay_audit.get("replay_type") != "DETERMINISTIC_RAW_AND_CANONICAL_INPUT_REEXECUTION"
            or replay_audit.get("decision_sha256") != decision_hash
            or replay_audit.get("software_commit") != candidate.get("software_commit")
            or replay_audit.get("raw_archive_hashes_verified") is not True):
        _fail("post-Gameweek audit did not verify the exact frozen-decision replay")

    admission_events = admission_report.get("events")
    admitted = next((row for row in admission_events if isinstance(row, Mapping)
                     and row.get("gameweek") == gameweek), None) if isinstance(admission_events, list) else None
    if (not isinstance(admitted, Mapping)
            or admitted.get("classification") != "DECISION_BACKTEST_ELIGIBLE"
            or admitted.get("historical_evidence_admitted") is not True
            or admitted.get("official_score_reconciled") is not True):
        _fail("target Gameweek is not independently classified DECISION_BACKTEST_ELIGIBLE")

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
        _fail("official batch lacks the matching finalized, no-chip, non-admitted event")

    official_archives = source_record.get("source_archives")
    if not isinstance(official_archives, list):
        _fail("official reconciliation source archives are missing")
    by_type = {row.get("source_type"): row for row in official_archives if isinstance(row, Mapping)}
    if set(by_type) != {"bootstrap_static", "manager_picks", "event_live"} or len(official_archives) != 3:
        _fail("official reconciliation must contain exactly bootstrap, manager-picks and event-live archives")

    bootstrap_archive = by_type["bootstrap_static"]
    _, bootstrap = _archive_payload(bootstrap_archive, "bootstrap_static")
    bootstrap_events = bootstrap.get("events")
    event_rows = [row for row in bootstrap_events if isinstance(row, Mapping)
                  and row.get("id") == gameweek] if isinstance(bootstrap_events, list) else []
    if (len(event_rows) != 1 or event_rows[0].get("finished") is not True
            or event_rows[0].get("data_checked") is not True):
        _fail("official bootstrap does not confirm a finalized and data-checked Gameweek")
    # Use the timestamp at which the official bootstrap first recorded both
    # finalization flags as a conservative finalization-observation timestamp.
    finalized_observed_at = _time(
        bootstrap_archive.get("captured_at_utc"), "bootstrap finalization observation"
    )

    audited_archives = audited.get("archives")
    if not isinstance(audited_archives, list):
        _fail("independent audit is missing official scoring archive bindings")
    audit_archive_by_type = {
        row.get("source_type"): row for row in audited_archives if isinstance(row, Mapping)
    }
    for source_type, archive in by_type.items():
        audited_archive = audit_archive_by_type.get(source_type)
        if not isinstance(audited_archive, Mapping):
            _fail(f"official {source_type} archive is absent from the independent audit")
        for field in ("raw_snapshot_id", "raw_sha256", "captured_at_utc", "source_url"):
            if archive.get(field) != audited_archive.get(field):
                _fail(f"official {source_type} archive {field} does not match the independent audit")

    live_archive = by_type["event_live"]
    _, live_payload = _archive_payload(live_archive, "event_live")
    live_captured_at = _time(live_archive["captured_at_utc"], "event_live.captured_at_utc")
    if live_captured_at < finalized_observed_at:
        _fail("official event-live points were captured before finalized status was observed")
    live_url = live_archive["source_url"].rstrip("/")
    if not live_url.endswith(f"/event/{gameweek}/live"):
        _fail("official event-live archive URL does not match the target Gameweek")
    live_elements = live_payload.get("elements")
    if not isinstance(live_elements, list):
        _fail("official event-live archive has no elements array")
    points_by_id: dict[int, dict[str, int]] = {}
    for row in live_elements:
        if not isinstance(row, Mapping) or isinstance(row.get("id"), bool) or not isinstance(row.get("id"), int):
            continue
        stats = row.get("stats")
        if not isinstance(stats, Mapping):
            continue
        values = {}
        valid = True
        for field in ("total_points", "minutes", "yellow_cards", "red_cards"):
            value = stats.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or (
                field in {"minutes", "yellow_cards", "red_cards"} and value < 0
            ):
                valid = False
                break
            values[field] = value
        if valid:
            points_by_id[row["id"]] = values

    manager_state = candidate.get("manager_state")
    if not isinstance(manager_state, Mapping):
        _fail("frozen candidate manager_state is missing")
    roster = manager_state.get("squad_snapshot")
    hold_plan = manager_state.get("hold_plan")
    if not isinstance(roster, list) or len(roster) != 15 or not isinstance(hold_plan, Mapping):
        _fail("frozen candidate must contain the 15-player roster and hold plan")
    squad_ids = [row.get("fpl_element_id") for row in roster if isinstance(row, Mapping)]
    if len(squad_ids) != 15 or len(set(squad_ids)) != 15:
        _fail("frozen candidate roster must contain 15 unique player IDs")
    if not isinstance(decision.get("action"), str) or decision.get("action") not in {"HOLD", "TRANSFER"}:
        _fail("frozen decision action must be HOLD or TRANSFER")
    expected_ids = set(squad_ids)
    if decision["action"] == "TRANSFER":
        incoming = decision.get("transfer_in_id")
        if isinstance(incoming, bool) or not isinstance(incoming, int) or incoming in expected_ids:
            _fail("frozen transfer incoming player ID is invalid or already owned")
        expected_ids.add(incoming)
    if not expected_ids.issubset(points_by_id):
        missing = sorted(expected_ids - set(points_by_id))
        _fail("official event-live archive is missing decision-cohort player IDs: " +
              ", ".join(str(value) for value in missing))

    realised_rows = [
        {"fpl_element_id": player_id, **points_by_id[player_id]}
        for player_id in sorted(expected_ids)
    ]
    realised_archive = {
        "source_type": "realised_points",
        "source_url": live_archive["source_url"],
        "raw_snapshot_id": live_archive["raw_snapshot_id"],
        "raw_sha256": live_archive["raw_sha256"],
        "captured_at_utc": live_archive["captured_at_utc"],
        "finalized_at_utc": finalized_observed_at.isoformat().replace("+00:00", "Z"),
        "raw_payload_base64": live_archive["raw_payload_base64"],
        "finalization_basis": "OFFICIAL_BOOTSTRAP_FINISHED_AND_DATA_CHECKED_OBSERVED",
        "finalization_observation_snapshot_id": bootstrap_archive.get("raw_snapshot_id"),
        "finalization_observation_sha256": bootstrap_archive.get("raw_sha256"),
    }

    source_archives = candidate.get("source_archives")
    if not isinstance(source_archives, list) or len(source_archives) != 3:
        _fail("frozen candidate must contain exactly three pre-deadline source archives")
    result = {
        "evidence_class": "REAL_CANDIDATE",
        "manager_team_id": manager_id,
        "target_gameweek": gameweek,
        "deadline_utc": candidate.get("deadline_utc"),
        "as_of_utc": candidate.get("as_of_utc"),
        "season": candidate.get("season"),
        "provider_snapshot_id": candidate.get("provider_snapshot_id"),
        "provider_identity": candidate.get("provider_identity"),
        "decision_contract_version": candidate.get("decision_contract_version"),
        "software_commit": candidate.get("software_commit"),
        "source_archives": [*source_archives, realised_archive],
        "manager_state": {
            "squad_snapshot": roster,
            "bank": manager_state.get("bank"),
            "free_transfers": manager_state.get("free_transfers"),
            "personal_risk_profile": manager_state.get("personal_risk_profile"),
            "formation": manager_state.get("formation"),
            "chip": manager_state.get("chip"),
            "hold_plan": hold_plan,
        },
        "frozen_decision": decision,
        "realised_player_points": realised_rows,
        "assembly_contract_version": "0.1.0",
        "assembly_provenance": {
            "official_batch_manager_team_id": manager_id,
            "target_gameweek": gameweek,
            "event_live_raw_sha256": live_archive.get("raw_sha256"),
            "finalization_observation_raw_sha256": bootstrap_archive.get("raw_sha256"),
            "admission_classification": admitted.get("classification"),
            "recommendation_execution_match": recommendation_audit.get("execution_match"),
            "frozen_replay_status": replay_audit.get("status"),
        },
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recommendation", type=Path)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--admission-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    recommendation = json.loads(args.recommendation.read_text(encoding="utf-8"))
    batch = json.loads(args.batch.read_text(encoding="utf-8"))
    audit = json.loads(args.audit_report.read_text(encoding="utf-8"))
    admission = json.loads(args.admission_report.read_text(encoding="utf-8"))
    record = assemble_evaluation_record(recommendation, batch, audit, admission)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n",
                           encoding="utf-8")
    print(json.dumps({
        "manager_team_id": record["manager_team_id"],
        "target_gameweek": record["target_gameweek"],
        "decision_action": record["frozen_decision"]["action"],
        "realised_player_count": len(record["realised_player_points"]),
        "realised_archive_sha256": record["assembly_provenance"]["event_live_raw_sha256"],
        "evaluation_record": str(args.output),
        "scoring_performed": False,
        "historical_evidence_admitted_by_assembler": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
