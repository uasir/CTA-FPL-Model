from __future__ import annotations

import pytest

from analyze_fpl_field_relative_risk import analyze_field_relative_risk, FieldRiskInputError


def inputs():
    forecasts = [
        {"fpl_element_id": player_id, "expected_points": 5.0}
        for player_id in range(1, 12)
    ]
    eo = {player_id: 50.0 for player_id in range(1, 12)}
    covariance = []
    for left in range(1, 12):
        for right in range(left, 12):
            covariance.append({
                "player1_id": left,
                "player2_id": right,
                "shrunk_covariance": 1.0 if left == right else 0.0,
            })
    metadata = {
        "target_deadline": "2026-11-21T11:00:00Z",
        "eo_deadline": "2026-11-21T11:00:00Z",
        "picks_lock_verified": True,
        "eo_cohort": "LiveFPL top 100k",
        "eo_sample_size": 1000,
        "eo_captured_at": "2026-11-21T11:05:00Z",
        "covariance_window_gameweeks": 10,
    }
    return forecasts, eo, covariance, metadata


def test_field_relative_variance_decomposes_own_field_and_covariance():
    forecasts, eo, covariance, metadata = inputs()
    result = analyze_field_relative_risk(forecasts, list(range(1, 12)), 1, eo, covariance, metadata)
    assert result["status"] == "RESEARCH_ONLY_FIELD_RELATIVE_RISK_ESTIMATE"
    assert result["expected_points_difference_vs_field"] == pytest.approx(32.5)
    assert result["own_xi_variance"] == pytest.approx(14.0)
    assert result["field_variance"] == pytest.approx(2.75)
    assert result["own_field_covariance"] == pytest.approx(6.0)
    assert result["relative_score_variance"] == pytest.approx(4.75)
    assert result["relative_score_variance"] == pytest.approx(
        result["own_xi_variance"] + result["field_variance"] - 2 * result["own_field_covariance"]
    )
    assert result["decision_weight"] == 0
    assert result["used_for_recommendation"] is False


def test_missing_field_eo_is_not_silently_treated_as_zero():
    forecasts, eo, covariance, metadata = inputs()
    del eo[11]
    result = analyze_field_relative_risk(forecasts, list(range(1, 12)), 1, eo, covariance, metadata)
    assert result["status"] == "INCOMPLETE_FIELD_EO_UNIVERSE"
    assert result["missing_player_ids"] == [11]
    assert result["decision_weight"] == 0


def test_eo_must_match_target_deadline_and_verified_lock():
    forecasts, eo, covariance, metadata = inputs()
    metadata["eo_deadline"] = "2026-11-20T11:00:00Z"
    result = analyze_field_relative_risk(forecasts, list(range(1, 12)), 1, eo, covariance, metadata)
    assert result["status"] == "EO_NOT_DEADLINE_MATCHED_OR_LOCK_VERIFIED"


def test_incomplete_covariance_matrix_is_not_imputed():
    forecasts, eo, covariance, metadata = inputs()
    covariance.pop()
    result = analyze_field_relative_risk(forecasts, list(range(1, 12)), 1, eo, covariance, metadata)
    assert result["status"] == "INCOMPLETE_COVARIANCE_MATRIX"
    assert result["decision_weight"] == 0


def test_non_psd_covariance_matrix_is_rejected_for_risk_scoring():
    forecasts, eo, covariance, metadata = inputs()
    for row in covariance:
        if {row["player1_id"], row["player2_id"]} == {1, 2}:
            row["shrunk_covariance"] = -2.0
    result = analyze_field_relative_risk(forecasts, list(range(1, 12)), 1, eo, covariance, metadata)
    assert result["status"] == "NON_PSD_COVARIANCE_MATRIX"
    assert result["minimum_eigenvalue"] < 0


def test_invalid_captain_or_duplicate_xi_is_rejected():
    forecasts, eo, covariance, metadata = inputs()
    with pytest.raises(FieldRiskInputError, match="captain_id"):
        analyze_field_relative_risk(forecasts, list(range(1, 12)), 12, eo, covariance, metadata)
    with pytest.raises(FieldRiskInputError, match="unique"):
        analyze_field_relative_risk(forecasts, [1] * 11, 1, eo, covariance, metadata)
