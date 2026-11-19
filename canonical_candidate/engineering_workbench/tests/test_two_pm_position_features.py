from build_vaastav_fpl_multiseason_panel import build_season_rows
from compare_2pm_position_ablation import compare_predictions, rank_by_deadline
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

def test_position_ablation_requires_exact_same_player_gameweek_keys():
    base = {("2025-26", "101", 1): {"actual": 2.0, "raw": 1.0, "calibrated": 1.0}}
    position = {("2025-26", "101", 1): {"actual": 2.0, "raw": 1.2, "calibrated": 1.2},
                ("2025-26", "102", 1): {"actual": 3.0, "raw": 1.0, "calibrated": 1.0}}
    try:
        compare_predictions(base, position)
    except ValueError as exc:
        assert "identical player-gameweek keys" in str(exc)
    else:
        raise AssertionError("non-identical cohorts must be rejected")


def test_position_ablation_requires_identical_actual_points():
    base = {("2025-26", "101", 1): {"actual": 2.0, "raw": 1.0, "calibrated": 1.0}}
    position = {("2025-26", "101", 1): {"actual": 3.0, "raw": 1.2, "calibrated": 1.2}}
    try:
        compare_predictions(base, position)
    except ValueError as exc:
        assert "Actual points differ" in str(exc)
    else:
        raise AssertionError("different actual targets must be rejected")

def test_ranking_is_computed_within_each_season_gameweek_deadline():
    rows = [
        {"season": "2025-26", "gameweek": 1, "actual": 10.0, "prediction": 10.0},
        {"season": "2025-26", "gameweek": 1, "actual": 0.0, "prediction": 0.0},
        {"season": "2025-26", "gameweek": 2, "actual": 0.0, "prediction": 10.0},
        {"season": "2025-26", "gameweek": 2, "actual": 10.0, "prediction": 0.0},
    ]
    summary, deadlines = rank_by_deadline(rows, "prediction", top_k=1)
    assert summary["n_deadlines"] == 2
    assert set(deadlines) == {("2025-26", 1), ("2025-26", 2)}
    assert summary["macro_selected_mean_points"] == 5.0