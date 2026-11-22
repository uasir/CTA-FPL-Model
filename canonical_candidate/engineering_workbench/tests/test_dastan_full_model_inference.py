from pathlib import Path
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_dastan_full_model_inference import validate_input, validate_predictions


IDENTITY = [
    "season", "gameweek", "fpl_code", "fpl_element_id", "fixture_id",
    "position", "team_name", "opponent_team_name", "kickoff_time",
]
PREDICTIONS = [
    "xpts", "multibucket", "direct", "p60", "p_any", "expected_minutes",
    "p_band0", "p_band1", "p_band2", "p_band3",
]


def sample_frame():
    return pd.DataFrame([{
        "season": "2026-27",
        "gameweek": 12,
        "fpl_code": 101,
        "fpl_element_id": 1,
        "fixture_id": 900,
        "position": "MID",
        "team_name": "Arsenal",
        "opponent_team_name": "Chelsea",
        "kickoff_time": "2026-11-28T15:00:00Z",
        "f1": 0.25,
        "f2": 1.0,
    }])


def test_validate_input_accepts_complete_finite_feature_frame():
    validate_input(sample_frame(), ["f1", "f2"])


def test_validate_input_rejects_duplicate_fixture_rows():
    frame = pd.concat([sample_frame(), sample_frame()], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        validate_input(frame, ["f1", "f2"])


def test_validate_predictions_requires_exact_fixture_population():
    source = sample_frame()
    predicted = source[IDENTITY].copy()
    for field in PREDICTIONS:
        predicted[field] = 1.0
    result = validate_predictions(predicted, source)
    assert len(result) == 1
    assert result["xpts"].iloc[0] == 1.0


def test_validate_predictions_rejects_incomplete_or_negative_points():
    source = sample_frame()
    predicted = source[IDENTITY].copy()
    for field in PREDICTIONS:
        predicted[field] = 1.0
    predicted.loc[0, "xpts"] = -0.1
    with pytest.raises(ValueError, match="negative"):
        validate_predictions(predicted, source)
