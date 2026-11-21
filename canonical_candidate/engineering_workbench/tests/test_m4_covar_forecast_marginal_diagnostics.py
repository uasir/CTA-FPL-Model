from __future__ import annotations

import pytest

from m4_covar_forecast_marginal_diagnostics import (
    ForecastDiagnosticsError,
    evaluate_matched_forecast_panel,
)


def panel():
    return {
        "dataset_type": "MULTI_GAMEWEEK_PROSPECTIVE_CONVENTIONAL_FORECAST_OUTCOME_PANEL",
        "season": "2026-27",
        "gameweeks": [11, 12],
        "cluster_unit": "GAMEWEEK",
        "joint_dependence_inferred_from_marginal_player_rows": False,
        "missing_observations_zero_filled": 0,
        "decision_weight": 0.0,
        "production_eligible": False,
        "matched_rows": [
            {"gameweek": 11, "fpl_element_id": 1, "expected_points": 4.0, "actual_points": 6.0, "expected_minutes": 80.0, "actual_minutes": 90.0, "finality_status": "PASS_EXACT_MATCH"},
            {"gameweek": 11, "fpl_element_id": 2, "expected_points": 2.0, "actual_points": 0.0, "expected_minutes": 30.0, "actual_minutes": 0.0, "finality_status": "PASS_EXACT_MATCH"},
            {"gameweek": 12, "fpl_element_id": 1, "expected_points": 5.0, "actual_points": 3.0, "expected_minutes": 90.0, "actual_minutes": 60.0, "finality_status": "PASS_EXACT_MATCH"},
        ],
    }


def test_reports_marginal_metrics_and_gameweek_cluster_intervals():
    result = evaluate_matched_forecast_panel(panel(), resamples=100, seed=7)
    assert result["status"] == "MARGINAL_FORECAST_DIAGNOSTICS_CREATED"
    assert result["matched_player_gameweek_rows"] == 3
    assert result["overall_pooled_player_gameweek_metrics"]["points_mae"] == pytest.approx(2.0)
    assert result["gameweek_cluster_bootstrap"]["independent_clusters"] == 2
    assert result["gameweek_cluster_bootstrap"]["small_sample_warning"]
    assert result["expected_points_bands"][1]["count"] == 1
    assert result["decision_weight"] == 0.0
    assert result["production_eligible"] is False


def test_rejects_joint_dependence_claim():
    data = panel()
    data["joint_dependence_inferred_from_marginal_player_rows"] = True
    with pytest.raises(ForecastDiagnosticsError, match="joint dependence"):
        evaluate_matched_forecast_panel(data, resamples=100)


def test_rejects_duplicate_player_gameweek():
    data = panel()
    data["matched_rows"].append(dict(data["matched_rows"][0]))
    with pytest.raises(ForecastDiagnosticsError, match="unique"):
        evaluate_matched_forecast_panel(data, resamples=100)


def test_rejects_missing_finality():
    data = panel()
    data["matched_rows"][0]["finality_status"] = "NOT_VERIFIED"
    with pytest.raises(ForecastDiagnosticsError, match="finality"):
        evaluate_matched_forecast_panel(data, resamples=100)


def test_rejects_production_eligible_panel():
    data = panel()
    data["production_eligible"] = True
    with pytest.raises(ForecastDiagnosticsError, match="research-only"):
        evaluate_matched_forecast_panel(data, resamples=100)


def test_rejects_nan_and_unmatched_declared_gameweek():
    data = panel()
    data["matched_rows"][0]["expected_points"] = float("nan")
    with pytest.raises(ForecastDiagnosticsError, match="finite"):
        evaluate_matched_forecast_panel(data, resamples=100)
