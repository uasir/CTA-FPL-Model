#!/usr/bin/env python3
"""Aggregate independently scored M3 real decision events without promoting them.

Input files are evaluator outputs, not raw candidates. Synthetic, unadmitted,
duplicate, malformed, or cross-manager records are rejected. Results are grouped
by provider identity so unlike forecast products are never silently pooled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

REAL_STATUS = "REAL_DECISION_BACKTEST_EVENT_SCORED_NOT_PROMOTION_EVIDENCE"


class AggregationError(ValueError):
    """Raised when a purported real evaluation cohort is unsafe to aggregate."""


def _fail(message: str) -> None:
    raise AggregationError(message)


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        _fail(f"{field} must be a finite number")
    return float(value)


def _validate_row(row: Any, index: int) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        _fail(f"records[{index}] must be an object")
    if row.get("evidence_class") != "REAL_CANDIDATE" or row.get("evaluation_status") != REAL_STATUS:
        _fail(f"records[{index}] is not an independently admitted and scored real event")
    if row.get("historical_performance_validated") is not False:
        _fail(f"records[{index}] must not claim historical performance validation")
    manager = row.get("manager_team_id")
    gw = row.get("target_gameweek")
    if isinstance(manager, bool) or not isinstance(manager, int) or manager < 1:
        _fail(f"records[{index}].manager_team_id must be a positive integer")
    if isinstance(gw, bool) or not isinstance(gw, int) or gw < 1:
        _fail(f"records[{index}].target_gameweek must be a positive integer")
    for field in ("evaluation_input_sha256", "frozen_decision_sha256", "software_commit"):
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            _fail(f"records[{index}].{field} is required")
    provider = row.get("provider_identity")
    if not isinstance(provider, Mapping):
        _fail(f"records[{index}].provider_identity must be an object")
    for field in ("name", "product", "variant"):
        if not isinstance(provider.get(field), str) or not provider[field].strip():
            _fail(f"records[{index}].provider_identity.{field} is required")
    action = row.get("recommended_action")
    if action not in {"HOLD", "TRANSFER"}:
        _fail(f"records[{index}].recommended_action must be HOLD or TRANSFER")
    recommended = row.get("recommended")
    hold = row.get("hold")
    if not isinstance(recommended, Mapping) or not isinstance(hold, Mapping):
        _fail(f"records[{index}] must include recommended and hold scores")
    recommended_net = _number(recommended.get("net_points"), f"records[{index}].recommended.net_points")
    hold_net = _number(hold.get("net_points"), f"records[{index}].hold.net_points")
    delta = _number(row.get("net_points_delta_vs_hold"), f"records[{index}].net_points_delta_vs_hold")
    if not math.isclose(delta, recommended_net - hold_net, abs_tol=1e-9):
        _fail(f"records[{index}] net_points_delta_vs_hold does not equal recommended minus hold")
    hits = _number(recommended.get("transfer_hit_points"), f"records[{index}].recommended.transfer_hit_points")
    if hits < 0 or (action == "HOLD" and hits != 0):
        _fail(f"records[{index}] has invalid transfer hit cost")
    if not isinstance(row.get("source_provenance"), list) or not row["source_provenance"]:
        _fail(f"records[{index}].source_provenance is required")
    return {
        "manager_team_id": manager,
        "target_gameweek": gw,
        "provider_identity": dict(provider),
        "recommended_action": action,
        "recommended_net_points": recommended_net,
        "hold_net_points": hold_net,
        "net_points_delta_vs_hold": delta,
        "transfer_hit_points": hits,
        "evaluation_input_sha256": row["evaluation_input_sha256"],
        "frozen_decision_sha256": row["frozen_decision_sha256"],
        "software_commit": row["software_commit"],
    }


def _summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    deltas = [row["net_points_delta_vs_hold"] for row in rows]
    transfers = [row for row in rows if row["recommended_action"] == "TRANSFER"]
    holds = [row for row in rows if row["recommended_action"] == "HOLD"]
    wins = sum(value > 0 for value in deltas)
    losses = sum(value < 0 for value in deltas)
    ties = len(deltas) - wins - losses
    return {
        "event_count": len(rows),
        "gameweeks": [row["target_gameweek"] for row in rows],
        "recommended_action_counts": {"TRANSFER": len(transfers), "HOLD": len(holds)},
        "positive_delta_events": wins,
        "negative_delta_events": losses,
        "neutral_delta_events": ties,
        "positive_delta_rate": wins / len(rows),
        "cumulative_net_points_delta_vs_hold": sum(deltas),
        "mean_net_points_delta_vs_hold": statistics.fmean(deltas),
        "median_net_points_delta_vs_hold": statistics.median(deltas),
        "population_stddev_net_points_delta": statistics.pstdev(deltas),
        "total_transfer_hit_points": sum(row["transfer_hit_points"] for row in rows),
        "transfer_event_mean_delta": statistics.fmean(row["net_points_delta_vs_hold"] for row in transfers) if transfers else None,
        "hold_event_mean_delta": statistics.fmean(row["net_points_delta_vs_hold"] for row in holds) if holds else None,
        "events": rows,
    }


def aggregate_evaluation_results(records: list[Any]) -> dict[str, Any]:
    """Validate and aggregate event results, separated by manager and provider."""
    if not isinstance(records, list) or not records:
        _fail("at least one evaluation result is required")
    rows = [_validate_row(row, index) for index, row in enumerate(records)]
    managers = {row["manager_team_id"] for row in rows}
    if len(managers) != 1:
        _fail("one aggregation run may contain only one manager")
    seen_gw: set[tuple[int, int, str, str, str]] = set()
    seen_inputs: set[str] = set()
    for index, row in enumerate(rows):
        provider = row["provider_identity"]
        key = (row["manager_team_id"], row["target_gameweek"],
               provider["name"], provider["product"], provider["variant"])
        if key in seen_gw:
            _fail(f"duplicate manager/Gameweek/provider event: GW{row['target_gameweek']}")
        seen_gw.add(key)
        digest = row["evaluation_input_sha256"]
        if digest in seen_inputs:
            _fail(f"duplicate evaluation input at records[{index}]")
        seen_inputs.add(digest)

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        p = row["provider_identity"]
        groups[(p["name"], p["product"], p["variant"])].append(row)
    summaries = []
    for identity, cohort in sorted(groups.items()):
        cohort.sort(key=lambda row: row["target_gameweek"])
        summaries.append({
            "provider_identity": {"name": identity[0], "product": identity[1], "variant": identity[2]},
            **_summarise(cohort),
        })
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return {
        "aggregation_contract_version": "0.1.0",
        "manager_team_id": next(iter(managers)),
        "evidence_class": "AGGREGATED_REAL_EVENT_SCORES",
        "aggregation_input_sha256": hashlib.sha256(canonical).hexdigest(),
        "provider_cohorts": summaries,
        "promotion_eligible": False,
        "historical_performance_validated": False,
        "limitations": [
            "Only supplied independently admitted and scored event outputs are included.",
            "Cumulative points delta is descriptive, not a causal estimate or proof of future value.",
            "Provider cohorts are kept separate; no cross-provider pooling or consensus is inferred.",
            "No minimum sample-size, uncertainty, calibration, rank-impact, or release gate is satisfied by this aggregation alone.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evaluation_results", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    records = [json.loads(path.read_text(encoding="utf-8")) for path in args.evaluation_results]
    result = aggregate_evaluation_results(records)
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
