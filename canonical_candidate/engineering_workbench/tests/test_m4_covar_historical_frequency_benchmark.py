from __future__ import annotations

import pytest

from m4_covar_historical_frequency_benchmark import (
    HistoricalFrequencyBenchmarkError,
    build_expanding_window_frequency_reference,
)


def forecast(fid, gw, cutoff, as_of, kickoff, observed="A"):
    return {
        "forecast_id": fid, "gameweek_id": gw,
        "training_cutoff_utc": cutoff, "as_of_utc": as_of,
        "first_kickoff_utc": kickoff,
        "probabilities": {"A": 0.6, "B": 0.4},
        "observed_state_id": observed,
    }


def test_builds_expanding_window_frequency_using_only_prior_gameweeks():
    forecasts = [
        forecast("f1", "gw3", "2025-08-20T00:00:00Z", "2025-08-20T12:00:00Z", "2025-08-21T18:00:00Z"),
        forecast("f2", "gw4", "2025-08-27T00:00:00Z", "2025-08-27T12:00:00Z", "2025-08-28T18:00:00Z"),
    ]
    outcomes = [
        {"gameweek_id":"gw1","first_kickoff_utc":"2025-08-01T18:00:00Z","observed_state_id":"A"},
        {"gameweek_id":"gw2","first_kickoff_utc":"2025-08-15T18:00:00Z","observed_state_id":"B"},
        # This outcome is after f1's cutoff and must not leak into f1.
        {"gameweek_id":"gw2b","first_kickoff_utc":"2025-08-25T18:00:00Z","observed_state_id":"B"},
    ]
    result = build_expanding_window_frequency_reference(forecasts, outcomes, ["A", "B"], smoothing_alpha=1)
    first, second = result["forecasts"]
    assert first["reference_probabilities"] == {"A": 0.5, "B": 0.5}
    assert first["reference_benchmark"]["eligible_gameweek_ids"] == ["gw1", "gw2"]
    assert second["reference_probabilities"] == pytest.approx({"A": 0.4, "B": 0.6})
    assert second["reference_benchmark"]["eligible_gameweek_ids"] == ["gw1", "gw2", "gw2b"]
    assert first["reference_benchmark"]["training_gameweek_count"] == 2
    assert result["decision_weight"] == 0
    assert result["production_eligible"] is False


def test_repeated_forecast_snapshots_do_not_duplicate_historical_outcomes():
    rows = [
        forecast("f1", "gw2", "2025-08-10T00:00:00Z", "2025-08-10T12:00:00Z", "2025-08-11T18:00:00Z"),
        forecast("f2", "gw2", "2025-08-10T06:00:00Z", "2025-08-10T18:00:00Z", "2025-08-11T18:00:00Z"),
    ]
    result = build_expanding_window_frequency_reference(
        rows,
        [{"gameweek_id":"gw1","first_kickoff_utc":"2025-08-01T18:00:00Z","observed_state_id":"A"}],
        ["A","B"],
    )
    assert [r["reference_benchmark"]["training_gameweek_count"] for r in result["forecasts"]] == [1, 1]


@pytest.mark.parametrize("outcomes", [
    [
        {"gameweek_id":"gw1","first_kickoff_utc":"2025-08-01T18:00:00Z","observed_state_id":"A"},
        {"gameweek_id":"gw1","first_kickoff_utc":"2025-08-02T18:00:00Z","observed_state_id":"B"},
    ],
    [{"gameweek_id":"gw1","first_kickoff_utc":"2025-08-01T18:00:00Z","observed_state_id":"C"}],
])
def test_rejects_duplicate_gameweeks_and_unknown_states(outcomes):
    with pytest.raises(HistoricalFrequencyBenchmarkError):
        build_expanding_window_frequency_reference(
            [forecast("f1","gw2","2025-08-10T00:00:00Z","2025-08-10T12:00:00Z","2025-08-11T18:00:00Z")],
            outcomes, ["A","B"],
        )


def test_rejects_target_gameweek_in_historical_outcomes():
    with pytest.raises(HistoricalFrequencyBenchmarkError, match="Target Gameweek"):
        build_expanding_window_frequency_reference(
            [forecast("f1","gw1","2025-08-10T00:00:00Z","2025-08-10T12:00:00Z","2025-08-11T18:00:00Z")],
            [{"gameweek_id":"gw1","first_kickoff_utc":"2025-08-01T18:00:00Z","observed_state_id":"A"}],
            ["A","B"],
        )


def test_rejects_timezone_naive_and_nonpositive_smoothing():
    row = forecast("f1","gw2","2025-08-10T00:00:00","2025-08-10T12:00:00Z","2025-08-11T18:00:00Z")
    with pytest.raises(HistoricalFrequencyBenchmarkError, match="timezone"):
        build_expanding_window_frequency_reference(
            [row],
            [{"gameweek_id":"gw1","first_kickoff_utc":"2025-08-01T18:00:00Z","observed_state_id":"A"}],
            ["A","B"],
        )
    row = forecast("f1","gw2","2025-08-10T00:00:00Z","2025-08-10T12:00:00Z","2025-08-11T18:00:00Z")
    with pytest.raises(HistoricalFrequencyBenchmarkError, match="smoothing_alpha"):
        build_expanding_window_frequency_reference(
            [row],
            [{"gameweek_id":"gw1","first_kickoff_utc":"2025-08-01T18:00:00Z","observed_state_id":"A"}],
            ["A","B"], smoothing_alpha=0,
        )
