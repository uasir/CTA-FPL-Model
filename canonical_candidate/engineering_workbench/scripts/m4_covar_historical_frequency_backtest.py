"""Run a chronological test-split comparison against expanding-window frequency."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from m4_covar_historical_frequency_benchmark import build_expanding_window_frequency_reference
from m4_covar_joint_forecast_dataset import validate_joint_forecast_dataset
from m4_covar_joint_probability_calibration import evaluate_joint_probability_calibration


class HistoricalFrequencyBacktestError(ValueError):
    """Invalid chronological benchmark evaluation request."""


def evaluate_against_expanding_frequency_reference(
    forecasts: Sequence[Mapping[str, Any]],
    historical_outcomes: Sequence[Mapping[str, Any]],
    state_catalogue: Sequence[str],
    split_gameweeks: Mapping[str, Sequence[str]],
    *,
    smoothing_alpha: float = 1.0,
    bootstrap_resamples: int = 2000,
    bootstrap_seed: int = 42,
) -> dict[str, Any]:
    """Evaluate only the declared chronological test Gameweeks.

    The complete forecast collection is checked for disjoint chronological
    train/validation/test Gameweek partitions. Reference forecasts are built
    only for test rows, using historical outcomes demonstrably available
    before each test row's training cutoff. Multiple snapshots remain
    Gameweek clusters in the calibration/bootstrap evaluator.
    """
    temporal = validate_joint_forecast_dataset(forecasts, split_gameweeks)
    test_gameweeks = set(str(value) for value in split_gameweeks["test"])
    test_forecasts = [
        row for row in forecasts
        if str(row.get("gameweek_id", "")) in test_gameweeks
    ]
    if not test_forecasts:
        raise HistoricalFrequencyBacktestError("test split contains no forecast rows")
    reference = build_expanding_window_frequency_reference(
        test_forecasts, historical_outcomes, state_catalogue,
        smoothing_alpha=smoothing_alpha,
    )
    calibration = evaluate_joint_probability_calibration(
        reference["forecasts"],
        bootstrap_resamples=bootstrap_resamples,
        bootstrap_seed=bootstrap_seed,
    )
    return {
        "schema_version": "1.0.0",
        "backtest_status": "CHRONOLOGICAL_TEST_SPLIT_EVALUATED",
        "temporal_dataset_validation": temporal,
        "test_gameweek_ids": sorted(test_gameweeks),
        "test_forecast_count": len(test_forecasts),
        "reference_benchmark": {
            key: value for key, value in reference.items() if key != "forecasts"
        },
        "calibration": calibration,
        "evaluation_scope": "DECLARED_TEST_GAMEWEEKS_ONLY",
        "source_authenticity_verified": False,
        "archived_source_bytes_verified": False,
        "historical_dataset_certified": False,
        "decision_weight": 0.0,
        "production_eligible": False,
    }
