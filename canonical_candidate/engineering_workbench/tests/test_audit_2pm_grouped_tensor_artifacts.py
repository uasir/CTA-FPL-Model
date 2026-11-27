import json

import numpy as np
import pandas as pd
import pytest

import audit_2pm_grouped_tensor_artifacts as audit


def _write_dataset(root, *, history_time="2024-08-01T12:00:00Z", target_points=-1.0,
                   fixture_count=1, mask=None, duplicate=False):
    shard = root / "player_gameweek_tensors" / "2024-25" / "gw_1"
    shard.mkdir(parents=True)
    x = np.zeros((1, 1, 6, 286), dtype=np.float32)
    np.save(shard / "X_player_gw_000.npy", x)
    np.save(shard / "fixture_mask_000.npy",
            np.asarray([[1]] if mask is None else mask, dtype=np.uint8))
    np.save(shard / "source_availability_state_000.npy", np.full(x.shape, 2, dtype=np.uint8))
    np.save(shard / "observed_value_mask_000.npy", np.ones(x.shape, dtype=np.uint8))
    np.save(shard / "y_player_gw_000.npy", np.asarray([target_points], dtype=np.float32))
    row = {
        "season": "2024-25",
        "gameweek": 1,
        "fpl_code": 10,
        "fixture_count": fixture_count,
        "history_fixture_ids": json.dumps(["a", "b", "c", "d", "e"]),
        "history_state_as_of_times": json.dumps([history_time] * 5),
        "sequence_gap_days": json.dumps([1, 2, 3, 4, 5]),
        "target_deadline_time": "2024-08-02T12:00:00Z",
        "target_first_kickoff_time": "2024-08-03T12:00:00Z",
        "fixture_target_points": json.dumps([target_points]),
        "target_points": target_points,
    }
    pd.DataFrame([row]).to_csv(shard / "metadata_player_gw_000.csv", index=False)
    report = {
        "admission_status": "NOT_ADMITTED",
        "training_authorized": False,
        "postmatch_state_rows": 5,
        "season_gameweek_groups_processed": 1,
        "player_gameweek_candidate_groups_considered": 1,
        "player_gameweek_samples_emitted": 1,
        "feature_order": [f"feature_{i}" for i in range(286)],
        "snapshot_missing_sentinel_features": [],
    }
    (root / "postmatch_grouped_dataset_report.json").write_text(json.dumps(report))
    if duplicate:
        # A second shard with the same player-Gameweek key must be rejected.
        second = root / "player_gameweek_tensors" / "2024-25" / "gw_2"
        second.mkdir(parents=True)
        np.save(second / "X_player_gw_001.npy", x)
        np.save(second / "fixture_mask_001.npy", np.asarray([[1]], dtype=np.uint8))
        np.save(second / "source_availability_state_001.npy", np.full(x.shape, 2, dtype=np.uint8))
        np.save(second / "observed_value_mask_001.npy", np.ones(x.shape, dtype=np.uint8))
        np.save(second / "y_player_gw_001.npy", np.asarray([target_points], dtype=np.float32))
        pd.DataFrame([row]).to_csv(second / "metadata_player_gw_001.csv", index=False)


def test_integrity_audit_accepts_valid_candidate_and_preserves_negative_labels(tmp_path):
    _write_dataset(tmp_path)
    result = audit.audit_dataset(tmp_path)
    assert result["status"] == "PASS"
    assert result["admission_status"] == "NOT_ADMITTED"
    assert result["training_authorized"] is False
    assert result["samples"] == 1
    assert result["negative_target_labels_preserved"] == 1
    assert result["nan_feature_rate"] == 0.0


def test_integrity_audit_rejects_history_state_at_or_after_deadline(tmp_path):
    _write_dataset(tmp_path, history_time="2024-08-02T12:00:00Z")
    with pytest.raises(ValueError, match="strictly pre-deadline"):
        audit.audit_dataset(tmp_path)


def test_integrity_audit_rejects_fixture_mask_metadata_mismatch(tmp_path):
    _write_dataset(tmp_path, fixture_count=2, mask=[[1]])
    with pytest.raises(ValueError, match="Fixture mask does not match metadata"):
        audit.audit_dataset(tmp_path)


def test_integrity_audit_rejects_duplicate_player_gameweek_across_shards(tmp_path):
    _write_dataset(tmp_path, duplicate=True)
    with pytest.raises(ValueError, match="Duplicate player-Gameweek sample"):
        audit.audit_dataset(tmp_path)


def test_integrity_audit_rejects_observed_value_on_structural_absence(tmp_path):
    _write_dataset(tmp_path)
    shard = tmp_path / "player_gameweek_tensors" / "2024-25" / "gw_1"
    state = np.load(shard / "source_availability_state_000.npy")
    state[..., 0] = 0
    np.save(shard / "source_availability_state_000.npy", state)
    with pytest.raises(ValueError, match="Structurally unavailable feature marked observed"):
        audit.audit_dataset(tmp_path)


def test_integrity_audit_rejects_observed_nonfinite_feature(tmp_path):
    _write_dataset(tmp_path)
    shard = tmp_path / "player_gameweek_tensors" / "2024-25" / "gw_1"
    x = np.load(shard / "X_player_gw_000.npy")
    x[..., 0] = np.nan
    np.save(shard / "X_player_gw_000.npy", x)
    with pytest.raises(ValueError, match="non-finite value as observed"):
        audit.audit_dataset(tmp_path)


def test_integrity_audit_rejects_missing_snapshot_sentinel_marked_observed(tmp_path):
    _write_dataset(tmp_path)
    report_path = tmp_path / "postmatch_grouped_dataset_report.json"
    report = json.loads(report_path.read_text())
    report["snapshot_missing_sentinel_features"] = ["feature_0"]
    report_path.write_text(json.dumps(report))
    shard = tmp_path / "player_gameweek_tensors" / "2024-25" / "gw_1"
    x = np.load(shard / "X_player_gw_000.npy")
    x[..., 0] = -1.0
    np.save(shard / "X_player_gw_000.npy", x)
    with pytest.raises(ValueError, match="Missing-snapshot sentinel marked observed"):
        audit.audit_dataset(tmp_path)
