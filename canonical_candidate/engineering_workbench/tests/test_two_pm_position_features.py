from build_vaastav_fpl_multiseason_panel import build_season_rows
from evaluate_two_pm_transformer_walk_forward import (
    BASE_TRANSFORMER_FEATURES, POSITION_FEATURES, TRANSFORMER_FEATURE_SETS, available_features,
)


def test_multiseason_panel_encodes_position_as_four_one_hot_features():
    rows = build_season_rows("2025-26", [{
        "element": "101",
        "round": "1",
        "kickoff_time": "2025-08-15T12:00:00Z",
        "minutes": "90",
        "total_points": "6",
        "position": "DEF",
        "expected_goals": "0.1",
        "expected_assists": "0.0",
        "was_home": "true",
        "fixture": "1",
    }])
    assert len(rows) == 1
    assert [rows[0][key] for key in POSITION_FEATURES] == [0.0, 1.0, 0.0, 0.0]


def test_position_ablation_is_separate_from_unchanged_base_feature_set():
    assert TRANSFORMER_FEATURE_SETS["base"] == BASE_TRANSFORMER_FEATURES
    assert TRANSFORMER_FEATURE_SETS["position"] == BASE_TRANSFORMER_FEATURES + POSITION_FEATURES
    row = {feature: 0.0 for feature in BASE_TRANSFORMER_FEATURES + POSITION_FEATURES}
    base = available_features([row], TRANSFORMER_FEATURE_SETS["base"])
    with_position = available_features([row], TRANSFORMER_FEATURE_SETS["position"])
    assert not any(feature in base for feature in POSITION_FEATURES)
    assert all(feature in with_position for feature in POSITION_FEATURES)