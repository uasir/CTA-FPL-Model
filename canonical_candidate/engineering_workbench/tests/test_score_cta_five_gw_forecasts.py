from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from score_cta_five_gw_forecasts import expected_appearance_points, scale_points_per_90


def test_points_per_90_are_scaled_by_dastan_expected_minutes():
    result = scale_points_per_90([8.0, 6.0, -1.0], [90.0, 45.0, 30.0])
    np.testing.assert_allclose(result, [8.0, 3.0, -1.0 / 3.0])


def test_points_per_90_rejects_invalid_minutes():
    with pytest.raises(ValueError, match="within"):
        scale_points_per_90([8.0], [95.0])


def test_points_per_90_rejects_non_finite_predictions():
    with pytest.raises(ValueError, match="finite"):
        scale_points_per_90([np.nan], [90.0])


def test_points_per_90_requires_matching_shapes():
    with pytest.raises(ValueError, match="matching shapes"):
        scale_points_per_90([8.0, 6.0], [90.0])


def test_expected_appearance_points_uses_any_and_60_minute_probabilities():
    result = expected_appearance_points([0.8, 0.6, 0.0], [0.5, 0.2, 0.0])
    np.testing.assert_allclose(result, [1.3, 0.8, 0.0])


def test_expected_appearance_points_rejects_incoherent_probabilities():
    with pytest.raises(ValueError, match="0 <= p60"):
        expected_appearance_points([0.5], [0.6])
