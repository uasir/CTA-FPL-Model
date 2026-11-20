#!/usr/bin/env python3
"""Classify reconciled FPL history by its actual evidence strength.

Scoring reconciliation is not decision-backtest admission. Decision eligibility
requires a separate, timestamp-valid evidence manifest for every required input.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


class EvidenceAdmissionError(ValueError):
    pass


REQUIRED_DECISION_SOURCES = {
    "provider_forecast", "player_metadata", "manager_deadline_state"
}
REQUIRED_MANAGER_FIELDS = {
    "squad_15", "bank", "free_transfers", "purchase_prices",
    "selling_prices", "chip_state", "starting_xi", "bench_order",
    "reserve_goalkeeper_id", "captain_id", "vice_captain_id",
}


def _parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise EvidenceAdmissionError(f"{label} must be a timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceAdmissionError(f"{label} is not a valid ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceAdmissionError(f"{label} must include a timezone")
    return parsed


def _decision_eligibility(manifest: Any, gameweek: int) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not isinstance(manifest, Mapping):
        return False, ["No separate point-in-time decision evidence manifest supplied"]

    deadline = None
    try:
        deadline = _parse_time(manifest.get("deadline_utc"), "deadline_utc")
        as_of = _parse_time(manifest.get("decision_as_of_utc"), "decision_as_of_utc")
        if as_of >= deadline:
            reasons.append("Decision timestamp is not strictly before the deadline")
    except EvidenceAdmissionError as exc:
        reasons.append(str(exc))

    sources = manifest.get("sources")
    if not isinstance(sources, list):
        sources = []
    source_map = {
        row.get("source_type"): row for row in sources if isinstance(row, Mapping)
    }
    for source_type in sorted(REQUIRED_DECISION_SOURCES):
        row = source_map.get(source_type)
        if row is None:
            reasons.append(f"Missing {source_type} source archive")
            continue
        digest = row.get("raw_sha256")
        if not row.get("raw_snapshot_id") or not isinstance(digest, str) or len(digest) != 64:
            reasons.append(f"{source_type} archive lacks snapshot ID or a 64-character SHA-256")
        elif any(char not in "0123456789abcdef" for char in digest.lower()):
            reasons.append(f"{source_type} archive SHA-256 is malformed")
        try:
            captured = _parse_time(row.get("captured_at_utc"),
                                   f"{source_type}.captured_at_utc")
            if deadline is not None and captured >= deadline:
                reasons.append(f"{source_type} archive was captured at/after deadline")
        except EvidenceAdmissionError as exc:
            reasons.append(str(exc))
        if source_type == "provider_forecast":
            try:
                generated = _parse_time(row.get("generated_at_utc"),
                                        "provider_forecast.generated_at_utc")
                if deadline is not None and generated >= deadline:
                    reasons.append("Provider forecast was generated at/after deadline")
            except EvidenceAdmissionError as exc:
                reasons.append(str(exc))

    manager_state = manifest.get("manager_state")
    if not isinstance(manager_state, Mapping):
        reasons.append("Missing manager_state evidence payload")
    else:
        for field in sorted(REQUIRED_MANAGER_FIELDS):
            if field not in manager_state or manager_state[field] is None:
                reasons.append(f"Manager deadline state missing {field}")
        if manager_state.get("chip_state") not in ("NONE", None):
            reasons.append("Chip state is outside the initial decision contract")
        squad = manager_state.get("squad_15")
        if not isinstance(squad, list) or len(squad) != 15 or len(set(squad)) != 15:
            reasons.append("Manager deadline squad must contain exactly 15 unique players")
        for field in ("purchase_prices", "selling_prices"):
            prices = manager_state.get(field)
            if not isinstance(prices, Mapping) or not isinstance(squad, list) or any(
                str(player_id) not in prices and player_id not in prices for player_id in squad
            ):
                reasons.append(f"Manager deadline {field} must cover all 15 players")

    if manifest.get("target_gameweek") != gameweek:
        reasons.append("Decision evidence manifest Gameweek mismatch")
    if manifest.get("evidence_is_point_in_time") is not True:
        reasons.append("Manifest does not explicitly attest point-in-time evidence")
    return not reasons, reasons


def classify_batch(batch: Mapping[str, Any],
                   decision_manifests: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if batch.get("historical_evidence_admitted") is not False:
        raise EvidenceAdmissionError("Input batch must retain historical_evidence_admitted=false")
    manager_id = batch.get("manager_team_id")
    if not isinstance(manager_id, int) or manager_id <= 0:
        raise EvidenceAdmissionError("Invalid manager_team_id")
    results = batch.get("results")
    if not isinstance(results, list):
        raise EvidenceAdmissionError("Batch results must be a list")
    manifests = decision_manifests or {}
    events = []
    for row in results:
        gw = row.get("gameweek")
        status = row.get("status")
        if not isinstance(gw, int) or gw <= 0:
            raise EvidenceAdmissionError("Invalid Gameweek in batch result")
        if status == "RECONCILED":
            record = row.get("result")
            if not isinstance(record, Mapping) or record.get("manager_team_id") != manager_id:
                raise EvidenceAdmissionError(f"GW{gw}: reconciled record identity mismatch")
            if record.get("target_gameweek") != gw or record.get("event_finalized") is not True:
                raise EvidenceAdmissionError(f"GW{gw}: record is not a finalized matching event")
            reconciliation = record.get("reconciliation")
            if not isinstance(reconciliation, Mapping) or reconciliation.get("status") != "RECONCILED":
                raise EvidenceAdmissionError(f"GW{gw}: official scoring reconciliation missing")
            if record.get("historical_evidence_admitted") is not False:
                raise EvidenceAdmissionError(f"GW{gw}: source record must not self-admit")
            if record.get("active_chip") not in (None, ""):
                classification = "EXCLUDED"
                reasons = ["Chip Gameweek is outside the initial scoring and decision contract"]
            else:
                manifest = manifests.get(str(gw), manifests.get(gw))
                eligible, reasons = _decision_eligibility(manifest, gw)
                classification = "DECISION_BACKTEST_ELIGIBLE" if eligible else "SCORING_RECONCILIATION_ONLY"
        elif status == "EXCLUDED":
            classification = "EXCLUDED"
            reasons = [row.get("error") or "Official scoring reconciliation was excluded"]
        else:
            raise EvidenceAdmissionError(f"GW{gw}: unsupported batch status {status!r}")
        events.append({
            "gameweek": gw,
            "classification": classification,
            "historical_evidence_admitted": classification == "DECISION_BACKTEST_ELIGIBLE",
            "reasons": reasons,
            "official_score_reconciled": status == "RECONCILED",
        })
    counts = {key: sum(event["classification"] == key for event in events) for key in (
        "DECISION_BACKTEST_ELIGIBLE", "SCORING_RECONCILIATION_ONLY",
        "DIAGNOSTIC_ONLY", "EXCLUDED"
    )}
    return {
        "admission_contract_version": "0.1.0",
        "manager_team_id": manager_id,
        "events": events,
        "counts": counts,
        "historical_evidence_admitted": counts["DECISION_BACKTEST_ELIGIBLE"] > 0,
        "decision_backtest_status": (
            "ELIGIBLE_COHORT_EXISTS" if counts["DECISION_BACKTEST_ELIGIBLE"]
            else "NO_DECISION_BACKTEST_ELIGIBLE_EVENTS"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    parser.add_argument("--decision-manifests", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    batch = json.loads(args.batch.read_text(encoding="utf-8"))
    manifests = {}
    if args.decision_manifests:
        manifests = json.loads(args.decision_manifests.read_text(encoding="utf-8"))
    result = classify_batch(batch, manifests)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "events"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
