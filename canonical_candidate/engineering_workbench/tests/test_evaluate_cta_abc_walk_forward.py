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
