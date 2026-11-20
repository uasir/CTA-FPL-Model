from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from evaluate_cta_abc_walk_forward import (
    aggregate_player_gameweek,
    build_folds,
    candidate_sets,
    deadline_local_ranking,
    feature_coverage,
    metrics,
    summarize_layer_feature_availability,
)


def test_walk_forward_splits_only_at_whole_gameweek_boundaries():
    gameweeks = list(range(1, 39))
    folds = build_folds(gameweeks, min_train_gameweeks=18, test_window=4)
    assert folds
    for fold in folds:
        assert max(fold["train_deadlines"]) < min(fold["test_deadlines"])
        assert len(fold["test_deadlines"]) <= 4
    flattened = [gw for fold in folds for gw in fold["test_deadlines"]]
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
        {"season": "2017/18", "player_id": "10", "gameweek": 7, "actual": 7.0, "predicted": 6.5, "fixture_rows": 2},
        {"season": "2017/18", "player_id": "11", "gameweek": 7, "actual": 1.0, "predicted": 1.5, "fixture_rows": 1},
    ]


def test_candidate_registry_keeps_abc_standalone_and_augmented_separate():
    candidates = candidate_sets()
    assert "ABC_ONLY_ABC" in candidates
    assert "FPL_HISTORY_ONLY" in candidates
    assert "FPL_PLUS_ABC" in candidates
    assert not any(name.startswith("FPL_") for name in candidates["ABC_ONLY_ABC"])
    assert all(name.startswith("abc_") for name in candidates["ABC_ONLY_ABC"])


def test_abc_ranking_is_calculated_within_each_season_gameweek_not_pooled():
    rows = [
        {"season": "2017/18", "player_id": "a", "gameweek": 1, "actual": 10, "predicted": 9},
        {"season": "2017/18", "player_id": "b", "gameweek": 1, "actual": 2, "predicted": 1},
        {"season": "2017/18", "player_id": "c", "gameweek": 2, "actual": 1, "predicted": 9},
        {"season": "2017/18", "player_id": "d", "gameweek": 2, "actual": 8, "predicted": 1},
    ]
    result = deadline_local_ranking(rows, top_k=1)
    assert result["n_deadlines"] == 2
    assert result["method"] == "RANK_WITHIN_EACH_SEASON_GAMEWEEK_THEN_MACRO_AVERAGE"
    assert result["by_deadline"]["2017/18:GW1"]["selected_mean_points"] == 10
    assert result["by_deadline"]["2017/18:GW2"]["selected_mean_points"] == 1
    assert result["macro_selected_mean_points"] == 5.5
    assert "deadline_local_ranking" in metrics(rows, top_k=1)
    assert "ranking" not in metrics(rows, top_k=1)["forecast"]


def test_player_gameweek_aggregation_keeps_seasons_separate():
    rows = [
        {"season": "2017/18", "fpl_element_id": "10", "gameweek": "1", "target_fpl_total_points": "2"},
        {"season": "2017/18", "fpl_element_id": "10", "gameweek": "1", "target_fpl_total_points": "3"},
        {"season": "2018/19", "fpl_element_id": "10", "gameweek": "1", "target_fpl_total_points": "7"},
    ]
    result = aggregate_player_gameweek(rows, [1.0, 2.0, 6.0])
    assert len(result) == 2
    assert result[0]["season"] == "2017/18"
    assert result[0]["actual"] == 5.0
    assert result[0]["predicted"] == 3.0
    assert result[0]["fixture_rows"] == 2
    assert result[1]["season"] == "2018/19"
    assert result[1]["actual"] == 7.0


def test_deadline_ranking_does_not_pool_same_gameweek_across_seasons():
    records = [
        {"season": "2017/18", "gameweek": 1, "player_id": "a", "actual": 1, "predicted": 1},
        {"season": "2017/18", "gameweek": 1, "player_id": "b", "actual": 2, "predicted": 2},
        {"season": "2018/19", "gameweek": 1, "player_id": "a", "actual": 10, "predicted": 10},
        {"season": "2018/19", "gameweek": 1, "player_id": "b", "actual": 20, "predicted": 20},
    ]
    result = deadline_local_ranking(records, top_k=1)
    assert result["n_deadlines"] == 2
    assert set(result["by_deadline"]) == {"2017/18:GW1", "2018/19:GW1"}


def test_abc_metrics_count_same_player_in_different_seasons_separately():
    records = [
        {"season": "2017/18", "gameweek": 1, "player_id": "10", "actual": 1, "predicted": 1},
        {"season": "2018/19", "gameweek": 1, "player_id": "10", "actual": 2, "predicted": 2},
    ]
    result = metrics(records, top_k=1)
    assert result["n_player_gameweeks"] == 2
    assert result["n_unique_players"] == 2


def test_expanding_folds_preserve_season_gameweek_chronology():
    deadlines = (
        [("2017/18", gw) for gw in range(1, 21)]
        + [("2018/19", gw) for gw in range(1, 5)]
    )
    folds = build_folds(deadlines, min_train_gameweeks=18, test_window=4)
    assert folds[0]["train_deadlines"] == deadlines[:18]
    assert folds[0]["test_deadlines"] == deadlines[18:22]
    assert folds[0]["test_deadlines"] == [
        ("2017/18", 19), ("2017/18", 20), ("2018/19", 1), ("2018/19", 2)
    ]


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


def test_abc_2pm_comparator_key_includes_normalized_season():
    from compare_abc_with_2pm_same_cohort import key

    assert key("2017/18", "10", 1) == ("2017-18", "10", 1)
    assert key("2018/19", "10", 1) != key("2017/18", "10", 1)
