#!/usr/bin/env python3
"""Apply deterministic Gameweek-cluster bootstrap evidence gates to M3 cohorts.

The resampling unit is one complete manager/Gameweek decision record. This is
an uncertainty screen only; it neither admits events nor authorizes promotion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from pathlib import Path
from typing import Any, Mapping


class StatisticalGateError(ValueError):
    """Raised when the descriptive aggregate is not a valid input."""


def _fail(message: str) -> None:
    raise StatisticalGateError(message)


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        _fail(f"{label} must be finite")
    return float(value)


def _quantile(sorted_values: list[float], probability: float) -> float:
    """Linear-interpolated sample quantile (Hyndman-Fan type 7)."""
    if not sorted_values or not 0.0 <= probability <= 1.0:
        _fail("quantile requires values and a probability in [0, 1]")
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def _bootstrap_mean_ci(values: list[float], seed_material: Mapping[str, Any],
                       replicates: int) -> dict[str, Any]:
    if len(values) < 2:
        return {"lower_95": None, "upper_95": None, "bootstrap_standard_error": None,
                "replicates": replicates, "seed_sha256": None}
    canonical = json.dumps(
        {"seed_material": seed_material, "values": values},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    seed_digest = hashlib.sha256(canonical).hexdigest()
    rng = random.Random(int(seed_digest, 16))
    n = len(values)
    means = [
        statistics.fmean(values[rng.randrange(n)] for _ in range(n))
        for _ in range(replicates)
    ]
    ordered = sorted(means)
    return {
        "lower_95": _quantile(ordered, 0.025),
        "upper_95": _quantile(ordered, 0.975),
        "bootstrap_standard_error": statistics.stdev(means),
        "replicates": replicates,
        "seed_sha256": seed_digest,
        "resampling_unit": "complete manager/Gameweek decision record",
        "interval_method": "two-sided percentile cluster bootstrap",
        "quantile_method": "linear interpolation (Hyndman-Fan type 7)",
    }


def _wilson_95(successes: int, n: int) -> dict[str, float]:
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


def assess_cohort(cohort: Mapping[str, Any], aggregation_input_sha256: str,
                  min_events: int = 20, min_transfers: int = 10,
                  material_effect_points: float = 0.0,
                  bootstrap_replicates: int = 10000) -> dict[str, Any]:
    identity = cohort.get("provider_identity")
    events = cohort.get("events")
    if not isinstance(identity, Mapping) or not all(
        isinstance(identity.get(k), str) and identity[k].strip()
        for k in ("name", "product", "variant")
    ):
        _fail("provider cohort identity is incomplete")
    if not isinstance(events, list) or not events:
        _fail("provider cohort must contain event rows")
    if isinstance(min_events, bool) or not isinstance(min_events, int) or min_events < 2:
        _fail("minimum event threshold must be an integer >= 2")
    if isinstance(min_transfers, bool) or not isinstance(min_transfers, int) or min_transfers < 1:
        _fail("minimum transfer threshold must be an integer >= 1")
    if isinstance(bootstrap_replicates, bool) or not isinstance(bootstrap_replicates, int) or bootstrap_replicates < 1000:
        _fail("bootstrap replicates must be an integer >= 1000")
    material_effect_points = _finite(material_effect_points, "material_effect_points")
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
        if action == "HOLD" and not math.isclose(delta, 0.0, abs_tol=1e-9):
            _fail(f"events[{index}] HOLD decision must have zero delta versus hold")
        deltas.append(delta)
        if action == "TRANSFER":
            transfers += 1

    seed_material = {
        "aggregation_input_sha256": aggregation_input_sha256,
        "provider_identity": dict(identity),
        "gameweeks": sorted(seen_gws),
        "bootstrap_contract": "m3-gameweek-cluster-bootstrap-v1",
    }
    ci = _bootstrap_mean_ci(deltas, seed_material, bootstrap_replicates)
    if len(events) < min_events or transfers < min_transfers or ci["lower_95"] is None:
        status = "INSUFFICIENT_EVIDENCE"
    elif ci["lower_95"] > material_effect_points:
        status = "EVIDENCE_THRESHOLD_MET"
    else:
        status = "INCONCLUSIVE"
    positive = sum(v > 0 for v in deltas)
    return {
        "provider_identity": dict(identity),
        "event_count": len(events),
        "distinct_gameweeks": len(seen_gws),
        "transfer_decision_count": transfers,
        "hold_decision_count": len(events) - transfers,
        "mean_net_points_delta_vs_hold": statistics.fmean(deltas),
        "median_net_points_delta_vs_hold": statistics.median(deltas),
        "sample_stddev_net_points_delta": statistics.stdev(deltas) if len(deltas) > 1 else None,
        "mean_delta_gameweek_bootstrap_95_ci": ci,
        "positive_delta_rate": positive / len(deltas),
        "positive_delta_rate_wilson_95_ci": _wilson_95(positive, len(deltas)),
        "transfer_decisions": _action_summary(events, "TRANSFER"),
        "hold_decisions": _action_summary(events, "HOLD"),
        "pre_registered_thresholds": {
            "minimum_scored_gameweeks": min_events,
            "minimum_transfer_decisions": min_transfers,
            "minimum_mean_effect_points_per_gameweek": material_effect_points,
            "confidence_level": 0.95,
            "bootstrap_replicates": bootstrap_replicates,
            "resampling_unit": "complete manager/Gameweek decision record",
            "interval_method": "two-sided percentile cluster bootstrap",
            "positive_rate_interval": "Wilson score interval",
        },
        "evidence_status": status,
        "promotion_eligible": False,
        "historical_performance_validated": False,
    }


def assess_aggregation(aggregation: Mapping[str, Any], min_events: int = 20,
                      min_transfers: int = 10, material_effect_points: float = 0.0,
                      bootstrap_replicates: int = 10000) -> dict[str, Any]:
    if aggregation.get("evidence_class") != "AGGREGATED_REAL_EVENT_SCORES":
        _fail("input must be an M3 real-event aggregation")
    if aggregation.get("promotion_eligible") is not False or aggregation.get("historical_performance_validated") is not False:
        _fail("input aggregation must remain explicitly non-promotion evidence")
    cohorts = aggregation.get("provider_cohorts")
    if not isinstance(cohorts, list) or not cohorts:
        _fail("aggregation must contain provider cohorts")
    digest = aggregation.get("aggregation_input_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        _fail("aggregation_input_sha256 must be a lowercase SHA-256 digest")
    results = [
        assess_cohort(c, digest, min_events, min_transfers,
                      material_effect_points, bootstrap_replicates)
        for c in cohorts
    ]
    return {
        "statistical_gate_contract_version": "0.2.0",
        "manager_team_id": aggregation.get("manager_team_id"),
        "aggregation_input_sha256": digest,
        "provider_cohorts": results,
        "overall_evidence_status": (
            "EVIDENCE_THRESHOLD_MET" if any(r["evidence_status"] == "EVIDENCE_THRESHOLD_MET" for r in results)
            else "INCONCLUSIVE" if any(r["evidence_status"] == "INCONCLUSIVE" for r in results)
            else "INSUFFICIENT_EVIDENCE"
        ),
        "promotion_eligible": False,
        "historical_performance_validated": False,
        "limitations": [
            "Bootstrap resampling uses complete manager/Gameweek decision records and keeps provider cohorts separate.",
            "Gameweek resampling assumes exchangeability across observed Gameweeks; temporal dependence and changing season conditions can still invalidate nominal coverage.",
            "This interval does not establish causality, forecast accuracy, rank impact or future performance.",
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
    parser.add_argument("--bootstrap-replicates", type=int, default=10000)
    args = parser.parse_args()
    source = json.loads(args.aggregation.read_text(encoding="utf-8"))
    result = assess_aggregation(source, args.min_events, args.min_transfers,
                                args.material_effect_points, args.bootstrap_replicates)
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
