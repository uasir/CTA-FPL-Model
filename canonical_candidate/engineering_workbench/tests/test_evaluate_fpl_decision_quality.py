import pytest

from evaluate_fpl_decision_quality import (
    evaluate_forecast,
    prediction_quantile_diagnostics,
)


def test_prediction_quantile_diagnostics_exposes_upper_tail_underprediction():
    actual = [0, 1, 2, 3, 4, 5, 6, 7, 12, 16]
    predicted = [0, 1, 2, 3, 4, 5, 5, 5, 5, 5]
    report = prediction_quantile_diagnostics(actual, predicted, bins=5)

    # Five identical high-end forecasts remain together rather than being split
    # across quantile bins and creating artificial calibration differences.
    assert len(report["bins"]) == 4
    assert [item["n"] for item in report["bins"]] == [2, 2, 1, 5]
    upper = report["bins"][-1]
    assert upper["actual_mean"] == pytest.approx(9.2)
    assert upper["predicted_mean"] == pytest.approx(5.0)
    assert upper["mean_actual_minus_predicted"] == pytest.approx(4.2)
    assert upper["actual_10_plus_rate"] == pytest.approx(0.4)


def test_prediction_quantile_diagnostics_is_deterministic_with_tied_predictions():
    first = prediction_quantile_diagnostics([1, 2, 3, 4], [2, 2, 2, 2], bins=2)
    second = prediction_quantile_diagnostics([1, 2, 3, 4], [2, 2, 2, 2], bins=2)
    assert first == second
    assert [item["n"] for item in first["bins"]] == [4]
    assert first["bins"][0]["predicted_mean"] == pytest.approx(2.0)


def test_prediction_quantile_diagnostics_validates_alignment_and_bin_count():
    with pytest.raises(ValueError):
        prediction_quantile_diagnostics([1, 2], [1])
    with pytest.raises(ValueError):
        prediction_quantile_diagnostics([1, 2], [1, 2], bins=0)


def test_composite_forecast_report_includes_distribution_diagnostics():
    report = evaluate_forecast([0, 2, 8, 12], [0, 2, 4, 4])
    assert "prediction_quantile_diagnostics" in report
    assert report["prediction_quantile_diagnostics"]["overall_mean_actual_minus_predicted"] == pytest.approx(3.0)


def test_prediction_quantile_diagnostics_caps_bin_count_at_sample_size():
    report = prediction_quantile_diagnostics([1, 2, 3], [1, 2, 3], bins=10)
    assert len(report["bins"]) == 3
    assert [item["n"] for item in report["bins"]] == [1, 1, 1]


def test_correct_recommendation_can_coexist_with_inaccurate_point_forecast():
    report = evaluate_forecast(
        actual_points=[2, 15],
        expected_points=[2, 8],
        decision_records=[{
            "decision_id": "choose-between-A-and-B",
            "chosen_option_id": "B",
            "options": [
                {"option_id": "A", "actual_utility": 2},
                {"option_id": "B", "actual_utility": 15},
            ],
        }],
    )
    assert report["point_errors"]["mae"] == pytest.approx(3.5)
    assert report["decision_performance"]["mean_regret_vs_best_feasible"] == 0
    assert report["decision_performance"]["recommendation_optimal_rate"] == 1
    assert report["decision_performance"]["decisions"][0]["chosen_option_id"] == "B"


def test_decision_regret_penalises_selecting_the_inferior_feasible_option():
    from evaluate_fpl_decision_quality import decision_outcome_metrics

    report = decision_outcome_metrics([{
        "chosen_option_id": "A",
        "options": [
            {"option_id": "A", "actual_utility": 2},
            {"option_id": "B", "actual_utility": 15},
        ],
    }])
    assert report["mean_regret_vs_best_feasible"] == pytest.approx(13)
    assert report["recommendation_optimal_rate"] == 0
    assert report["pairwise_loss_rate"] == 1


def test_decision_regret_respects_feasibility_constraints():
    from evaluate_fpl_decision_quality import decision_outcome_metrics

    report = decision_outcome_metrics([{
        "chosen_option_id": "A",
        "options": [
            {"option_id": "A", "actual_utility": 7},
            {"option_id": "B", "actual_utility": 20, "feasible": False},
            {"option_id": "C", "actual_utility": 5},
        ],
    }], utility_definition="net_gw_points_after_fpl_constraints")
    assert report["mean_regret_vs_best_feasible"] == 0
    assert report["pairwise_comparisons"] == 1
    assert report["utility_definition"] == "net_gw_points_after_fpl_constraints"


def test_decision_metrics_reject_an_infeasible_recommendation():
    from evaluate_fpl_decision_quality import decision_outcome_metrics

    with pytest.raises(ValueError, match="must be feasible"):
        decision_outcome_metrics([{
            "chosen_option_id": "B",
            "options": [
                {"option_id": "A", "actual_utility": 7},
                {"option_id": "B", "actual_utility": 20, "feasible": False},
            ],
        }])


def test_decision_metrics_reject_duplicate_option_ids():
    from evaluate_fpl_decision_quality import decision_outcome_metrics

    with pytest.raises(ValueError, match="unique"):
        decision_outcome_metrics([{
            "chosen_option_id": "A",
            "options": [
                {"option_id": "A", "actual_utility": 2},
                {"option_id": "A", "actual_utility": 15},
            ],
        }])
