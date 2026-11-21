from __future__ import annotations
import copy
import pytest
from m4_covar_m3_anchored_covar_model_contract import (
    M3AnchoredCovarModelInputError, validate_m3_anchored_covar_model_inputs,
)

def inputs():
    anchor = {
        "bundle_type": "M3_CONVENTIONAL_FORECAST_ONLY_COVAR_INPUT",
        "season": "2026-27", "target_gameweek": 11, "mode": "REGULAR_GW",
        "as_of_utc": "2026-11-20T20:14:42Z", "deadline_utc": "2026-11-21T11:00:00Z",
        "forecast_snapshot_id": "fplcat-gw11", "model_version": "external:FPL Cat:published xP",
        "player_forecasts": [
            {"fpl_element_id": 10, "expected_points": 4.5, "expected_minutes": 75},
            {"fpl_element_id": 20, "expected_points": 3.2, "expected_minutes": 90},
        ],
        "decision_weight": 0.0, "production_eligible": False,
    }
    history = [{
        "gameweek": 10, "first_kickoff_utc": "2026-11-07T12:30:00Z",
        "outcome_available_at_utc": "2026-11-08T23:00:00Z",
        "finality_audit_status": "PASS_EXACT_MATCH", "outcome_dataset_sha256": "a" * 64,
        "availability_evidence_type": "OFFICIAL_FINISHED_FIXTURE_TIMESTAMPS",
        "player_fixture_outcomes": [
            {"fpl_element_id": 10, "fixture_id": 100, "minutes": 90, "total_points": 8},
            {"fpl_element_id": 20, "fixture_id": 100, "minutes": 60, "total_points": 2},
        ],
    }]
    return anchor, history

def test_accepts_m3_anchor_and_reconciled_chronological_history():
    anchor, history = inputs()
    report = validate_m3_anchored_covar_model_inputs(
        m3_forecast_anchor=anchor, historical_gameweeks=history,
        target_first_kickoff_utc="2026-11-21T12:30:00Z",
        training_cutoff_utc="2026-11-20T20:00:00Z")
    assert report["validation_status"] == "M3_ANCHORED_COVAR_MODEL_INPUTS_ACCEPTED"
    assert report["uses_m3_player_expected_points_as_mean_anchor"] is True
    assert report["joint_probabilities_generated"] is False
    assert report["historical_availability_authentication_verified"] is False
    assert report["decision_weight"] == 0.0
    assert report["production_eligible"] is False

@pytest.mark.parametrize("field,value,match", [
    ("mode", "FREE_HIT", "regular Gameweeks"),
    ("decision_weight", 0.2, "research-only"),
    ("production_eligible", True, "research-only"),
])
def test_rejects_wrong_anchor_policy(field, value, match):
    anchor, history = inputs(); anchor[field] = value
    with pytest.raises(M3AnchoredCovarModelInputError, match=match):
        validate_m3_anchored_covar_model_inputs(
            m3_forecast_anchor=anchor, historical_gameweeks=history,
            target_first_kickoff_utc="2026-11-21T12:30:00Z",
            training_cutoff_utc="2026-11-20T20:00:00Z")

def test_rejects_history_after_training_cutoff():
    anchor, history = inputs(); history[0]["outcome_available_at_utc"] = "2026-11-20T21:00:00Z"
    with pytest.raises(M3AnchoredCovarModelInputError, match="not available strictly"):
        validate_m3_anchored_covar_model_inputs(
            m3_forecast_anchor=anchor, historical_gameweeks=history,
            target_first_kickoff_utc="2026-11-21T12:30:00Z",
            training_cutoff_utc="2026-11-20T20:00:00Z")

def test_rejects_unreconciled_historical_gameweek():
    anchor, history = inputs(); history[0]["finality_audit_status"] = "PENDING"
    with pytest.raises(M3AnchoredCovarModelInputError, match="finality audit"):
        validate_m3_anchored_covar_model_inputs(
            m3_forecast_anchor=anchor, historical_gameweeks=history,
            target_first_kickoff_utc="2026-11-21T12:30:00Z",
            training_cutoff_utc="2026-11-20T20:00:00Z")

def test_rejects_target_gameweek_in_training_rows():
    anchor, history = inputs(); history[0]["gameweek"] = 11
    with pytest.raises(M3AnchoredCovarModelInputError, match="strictly before"):
        validate_m3_anchored_covar_model_inputs(
            m3_forecast_anchor=anchor, historical_gameweeks=history,
            target_first_kickoff_utc="2026-11-21T12:30:00Z",
            training_cutoff_utc="2026-11-20T20:00:00Z")

def test_rejects_duplicate_player_fixture_outcome():
    anchor, history = inputs()
    history[0]["player_fixture_outcomes"].append(copy.deepcopy(history[0]["player_fixture_outcomes"][0]))
    with pytest.raises(M3AnchoredCovarModelInputError, match="duplicate player-fixture"):
        validate_m3_anchored_covar_model_inputs(
            m3_forecast_anchor=anchor, historical_gameweeks=history,
            target_first_kickoff_utc="2026-11-21T12:30:00Z",
            training_cutoff_utc="2026-11-20T20:00:00Z")

def test_rejects_history_from_future_gameweek():
    anchor, history = inputs(); history[0]["first_kickoff_utc"] = "2026-11-22T12:00:00Z"
    with pytest.raises(M3AnchoredCovarModelInputError, match="strictly before"):
        validate_m3_anchored_covar_model_inputs(
            m3_forecast_anchor=anchor, historical_gameweeks=history,
            target_first_kickoff_utc="2026-11-21T12:30:00Z",
            training_cutoff_utc="2026-11-20T20:00:00Z")
