#!/usr/bin/env python3
"""Build a conventional recommendation report with isolated optional field context.

The conventional validator is authoritative. The optionality adapter may add
field context only as a descriptive sidecar and never recalculates the decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from m5_conventional_delivery_contract import validate_conventional_m5_output
from m4_m3_optionality_adapter import attach_optional_m4_context
from m4_m3_replay_evidence_adapter import verify_m3_replay_evidence


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def build_conventional_delivery_report(
    conventional_output: Mapping[str, Any],
    field_context: Mapping[str, Any] | None = None,
    m3_replay_report: Mapping[str, Any] | None = None,
    decision_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate first, then attach field context and independently verify frozen M3 evidence."""
    acceptance = validate_conventional_m5_output(conventional_output)
    optionality = attach_optional_m4_context(conventional_output, field_context)
    if (m3_replay_report is None) != (decision_evidence is None):
        raise ValueError("M3 replay report and decision evidence must be supplied together")
    replay_evidence = (
        verify_m3_replay_evidence(conventional_output, m3_replay_report, decision_evidence)
        if m3_replay_report is not None else
        {"status": "NOT_SUPPLIED", "release_eligible": False}
    )

    # The adapter returns a deep-copied original payload. Assert exact canonical
    # equality here as a second boundary at the report layer.
    original_hash = hashlib.sha256(_canonical(dict(conventional_output))).hexdigest()
    if optionality["m3_output_sha256"] != original_hash:
        raise ValueError("optional context changed the conventional recommendation payload")

    action = acceptance["action"]
    decision = conventional_output["frozen_decision"]
    plan = decision["squad_plan"]
    transfer = (
        {"out": decision.get("transfer_out_id"), "in": decision.get("transfer_in_id")}
        if action == "TRANSFER" else None
    )
    report = {
        "report_type": "CONVENTIONAL_PERSONAL_SQUAD_DELIVERY",
        "status": "PASS_CONVENTIONAL_DELIVERY_WITH_OPTIONAL_FIELD_CONTEXT",
        "conventional": {
            "acceptance": acceptance,
            "action": action,
            "transfer": transfer,
            "starting_xi": list(plan["starting_xi"]),
            "formation": plan["formation"],
            "bench_order": list(plan["bench_order"]),
            "reserve_goalkeeper_id": plan["reserve_goalkeeper_id"],
            "captain_id": plan["captain_id"],
            "vice_captain_id": plan["vice_captain_id"],
            "frozen_decision_sha256": decision["decision_sha256"],
            "source_output_sha256": original_hash,
            "recommendation": dict(conventional_output["recommendation"]),
            "provider_identity": dict(conventional_output["provider_identity"]),
            "provider_snapshot_id": conventional_output["provider_snapshot_id"],
            "decision_as_of_utc": conventional_output["decision_as_of_utc"],
            "deadline_utc": conventional_output["deadline_utc"],
        },
        "m3_replay_evidence": replay_evidence,
        "field_context": {
            "status": optionality["m4_status"],
            "withheld_reason": optionality["m4_withheld_reason"],
            "context": optionality["m4_context"],
            "role": "DESCRIPTIVE_ONLY",
        },
        "guardrails": {
            "release_eligible": False,
            "expected_points_unchanged": True,
            "frozen_decision_unchanged": True,
            "ev_eo_blended": False,
            "covar_decision_weight": 0,
            "field_context_can_change_recommendation": False,
            "frozen_m3_replay_verified": replay_evidence["status"] == "VERIFIED",
        },
    }
    report["report_sha256"] = hashlib.sha256(_canonical(report)).hexdigest()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conventional", type=Path, required=True)
    parser.add_argument("--field-context", type=Path)
    parser.add_argument("--m3-replay-report", type=Path)
    parser.add_argument("--decision-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    conventional = json.loads(args.conventional.read_text(encoding="utf-8"))
    field_context = (
        json.loads(args.field_context.read_text(encoding="utf-8"))
        if args.field_context else None
    )
    replay_report = (
        json.loads(args.m3_replay_report.read_text(encoding="utf-8"))
        if args.m3_replay_report else None
    )
    decision_evidence = (
        json.loads(args.decision_evidence.read_text(encoding="utf-8"))
        if args.decision_evidence else None
    )
    report = build_conventional_delivery_report(
        conventional, field_context, replay_report, decision_evidence,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "action": report["conventional"]["action"],
        "field_context_status": report["field_context"]["status"],
        "m3_replay_evidence_status": report["m3_replay_evidence"]["status"],
        "report_sha256": report["report_sha256"],
        "release_eligible": False,
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
