from __future__ import annotations

import pytest

from m4_covar_historical_frequency_backtest import (
    HistoricalFrequencyBacktestError,
    evaluate_against_expanding_frequency_reference,
)


def row(fid, gw, kickoff, observed):
    date = kickoff[:10]
    return {
        "forecast_id": fid,
        "gameweek_id": gw,
        "as_of_utc": f"{date}T12:00:00Z",
        "first_kickoff_utc": f"{date}T18:00:00Z",
        "training_cutoff_utc": f"{date}T00:00:00Z",
        "probabilities": {"A": 0.7, "B": 0.3},
        "observed_state_id": observed,
    }


def test_evaluates_only_test_split_against_point_in_time_frequency_reference():
    forecasts = [
        row("f-gw1", "gw1", "2025-08-01T18:00:00Z", "A"),
        row("f-gw2", "gw2", "2025-08-08T18:00:00Z", "B"),
        row("f-gw3-a", "gw3", "2025-08-15T18:00:00Z", "A"),
        row("f-gw3-b", "gw3", "2025-08-15T18:00:00Z", "A"),
    ]
    outcomes = [
        {"gameweek_id":"gw1","first_kickoff_utc":"2025-08-01T18:00:00Z",
         "outcome_available_at_utc":"2025-08-04T00:00:00Z","observed_state_id":"A"},
        {"gameweek_id":"gw2","first_kickoff_utc":"2025-08-08T18:00:00Z",
         "outcome_available_at_utc":"2025-08-11T00:00:00Z","observed_state_id":"B"},
    ]
    result = evaluate_against_expanding_frequency_reference(
        forecasts, outcomes, ["A","B"],
        {"train":["gw1"],"validation":["gw2"],"test":["gw3"]},
        bootstrap_resamples=100,
    )
    assert result["backtest_status"] == "CHRONOLOGICAL_TEST_SPLIT_EVALUATED"
    assert result["evaluation_scope"] == "DECLARED_TEST_GAMEWEEKS_ONLY"
    assert result["test_gameweek_ids"] == ["gw3"]
    assert result["test_forecast_count"] == 2
    assert result["calibration"]["forecast_count"] == 2
    assert result["calibration"]["gameweek_count"] == 1
    assert result["reference_benchmark"]["reference_method"] == "EXPANDING_WINDOW_GAMEWEEK_HISTORICAL_FREQUENCY"
    assert result["source_authenticity_verified"] is False
    assert result["decision_weight"] == 0
    assert result["production_eligible"] is False


def test_rejects_split_overlap_or_nonchronological_gameweeks():
    forecasts = [
        row("f1","gw1","2025-08-01T18:00:00Z","A"),
        row("f2","gw2","2025-08-08T18:00:00Z","B"),
        row("f3","gw3","2025-08-15T18:00:00Z","A"),
    ]
    outcomes = [
        {"gameweek_id":"gw1","first_kickoff_utc":"2025-08-01T18:00:00Z",
         "outcome_available_at_utc":"2025-08-04T00:00:00Z","observed_state_id":"A"},
        {"gameweek_id":"gw2","first_kickoff_utc":"2025-08-08T18:00:00Z",
         "outcome_available_at_utc":"2025-08-11T00:00:00Z","observed_state_id":"B"},
    ]
    with pytest.raises(ValueError, match="more than one split"):
        evaluate_against_expanding_frequency_reference(
            forecasts, outcomes, ["A","B"],
            {"train":["gw1"],"validation":["gw2"],"test":["gw2","gw3"]},
            bootstrap_resamples=100,
        )


def test_fails_when_test_gameweek_has_no_historical_training_outcomes():
    forecasts = [row("f1","gw1","2025-08-01T18:00:00Z","A")]
    with pytest.raises(HistoricalFrequencyBacktestError):
        evaluate_against_expanding_frequency_reference(
            forecasts, [], ["A","B"],
            {"train":["gw1"],"validation":["gw2"],"test":["gw3"]},
            bootstrap_resamples=100,
        )
