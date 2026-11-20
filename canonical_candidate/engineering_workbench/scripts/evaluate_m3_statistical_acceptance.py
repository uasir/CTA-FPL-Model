#!/usr/bin/env python3
"""Apply pre-registered statistical evidence gates to M3 provider cohorts.

This is an uncertainty screen, not a causal analysis or promotion decision.
It consumes the descriptive aggregator output and keeps provider variants apart.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any, Mapping

# Two-sided 95% Student-t critical values for df=1..30; normal limit thereafter.
_T95 = (12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262,
        2.228, 2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101,
        2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052,
        2.048, 2.045, 2.042)


class StatisticalGateError(ValueError):
    """Raised when the descriptive aggregate is not a valid input."""


def _fail(message: str) -> None:
    raise StatisticalGateError(message)


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        _fail(f"{label} must be finite")
    return float(value)


def _t_critical(n: int) -> float:
    df = n - 1
    return _T95[df - 1] if df <= len(_T95) else 1.96


def _mean_ci(values: list[float]) -> dict[str, float | None]:
    n = len(values)
    mean = statistics.fmean(values)
    if n < 2:
        return {"lower_95": None, "upper_95": None, "standard_error": None}
    se = statistics.stdev(values) / math.sqrt(n)
    margin = _t_critical(n) * se
    return {"lower_95": mean - margin, "upper_95": mean + margin, "standard_error": se}


def _wilson_95(successes: int, n: int) -> dict[str, float]:
    # Wilson score interval, z=1.96.
    z = 1.96
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt((p * (1 - p) / n) + (z * z / (4 * n * n))) / denominator
    return {"lower_95": max(0.0, centre - half), "upper_95": min(1.0, centre + half)}


def _action_summary(events: list[Mapping[str, Any]], action: str) -> dict[str, Any]:
    selected = [e for e in events if e.get("recommended_action") == action]
    deltas = [_finite(e.get("net_points_delta_vs_hold"), f"{action} delta") for e in selected]
    return {
        "event_count": len(selected),
        "mean_delta_vs_hold": statistics.fmean(deltas) if deltas else None,
        "cumulative_delta_vs_hold": sum(deltas),
        "deltas": deltas,
    }


def assess_cohort(cohort: Mapping[str, Any], min_events: int = 20,
                  min_transfers: int = 10, material_effect_points: float = 0.0) -> dict[str, Any]:
    identity = cohort.get("provider_identity")
    events = cohort.get("events")
    if not isinstance(identity, Mapping) or not all(
        isinstance(identity.get(k), str) and identity[k].strip() for k in ("name", "product", "variant")
    ):
        _fail("provider cohort identity is incomplete")
    if not isinstance(events, list) or not events:
        _fail("provider cohort must contain event rows")
    deltas: list[float] = []
    transfers = 0
    seen_gws: set[int] = set()
    for index, event in enumerate(events):
        if not isinstance(event, Mapping):
            _fail(f"events[{index}] must be an object")
        gw = event.get("target_gameweek")
        if isinstance(gw, bool) or not isinstance(gw, int) or gw < 1 or gw in seen_gws:
            _fail("provider cohort contains invalid or duplicate Gameweek")
        seen_gws.add(gw)
        action = event.get("recommended_action")
        if action not in {"HOLD", "TRANSFER"}:
            _fail(f"events[{index}] action must be HOLD or TRANSFER")
        delta = _finite(event.get("net_points_delta_vs_hold"), f"events[{index}].net_points_delta_vs_hold")
        deltas.append(delta)
        if action == "TRANSFER":
            transfers += 1
    ci = _mean_ci(deltas)
    if len(events) < min_events or transfers < min_transfers or ci["lower_95"] is None:
        status = "INSUFFICIENT_EVIDENCE"
    elif ci["lower_95"] > material_effect_points:
        status = "EVIDENCE_THRESHOLD_MET"
    else:
        status = "INCONCLUSIVE"
    positive = sum(v > 0 for v in deltas)
    transfer_summary = _action_summary(events, "TRANSFER")
    hold_summary = _action_summary(events, "HOLD")
    return {
        "provider_identity": dict(identity),
        "event_count": len(events),
        "distinct_gameweeks": len(seen_gws),
        "transfer_decision_count": transfers,
        "hold_decision_count": len(events) - transfers,
        "mean_net_points_delta_vs_hold": statistics.fmean(deltas),
        "median_net_points_delta_vs_hold": statistics.median(deltas),
        "sample_stddev_net_points_delta": statistics.stdev(deltas) if len(deltas) > 1 else None,
        "mean_delta_student_t_95_ci": ci,
        "positive_delta_rate": positive / len(deltas),
        "positive_delta_rate_wilson_95_ci": _wilson_95(positive, len(deltas)),
        "transfer_decisions": transfer_summary,
        "hold_decisions": hold_summary,
        "pre_registered_thresholds": {
            "minimum_scored_gameweeks": min_events,
            "minimum_transfer_decisions": min_transfers,
            "minimum_mean_effect_points_per_gameweek": material_effect_points,
            "confidence_level": 0.95,
            "interval_method": "two-sided Student-t interval on gameweek-level paired deltas",
            "positive_rate_interval": "Wilson score interval",
        },
        "evidence_status": status,
        "promotion_eligible": False,
        "historical_performance_validated": False,
    }


def assess_aggregation(aggregation: Mapping[str, Any], min_events: int = 20,
                      min_transfers: int = 10, material_effect_points: float = 0.0) -> dict[str, Any]:
    if aggregation.get("evidence_class") != "AGGREGATED_REAL_EVENT_SCORES":
        _fail("input must be an M3 real-event aggregation")
    if aggregation.get("promotion_eligible") is not False or aggregation.get("historical_performance_validated") is not False:
        _fail("input aggregation must remain explicitly non-promotion evidence")
    cohorts = aggregation.get("provider_cohorts")
    if not isinstance(cohorts, list) or not cohorts:
        _fail("aggregation must contain provider cohorts")
    if min_events < 2 or min_transfers < 1 or not math.isfinite(material_effect_points):
        _fail("threshold configuration is invalid")
    results = [assess_cohort(c, min_events, min_transfers, material_effect_points) for c in cohorts]
    return {
        "statistical_gate_contract_version": "0.1.0",
        "manager_team_id": aggregation.get("manager_team_id"),
        "aggregation_input_sha256": aggregation.get("aggregation_input_sha256"),
        "provider_cohorts": results,
        "overall_evidence_status": (
            "EVIDENCE_THRESHOLD_MET" if any(r["evidence_status"] == "EVIDENCE_THRESHOLD_MET" for r in results)
            else "INCONCLUSIVE" if any(r["evidence_status"] == "INCONCLUSIVE" for r in results)
            else "INSUFFICIENT_EVIDENCE"
        ),
        "promotion_eligible": False,
        "historical_performance_validated": False,
        "limitations": [
            "Gameweek-level deltas are treated as independent for the Student-t interval; serial dependence can make this interval too narrow.",
            "This is not a gameweek-clustered bootstrap and does not establish causality, forecast accuracy, rank impact or future performance.",
            "Thresholds are engineering defaults and must be reviewed and frozen before comparative results are inspected.",
            "Meeting this statistical screen is not model approval, provider promotion or release authorization.",
            "HOLD events have zero recommendation-versus-hold delta by construction and are reported separately; they do not count toward the transfer minimum.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("aggregation", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-events", type=int, default=20)
    parser.add_argument("--min-transfers", type=int, default=10)
    parser.add_argument("--material-effect-points", type=float, default=0.0)
    args = parser.parse_args()
    source = json.loads(args.aggregation.read_text(encoding="utf-8"))
    result = assess_aggregation(source, args.min_events, args.min_transfers, args.material_effect_points)
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
