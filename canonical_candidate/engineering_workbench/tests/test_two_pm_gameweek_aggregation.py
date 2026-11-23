import math

import pytest

from two_pm_gameweek_aggregation import aggregate_fixture_forecasts_to_gameweek


def fixture_record(fixture_id, player=1001, gameweek=12, p=0.7, l1=4.0, l2=1.0):
    expected = p * l1 + (1 - p) * l2
    variance = (
        p * (l1 + l1 * l1)
        + (1 - p) * (l2 + l2 * l2)
        - expected * expected
    )
    return {
        "player_id": player,
        "target_gameweek": gameweek,
        "target_fixture_id": fixture_id,
        "model_name": "2PM-PoissonMixture-Transformer",
        "model_version": "0.1.0",
        "feature_schema_version": "dastan-286-v1",
        "forecast_as_of": "2026-11-23T10:00:00+00:00",
        "training_cutoff": "2026-11-01T00:00:00+00:00",
        "data_snapshot_hashes": {"features": "a" * 64},
        "p": p,
        "lambda_1": l1,
        "lambda_2": l2,
        "expected_points": expected,
        "variance": variance,
        "standard_deviation": math.sqrt(max(0, variance)),
        "quality_metadata": {"status": "CANDIDATE"},
    }


def test_double_gameweek_aggregation_preserves_exact_four_component_mixture():
    first = fixture_record(9001, p=0.7, l1=4.0, l2=1.0)
    second = fixture_record(9002, p=0.6, l1=3.0, l2=2.0)
    result = aggregate_fixture_forecasts_to_gameweek(
        [first, second],
        dependence_assumption="independent_fixture_scores",
    )
    assert result["forecast_grain"] == "player_gameweek"
    assert result["target_fixture_ids"] == [9001, 9002]
    assert result["fixture_count"] == 2
    assert len(result["mixture_components"]) == 4
    assert math.isclose(result["expected_points"], 5.7, rel_tol=1e-9)
    assert math.isclose(
        result["variance"], first["variance"] + second["variance"], rel_tol=1e-8
    )
    assert math.isclose(
        sum(component["weight"] for component in result["mixture_components"]),
        1.0,
        rel_tol=1e-9,
    )
    assert result["probability_6_plus"] >= result["probability_8_plus"]
    assert result["probability_8_plus"] >= result["probability_10_plus"]
    assert result["production_eligible"] is False
    assert "p" not in result and "lambda_1" not in result


def test_single_fixture_keeps_two_component_distribution():
    result = aggregate_fixture_forecasts_to_gameweek(
        [fixture_record(9001)],
        dependence_assumption="independent_fixture_scores",
    )
    assert result["fixture_count"] == 1
    assert len(result["mixture_components"]) == 2
    assert math.isclose(result["expected_points"], 3.1, rel_tol=1e-9)


def test_aggregation_requires_explicit_assumption_and_consistent_identity():
    with pytest.raises(ValueError, match="explicitly"):
        aggregate_fixture_forecasts_to_gameweek(
            [fixture_record(9001)],
            dependence_assumption="unknown",
        )
    with pytest.raises(ValueError, match="one player and Gameweek"):
        aggregate_fixture_forecasts_to_gameweek(
            [fixture_record(9001), fixture_record(9002, player=1002)],
            dependence_assumption="independent_fixture_scores",
        )
    with pytest.raises(ValueError, match="duplicate fixture"):
        aggregate_fixture_forecasts_to_gameweek(
            [fixture_record(9001), fixture_record(9001)],
            dependence_assumption="independent_fixture_scores",
        )



def test_aggregation_rejects_inconsistent_fixture_distribution_summary():
    bad = fixture_record(9001)
    bad["expected_points"] += 1.0
    with pytest.raises(ValueError, match="expected_points disagrees"):
        aggregate_fixture_forecasts_to_gameweek(
            [bad],
            dependence_assumption="independent_fixture_scores",
        )
