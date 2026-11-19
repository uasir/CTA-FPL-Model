import pytest

from evaluate_fpl_decision_quality import (
    evaluate_forecast,
    prediction_quantile_diagnostics,
)


def test_prediction_quantile_diagnostics_exposes_upper_tail_underprediction():
    actual = [0, 1, 2, 3, 4, 5, 6, 7, 12, 16]
    predicted = [0, 1, 2, 3, 4, 5, 5, 5, 5, 5]
    report = prediction_quantile_diagnostics(actual, predicted, bins=5)

    assert len(report["bins"]) == 5
    assert [item["n"] for item in report["bins"]] == [2, 2, 2, 2, 2]
    upper = report["bins"][-1]
    assert upper["actual_mean"] == pytest.approx(14.0)
    assert upper["predicted_mean"] == pytest.approx(5.0)
    assert upper["mean_actual_minus_predicted"] == pytest.approx(9.0)
    assert upper["actual_10_plus_rate"] == pytest.approx(1.0)


def test_prediction_quantile_diagnostics_is_deterministic_with_tied_predictions():
    first = prediction_quantile_diagnostics([1, 2, 3, 4], [2, 2, 2, 2], bins=2)
    second = prediction_quantile_diagnostics([1, 2, 3, 4], [2, 2, 2, 2], bins=2)
    assert first == second
    assert [item["n"] for item in first["bins"]] == [2, 2]


def test_prediction_quantile_diagnostics_validates_alignment_and_bin_count():
    with pytest.raises(ValueError):
        prediction_quantile_diagnostics([1, 2], [1])
    with pytest.raises(ValueError):
        prediction_quantile_diagnostics([1, 2], [1, 2], bins=0)


def test_composite_forecast_report_includes_distribution_diagnostics():
    report = evaluate_forecast([0, 2, 8, 12], [0, 2, 4, 4])
    assert "prediction_quantile_diagnostics" in report
    assert report["prediction_quantile_diagnostics"]["overall_mean_actual_minus_predicted"] == pytest.approx(3.0)
