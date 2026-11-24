import json

import numpy as np
import pandas as pd

from build_2pm_target_query_tensors import build_target_query_tensors


FEATURES = [f"feature_{index:03d}" for index in range(286)]


def make_history_rows():
    rows = []
    kickoffs = pd.date_range("2026-07-01T12:00:00Z", periods=5, freq="7D")
    for index, kickoff in enumerate(kickoffs):
        deadline = kickoff - pd.Timedelta(hours=3)
        rows.append({
            "season": "2025-26",
            "gameweek": 30 + index,
            "fixture": 600 + index,
            "fpl_code": 12345,
            "kickoff_time": kickoff,
            "match_available_at": kickoff + pd.Timedelta(hours=24),
            "deadline_time": deadline,
            "feature_cutoff_time": deadline,
            "minutes": 90,
            "completion_time_quality": "CONSERVATIVE_24H_UPPER_BOUND",
            "source_vintage_status": "RETROSPECTIVE_SOURCE_VINTAGE_NOT_VERIFIED",
            "target_points": index + 1,
            **{feature: float(index + 1) for feature in FEATURES},
        })
    return pd.DataFrame(rows)


def make_target_row():
    kickoff = pd.Timestamp("2026-08-05T12:00:00Z")
    deadline = kickoff - pd.Timedelta(hours=3)
    return pd.DataFrame([{
        "season": "2026-27",
        "gameweek": 12,
        "fixture": 9001,
        "fpl_code": 12345,
        "kickoff_time": kickoff,
        "match_available_at": pd.NaT,
        "deadline_time": deadline,
        "feature_cutoff_time": deadline,
        "minutes": 0,
        "completion_time_quality": "NOT_FINISHED",
        "source_vintage_status": "CURRENT_TARGET_QUERY_FROM_PREDEADLINE_SNAPSHOT",
        "target_points": np.nan,
        "row_role": "TARGET_QUERY",
        **{feature: 88.0 for feature in FEATURES},
    }])


def test_builds_only_target_query_tensors_using_historical_context(tmp_path):
    history_path = tmp_path / "historical.parquet"
    active_path = tmp_path / "active.parquet"
    schema_path = tmp_path / "schema.json"
    tensor_dir = tmp_path / "target-tensors"
    report_path = tmp_path / "report.json"
    make_history_rows().to_parquet(history_path, index=False)
    make_target_row().to_parquet(active_path, index=False)
    schema_path.write_text(json.dumps({
        "feature_count": 286,
        "feature_order": FEATURES,
    }))

    report = build_target_query_tensors(
        history_path,
        active_path,
        schema_path,
        tensor_dir,
        report_path,
        target_season="2026-27",
        target_gameweek=12,
    )
    assert report["counts"]["emitted"] == 1
    tensor = np.load(tensor_dir / "X_target_00000.npy")
    assert tensor.shape == (1, 6, 286)
    assert tensor[0, :5, 0].tolist() == [1, 2, 3, 4, 5]
    assert tensor[0, 5, 0] == 88.0
    metadata = pd.read_csv(tensor_dir / "metadata_target_00000.csv")
    assert metadata.loc[0, "fixture_id"] == 9001
    assert metadata.loc[0, "target_points"] != metadata.loc[0, "target_points"]
    assert report_path.exists()


def test_excludes_target_without_five_prior_played_matches(tmp_path):
    history_path = tmp_path / "historical.parquet"
    active_path = tmp_path / "active.parquet"
    schema_path = tmp_path / "schema.json"
    make_history_rows().iloc[:4].to_parquet(history_path, index=False)
    make_target_row().to_parquet(active_path, index=False)
    schema_path.write_text(json.dumps({
        "feature_count": 286,
        "feature_order": FEATURES,
    }))
    report = build_target_query_tensors(
        history_path,
        active_path,
        schema_path,
        tmp_path / "tensors",
        tmp_path / "report.json",
        target_season="2026-27",
        target_gameweek=12,
    )
    assert report["counts"]["emitted"] == 0
    assert report["counts"]["insufficient_previous_played_matches"] == 1



def test_rejects_target_query_with_realized_points(tmp_path):
    history_path = tmp_path / "historical.parquet"
    active_path = tmp_path / "active.parquet"
    schema_path = tmp_path / "schema.json"
    make_history_rows().to_parquet(history_path, index=False)
    target = make_target_row()
    target.loc[0, "target_points"] = 6.0
    target.to_parquet(active_path, index=False)
    schema_path.write_text(json.dumps({
        "feature_count": 286,
        "feature_order": FEATURES,
    }))
    import pytest
    with pytest.raises(ValueError, match="must not contain realized target points"):
        build_target_query_tensors(
            history_path,
            active_path,
            schema_path,
            tmp_path / "tensors",
            tmp_path / "report.json",
            target_season="2026-27",
            target_gameweek=12,
        )


def test_rejects_target_snapshot_inside_five_minute_buffer(tmp_path):
    history_path = tmp_path / "historical.parquet"
    active_path = tmp_path / "active.parquet"
    schema_path = tmp_path / "schema.json"
    make_history_rows().to_parquet(history_path, index=False)
    target = make_target_row()
    target["market_snapshot_at"] = pd.Timestamp("2026-08-05T08:59:00Z")
    target.to_parquet(active_path, index=False)
    schema_path.write_text(json.dumps({
        "feature_count": 286,
        "feature_order": FEATURES,
    }))
    import pytest
    with pytest.raises(ValueError, match="five-minute deadline safety buffer"):
        build_target_query_tensors(
            history_path,
            active_path,
            schema_path,
            tmp_path / "tensors",
            tmp_path / "report.json",
            target_season="2026-27",
            target_gameweek=12,
        )
