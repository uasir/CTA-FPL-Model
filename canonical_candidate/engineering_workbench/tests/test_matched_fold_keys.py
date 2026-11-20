import csv

import pytest

from matched_fold_keys import (
    canonical_key,
    load_partition_keys,
    sha_keys,
    verify_manifest_partition_hashes,
)


def test_canonical_key_normalizes_historical_season_labels():
    assert canonical_key("2017/18", "10", "7") == ("2017-18", "10", 7)
    assert canonical_key("2017-2018", "10", 7) == ("2017-18", "10", 7)


def test_partition_reader_and_manifest_hash_gate(tmp_path):
    path = tmp_path / "keys.csv"
    rows = [
        (1, "fit", "2017/18", "10", 2),
        (1, "calibration", "2017-18", "11", 3),
        (1, "test", "2017-18", "12", 4),
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["fold", "partition", "season", "fpl_element_id", "gameweek"])
        writer.writerows(rows)
    partitions = load_partition_keys(path)
    assert partitions[1]["fit"] == [("2017-18", "10", 2)]
    manifest = {"status": "PASS_MATCHED_FOLD_MANIFEST", "folds": [{
        "fold": 1, "status": "READY",
        "fit_key_sha256": sha_keys(partitions[1]["fit"]),
        "calibration_key_sha256": sha_keys(partitions[1]["calibration"]),
        "test_key_sha256": sha_keys(partitions[1]["test"]),
    }]}
    assert verify_manifest_partition_hashes(partitions, manifest)


def test_partition_reader_rejects_duplicate_keys(tmp_path):
    path = tmp_path / "keys.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["fold", "partition", "season", "fpl_element_id", "gameweek"])
        writer.writerow([1, "fit", "2017/18", "10", 2])
        writer.writerow([1, "fit", "2017-18", "10", 2])
        writer.writerow([1, "calibration", "2017-18", "11", 3])
        writer.writerow([1, "test", "2017-18", "12", 4])
    with pytest.raises(ValueError, match="Duplicate"):
        load_partition_keys(path)


def test_manifest_hash_mismatch_fails_closed(tmp_path):
    path = tmp_path / "keys.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["fold", "partition", "season", "fpl_element_id", "gameweek"])
        writer.writerow([1, "fit", "2017/18", "10", 2])
        writer.writerow([1, "calibration", "2017-18", "11", 3])
        writer.writerow([1, "test", "2017-18", "12", 4])
    partitions = load_partition_keys(path)
    manifest = {"folds": [{
        "fold": 1,
        "fit_key_sha256": "wrong",
        "calibration_key_sha256": sha_keys(partitions[1]["calibration"]),
        "test_key_sha256": sha_keys(partitions[1]["test"]),
    }]}
    with pytest.raises(ValueError, match="differs from manifest"):
        verify_manifest_partition_hashes(partitions, manifest)


def test_blocked_manifest_cannot_be_scored(tmp_path):
    path = tmp_path / "keys.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["fold", "partition", "season", "fpl_element_id", "gameweek"])
        writer.writerow([1, "fit", "2017/18", "10", 2])
        writer.writerow([1, "calibration", "2017-18", "11", 3])
        writer.writerow([1, "test", "2017-18", "12", 4])
    partitions = load_partition_keys(path)
    with pytest.raises(ValueError, match="not in PASS"):
        verify_manifest_partition_hashes(partitions, {"status": "BLOCKED_FOLD_COVERAGE", "folds": []})
