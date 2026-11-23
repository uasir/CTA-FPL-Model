"""Aggregate fixture-level 2PM distributions to an FPL player-Gameweek forecast.

The only implemented aggregation assumption is explicit conditional independence of
fixture scores. The resulting sum is a 2^n-component Poisson mixture, not generally
a two-component mixture. This module does not make squad or portfolio decisions.
"""
from __future__ import annotations

import math
from typing import Any, Sequence


def _poisson_tail(rate: float, threshold: int) -> float:
    if threshold <= 0:
        return 1.0
    cdf_below = sum(
        math.exp(-rate + points * math.log(rate) - math.lgamma(points + 1.0))
        for points in range(threshold)
    )
    return min(1.0, max(0.0, 1.0 - cdf_below))


def aggregate_fixture_forecasts_to_gameweek(
    fixture_records: Sequence[dict[str, Any]],
    *,
    dependence_assumption: str,
) -> dict[str, Any]:
    """Convolve fixture-level mixture distributions under an explicit assumption."""
    if dependence_assumption != "independent_fixture_scores":
        raise ValueError(
            "dependence_assumption must explicitly be 'independent_fixture_scores'"
        )
    records = list(fixture_records)
    if not records:
        raise ValueError("at least one fixture forecast is required")

    required = {
        "player_id", "target_gameweek", "target_fixture_id", "model_name",
        "model_version", "feature_schema_version", "forecast_as_of",
        "training_cutoff", "data_snapshot_hashes", "p", "lambda_1",
        "lambda_2", "expected_points", "variance", "standard_deviation",
    }
    for index, record in enumerate(records):
        missing = sorted(required - set(record))
        if missing:
            raise ValueError(f"fixture forecast {index} missing fields: {missing}")
    player_ids = {str(record["player_id"]) for record in records}
    gameweeks = {int(record["target_gameweek"]) for record in records}
    if len(player_ids) != 1 or len(gameweeks) != 1:
        raise ValueError("all fixture forecasts must belong to one player and Gameweek")
    fixture_ids = [str(record["target_fixture_id"]) for record in records]
    if len(fixture_ids) != len(set(fixture_ids)):
        raise ValueError("duplicate fixture forecasts found for one player/Gameweek")

    support_shifts = [int(record.get("support_shift", 0)) for record in records]
    if any(shift < 0 for shift in support_shifts) or len(set(support_shifts)) != 1:
        raise ValueError("fixture forecasts must share one non-negative support_shift")
    invariant_fields = (
        "model_name", "model_version", "feature_schema_version",
        "forecast_as_of", "training_cutoff", "data_snapshot_hashes",
    )
    for field in invariant_fields:
        if any(record[field] != records[0][field] for record in records[1:]):
            raise ValueError(f"fixture forecasts disagree on {field}")

    components: list[tuple[float, float]] = [(1.0, 0.0)]
    for record in records:
        p = float(record["p"])
        lambda_1 = float(record["lambda_1"])
        lambda_2 = float(record["lambda_2"])
        if (
            not all(math.isfinite(value) for value in (p, lambda_1, lambda_2))
            or not (0.0 < p < 1.0)
            or lambda_1 <= 0
            or lambda_2 <= 0
        ):
            raise ValueError("fixture mixture parameters must be finite and valid")
        support_shift = int(record.get("support_shift", 0))
        if support_shift < 0:
            raise ValueError("fixture support_shift must be non-negative")
        count_expectation = p * lambda_1 + (1.0 - p) * lambda_2
        expected = count_expectation - support_shift
        second_moment = (
            p * (lambda_1 + lambda_1 * lambda_1)
            + (1.0 - p) * (lambda_2 + lambda_2 * lambda_2)
        )
        variance = max(0.0, second_moment - count_expectation * count_expectation)
        if not math.isclose(
            expected, float(record["expected_points"]), rel_tol=1e-5, abs_tol=1e-6
        ):
            raise ValueError("fixture expected_points disagrees with mixture parameters")
        if not math.isclose(
            variance, float(record["variance"]), rel_tol=1e-5, abs_tol=1e-6
        ):
            raise ValueError("fixture variance disagrees with mixture parameters")
        expanded = []
        for weight, rate_sum in components:
            expanded.append((weight * p, rate_sum + lambda_1))
            expanded.append((weight * (1.0 - p), rate_sum + lambda_2))
        components = expanded

    total_weight = sum(weight for weight, _ in components)
    components = [
        (weight / total_weight, rate)
        for weight, rate in components
    ]
    total_support_shift = sum(int(record.get("support_shift", 0)) for record in records)
    count_expectation = sum(weight * rate for weight, rate in components)
    expected_points = count_expectation - total_support_shift
    second_moment = sum(
        weight * (rate + rate * rate) for weight, rate in components
    )
    variance = max(0.0, second_moment - count_expectation * count_expectation)

    return {
        "player_id": records[0]["player_id"],
        "target_gameweek": int(records[0]["target_gameweek"]),
        "target_fixture_ids": [record["target_fixture_id"] for record in records],
        "forecast_grain": "player_gameweek",
        "forecast_type": "independent_sum_of_fixture_shifted_poisson_mixtures",
        "aggregation_assumption": dependence_assumption,
        "fixture_count": len(records),
        "support_shift": total_support_shift,
        "support_lower_bound": -total_support_shift,
        "model_name": records[0]["model_name"],
        "model_version": records[0]["model_version"],
        "feature_schema_version": records[0]["feature_schema_version"],
        "forecast_as_of": records[0]["forecast_as_of"],
        "training_cutoff": records[0]["training_cutoff"],
        "data_snapshot_hashes": records[0]["data_snapshot_hashes"],
        "expected_points": expected_points,
        "variance": variance,
        "standard_deviation": math.sqrt(variance),
        "probability_6_plus": sum(
            weight * _poisson_tail(rate, 6 + total_support_shift) for weight, rate in components
        ),
        "probability_8_plus": sum(
            weight * _poisson_tail(rate, 8 + total_support_shift) for weight, rate in components
        ),
        "probability_10_plus": sum(
            weight * _poisson_tail(rate, 10 + total_support_shift) for weight, rate in components
        ),
        "mixture_components": [
            {"weight": weight, "lambda": rate}
            for weight, rate in components
        ],
        "fixture_forecasts": [
            {
                "fixture_id": record["target_fixture_id"],
                "p": float(record["p"]),
                "lambda_1": float(record["lambda_1"]),
                "lambda_2": float(record["lambda_2"]),
                "support_shift": int(record.get("support_shift", 0)),
                "expected_points": float(record["expected_points"]),
                "variance": float(record["variance"]),
            }
            for record in records
        ],
        "quality_metadata": {
            "fixture_quality": [
                record.get("quality_metadata", {}) for record in records
            ],
            "distribution_note": (
                "Exact convolution under independent fixture-score draws; "
                "cross-fixture dependence is not modelled."
            ),
        },
        "production_eligible": False,
    }
