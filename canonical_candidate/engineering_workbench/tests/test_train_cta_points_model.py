from pathlib import Path
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from train_cta_points_model import with_training_target


def test_dastan_total_points_becomes_cta_training_target():
    frame = pd.DataFrame({"total_points": [2, 8, 0], "minutes": [90, 90, 0]})
    result = with_training_target(frame)
    assert result["target_points"].tolist() == [2, 8, 0]
    assert "target_points" not in frame.columns


def test_existing_explicit_target_is_preserved():
    frame = pd.DataFrame({"target_points": [4.5], "total_points": [8]})
    result = with_training_target(frame)
    assert result["target_points"].tolist() == [4.5]


def test_missing_training_target_fails_clearly():
    with pytest.raises(ValueError, match="total_points"):
        with_training_target(pd.DataFrame({"minutes": [90]}))
