"""Verify that a conventional M3 output is bound to its frozen replay evidence."""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Mapping


class M3ReplayEvidenceError(ValueError):
    """Raised when frozen M3 replay evidence does not match the decision output."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise M3ReplayEvidenceError(f"{label} must be an object")
    return value


def _same(left: Any, right: Any, label: str) -> None:
    if left != right:
        raise M3ReplayEvidenceError(f"M3 replay evidence mismatch: {label}")


def _source_archive_hashes(candidate: Mapping[str, Any], evidence: Mapping[str, Any]) -> list[str]:
    candidate_sources = candidate.get("source_archives")
    evidence_sources = evidence.get("sources")
    if not isinstance(candidate_sources, list) or not candidate_sources:
        raise M3ReplayEvidenceError("M3 candidate source archives are missing")
    if not isinstance(evidence_sources, list) or len(evidence_sources) != len(candidate_sources):
        raise M3ReplayEvidenceError("decision evidence source archive count differs from M3 candidate")

    def normalize(rows: list[Any], label: str) -> list[tuple[str, str, str]]:
        normalized = []
        for index, raw in enumerate(rows):
            row = _mapping(raw, f"{label}[{index}]")
            captured = row.get("captured_at_utc")
            generated = row.get("generated_at_utc")
            payload = row.get("raw_payload_base64")
            if not all(isinstance(value, str) and value for value in (captured, generated, payload)):
                raise M3ReplayEvidenceError(f"{label}[{index}] lacks raw archive provenance")
            try:
                decoded = base64.b64decode(payload, validate=True)
            except (ValueError, TypeError) as exc:
                raise M3ReplayEvidenceError(f"{label}[{index}] has invalid base64 payload") from exc
            if not decoded:
                raise M3ReplayEvidenceError(f"{label}[{index}] has an empty raw payload")
            normalized.append((captured, generated, payload))
        return sorted(normalized)

    candidate_rows = normalize(candidate_sources, "M3 candidate source_archives")
    evidence_rows = normalize(evidence_sources, "decision evidence sources")
    _same(candidate_rows, evidence_rows, "raw source archives")
    return [
        hashlib.sha256(base64.b64decode(payload, validate=True)).hexdigest()
        for _, _, payload in candidate_rows
    ]


def verify_m3_replay_evidence(
    m3_output: Mapping[str, Any],
    replay_report: Mapping[str, Any],
    decision_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify frozen decision hashes, replay status, point-in-time state and raw archives."""
    m3 = _mapping(m3_output, "M3 output")
    replay = _mapping(replay_report, "M3 replay report")
    evidence_root = _mapping(decision_evidence, "decision evidence")
    candidate = _mapping(m3.get("evaluation_candidate"), "M3 evaluation_candidate")
    frozen = _mapping(m3.get("frozen_decision"), "M3 frozen_decision")

    if replay.get("status") != "PASSED":
        raise M3ReplayEvidenceError("M3 frozen replay did not pass")
    if replay.get("replay_type") != "DETERMINISTIC_RAW_AND_CANONICAL_INPUT_REEXECUTION":
        raise M3ReplayEvidenceError("M3 replay type is not deterministic raw/canonical re-execution")
    for flag in ("frozen_decision_match", "recommendation_match", "raw_archive_hashes_verified"):
        if replay.get(flag) is not True:
            raise M3ReplayEvidenceError(f"M3 replay report does not verify {flag}")
    if m3.get("release_eligible") is not False or replay.get("release_eligible") is not False:
        raise M3ReplayEvidenceError("M3 replay evidence must remain exploratory and release-ineligible")

    manager_id = m3.get("manager_team_id")
    gameweek = m3.get("target_gameweek")
    _same(replay.get("manager_team_id"), manager_id, "manager team ID")
    _same(replay.get("target_gameweek"), gameweek, "target Gameweek")
    _same(candidate.get("manager_team_id"), manager_id, "candidate manager team ID")
    _same(candidate.get("target_gameweek"), gameweek, "candidate target Gameweek")
    _same(candidate.get("deadline_utc"), m3.get("deadline_utc"), "candidate deadline")
    _same(candidate.get("as_of_utc"), m3.get("decision_as_of_utc"), "candidate decision timestamp")
    _same(candidate.get("provider_identity"), m3.get("provider_identity"), "provider identity")
    _same(candidate.get("provider_snapshot_id"), m3.get("provider_snapshot_id"), "provider snapshot ID")
    _same(replay.get("software_commit"), candidate.get("software_commit"), "replay software commit")

    evidence = evidence_root.get(str(gameweek), evidence_root.get(gameweek))
    evidence = _mapping(evidence, f"decision evidence for GW{gameweek}")
    if evidence.get("evidence_is_point_in_time") is not True:
        raise M3ReplayEvidenceError("decision evidence is not marked point-in-time")
    for key, expected in (
        ("manager_team_id", manager_id),
        ("target_gameweek", gameweek),
        ("deadline_utc", m3.get("deadline_utc")),
        ("decision_as_of_utc", m3.get("decision_as_of_utc")),
    ):
        _same(evidence.get(key), expected, f"decision evidence {key}")
    candidate_season = candidate.get("season", m3.get("season"))
    evidence_season = evidence.get("season")
    if candidate_season is not None and candidate_season != evidence_season:
        raise M3ReplayEvidenceError("decision evidence season differs from M3 candidate")
    season = evidence_season
    if not isinstance(season, str) or not season.strip():
        raise M3ReplayEvidenceError("decision evidence season is missing")

    provider_snapshot = _mapping(evidence.get("provider_snapshot"), "decision evidence provider snapshot")
    _same(provider_snapshot.get("snapshot_id"), m3.get("provider_snapshot_id"), "provider snapshot ID in evidence")
    _same(provider_snapshot.get("provider"), m3.get("provider_identity"), "provider identity in evidence")
    _same(provider_snapshot.get("target_gameweek"), gameweek, "provider snapshot Gameweek")
    _same(provider_snapshot.get("season"), season, "provider snapshot season")

    candidate_state = _mapping(candidate.get("manager_state"), "M3 candidate manager_state")
    evidence_state = _mapping(evidence.get("manager_state"), "decision evidence manager_state")
    for candidate_key, evidence_key in (
        ("bank", "bank"),
        ("free_transfers", "free_transfers"),
        ("formation", "formation"),
        ("chip", "chip_state"),
    ):
        _same(candidate_state.get(candidate_key), evidence_state.get(evidence_key), f"manager state {candidate_key}")
    candidate_squad = candidate_state.get("squad_snapshot")
    evidence_squad = evidence_state.get("squad_15")
    if not isinstance(candidate_squad, list) or not isinstance(evidence_squad, list):
        raise M3ReplayEvidenceError("manager squad snapshot is missing")
    candidate_ids = sorted(row.get("fpl_element_id") for row in candidate_squad if isinstance(row, Mapping))
    evidence_ids = sorted(evidence_squad)
    if len(candidate_ids) != 15 or len(set(candidate_ids)) != 15:
        raise M3ReplayEvidenceError("M3 candidate squad snapshot must contain 15 unique players")
    _same(candidate_ids, evidence_ids, "manager squad IDs")

    hold = _mapping(candidate_state.get("hold_plan"), "M3 candidate hold plan")
    for candidate_key, evidence_key in (
        ("squad_ids", "squad_15"),
        ("starting_xi", "starting_xi"),
        ("bench_order", "bench_order"),
        ("reserve_goalkeeper_id", "reserve_goalkeeper_id"),
        ("captain_id", "captain_id"),
        ("vice_captain_id", "vice_captain_id"),
        ("formation", "formation"),
    ):
        _same(hold.get(candidate_key), evidence_state.get(evidence_key), f"hold plan {candidate_key}")

    decision_hash = frozen.get("decision_sha256")
    decision_body = dict(frozen)
    decision_body.pop("decision_sha256", None)
    computed_decision_hash = hashlib.sha256(_canonical(decision_body)).hexdigest()
    if not isinstance(decision_hash, str) or computed_decision_hash != decision_hash:
        raise M3ReplayEvidenceError("frozen decision SHA-256 is invalid")
    _same(replay.get("decision_sha256"), decision_hash, "frozen decision SHA-256")
    replayed_payload_hash = hashlib.sha256(_canonical(dict(frozen))).hexdigest()
    _same(replay.get("replayed_payload_sha256"), replayed_payload_hash, "replayed frozen payload SHA-256")

    source_hashes = _source_archive_hashes(candidate, evidence)
    return {
        "status": "VERIFIED",
        "replay_report_status": replay["status"],
        "replay_type": replay["replay_type"],
        "manager_team_id": manager_id,
        "season": season,
        "target_gameweek": gameweek,
        "decision_sha256": decision_hash,
        "replayed_payload_sha256": replayed_payload_hash,
        "replay_report_sha256": hashlib.sha256(_canonical(dict(replay))).hexdigest(),
        "decision_evidence_sha256": hashlib.sha256(_canonical(dict(evidence))).hexdigest(),
        "source_archive_count": len(source_hashes),
        "source_archive_sha256": source_hashes,
        "point_in_time_evidence": True,
        "release_eligible": False,
    }
