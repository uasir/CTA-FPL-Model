#!/usr/bin/env python3
"""Fail-closed research gate for covariance-backed FPL portfolio risk."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping


class CovarGateError(ValueError):
    pass


DEFAULT_SHRINKAGE_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)


def _finite(value: Any, label: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool):
        raise CovarGateError(f"{label} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise CovarGateError(f"{label} must be numeric") from exc
    if not math.isfinite(result) or (nonnegative and result < 0):
        raise CovarGateError(f"{label} must be finite" + (" and non-negative" if nonnegative else ""))
    return result


def _covariance_matrix(pair_rows: list[Mapping[str, Any]]) -> dict[str, dict[str, float]]:
    matrix: dict[str, dict[str, float]] = {}
    seen = set()
    for row in pair_rows:
        p1, p2 = str(row.get("player1_id", "")), str(row.get("player2_id", ""))
        if not p1 or not p2:
            raise CovarGateError("covariance pair rows require both player IDs")
        key = tuple(sorted((p1, p2)))
        if key in seen:
            raise CovarGateError(f"duplicate covariance pair: {key}")
        seen.add(key)
        value = _finite(row.get("covariance"), f"covariance {p1}/{p2}")
        matrix.setdefault(p1, {})[p2] = value
        matrix.setdefault(p2, {})[p1] = value
    return matrix


def portfolio_variance_sensitivity(
    pair_rows: list[Mapping[str, Any]],
    portfolio_weights: Mapping[str, Any],
    *,
    shrinkage_grid: tuple[float, ...] = DEFAULT_SHRINKAGE_GRID,
) -> dict[str, Any]:
    """Recompute descriptive portfolio variance under diagonal shrinkage choices."""
    if not isinstance(portfolio_weights, Mapping) or not portfolio_weights:
        return {"status": "NOT_COMPUTED", "reason": "portfolio_weights_not_supplied", "scenarios": []}
    weights = {str(key): _finite(value, f"weight.{key}", nonnegative=True)
               for key, value in portfolio_weights.items()}
    matrix = _covariance_matrix(pair_rows)
    missing = sorted(
        player_id for player_id in weights
        if player_id not in matrix or any(other not in matrix[player_id] for other in weights)
    )
    if missing:
        return {
            "status": "INCOMPLETE_COVARIANCE_COVERAGE",
            "missing_player_ids": missing,
            "scenarios": [],
        }
    scenarios = []
    ids = list(weights)
    for shrinkage in shrinkage_grid:
        alpha = _finite(shrinkage, "shrinkage", nonnegative=True)
        if alpha > 1:
            raise CovarGateError("shrinkage must be between 0 and 1")
        variance = 0.0
        for p1 in ids:
            for p2 in ids:
                raw = matrix[p1][p2]
                adjusted = raw if p1 == p2 else raw * (1.0 - alpha)
                variance += weights[p1] * weights[p2] * adjusted
        scenarios.append({
            "shrinkage": alpha,
            "portfolio_variance_points_squared": round(variance, 10),
        })
    values = [row["portfolio_variance_points_squared"] for row in scenarios]
    spread = max(values) - min(values)
    baseline = abs(values[0])
    return {
        "status": "COMPUTED_DESCRIPTIVE_SENSITIVITY",
        "portfolio_player_count": len(weights),
        "shrinkage_grid": list(shrinkage_grid),
        "scenarios": scenarios,
        "absolute_variance_spread_points_squared": round(spread, 10),
        "relative_variance_spread_vs_unshrunk": round(spread / baseline, 10) if baseline > 0 else None,
        "interpretation": "Sensitivity to diagonal shrinkage only; not uncertainty bounds or evidence of out-of-sample utility.",
    }


def assess_covar_eligibility(
    covariance_report: Mapping[str, Any],
    pair_rows: list[Mapping[str, Any]],
    *,
    evidence: Mapping[str, Any] | None = None,
    policy: Mapping[str, Any] | None = None,
    portfolio_weights: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assess research evidence; never enable production CoVar or assign a weight."""
    if not isinstance(covariance_report, Mapping) or not isinstance(pair_rows, list):
        raise CovarGateError("covariance report and pair rows are required")
    evidence = evidence or {}
    policy = policy or {}
    if not isinstance(evidence, Mapping) or not isinstance(policy, Mapping):
        raise CovarGateError("evidence and policy must be objects")

    blockers: list[str] = []
    checks: dict[str, Any] = {}
    point_in_time = covariance_report.get("point_in_time_status")
    checks["point_in_time_integrity"] = point_in_time == "VERIFIED"
    if not checks["point_in_time_integrity"]:
        blockers.append("point_in_time_integrity_not_verified")

    source_hash = str(covariance_report.get("source_sha256", "")).lower()
    source_url = str(covariance_report.get("source_url", "")).strip()
    checks["source_provenance"] = (
        len(source_hash) == 64 and all(ch in "0123456789abcdef" for ch in source_hash)
        and bool(source_url)
    )
    if not checks["source_provenance"]:
        blockers.append("source_provenance_hash_or_url_missing")

    window_size = covariance_report.get("window_size")
    min_window = policy.get("minimum_window_gameweeks")
    checks["window_size"] = {
        "observed": window_size,
        "minimum_required": min_window,
        "passed": isinstance(window_size, int) and isinstance(min_window, int) and window_size >= min_window,
    }
    if not checks["window_size"]["passed"]:
        blockers.append("window_size_policy_missing_or_not_met")

    panel_players = covariance_report.get("players_in_window")
    complete_players = covariance_report.get("complete_panel_players")
    coverage = (
        complete_players / panel_players
        if isinstance(complete_players, int) and isinstance(panel_players, int) and panel_players > 0
        else None
    )
    min_coverage = policy.get("minimum_complete_panel_coverage")
    checks["complete_panel_coverage"] = {
        "observed": coverage,
        "minimum_required": min_coverage,
        "passed": (
            coverage is not None and isinstance(min_coverage, (int, float))
            and 0 < min_coverage <= 1 and coverage >= min_coverage
        ),
    }
    if not checks["complete_panel_coverage"]["passed"]:
        blockers.append("complete_panel_coverage_policy_missing_or_not_met")

    stability = covariance_report.get("rolling_correlation_stability") or {}
    min_corr_stability = policy.get("minimum_correlation_of_correlations")
    max_corr_change = policy.get("maximum_median_absolute_correlation_change")
    corr_of_corr = stability.get("correlation_of_correlations")
    median_change = stability.get("median_absolute_correlation_change")
    checks["rolling_stability"] = {
        "status": stability.get("status"),
        "correlation_of_correlations": corr_of_corr,
        "minimum_required": min_corr_stability,
        "median_absolute_correlation_change": median_change,
        "maximum_allowed_change": max_corr_change,
        "passed": (
            stability.get("status") in {"PASS", "PASSED", "EXPLORATORY_STABILITY_DIAGNOSTIC"}
            and isinstance(corr_of_corr, (int, float))
            and isinstance(median_change, (int, float))
            and isinstance(min_corr_stability, (int, float))
            and isinstance(max_corr_change, (int, float))
            and corr_of_corr >= min_corr_stability
            and median_change <= max_corr_change
        ),
    }
    if not checks["rolling_stability"]["passed"]:
        blockers.append("rolling_stability_policy_missing_or_not_met")

    sensitivity = portfolio_variance_sensitivity(pair_rows, portfolio_weights or {})
    max_sensitivity = policy.get("maximum_relative_shrinkage_variance_spread")
    relative_spread = sensitivity.get("relative_variance_spread_vs_unshrunk")
    checks["shrinkage_sensitivity"] = {
        **sensitivity,
        "maximum_relative_spread_allowed": max_sensitivity,
        "passed": (
            sensitivity.get("status") == "COMPUTED_DESCRIPTIVE_SENSITIVITY"
            and relative_spread is not None
            and isinstance(max_sensitivity, (int, float))
            and relative_spread <= max_sensitivity
        ),
    }
    if not checks["shrinkage_sensitivity"]["passed"]:
        blockers.append("shrinkage_sensitivity_policy_missing_or_not_met")

    point_evidence = evidence.get("point_in_time_evidence") or {}
    uncertainty = evidence.get("uncertainty_assessment") or {}
    oos = evidence.get("out_of_sample_validation") or {}
    checks["independent_point_in_time_evidence"] = (
        isinstance(point_evidence, Mapping)
        and point_evidence.get("status") == "PASSED"
        and bool(point_evidence.get("artifact_sha256"))
        and bool(point_evidence.get("as_of_utc"))
    )
    if not checks["independent_point_in_time_evidence"]:
        blockers.append("independent_point_in_time_evidence_missing")
    checks["uncertainty_assessment"] = (
        isinstance(uncertainty, Mapping)
        and uncertainty.get("status") == "PASSED"
        and bool(uncertainty.get("artifact_sha256"))
    )
    if not checks["uncertainty_assessment"]:
        blockers.append("independent_uncertainty_assessment_missing")
    utility_lower = oos.get("incremental_utility_lower_ci") if isinstance(oos, Mapping) else None
    checks["out_of_sample_incremental_utility"] = (
        isinstance(oos, Mapping)
        and oos.get("status") == "PASSED"
        and isinstance(utility_lower, (int, float))
        and utility_lower > 0
        and bool(oos.get("artifact_sha256"))
    )
    if not checks["out_of_sample_incremental_utility"]:
        blockers.append("positive_out_of_sample_incremental_utility_not_verified")

    ready_for_review = not blockers
    return {
        "status": "READY_FOR_EXPLICIT_REVIEW" if ready_for_review else "RESEARCH_ONLY_BLOCKED",
        "checks": checks,
        "blockers": blockers,
        "decision_weight": 0.0,
        "production_eligible": False,
        "release_eligible": False,
        "interpretation": (
            "Passing this evidence gate only permits explicit human review; it never activates CoVar. "
            "Production weight remains zero until separately validated and approved."
        ),
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--portfolio-weights", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    with args.pairs.open(newline="", encoding="utf-8") as handle:
        import csv
        pairs = list(csv.DictReader(handle))
    evidence = json.loads(args.evidence.read_text(encoding="utf-8")) if args.evidence else {}
    policy = json.loads(args.policy.read_text(encoding="utf-8")) if args.policy else {}
    weights = json.loads(args.portfolio_weights.read_text(encoding="utf-8")) if args.portfolio_weights else {}
    result = assess_covar_eligibility(
        report, pairs, evidence=evidence, policy=policy, portfolio_weights=weights
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
                           encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "blockers": result["blockers"],
        "decision_weight": 0.0,
        "production_eligible": False,
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
