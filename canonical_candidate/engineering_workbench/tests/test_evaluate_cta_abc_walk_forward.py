from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from evaluate_cta_abc_walk_forward import aggregate_player_gameweek, build_folds, candidate_sets, evaluate_matched
from matched_fold_keys import sha_keys


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



def test_matched_abc_fits_one_aggregated_row_per_player_gameweek(monkeypatch):
    fit = [("2017-18", "1", 2), ("2017-18", "2", 2)]
    calibration = [("2017-18", "3", 3), ("2017-18", "4", 3)]
    test = [("2017-18", "5", 4), ("2017-18", "6", 4)]
    parts = {1: {"fit": fit, "calibration": calibration, "test": test}}
    rows = []
    for key, target, prediction in zip(fit + calibration + test,
                                       [2, 4, 3, 5, 6, 8],
                                       [1.5, 3.5, 2.5, 4.5, 5.5, 7.5]):
        rows.append({
            "season": "2017/18",
            "fpl_element_id": key[1],
            "gameweek": key[2],
            "research_eligible_for_model": "true",
            "target_fpl_total_points": str(target),
            "mock_prediction": prediction,
        })

    fitted_row_counts = []
    monkeypatch.setattr(
        "evaluate_cta_abc_walk_forward.available_features",
        lambda fit_rows, candidates: list(candidates),
    )
    def fake_fit_ridge(fit_rows, target_name, features, ridge_lambda):
        fitted_row_counts.append(len(fit_rows))
        return {"fit_rows": len(fit_rows)}
    monkeypatch.setattr("evaluate_cta_abc_walk_forward.fit_ridge", fake_fit_ridge)
    monkeypatch.setattr(
        "evaluate_cta_abc_walk_forward.predict",
        lambda model, row: float(row["mock_prediction"]),
    )
    monkeypatch.setattr(
        "evaluate_cta_abc_walk_forward.metrics",
        lambda records, top_k=20: {"n_player_gameweeks": len(records)},
    )
    monkeypatch.setattr(
        "evaluate_cta_abc_walk_forward.cluster_bootstrap_paired_errors",
        lambda *args, **kwargs: {"status": "TEST_STUB"},
    )

    manifest = {
        "season": "2017-18",
        "folds": [{
            "fold": 1,
            "fit_key_sha256": sha_keys(fit),
            "calibration_key_sha256": sha_keys(calibration),
            "test_key_sha256": sha_keys(test),
        }],
    }
    report = evaluate_matched(rows, {}, parts, manifest, n_boot=100)
    assert fitted_row_counts == [2, 2]
    assert report["training_unit"].startswith("one aggregated player-Gameweek")
    assert report["folds"][0]["fit_player_gameweeks"] == 2
    assert report["folds"][0]["calibration_player_gameweeks"] == 2
    assert report["folds"][0]["test_player_gameweeks"] == 2
