from pathlib import Path
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from train_cta_points_model import with_training_target


def test_fpl_points_become_appearance_conditional_points_per_90():
    frame = pd.DataFrame({
        "total_points": [8, 4, 0, 2],
        "minutes": [90, 45, 0, 15],
    })
    result = with_training_target(frame)
    assert result["target_points_per_90"].iloc[0] == 6
    assert result["target_points_per_90"].iloc[1] == 6
    assert pd.isna(result["target_points_per_90"].iloc[2])
    assert pd.isna(result["target_points_per_90"].iloc[3])
    assert "target_points_per_90" not in frame.columns


def test_existing_explicit_points_per_90_target_is_preserved():
    frame = pd.DataFrame({
        "target_points_per_90": [4.5],
        "total_points": [8],
        "minutes": [90],
    })
    result = with_training_target(frame)
    assert result["target_points_per_90"].tolist() == [4.5]


def test_missing_training_target_inputs_fail_clearly():
    with pytest.raises(ValueError, match="observed FPL points field"):
        with_training_target(pd.DataFrame({"minutes": [90]}))
