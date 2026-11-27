import json

import numpy as np
import pandas as pd

import build_2pm_postmatch_grouped_dataset as grouped


def test_grouped_dataset_builds_one_scoped_player_gameweek_at_a_time(tmp_path, monkeypatch):
    features = [f"feature_{i:03d}" for i in range(286)]
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({"feature_count": 286, "feature_order": features}))

    candidate = pd.DataFrame([
        {"season": "2024-25", "gameweek": 1, "fpl_code": 10, "fixture": "A", "forecast_target_eligible": True},
        {"season": "2024-25", "gameweek": 1, "fpl_code": 10, "fixture": "A0", "forecast_target_eligible": False},
        {"season": "2024-25", "gameweek": 1, "fpl_code": 11, "fixture": "B", "forecast_target_eligible": True},
        {"season": "2024-25", "gameweek": 2, "fpl_code": 10, "fixture": "C", "forecast_target_eligible": True},
        {"season": "2025-26", "gameweek": 1, "fpl_code": 10, "fixture": "D", "forecast_target_eligible": True},
    ])
    candidate.to_parquet(tmp_path / "candidate.parquet", index=False)
    pd.DataFrame({"player": [1]}).to_parquet(tmp_path / "players.parquet", index=False)
    pd.DataFrame({"team": [1]}).to_parquet(tmp_path / "teams.parquet", index=False)

    states = pd.DataFrame([
        {"season": "2024-25", "fpl_code": 10, "fixture": "A0", "state": "started-history"},
        {"season": "2024-25", "fpl_code": 10, "fixture": "A", "state": "a"},
        {"season": "2024-25", "fpl_code": 11, "fixture": "B", "state": "b"},
        {"season": "2024-25", "fpl_code": 12, "state": "not-targeted"},
        {"season": "2025-26", "fpl_code": 10, "state": "other-season"},
    ])
    monkeypatch.setattr(grouped, "load_schema", lambda _: (features, "feature-hash"))
    monkeypatch.setattr(grouped, "load_dastan_package", lambda _: (None, None, object(), None, None))
    monkeypatch.setattr(grouped.pd, "read_parquet", lambda path: {
        "candidate.parquet": candidate.copy(),
        "players.parquet": pd.DataFrame({"player": [1]}),
        "teams.parquet": pd.DataFrame({"team": [1]}),
    }[path.name])
    postmatch_input = {}
    def fake_postmatch_builder(candidate_frame, *args):
        postmatch_input["candidate_rows"] = len(candidate_frame)
        postmatch_input["history_fixtures"] = candidate_frame["fixture"].tolist()
        return states.copy(), {"rows": len(states)}
    monkeypatch.setattr(grouped, "build_postmatch_state_vectors", fake_postmatch_builder)

    calls = []
    def fake_tensor_builder(history, targets, schema_path, shard_dir, report_path, **kwargs):
        calls.append({
            "history": history.copy(),
            "targets": targets.copy(),
            "kwargs": kwargs,
        })
        return {
            "counts": {
                "emitted": int(targets["fpl_code"].nunique()),
                "player_gameweek_groups": int(targets["fpl_code"].nunique()),
                "insufficient_previous_played_matches": 0,
                "postmatch_state_not_available_by_deadline": 0,
                "gap_over_21_days": 0,
            },
            "shards": [{"path": "shard"}],
        }
    monkeypatch.setattr(grouped, "build_player_gameweek_sequence_tensors", fake_tensor_builder)

    report = grouped.build_dataset(
        tmp_path, tmp_path / "candidate.parquet", tmp_path / "players.parquet",
        tmp_path / "teams.parquet", schema, tmp_path / "out",
    )

    assert len(calls) == 3
    assert postmatch_input["candidate_rows"] == 5
    assert "A0" in postmatch_input["history_fixtures"]
    assert calls[0]["history"]["fpl_code"].tolist() == [10, 10, 11]
    assert calls[0]["targets"]["fpl_code"].tolist() == [10, 11]
    assert "A0" not in calls[0]["targets"]["fixture"].tolist()
    assert "started-history" in calls[0]["history"]["state"].tolist()
    assert calls[1]["history"]["fpl_code"].tolist() == [10, 10]
    assert calls[1]["targets"]["fixture"].tolist() == ["C"]
    assert calls[2]["history"]["season"].tolist() == ["2025-26"]
    assert [c["kwargs"]["target_gameweek"] for c in calls] == [1, 2, 1]
    assert all(c["kwargs"]["target_mode"] == "historical" for c in calls)
    assert report["season_gameweek_groups_processed"] == 3
    assert report["player_gameweek_candidate_groups_considered"] == 4
    assert report["player_gameweek_samples_emitted"] == 4
    assert report["player_gameweek_exclusions"] == {
        "insufficient_previous_played_matches": 0,
        "postmatch_state_not_available_by_deadline": 0,
        "gap_over_21_days": 0,
    }
    assert report["admission_status"] == "NOT_ADMITTED"
    assert report["training_authorized"] is False
    assert (tmp_path / "out" / "postmatch_states.parquet").exists()
    assert (tmp_path / "out" / "postmatch_grouped_dataset_report.json").exists()


def test_cached_tensor_mask_backfill_avoids_rebuilding_and_masks_padding(tmp_path):
    features = [f"feature_{i:03d}" for i in range(286)]
    shard_dir = tmp_path / "cached_gw"
    shard_dir.mkdir()
    x = np.zeros((1, 2, 6, 286), dtype=np.float32)
    fixture_mask = np.asarray([[1, 0]], dtype=np.uint8)
    np.save(shard_dir / "X_player_gw_00000.npy", x)
    np.save(shard_dir / "fixture_mask_00000.npy", fixture_mask)
    shards = [{
        "tensor": "X_player_gw_00000.npy",
        "fixture_mask": "fixture_mask_00000.npy",
        "labels": "y_player_gw_00000.npy",
        "metadata": "metadata_player_gw_00000.csv",
        "samples": 1,
    }]
    manifest = {
        "feature_source_availability": {
            "state_codes": {"UNAVAILABLE": 0, "AVAILABLE": 1, "UNKNOWN": 2},
            "default_state": "UNKNOWN",
            "groups": {"defensive_regime_dependent": {"2024-25": "UNAVAILABLE"}},
        },
        "feature_groups": {
            "defensive_regime_dependent": {"feature_order": ["feature_000"]}
        },
        "snapshot_missing_sentinel_features": [],
    }

    updated = grouped.backfill_cached_shard_masks(
        shard_dir, shards, "2024-25", features, manifest
    )

    assert updated[0]["source_availability_state"] == "source_availability_state_00000.npy"
    assert updated[0]["observed_value_mask"] == "observed_value_mask_00000.npy"
    availability = np.load(shard_dir / updated[0]["source_availability_state"])
    observed = np.load(shard_dir / updated[0]["observed_value_mask"])
    assert availability.shape == x.shape
    assert observed.shape == x.shape
    assert np.all(availability[0, 0, :, 0] == 0)
    assert np.all(observed[0, 0, :, 0] == 0)
    assert np.all(availability[0, 0, :, 1:] == 2)
    assert np.all(observed[0, 0, :, 1:] == 1)
    assert np.all(availability[0, 1] == 0)
    assert np.all(observed[0, 1] == 0)
