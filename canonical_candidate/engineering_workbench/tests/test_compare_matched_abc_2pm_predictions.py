from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest
from compare_matched_abc_2pm_predictions import (
    deadline_metric,
    metrics,
    player_cluster_bootstrap,
    read_predictions,
    validate_predictions,
)
from matched_fold_keys import sha_keys


def test_prediction_reader_normalizes_season_and_rejects_duplicates(tmp_path):
    path = tmp_path / "abc.csv"
    fields = ["fold", "season", "fpl_element_id", "gameweek", "actual_points",
              "abc_raw_points", "abc_calibrated_points", "fpl_history_calibrated_points"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(dict(fold=1, season="2017/18", fpl_element_id="10", gameweek=2,
                             actual_points=5, abc_raw_points=4, abc_calibrated_points=4.5,
                             fpl_history_calibrated_points=4.2))
    rows = read_predictions(path, "abc")
    assert ("2017-18", "10", 2) in rows
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writerow(dict(fold=1, season="2017-18", fpl_element_id="10", gameweek=2,
                             actual_points=5, abc_raw_points=4, abc_calibrated_points=4.5,
                             fpl_history_calibrated_points=4.2))
    with pytest.raises(ValueError, match="Duplicate"):
        read_predictions(path, "abc")


def test_prediction_keys_must_exactly_match_each_manifest_test_fold():
    key1 = ("2017-18", "10", 2)
    key2 = ("2017-18", "11", 2)
    parts = {1: {"fit": [("2017-18", "1", 1)],
                 "calibration": [("2017-18", "2", 1)],
                 "test": [key1, key2]}}
    manifest = {"folds": [{"fold": 1, "test_key_sha256": sha_keys([key1, key2])}]}
    predictions = {
        key1: {"fold": 1, "actual": 3.0},
        key2: {"fold": 1, "actual": 5.0},
    }
    result = validate_predictions("ABC", predictions, parts, manifest)
    assert result[1]["test_key_sha256"] == sha_keys([key1, key2])
    with pytest.raises(ValueError, match="differ from manifest"):
        validate_predictions("ABC", {key1: predictions[key1]}, parts, manifest)


def test_prediction_fold_labels_must_match_manifest():
    key = ("2017-18", "10", 2)
    parts = {1: {"fit": [("2017-18", "1", 1)],
                 "calibration": [("2017-18", "2", 1)], "test": [key]}}
    manifest = {"folds": [{"fold": 1, "test_key_sha256": sha_keys([key])}]}
    with pytest.raises(ValueError, match="fold labels"):
        validate_predictions("2PM", {key: {"fold": 2}}, parts, manifest)


def test_paired_bootstrap_and_deadline_metrics_are_finite():
    rows = [
        {"season": "2017-18", "player_id": str(i), "gameweek": 2,
         "actual": float(i % 5), "abc": float(i % 5) + .1,
         "two_pm": float(i % 5) + .4}
        for i in range(12)
    ]
    result = player_cluster_bootstrap(rows, "abc", "two_pm", n_boot=100, seed=4)
    assert result["clusters"] == 12
    assert result["mae_delta_ci95"][0] <= result["mae_delta_ci95"][1]
    ranked = deadline_metric(rows, "abc", top_k=5)
    assert ranked["top_k"] == 5
    assert 0 <= ranked["selected_mean_points"] <= 4
    assert metrics(rows, "abc")["n"] == 12
