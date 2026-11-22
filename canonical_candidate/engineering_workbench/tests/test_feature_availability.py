from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from feature_availability import mask_unavailable_features, unavailable_feature_names


def test_unavailable_understat_feature_names_preserve_schema_order():
    features = [
        "player_xg_1", "player_assists_1", "team_ppda_att_5",
        "opp_xga_38", "ar_rest_days", "player_xgbuildup_10",
    ]
    assert unavailable_feature_names(features) == [
        "player_xg_1", "team_ppda_att_5", "opp_xga_38", "player_xgbuildup_10",
    ]


def test_mask_unavailable_features_zeroes_same_columns_for_train_and_score():
    features = ["player_xg_1", "player_assists_1", "team_xga_5", "ar_rest_days"]
    frame = pd.DataFrame([{
        "player_xg_1": 0.7, "player_assists_1": 0.2,
        "team_xga_5": 1.4, "ar_rest_days": 6.0,
    }])
    masked, names = mask_unavailable_features(frame, features)
    assert names == ["player_xg_1", "team_xga_5"]
    assert masked.loc[0, "player_xg_1"] == 0.0
    assert masked.loc[0, "team_xga_5"] == 0.0
    assert masked.loc[0, "player_assists_1"] == 0.2
    assert masked.loc[0, "ar_rest_days"] == 6.0


def test_mask_unavailable_features_rejects_missing_schema_columns():
    frame = pd.DataFrame([{"player_xg_1": 0.1}])
    try:
        mask_unavailable_features(frame, ["player_xg_1", "player_assists_1"])
    except ValueError as exc:
        assert "player_assists_1" in str(exc)
    else:
        raise AssertionError("missing schema column was accepted")
