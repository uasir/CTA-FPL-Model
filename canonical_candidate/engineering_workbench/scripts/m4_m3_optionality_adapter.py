#!/usr/bin/env python3
"""Attach optional M4 context without changing a frozen M3 recommendation."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


class M3M4OptionalityError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise M3M4OptionalityError("M3 payload is not canonical JSON") from exc


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise M3M4OptionalityError(f"{label} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise M3M4OptionalityError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise M3M4OptionalityError(f"{label} must include a timezone")
    return parsed


def _verify_m3(m3: Mapping[str, Any]) -> tuple[str, str]:
    if not isinstance(m3, Mapping):
        raise M3M4OptionalityError("frozen M3 output must be an object")
    frozen = m3.get("frozen_decision")
    candidate = m3.get("evaluation_candidate")
    if not isinstance(frozen, Mapping) or not isinstance(candidate, Mapping):
        raise M3M4OptionalityError("M3 output must contain frozen_decision and evaluation_candidate")
    digest = frozen.get("decision_sha256")
    body = {key: value for key, value in frozen.items() if key != "decision_sha256"}
    expected = hashlib.sha256(_canonical(body)).hexdigest()
    if digest != expected:
        raise M3M4OptionalityError("M3 frozen decision hash does not match its content")
    if _canonical(candidate.get("frozen_decision")) != _canonical(dict(frozen)):
        raise M3M4OptionalityError("M3 evaluation_candidate frozen decision differs from top-level decision")
    for key in ("manager_team_id", "target_gameweek", "deadline_utc"):
        if candidate.get(key) != m3.get(key):
            raise M3M4OptionalityError(f"M3 evaluation_candidate {key} differs from top-level output")
    # Some archived M3 outputs carry season only inside evaluation_candidate.
    # Accept that canonical location when the top-level convenience field is absent.
    top_level_season = m3.get("season")
    candidate_season = candidate.get("season")
    if top_level_season is not None and candidate_season != top_level_season:
        raise M3M4OptionalityError("M3 evaluation_candidate season differs from top-level output")
    if candidate_season is not None and (
        not isinstance(candidate_season, str) or not candidate_season.strip()
    ):
        raise M3M4OptionalityError("M3 evaluation_candidate season must be a non-empty string")
    if candidate.get("as_of_utc") != m3.get("decision_as_of_utc"):
        raise M3M4OptionalityError("M3 evaluation_candidate as_of_utc differs from decision timestamp")
    return expected, hashlib.sha256(_canonical(dict(m3))).hexdigest()


def _validate_m4_against_m3(m4: Mapping[str, Any], m3: Mapping[str, Any],
                            decision_hash: str) -> None:
    if not isinstance(m4, Mapping) or m4.get("status") != "PASS_PREDEADLINE_FIELD_COMPARISON":
        raise M3M4OptionalityError("M4 comparison status is not a passing pre-deadline comparison")
    if m4.get("release_eligible") is not False:
        raise M3M4OptionalityError("M4 context must remain non-release-eligible")
    field = m4.get("field_context")
    if not isinstance(field, Mapping):
        raise M3M4OptionalityError("M4 field_context is missing")
    candidate = field.get("candidate")
    if not isinstance(candidate, Mapping):
        raise M3M4OptionalityError("M4 bound candidate is missing")
    if candidate.get("manager_team_id") != m3.get("manager_team_id"):
        raise M3M4OptionalityError("M4 manager ID differs from frozen M3")
    m3_season = m3.get("season")
    if m3_season is None:
        m3_season = m3["evaluation_candidate"].get("season")
    if not isinstance(m3_season, str) or not m3_season.strip():
        raise M3M4OptionalityError("M3 season is missing from both the output and evaluation candidate")
    if candidate.get("season") != m3_season or candidate.get("target_gameweek") != m3.get("target_gameweek"):
        raise M3M4OptionalityError("M4 season or Gameweek differs from frozen M3")
    if candidate.get("deadline_utc") != m3.get("deadline_utc"):
        raise M3M4OptionalityError("M4 deadline differs from frozen M3")
    if candidate.get("decision_sha256") != decision_hash:
        raise M3M4OptionalityError("M4 context is bound to a different frozen M3 decision")
    if candidate.get("action") != m3["frozen_decision"].get("action"):
        raise M3M4OptionalityError("M4 action differs from frozen M3 decision")
    if candidate.get("transfer_out_id") != m3["frozen_decision"].get("transfer_out_id"):
        raise M3M4OptionalityError("M4 outgoing player differs from frozen M3 decision")
    if candidate.get("transfer_in_id") != m3["frozen_decision"].get("transfer_in_id"):
        raise M3M4OptionalityError("M4 incoming player differs from frozen M3 decision")

    captured = _time(field.get("captured_at_utc"), "M4 field capture time")
    decision_at = _time(m3.get("decision_as_of_utc"), "M3 decision time")
    deadline = _time(m3.get("deadline_utc"), "M3 deadline")
    if not captured < decision_at < deadline:
        raise M3M4OptionalityError("M4 field snapshot must predate M3 decision and deadline")

    m3_state = m3["evaluation_candidate"].get("manager_state")
    if not isinstance(m3_state, Mapping):
        raise M3M4OptionalityError("M3 manager_state is missing")
    roster = m3_state.get("squad_snapshot")
    hold = m3_state.get("hold_plan")
    if not isinstance(roster, list) or not isinstance(hold, Mapping):
        raise M3M4OptionalityError("M3 original squad snapshot or hold plan is missing")
    original_ids = {str(row.get("fpl_element_id")) for row in roster if isinstance(row, Mapping)}
    if len(original_ids) != 15 or original_ids != set(map(str, candidate.get("squad_15", []))):
        raise M3M4OptionalityError("M4 original squad differs from frozen M3 squad")
    for m4_key, m3_key in (
        ("starting_xi", "starting_xi"),
        ("bench_order", "bench_order"),
        ("reserve_goalkeeper_id", "reserve_goalkeeper_id"),
        ("captain_id", "captain_id"),
        ("vice_captain_id", "vice_captain_id"),
        ("formation", "formation"),
    ):
        expected_value = hold.get(m3_key)
        actual_value = candidate.get(m4_key)
        if isinstance(expected_value, list):
            matches = list(map(str, actual_value or [])) == list(map(str, expected_value))
        else:
            matches = str(actual_value) == str(expected_value)
        if not matches:
            raise M3M4OptionalityError(f"M4 original manager state {m4_key} differs from frozen M3")

    diagnostics = m4.get("field_diagnostics")
    baseline = m4.get("portfolio_exposure_baseline")
    comparison = m4.get("comparison")
    if not isinstance(diagnostics, Mapping) or diagnostics.get("status") != "PASS_FIELD_CONTEXT_DIAGNOSTICS":
        raise M3M4OptionalityError("M4 field diagnostics are missing or invalid")
    if not isinstance(baseline, Mapping) or baseline.get("status") != "PASS_NONCOVARIANCE_PORTFOLIO_EXPOSURE_BASELINE":
        raise M3M4OptionalityError("M4 portfolio baseline is missing or invalid")
    if not isinstance(comparison, Mapping):
        raise M3M4OptionalityError("M4 candidate comparison is missing")
    if comparison.get("covar") != "DISABLED" or comparison.get("expected_points") != "NOT_COMBINED_WITH_EO":
        raise M3M4OptionalityError("M4 comparison violates EV/EO or CoVar boundary")
    if baseline.get("covar") != "DISABLED" or baseline.get("expected_points") != "NOT_COMBINED_WITH_EO":
        raise M3M4OptionalityError("M4 portfolio baseline violates EV/EO or CoVar boundary")


def attach_optional_m4_context(
    m3_output: Mapping[str, Any],
    m4_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a wrapper whose M3 payload is byte-canonical identical in all modes."""
    decision_hash, m3_hash = _verify_m3(m3_output)
    preserved_m3 = copy.deepcopy(dict(m3_output))
    if m4_context is None:
        m4_status, reason, attached = "NOT_SUPPLIED", None, None
    else:
        try:
            _validate_m4_against_m3(m4_context, m3_output, decision_hash)
            m4_status, reason, attached = "ATTACHED_DESCRIPTIVE_CONTEXT", None, copy.deepcopy(dict(m4_context))
        except (M3M4OptionalityError, TypeError, KeyError, ValueError) as exc:
            m4_status, reason, attached = "WITHHELD_DEGRADED_MODE", str(exc), None

    if hashlib.sha256(_canonical(preserved_m3)).hexdigest() != m3_hash:
        raise M3M4OptionalityError("M3 payload changed while attaching optional context")
    return {
        "status": "M3_PRESERVED_WITH_OPTIONAL_M4_CONTEXT",
        "m4_status": m4_status,
        "m4_withheld_reason": reason,
        "m3_output_sha256": m3_hash,
        "m3_frozen_decision_sha256": decision_hash,
        "m3_output": preserved_m3,
        "m4_context": attached,
        "release_eligible": False,
        "invariant": "M4 absent, stale, invalid or ineligible cannot change M3 output, EV, legality or frozen decision hash.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--m3", type=Path, required=True)
    parser.add_argument("--m4", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    m3 = json.loads(args.m3.read_text(encoding="utf-8"))
    m4 = json.loads(args.m4.read_text(encoding="utf-8")) if args.m4 else None
    result = attach_optional_m4_context(m3, m4)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
                           encoding="utf-8")
    print(json.dumps({
        "status": result["status"], "m4_status": result["m4_status"],
        "m3_output_sha256": result["m3_output_sha256"],
        "m3_frozen_decision_sha256": result["m3_frozen_decision_sha256"],
        "release_eligible": False, "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
