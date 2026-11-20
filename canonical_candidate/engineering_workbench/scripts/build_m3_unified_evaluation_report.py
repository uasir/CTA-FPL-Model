#!/usr/bin/env python3
"""Build one deterministic M3 descriptive + statistical evidence report.

Inputs must be independently admitted and scored event-result JSON files.
This orchestration layer does not admit, repair, or rescore events.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from aggregate_m3_multigameweek_evaluations import aggregate_evaluation_results
from evaluate_m3_statistical_acceptance import assess_aggregation


class UnifiedReportError(ValueError):
    """Raised when source event results cannot form a unified M3 report."""


def _canonical_record_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    provider = row.get("provider_identity")
    if not isinstance(provider, Mapping):
        provider = {}
    return (
        row.get("manager_team_id", -1),
        row.get("target_gameweek", -1),
        provider.get("name", ""),
        provider.get("product", ""),
        provider.get("variant", ""),
        row.get("evaluation_input_sha256", ""),
    )


def build_unified_report(
    records: list[Any],
    *,
    min_events: int = 20,
    min_transfers: int = 10,
    material_effect_points: float = 0.0,
    bootstrap_replicates: int = 10000,
) -> dict[str, Any]:
    """Aggregate event records and screen each provider cohort, without promotion."""
    if not isinstance(records, list) or not records:
        raise UnifiedReportError("at least one event result is required")
    # Canonicalize ordering so file argument order cannot change the aggregate
    # digest, bootstrap seed, or report payload.
    canonical_records = sorted(records, key=_canonical_record_key)
    aggregation = aggregate_evaluation_results(canonical_records)
    statistical = assess_aggregation(
        aggregation,
        min_events=min_events,
        min_transfers=min_transfers,
        material_effect_points=material_effect_points,
        bootstrap_replicates=bootstrap_replicates,
    )
    if aggregation["aggregation_input_sha256"] != statistical["aggregation_input_sha256"]:
        raise UnifiedReportError("statistical screen did not consume the exact aggregate")
    if aggregation["provider_cohorts"] and len(aggregation["provider_cohorts"]) != len(statistical["provider_cohorts"]):
        raise UnifiedReportError("provider cohort count changed between aggregate and statistical screen")
    return {
        "unified_m3_evaluation_report_version": "1.0.0",
        "manager_team_id": aggregation["manager_team_id"],
        "source_event_count": sum(c["event_count"] for c in aggregation["provider_cohorts"]),
        "aggregation_input_sha256": aggregation["aggregation_input_sha256"],
        "descriptive_performance": aggregation,
        "statistical_evidence": statistical,
        "overall_evidence_status": statistical["overall_evidence_status"],
        "promotion_eligible": False,
        "historical_performance_validated": False,
        "release_eligible": False,
        "interpretation": (
            "Descriptive performance and statistical uncertainty are presented together. "
            "This report is not a causal estimate, forecast validation, provider promotion, "
            "or recommendation release authorization."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evaluation_results", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-events", type=int, default=20)
    parser.add_argument("--min-transfers", type=int, default=10)
    parser.add_argument("--material-effect-points", type=float, default=0.0)
    parser.add_argument("--bootstrap-replicates", type=int, default=10000)
    args = parser.parse_args()

    records = [json.loads(path.read_text(encoding="utf-8")) for path in args.evaluation_results]
    report = build_unified_report(
        records,
        min_events=args.min_events,
        min_transfers=args.min_transfers,
        material_effect_points=args.material_effect_points,
        bootstrap_replicates=args.bootstrap_replicates,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
