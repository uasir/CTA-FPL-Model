#!/usr/bin/env python3
"""Synthetic full-Gameweek portfolio scoring with FPL lineup resolution.

All portfolios are evaluated against the exact same scenario IDs and
probabilities. This module is research-only and has no production authority.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

from m4_covar_full_gameweek_contract import validate_full_gameweek_document
from m4_covar_lineup_resolver import resolve_fpl_lineup


class CovarFullGameweekScoringError(ValueError):
    """Raised when validated full-Gameweek inputs cannot be scored."""


def _weighted_quantile(values: list[tuple[float, float]], quantile: float) -> float:
    ordered = sorted(values, key=lambda item: item[0])
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative + 1e-12 >= quantile:
            return float(value)
    return float(ordered[-1][0])


def _moments(values: list[tuple[float, float]]) -> tuple[float, float]:
    total_weight = sum(weight for _, weight in values)
    if not math.isclose(total_weight, 1.0, rel_tol=0, abs_tol=1e-9):
        raise CovarFullGameweekScoringError("scoring weights must sum to one")
    mean = sum(value * weight for value, weight in values)
    variance = sum(weight * (value - mean) ** 2 for value, weight in values)
    return mean, max(0.0, variance)


def _covariance(left: list[tuple[float, float]], right: list[tuple[float, float]]) -> float:
    left_mean, _ = _moments(left)
    right_mean, _ = _moments(right)
    return sum(
        weight * (left_value - left_mean) * (right_value - right_mean)
        for (left_value, weight), (right_value, right_weight) in zip(left, right)
        if math.isclose(weight, right_weight, rel_tol=0, abs_tol=1e-12)
    )


def _score_one_portfolio(
    portfolio: Mapping[str, Any],
    scenarios: list[Mapping[str, Any]],
    player_outcomes: list[Mapping[str, Mapping[str, Any]]],
    probabilities: list[float],
    mode: str,
) -> tuple[dict[str, Any], list[float], list[dict[str, float]]]:
    player_ids = [str(value) for value in portfolio["player_ids"]]
    player_positions = {
        str(pid): str(position).upper()
        for pid, position in portfolio["player_positions"].items()
    }
    scenario_scores: list[float] = []
    scenario_resolutions: list[dict[str, Any]] = []
    contribution_series = {pid: [] for pid in player_ids}

    for scenario, outcome_map, probability in zip(scenarios, player_outcomes, probabilities):
        resolution = resolve_fpl_lineup(
            player_ids=player_ids,
            starting_player_ids=portfolio["starting_player_ids"],
            starting_goalkeeper_id=str(portfolio["starting_goalkeeper_id"]),
            reserve_goalkeeper_id=str(portfolio["reserve_goalkeeper_id"]),
            bench_order=portfolio["bench_order"],
            player_positions=player_positions,
            captain_id=str(portfolio["captain_id"]),
            vice_captain_id=str(portfolio["vice_captain_id"]),
            player_minutes={pid: outcome_map[pid]["minutes"] for pid in player_ids},
            player_played={pid: outcome_map[pid]["played"] for pid in player_ids},
            player_points={pid: outcome_map[pid]["fpl_points"] for pid in player_ids},
            active_chip=portfolio.get("active_chip"),
            mode=mode,
        )
        score = float(resolution["total_points"])
        scenario_scores.append(score)
        for pid in player_ids:
            contribution_series[pid].append(float(resolution["player_contributions"].get(pid, 0.0)))
        scenario_resolutions.append({
            "scenario_id": str(scenario["scenario_id"]),
            "probability": probability,
            "total_points": score,
            "resolved_starting_xi": list(resolution["resolved_starting_xi"]),
            "substitutions": list(resolution["substitutions"]),
            "active_captain_id": resolution["active_captain_id"],
            "captain_multiplier": resolution["captain_multiplier"],
            "bench_boost_active": resolution["bench_boost_active"],
        })

    weighted_scores = list(zip(scenario_scores, probabilities))
    expected_points, variance = _moments(weighted_scores)
    contribution_weighted = {
        pid: list(zip(values, probabilities))
        for pid, values in contribution_series.items()
    }
    decomposition = []
    for i, left_id in enumerate(player_ids):
        for j in range(i, len(player_ids)):
            right_id = player_ids[j]
            left_mean, _ = _moments(contribution_weighted[left_id])
            right_mean, _ = _moments(contribution_weighted[right_id])
            covariance = sum(
                probabilities[k]
                * (contribution_series[left_id][k] - left_mean)
                * (contribution_series[right_id][k] - right_mean)
                for k in range(len(probabilities))
            )
            decomposition.append({
                "player_a": left_id,
                "player_b": right_id,
                "covariance_contribution": covariance if i == j else 2.0 * covariance,
            })
    decomposition_total = sum(row["covariance_contribution"] for row in decomposition)

    result = {
        "portfolio_id": str(portfolio["portfolio_id"]),
        "portfolio_role": portfolio.get("portfolio_role", "CANDIDATE"),
        "scenario_scores": [
            {"scenario_id": str(scenario["scenario_id"]), "points": score, "probability": probabilities[i]}
            for i, (scenario, score) in enumerate(zip(scenarios, scenario_scores))
        ],
        "scenario_resolutions": scenario_resolutions,
        "expected_points": expected_points,
        "variance": variance,
        "standard_deviation": math.sqrt(variance),
        "quantiles": {
            "p10": _weighted_quantile(weighted_scores, 0.10),
            "p25": _weighted_quantile(weighted_scores, 0.25),
            "p50": _weighted_quantile(weighted_scores, 0.50),
            "p75": _weighted_quantile(weighted_scores, 0.75),
            "p90": _weighted_quantile(weighted_scores, 0.90),
        },
        "minimum_points": min(scenario_scores),
        "maximum_points": max(scenario_scores),
        "variance_decomposition": decomposition,
        "variance_decomposition_total": decomposition_total,
        "variance_decomposition_matches_total": math.isclose(
            decomposition_total, variance, rel_tol=1e-8, abs_tol=1e-8
        ),
    }
    return result, scenario_scores, contribution_series


def score_full_gameweek_portfolios(
    document: Mapping[str, Any],
    *,
    baseline_portfolio_id: str | None = None,
) -> dict[str, Any]:
    """Validate and score candidate/field lineups on one shared scenario set."""
    try:
        validated = validate_full_gameweek_document(document)
    except (TypeError, ValueError) as exc:
        raise CovarFullGameweekScoringError(f"full-Gameweek input validation failed: {exc}") from exc

    mode = validated["mode"]
    scenarios = list(document["scenarios"])
    probabilities = [float(row["probability"]) for row in scenarios]
    player_outcomes = [
        {str(row["player_id"]): row for row in scenario["player_outcomes"]}
        for scenario in scenarios
    ]
    portfolio_rows = {
        str(row["portfolio_id"]): row
        for row in document["portfolios"]
    }
    if baseline_portfolio_id is not None and baseline_portfolio_id not in portfolio_rows:
        raise CovarFullGameweekScoringError(
            f"baseline_portfolio_id {baseline_portfolio_id!r} is not present"
        )

    results: dict[str, Any] = {}
    raw_scores: dict[str, list[float]] = {}
    for portfolio_id, portfolio in portfolio_rows.items():
        result, scores, _ = _score_one_portfolio(
            portfolio, scenarios, player_outcomes, probabilities, mode
        )
        results[portfolio_id] = result
        raw_scores[portfolio_id] = scores

    if baseline_portfolio_id is not None:
        baseline = raw_scores[baseline_portfolio_id]
        for portfolio_id, scores in raw_scores.items():
            differences = [score - baseline[i] for i, score in enumerate(scores)]
            weighted = list(zip(differences, probabilities))
            mean, variance = _moments(weighted)
            results[portfolio_id]["baseline_comparison"] = {
                "baseline_portfolio_id": baseline_portfolio_id,
                "expected_points_difference": mean,
                "probability_outscoring_baseline": sum(
                    weight for difference, weight in weighted if difference > 0
                ),
                "relative_score_quantiles": {
                    "p10": _weighted_quantile(weighted, 0.10),
                    "p50": _weighted_quantile(weighted, 0.50),
                    "p90": _weighted_quantile(weighted, 0.90),
                },
                "relative_score_standard_deviation": math.sqrt(variance),
                "is_baseline": portfolio_id == baseline_portfolio_id,
            }

    field_rows = [
        row for row in document["portfolios"]
        if row.get("portfolio_role", "CANDIDATE") == "FIELD"
    ]
    field_status = "NOT_AVAILABLE_NO_EXPLICIT_FIELD_PORTFOLIO"
    if field_rows:
        weights = {str(row["portfolio_id"]): float(row["field_weight"]) for row in field_rows}
        field_mean = sum(
            weights[pid] * results[pid]["expected_points"]
            for pid in weights
        )
        for portfolio_id, portfolio in portfolio_rows.items():
            if portfolio.get("portfolio_role", "CANDIDATE") != "CANDIDATE":
                continue
            differences: list[tuple[float, float]] = []
            probability_outscoring = 0.0
            for scenario_index, scenario_probability in enumerate(probabilities):
                candidate_score = raw_scores[portfolio_id][scenario_index]
                for field_id, field_weight in weights.items():
                    joint_weight = scenario_probability * field_weight
                    difference = candidate_score - raw_scores[field_id][scenario_index]
                    differences.append((difference, joint_weight))
                    if difference > 0:
                        probability_outscoring += joint_weight
            relative_mean, relative_variance = _moments(differences)
            results[portfolio_id]["field_comparison"] = {
                "field_portfolio_count": len(field_rows),
                "weighted_field_expected_points": field_mean,
                "expected_points_difference_vs_weighted_field": relative_mean,
                "probability_outscoring_weighted_field_portfolio": probability_outscoring,
                "relative_score_quantiles": {
                    "p10": _weighted_quantile(differences, 0.10),
                    "p50": _weighted_quantile(differences, 0.50),
                    "p90": _weighted_quantile(differences, 0.90),
                },
                "relative_score_standard_deviation": math.sqrt(relative_variance),
                "field_weighting": "EXPLICIT_SYNTHETIC_PORTFOLIO_WEIGHTS",
            }
        field_status = "AVAILABLE_EXPLICIT_FIELD_PORTFOLIOS"

    return {
        "schema_version": "1.0.0",
        "data_status": validated["data_status"],
        "mode": mode,
        "input_validation_status": validated["validation_status"],
        "shared_scenario_ids": [str(row["scenario_id"]) for row in scenarios],
        "portfolio_results": results,
        "baseline_portfolio_id": baseline_portfolio_id,
        "field_comparison_status": field_status,
        "production_eligible": False,
        "decision_weight": 0.0,
        "covar_used": False,
    }
