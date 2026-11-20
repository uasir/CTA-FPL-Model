#!/usr/bin/env python3
"""Bind a pre-deadline field sample to a frozen candidate and compare exposure."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from m4_field_context_contract import validate_field_context
from m4_candidate_field_comparison import compare_frozen_candidate_to_field
from m4_predeadline_field_artifact_adapter import load_predeadline_field_artifact


def build_predeadline_comparison(csv_path, report_path, candidate_path, *,
                                 season: str, source_url: str) -> dict:
    artifact = load_predeadline_field_artifact(
        csv_path, report_path, season=season, source_url=source_url
    )
    candidate = json.loads(Path(candidate_path).read_text(encoding="utf-8"))
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
                        help="Frozen M3 candidate JSON matching the M4 contract schema")
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
