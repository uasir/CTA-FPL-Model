#!/usr/bin/env python3
"""Deterministic portfolio scoring for the synthetic M4 CoVar prototype.

Consumes only validated scenario-level FPL points. It does not generate
forecasts, infer field portfolios, apply autosubs, or enable production use.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

from m4_covar_scenario_contract import (
    CovarScenarioContractError,
    validate_scenario_document,
)


class CovarScoringError(ValueError):
    """Raised when a valid scenario contract cannot be scored."""


def _weighted_quantile(values: list[tuple[float, float]], quantile: float) -> float:
    ordered = sorted(values, key=lambda item: item[0])
    cumulative = 0.0
    for value, probability in ordered:
        cumulative += probability
        if cumulative + 1e-12 >= quantile:
            return float(value)
    return float(ordered[-1][0])


def _moments(values: list[tuple[float, float]]) -> tuple[float, float]:
    mean = sum(value * probability for value, probability in values)
    variance = sum(probability * (value - mean) ** 2 for value, probability in values)
    return mean, max(0.0, variance)


def _covariance(
    left: list[tuple[float, float]],
    right: list[tuple[float, float]],
) -> float:
    left_mean = sum(value * probability for value, probability in left)
    right_mean = sum(value * probability for value, probability in right)
    if len(left) != len(right) or any(
        not math.isclose(left_row[1], right_row[1], rel_tol=0, abs_tol=1e-12)
        for left_row, right_row in zip(left, right)
    ):
        raise CovarScoringError("player series must share identical scenario probabilities")
    return sum(
        probability * (left_value - left_mean) * (right_value - right_mean)
        for (left_value, probability), (right_value, _) in zip(left, right)
    )


def score_scenario_portfolios(
    document: Mapping[str, Any],
    *,
    baseline_portfolio_id: str | None = None,
) -> dict[str, Any]:
    """Score supplied portfolios over explicit scenarios.

    A missing mode means REGULAR_GW. FREE_HIT is accepted only when explicitly
    set by the caller in the document; this scorer applies no implicit chip
    behavior. A baseline comparison is strictly portfolio-to-portfolio and
    must be explicitly requested by ID; it is not a proxy for field EO.
    """
    try:
        validated = validate_scenario_document(document)
    except CovarScenarioContractError:
        raise

    mode = document.get("mode", "REGULAR_GW")
    if mode not in ("REGULAR_GW", "FREE_HIT"):
        raise CovarScoringError("mode must be REGULAR_GW or explicitly FREE_HIT")

    players = {str(row["player_id"]): row for row in document["players"]}
    scenarios = document["scenarios"]
    probabilities = [float(row["probability"]) for row in scenarios]
    outcome_maps = [
        {str(row["player_id"]): row for row in scenario["player_outcomes"]}
        for scenario in scenarios
    ]
    portfolio_rows = {
        str(row["portfolio_id"]): row for row in document["portfolios"]
    }
    if baseline_portfolio_id is not None and baseline_portfolio_id not in portfolio_rows:
        raise CovarScoringError(
            f"baseline_portfolio_id {baseline_portfolio_id!r} is not present"
        )

    results: dict[str, Any] = {}
    raw_scores: dict[str, list[float]] = {}
    for portfolio_id, portfolio in portfolio_rows.items():
        selected = [str(value) for value in portfolio["player_ids"]]
        captain_id = str(portfolio["captain_id"])
        captain_multiplier = float(portfolio.get("captain_multiplier", 2))
        coefficients = {player_id: 1.0 for player_id in selected}
        coefficients[captain_id] = captain_multiplier

        scenario_scores: list[float] = []
        for outcome_map in outcome_maps:
            score = sum(
                coefficients[player_id] * float(outcome_map[player_id]["fpl_points"])
                for player_id in selected
            )
            scenario_scores.append(score)

        weighted_scores = list(zip(scenario_scores, probabilities))
        mean, variance = _moments(weighted_scores)
        player_series = {
            player_id: [
                float(outcome_map[player_id]["fpl_points"]) * coefficients[player_id]
                for outcome_map in outcome_maps
            ]
            for player_id in selected
        }
        player_weighted = {
            player_id: list(zip(series, probabilities))
            for player_id, series in player_series.items()
        }

        decomposition = []
        ids = selected
        for i, left_id in enumerate(ids):
            for j in range(i, len(ids)):
                right_id = ids[j]
                cov = _covariance(
                    player_weighted[left_id], player_weighted[right_id]
                )
                contribution = cov if i == j else 2.0 * cov
                decomposition.append({
                    "player_a": left_id,
                    "player_b": right_id,
                    "covariance_contribution": contribution,
                })

        results[portfolio_id] = {
            "scenario_scores": [
                {"scenario_id": scenario["scenario_id"], "points": score,
                 "probability": probabilities[index]}
                for index, (scenario, score) in enumerate(zip(scenarios, scenario_scores))
            ],
            "expected_points": mean,
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
            "variance_decomposition_total": sum(
                row["covariance_contribution"] for row in decomposition
            ),
        }
        raw_scores[portfolio_id] = scenario_scores

    if baseline_portfolio_id is not None:
        baseline_scores = raw_scores[baseline_portfolio_id]
        baseline_mean = results[baseline_portfolio_id]["expected_points"]
        for portfolio_id, scores in raw_scores.items():
            differences = [
                score - baseline_score
                for score, baseline_score in zip(scores, baseline_scores)
            ]
            weighted_differences = list(zip(differences, probabilities))
            relative_mean, relative_variance = _moments(weighted_differences)
            results[portfolio_id]["baseline_comparison"] = {
                "baseline_portfolio_id": baseline_portfolio_id,
                "expected_points_difference": relative_mean,
                "probability_outscoring_baseline": sum(
                    probability for difference, probability in weighted_differences
                    if difference > 0
                ),
                "relative_score_quantiles": {
                    "p10": _weighted_quantile(weighted_differences, 0.10),
                    "p50": _weighted_quantile(weighted_differences, 0.50),
                    "p90": _weighted_quantile(weighted_differences, 0.90),
                },
                "relative_score_standard_deviation": math.sqrt(relative_variance),
                "is_baseline": portfolio_id == baseline_portfolio_id,
            }

    return {
        "schema_version": "1.0.0",
        "mode": mode,
        "input_validation_status": validated["validation_status"],
        "portfolio_results": results,
        "baseline_portfolio_id": baseline_portfolio_id,
        "field_comparison_status": (
            "NOT_AVAILABLE_NO_EXPLICIT_FIELD_PORTFOLIO"
        ),
        "production_eligible": False,
        "decision_weight": 0.0,
    }
