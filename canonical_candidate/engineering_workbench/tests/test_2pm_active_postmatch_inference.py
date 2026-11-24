import json

import numpy as np
import pandas as pd

import build_2pm_active_postmatch_inference as inference


FEATURES = [f"feature_{index:03d}" for index in range(286)]


def make_candidate():
    deadline = pd.Timestamp("2026-11-27T11:00:00Z")
    rows = []
    history = {
        "season": "2026-27",
        "gameweek": 11,
        "fixture": "100",
        "fpl_code": 1,
        "row_role": "HISTORICAL_FIXTURE",
        "kickoff_time": pd.Timestamp("2026-11-20T12:00:00Z"),
        "deadline_time": pd.Timestamp("2026-11-20T09:00:00Z"),
        "feature_cutoff_time": pd.Timestamp("2026-11-20T09:00:00Z"),
        "match_available_at": pd.Timestamp("2026-11-21T12:00:00Z"),
        "minutes": 90.0,
        "target_points": 6.0,
        "source_vintage_status": "ACTIVE_SEASON_HISTORY_VINTAGE_NOT_ARCHIVED_AT_ORIGINAL_DEADLINES",
        "team_name": "Team A",
        "opponent_team_name": "Team B",
    }
    history.update({feature: 1.0 for feature in FEATURES})
    rows.append(history)
    for fixture, kickoff in (
        ("201", "2026-11-28T15:00:00Z"),
        ("202", "2026-11-29T15:00:00Z"),
    ):
        target = {
            "season": "2026-27",
            "gameweek": 12,
            "fixture": fixture,
            "fpl_code": 1,
            "row_role": "TARGET_QUERY",
            "kickoff_time": pd.Timestamp(kickoff),
            "deadline_time": deadline,
            "feature_cutoff_time": deadline,
            "match_available_at": pd.NaT,
            "minutes": 0.0,
            "target_points": np.nan,
            "source_vintage_status": "CURRENT_TARGET_QUERY_FROM_PREDEADLINE_SNAPSHOT",
            "team_name": "Team A",
            "opponent_team_name": "Team B",
        }
        target.update({feature: 2.0 for feature in FEATURES})
        rows.append(target)
    return pd.DataFrame(rows)


def test_builds_postmatch_history_and_fixture_query_tensors_for_selected_gameweek(
    tmp_path, monkeypatch
):
    candidate = make_candidate()
    player_matches = pd.DataFrame({"season": ["2026-27"]})
    team_matches = pd.DataFrame({"season": ["2026-27"]})
    monkeypatch.setattr(
        inference, "load_schema", lambda _: (FEATURES, "feature-order-hash")
    )
    monkeypatch.setattr(
        inference,
        "load_dastan_package",
        lambda _: (None, None, object(), None, None),
    )
    monkeypatch.setattr(
        inference.pd,
        "read_parquet",
        lambda path: {
            "candidate.parquet": candidate.copy(),
            "player-matches.parquet": player_matches.copy(),
            "team-matches.parquet": team_matches.copy(),
        }[path.name],
    )

    observed = {}

    def fake_postmatch(candidate_frame, player_history, team_history, features_module, features):
        observed["candidate_rows"] = len(candidate_frame)
        observed["row_roles"] = candidate_frame["row_role"].tolist()
        return pd.DataFrame({"postmatch_state": [1]}), {
            "status": "POSTMATCH_STATE_VECTORS_RECONSTRUCTED"
        }

    def fake_tensor_builder(
        states_path, target_frame, schema_path, tensor_dir, report_path, **kwargs
    ):
        observed["target_fixtures"] = target_frame["fixture"].tolist()
        observed["states_path"] = states_path
        observed["kwargs"] = kwargs
        return {
            "status": "PLAYER_GAMEWEEK_SEQUENCE_TENSORS_BUILT",
            "counts": {"emitted": 1},
            "shards": [{"samples": 1}],
        }

    monkeypatch.setattr(inference, "build_postmatch_state_vectors", fake_postmatch)
    monkeypatch.setattr(
        inference, "build_player_gameweek_sequence_tensors", fake_tensor_builder
    )

    report = inference.build_active_postmatch_inference(
        tmp_path,
        tmp_path / "candidate.parquet",
        tmp_path / "player-matches.parquet",
        tmp_path / "team-matches.parquet",
        tmp_path / "schema.json",
        tmp_path / "out",
        tmp_path / "out" / "report.json",
        target_season="2026-27",
        target_gameweek=12,
    )

    assert observed["candidate_rows"] == 3
    assert observed["row_roles"] == [
        "HISTORICAL_FIXTURE", "TARGET_QUERY", "TARGET_QUERY"
    ]
    assert observed["target_fixtures"] == ["201", "202"]
    assert observed["kwargs"]["target_mode"] == "inference"
    assert observed["kwargs"]["target_gameweek"] == 12
    assert report["admission_status"] == "NOT_ADMITTED"
    assert report["training_authorized"] is False
    assert report["target_fixture_count"] == 2
    saved = json.loads((tmp_path / "out" / "report.json").read_text())
    assert saved["status"] == "ACTIVE_POSTMATCH_INFERENCE_TENSORS_BUILT"
