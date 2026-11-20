from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from evaluate_cta_abc_walk_forward import aggregate_player_gameweek, build_folds, candidate_sets


def test_walk_forward_splits_only_at_whole_gameweek_boundaries():
    gameweeks = list(range(1, 39))
    folds = build_folds(gameweeks, min_train_gameweeks=18, test_window=4)
    assert folds
    for fold in folds:
        assert max(fold["train_gameweeks"]) < min(fold["test_gameweeks"])
        assert len(fold["test_gameweeks"]) <= 4
    flattened = [gw for fold in folds for gw in fold["test_gameweeks"]]
    assert len(flattened) == len(set(flattened))
    assert flattened == gameweeks[max(18, len(gameweeks) // 2):]


def test_player_fixture_predictions_aggregate_to_player_gameweek():
    rows = [
        {"fpl_element_id": "10", "gameweek": "7", "target_fpl_total_points": "2"},
        {"fpl_element_id": "10", "gameweek": "7", "target_fpl_total_points": "5"},
        {"fpl_element_id": "11", "gameweek": "7", "target_fpl_total_points": "1"},
    ]
    predictions = [2.5, 4.0, 1.5]
    result = aggregate_player_gameweek(rows, predictions)
    assert result == [
        {"player_id": "10", "gameweek": 7, "actual": 7.0, "predicted": 6.5, "fixture_rows": 2},
        {"player_id": "11", "gameweek": 7, "actual": 1.0, "predicted": 1.5, "fixture_rows": 1},
    ]


def test_candidate_registry_keeps_abc_standalone_and_augmented_separate():
    candidates = candidate_sets()
    assert "ABC_ONLY_ABC" in candidates
    assert "FPL_HISTORY_ONLY" in candidates
    assert "FPL_PLUS_ABC" in candidates
    assert not any(name.startswith("FPL_") for name in candidates["ABC_ONLY_ABC"])
    assert all(name.startswith("abc_") for name in candidates["ABC_ONLY_ABC"])



def test_abc_ranking_is_calculated_within_each_gameweek_not_pooled():
    from evaluate_cta_abc_walk_forward import deadline_local_ranking, metrics

    rows = [
        {"player_id": "a", "gameweek": 1, "actual": 10, "predicted": 9},
        {"player_id": "b", "gameweek": 1, "actual": 2, "predicted": 1},
        {"player_id": "c", "gameweek": 2, "actual": 1, "predicted": 9},
        {"player_id": "d", "gameweek": 2, "actual": 8, "predicted": 1},
    ]
    result = deadline_local_ranking(rows, top_k=1)
    assert result["n_deadlines"] == 2
    assert result["method"] == "RANK_WITHIN_EACH_FPL_GAMEWEEK_THEN_MACRO_AVERAGE"
    assert result["by_gameweek"]["1"]["selected_mean_points"] == 10
    assert result["by_gameweek"]["2"]["selected_mean_points"] == 1
    assert result["macro_selected_mean_points"] == 5.5
    assert "deadline_local_ranking" in metrics(rows, top_k=1)
    assert "ranking" not in metrics(rows, top_k=1)["forecast"]


def test_abc_2pm_comparator_key_includes_normalized_season():
    from compare_abc_with_2pm_same_cohort import key

    assert key("2017/18", "10", 1) == ("2017-18", "10", 1)
    assert key("2018/19", "10", 1) != key("2017/18", "10", 1)


def test_abc_feature_coverage_reports_observed_and_missing_rows():
    rows = [
        {"abc_a": "1.0", "abc_b": ""},
        {"abc_a": "0.0", "abc_b": "2.0"},
        {"abc_a": None, "abc_b": None},
    ]
    coverage = feature_coverage(rows, ["abc_a", "abc_b"])
    assert coverage["abc_a"]["observed_rows"] == 2
    assert coverage["abc_a"]["missing_rows"] == 1
    assert coverage["abc_a"]["coverage_rate"] == 2 / 3
    assert coverage["abc_b"]["observed_rows"] == 1
    assert coverage["abc_b"]["missing_rows"] == 2


def test_layer_feature_availability_marks_unsupported_features():
    summary = summarize_layer_feature_availability(
        {"ABC_ONLY_A": ["abc_progressive_passes", "abc_player_key_pass_rate"]},
        [{
            "models": {
                "ABC_ONLY_A": {
                    "feature_coverage_on_training_rows": {
                        "abc_progressive_passes": {"coverage_rate": 0.9},
                        "abc_player_key_pass_rate": {"coverage_rate": 0.6},
                    }
                }
            }
        }],
    )
    layer = summary["A_temporal_football_value"]
    assert layer["ever_observed_feature_count"] == 2
    assert "abc_player_tracked_xg_rate" in layer["never_observed_features"]
    assert layer["training_coverage_by_feature"]["abc_progressive_passes"]["minimum_coverage_rate"] == 0.9
