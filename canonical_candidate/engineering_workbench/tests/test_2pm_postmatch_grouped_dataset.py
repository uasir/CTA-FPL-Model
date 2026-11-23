import json

import pandas as pd

import build_2pm_postmatch_grouped_dataset as grouped


def test_grouped_dataset_builds_one_scoped_player_gameweek_at_a_time(tmp_path, monkeypatch):
    features = [f"feature_{i:03d}" for i in range(286)]
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({"feature_count": 286, "feature_order": features}))

    candidate = pd.DataFrame([
        {"season": "2024-25", "gameweek": 1, "fpl_code": 10, "fixture": "A"},
        {"season": "2024-25", "gameweek": 1, "fpl_code": 11, "fixture": "B"},
        {"season": "2024-25", "gameweek": 2, "fpl_code": 10, "fixture": "C"},
        {"season": "2025-26", "gameweek": 1, "fpl_code": 10, "fixture": "D"},
    ])
    candidate.to_parquet(tmp_path / "candidate.parquet", index=False)
    pd.DataFrame({"player": [1]}).to_parquet(tmp_path / "players.parquet", index=False)
    pd.DataFrame({"team": [1]}).to_parquet(tmp_path / "teams.parquet", index=False)

    states = pd.DataFrame([
        {"season": "2024-25", "fpl_code": 10, "state": "a"},
        {"season": "2024-25", "fpl_code": 11, "state": "b"},
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
    monkeypatch.setattr(
        grouped, "build_postmatch_state_vectors",
        lambda *args: (states.copy(), {"rows": len(states)}),
    )

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
    assert calls[0]["history"]["fpl_code"].tolist() == [10, 11]
    assert calls[0]["targets"]["fpl_code"].tolist() == [10, 11]
    assert calls[1]["history"]["fpl_code"].tolist() == [10]
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
