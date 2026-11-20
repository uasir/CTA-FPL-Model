#!/usr/bin/env python3
"""Bind a pre-deadline field sample to a frozen candidate and compare exposure."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from m4_field_context_contract import validate_field_context
from m4_candidate_field_comparison import compare_frozen_candidate_to_field
from m4_predeadline_field_artifact_adapter import load_predeadline_field_artifact


def adapt_m3_evaluation_candidate(document: dict) -> dict:
    """Map the real M3 output envelope to the M4 contract without changing its decision."""
    if not isinstance(document, dict):
        raise ValueError("M3 candidate document must be an object")
    source = document.get("evaluation_candidate", document)
    if not isinstance(source, dict):
        raise ValueError("M3 evaluation_candidate must be an object")
    state = source.get("manager_state")
    decision = source.get("frozen_decision")
    if not isinstance(state, dict) or not isinstance(decision, dict):
        raise ValueError("M3 candidate must contain manager_state and frozen_decision")
    # Keep direct M4-contract fixtures/inputs valid; production M3 outputs use hold_plan.
    if isinstance(state.get("manager_state"), dict) and "squad_15" in state["manager_state"]:
        return source
    roster = state.get("squad_snapshot")
    hold = state.get("hold_plan")
    if not isinstance(roster, list) or len(roster) != 15 or not isinstance(hold, dict):
        raise ValueError("M3 manager_state must contain 15-player squad_snapshot and hold_plan")
    try:
        squad = [int(row["fpl_element_id"]) for row in roster]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("M3 squad_snapshot has invalid FPL element IDs") from exc
    if len(set(squad)) != 15:
        raise ValueError("M3 squad_snapshot contains duplicate FPL element IDs")

    action = decision.get("action")
    outgoing, incoming = decision.get("transfer_out_id"), decision.get("transfer_in_id")
    if action == "TRANSFER":
        if outgoing not in squad or not isinstance(incoming, int) or incoming <= 0:
            raise ValueError("M3 transfer identity is invalid")
        if incoming in squad:
            raise ValueError("M3 incoming player already exists in original squad")
        expected_squad = sorted((set(squad) - {outgoing}) | {incoming})
        expected_xi = list(hold.get("starting_xi", []))
        expected_bench = list(hold.get("bench_order", []))
        if outgoing in expected_xi:
            expected_xi[expected_xi.index(outgoing)] = incoming
        elif outgoing in expected_bench:
            expected_bench[expected_bench.index(outgoing)] = incoming
        else:
            raise ValueError("M3 outgoing player has no starting-XI or bench slot")
    elif action == "HOLD":
        if outgoing is not None or incoming is not None:
            raise ValueError("M3 HOLD decision cannot carry transfer player IDs")
        expected_squad = sorted(squad)
        expected_xi = list(hold.get("starting_xi", []))
        expected_bench = list(hold.get("bench_order", []))
    else:
        raise ValueError("M3 action must be HOLD or TRANSFER")

    proposed_plan = decision.get("squad_plan")
    if not isinstance(proposed_plan, dict):
        raise ValueError("M3 frozen_decision.squad_plan is required")
    expected_plan = {
        "squad_ids": expected_squad,
        "starting_xi": expected_xi,
        "bench_order": expected_bench,
        "reserve_goalkeeper_id": hold.get("reserve_goalkeeper_id"),
        "captain_id": hold.get("captain_id"),
        "vice_captain_id": hold.get("vice_captain_id"),
        "formation": hold.get("formation"),
    }
    for key, expected in expected_plan.items():
        actual = proposed_plan.get(key)
        if key == "squad_ids":
            actual = sorted(actual or [])
        if actual != expected:
            raise ValueError(
                f"M3 proposed plan changes {key} beyond the frozen transfer's existing slot"
            )

    return {
        "manager_team_id": source.get("manager_team_id"),
        "season": source.get("season"),
        "target_gameweek": source.get("target_gameweek"),
        "deadline_utc": source.get("deadline_utc"),
        "as_of_utc": source.get("as_of_utc"),
        "frozen_decision": {
            "action": action,
            "transfer_out_id": outgoing,
            "transfer_in_id": incoming,
            "decision_sha256": decision.get("decision_sha256"),
        },
        "manager_state": {"manager_state": {
            "squad_15": squad,
            "starting_xi": list(hold.get("starting_xi", [])),
            "bench_order": list(hold.get("bench_order", [])),
            "reserve_goalkeeper_id": hold.get("reserve_goalkeeper_id"),
            "captain_id": hold.get("captain_id"),
            "vice_captain_id": hold.get("vice_captain_id"),
            "formation": hold.get("formation"),
        }},
    }


def build_predeadline_comparison(csv_path, report_path, candidate_path, *,
                                 season: str, source_url: str) -> dict:
    artifact = load_predeadline_field_artifact(
        csv_path, report_path, season=season, source_url=source_url
    )
    candidate_document = json.loads(Path(candidate_path).read_text(encoding="utf-8"))
    candidate = adapt_m3_evaluation_candidate(candidate_document)
    binding = validate_field_context(
        artifact["snapshot"], artifact["field_eo_rows"], candidate
    )
    comparison = compare_frozen_candidate_to_field(binding)
    return {
        "status": "PASS_PREDEADLINE_FIELD_COMPARISON",
        "evidence_role": artifact["evidence_role"],
        "picks_lock_verified": False,
        "provisional_picks": True,
        "field_context": binding,
        "comparison": comparison,
        "interpretation_boundary": (
            "Field EO is a time-stamped provisional sample of current picks, not final locked EO. "
            "It is descriptive exposure context only; expected points are not combined with EO."
        ),
        "release_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True,
                        help="Frozen M3 decision JSON (full M3 output or evaluation_candidate object)")
    parser.add_argument("--season", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_predeadline_comparison(
        args.csv, args.report, args.candidate,
        season=args.season, source_url=args.source_url,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
                           encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "snapshot_id": result["field_context"]["snapshot_id"],
        "gameweek": result["field_context"]["target_gameweek"],
        "candidate_action": result["field_context"]["candidate"]["action"],
        "evidence_role": result["evidence_role"],
        "release_eligible": False,
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
