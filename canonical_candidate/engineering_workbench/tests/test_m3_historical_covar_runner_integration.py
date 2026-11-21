from __future__ import annotations

from test_run_external_benchmark_personal_squad import run_input
from run_external_benchmark_personal_squad import run_external_benchmark_personal_squad


def _historical_context(payload):
    ids = [row["fpl_element_id"] for row in payload["provider_snapshot"]["records"]]
    pairs = []
    for index, left in enumerate(ids):
        for right in ids[index:]:
            pairs.append({
                "player1_id": str(left),
                "player2_id": str(right),
                "shrunk_covariance": 4.0 if left == right else 0.1,
            })
    return {
        "covariance_report": {
            "status": "EXPLORATORY_ONSIDE_ACTUALS_ONLY",
            "production_use": False,
            "model_trained": False,
            "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_FINAL_SCORING_AUDIT",
            "source_url": "https://onsidearena.com/data/graded-predictions.csv",
            "source_sha256": "a" * 64,
            "retrieved_at_utc": "2026-11-21T17:00:00Z",
            "source_license_and_attribution": "Provider-stated CC BY 4.0",
            "method": "sample covariance across a complete-case player-gameweek panel",
            "rolling_correlation_stability": {
                "status": "EXPLORATORY_STABILITY_DIAGNOSTIC",
                "first_window": [1, 2],
                "second_window": [3, 4, 5],
                "players": 12,
                "pairs": 66,
                "correlation_of_correlations": 0.00779916,
                "median_absolute_correlation_change": 0.50044957,
                "mean_absolute_correlation_change": 0.5779996,
                "interpretation": "Short-window instability caution only",
            },
            "source_panel": {
                "target_field": "actual_points only",
                "provider_forecasts_used": False,
            },
            "window_gameweeks": [1, 2, 3, 4, 5],
            "window_size": 5,
            "players_in_window": 20,
            "complete_panel_players": 15,
            "covariance_players": 14,
            "excluded_zero_variance_players": 1,
            "excluded_incomplete_players": 5,
            "expected_player_gameweek_cells": 100,
            "missing_player_gameweek_cells": 0,
            "shrinkage": {
                "type": "diagonal",
                "parameter": 0.5,
                "off_diagonal_multiplier": 0.5,
                "diagonal_unchanged": True,
                "positive_semidefinite_by_construction": True,
            },
        },
        "covariance_pairs": pairs,
    }


def test_runner_invokes_historical_covar_without_changing_ev_decision():
    payload = run_input()
    baseline = run_external_benchmark_personal_squad(payload)
    payload["historical_covariance_context"] = _historical_context(payload)
    enriched = run_external_benchmark_personal_squad(payload)

    base_recommendation = baseline["recommendation"]
    recommendation = enriched["recommendation"]
    assert recommendation["historical_covar_overlay"]["status"] == "AVAILABLE_HISTORICAL_COVAR_PROXY"
    assert recommendation["historical_covar_overlay"]["decision_weight"] == 0
    assert recommendation["historical_covar_overlay"]["production_eligible"] is False
    assert recommendation["historical_covar_overlay"]["field_comparison_status"] == "NOT_AVAILABLE_NO_FIELD_EXPOSURE_CAPTURE"
    assert recommendation["historical_covar_overlay"]["historical_covariance_source"]["source_sha256"] == "a" * 64
    assert recommendation["historical_covar_overlay"]["historical_covariance_stability_diagnostic"]["correlation_of_correlations"] == 0.0078
    diagnostics = recommendation["historical_covar_overlay"]["historical_covariance_diagnostics"]
    assert diagnostics["rolling_correlation_stability"]["correlation_of_correlations"] == 0.00779916
    assert diagnostics["sample_coverage"]["covariance_players"] == 14
    assert diagnostics["point_in_time_status"] == "NOT_VERIFIED_RETROSPECTIVE_FINAL_SCORING_AUDIT"
    assert recommendation["transfer_recommendation"] == base_recommendation["transfer_recommendation"]
    assert recommendation["squad_plan"] == base_recommendation["squad_plan"]


def test_runner_rejects_incomplete_historical_covariance_payload_shape():
    payload = run_input()
    payload["historical_covariance_context"] = {"covariance_report": {}}
    try:
        run_external_benchmark_personal_squad(payload)
    except ValueError as exc:
        assert "missing historical covariance fields" in str(exc)
    else:
        raise AssertionError("incomplete historical covariance context was accepted")



def test_runner_rejects_covariance_artifact_marked_for_production_use():
    payload = run_input()
    context = _historical_context(payload)
    context["covariance_report"]["production_use"] = True
    payload["historical_covariance_context"] = context
    try:
        run_external_benchmark_personal_squad(payload)
    except ValueError as exc:
        assert "must remain research-only" in str(exc)
    else:
        raise AssertionError("production-use covariance artifact was accepted")



def test_runner_computes_field_average_covariance_from_provisional_scoring_exposure(tmp_path):
    from test_run_external_benchmark_personal_squad import _write_predeadline_field_capture

    payload, _, _ = _write_predeadline_field_capture(tmp_path)
    payload["historical_covariance_context"] = _historical_context(payload)
    result = run_external_benchmark_personal_squad(payload)
    overlay = result["recommendation"]["historical_covar_overlay"]
    assert overlay["field_average_portfolio"]["status"] == "COMPUTED_HISTORICAL_FIELD_AVERAGE_PROXY"
    assert overlay["field_comparison_status"] == "AVAILABLE_FIELD_AVERAGE_HISTORICAL_PROXY"
    assert overlay["field_joint_manager_portfolio_status"] == "NOT_AVAILABLE_MARGINAL_EXPOSURE_ONLY"
    assert overlay["decision_weight"] == 0
    assert overlay["production_eligible"] is False
    assert overlay["baseline"]["field_average_covariance"] is not None
    assert overlay["baseline"]["relative_variance_vs_field_average"] is not None
    assert all(row["relative_variance_vs_field_average"] is not None
               for row in overlay["candidate_metrics"])



def test_runner_rejects_historical_covariance_source_that_uses_forecasts():
    payload = run_input()
    context = _historical_context(payload)
    context["covariance_report"]["source_panel"]["provider_forecasts_used"] = True
    payload["historical_covariance_context"] = context
    try:
        run_external_benchmark_personal_squad(payload)
    except ValueError as exc:
        assert "realized actual points only" in str(exc)
    else:
        raise AssertionError("forecast-contaminated covariance artifact was accepted")


def test_runner_rejects_inconsistent_covariance_shrinkage_metadata():
    payload = run_input()
    context = _historical_context(payload)
    context["covariance_report"]["shrinkage"]["off_diagonal_multiplier"] = 1.0
    payload["historical_covariance_context"] = context
    try:
        run_external_benchmark_personal_squad(payload)
    except ValueError as exc:
        assert "inconsistent with its parameter" in str(exc)
    else:
        raise AssertionError("inconsistent covariance shrinkage metadata was accepted")


def test_runner_rejects_malformed_historical_stability_diagnostic():
    payload = run_input()
    context = _historical_context(payload)
    context["covariance_report"]["rolling_correlation_stability"] = "not-an-object"
    payload["historical_covariance_context"] = context
    try:
        run_external_benchmark_personal_squad(payload)
    except ValueError as exc:
        assert "rolling correlation stability diagnostic must be an object" in str(exc)
    else:
        raise AssertionError("malformed stability diagnostic was accepted")
