import json

import numpy as np
import pandas as pd
import pytest

from build_2pm_player_gameweek_sequence_tensors import (
    build_player_gameweek_sequence_tensors,
)

FEATURES = [f"feature_{index:03d}" for index in range(286)]


def make_history(season="2026-27"):
    rows = []
    kickoffs = pd.date_range("2026-08-01T12:00:00Z", periods=5, freq="2D")
    for index, kickoff in enumerate(kickoffs):
        available = kickoff + pd.Timedelta(hours=26)
        row = {
            "season": season,
            "gameweek": index + 1,
            "fixture": f"H{index}",
            "fpl_code": 123,
            "kickoff_time": kickoff,
            "match_available_at": available,
            "postmatch_state_as_of_time": available + pd.Timedelta(nanoseconds=1),
            "postmatch_state_semantics": "AFTER_MATCH_DATA_AVAILABLE_CONSERVATIVE",
            "minutes": 90,
        }
        row.update({feature: float(index + 1) for feature in FEATURES})
        rows.append(row)
    return pd.DataFrame(rows)


def make_targets(*, mode="historical", points=(3.0, -1.0), season="2026-27"):
    deadline = pd.Timestamp("2026-08-12T09:00:00Z")
    rows = []
    for index, (fixture, hour) in enumerate((("D1", 12), ("D2", 18))):
        kickoff = pd.Timestamp(f"2026-08-12T{hour:02d}:00:00Z")
        row = {
            "season": season,
            "gameweek": 6,
            "fixture": fixture,
            "fpl_code": 123,
            "kickoff_time": kickoff,
            "deadline_time": deadline,
            "feature_cutoff_time": deadline,
            "minutes": 90 if mode == "historical" else 0,
        }
        if mode == "inference":
            row.update({
                "row_role": "TARGET_QUERY",
                "target_points": np.nan,
            })
        else:
            row["total_points"] = points[index]
        row.update({feature: 88.0 + index for feature in FEATURES})
        rows.append(row)
    return pd.DataFrame(rows)


def write_inputs(tmp_path, history, targets):
    history_path = tmp_path / "postmatch.parquet"
    targets_path = tmp_path / "targets.parquet"
    schema_path = tmp_path / "schema.json"
    history.to_parquet(history_path, index=False)
    targets.to_parquet(targets_path, index=False)
    schema_path.write_text(json.dumps({
        "feature_count": 286,
        "feature_order": FEATURES,
    }))
    return history_path, targets_path, schema_path


def build(tmp_path, history, targets, **kwargs):
    history_path, targets_path, schema_path = write_inputs(tmp_path, history, targets)
    return build_player_gameweek_sequence_tensors(
        history_path,
        targets_path,
        schema_path,
        tmp_path / "tensors",
        tmp_path / "report.json",
        target_season=kwargs.pop("target_season", "2026-27"),
        target_gameweek=6,
        **kwargs,
    )


def test_double_gameweek_is_one_player_gameweek_sample_with_two_fixture_queries(tmp_path):
    report = build(
        tmp_path,
        make_history(),
        make_targets(points=(3.0, -1.0)),
        target_mode="historical",
        label_grain="player_fixture",
    )
    assert report["counts"]["emitted"] == 1
    assert report["sample_grain"] == "player_gameweek"
    assert report["tensor_shape_per_sample"] == [2, 6, 286]
    tensor = np.load(tmp_path / "tensors" / "X_player_gw_00000.npy")
    mask = np.load(tmp_path / "tensors" / "fixture_mask_00000.npy")
    labels = np.load(tmp_path / "tensors" / "y_player_gw_00000.npy")
    assert tensor.shape == (1, 2, 6, 286)
    assert mask.tolist() == [[1, 1]]
    assert tensor[0, 0, :5, 0].tolist() == [1, 2, 3, 4, 5]
    assert tensor[0, 1, :5, 0].tolist() == [1, 2, 3, 4, 5]
    assert tensor[0, 0, 5, 0] == 88.0
    assert tensor[0, 1, 5, 0] == 89.0
    # Negative fixture points are preserved; the GW label is their sum.
    assert labels.tolist() == [2.0]
    metadata = pd.read_csv(tmp_path / "tensors" / "metadata_player_gw_00000.csv")
    assert json.loads(metadata.loc[0, "fixture_target_points"]) == [3.0, -1.0]


def test_gameweek_grain_label_is_deduplicated_not_summed(tmp_path):
    targets = make_targets(points=(2.0, 2.0))
    report = build(
        tmp_path,
        make_history(),
        targets,
        target_mode="historical",
        label_grain="player_gameweek",
    )
    labels = np.load(tmp_path / "tensors" / "y_player_gw_00000.npy")
    assert labels.tolist() == [2.0]
    assert report["counts"]["emitted"] == 1


def test_gameweek_grain_rejects_conflicting_repeated_labels(tmp_path):
    with pytest.raises(ValueError, match="same GW total"):
        build(
            tmp_path,
            make_history(),
            make_targets(points=(2.0, 4.0)),
            target_mode="historical",
            label_grain="player_gameweek",
        )


def test_inference_emits_one_group_for_double_gameweek_without_labels(tmp_path):
    report = build(
        tmp_path,
        make_history(),
        make_targets(mode="inference"),
        target_mode="inference",
    )
    assert report["counts"]["emitted"] == 1
    assert report["label_grain"] is None
    assert report["shards"][0]["labels"] is None
    tensor = np.load(tmp_path / "tensors" / "X_player_gw_00000.npy")
    assert tensor.shape == (1, 2, 6, 286)


def test_previous_season_history_is_not_carried_into_current_season(tmp_path):
    report = build(
        tmp_path,
        make_history(season="2025-26"),
        make_targets(),
        target_mode="historical",
        label_grain="player_fixture",
    )
    assert report["counts"]["emitted"] == 0
    assert report["counts"]["insufficient_previous_played_matches"] == 1


def test_rejects_dgw_target_fixtures_with_different_deadlines(tmp_path):
    targets = make_targets()
    targets.loc[1, "deadline_time"] += pd.Timedelta(minutes=1)
    targets.loc[1, "feature_cutoff_time"] += pd.Timedelta(minutes=1)
    with pytest.raises(ValueError, match="share one official deadline"):
        build(
            tmp_path,
            make_history(),
            targets,
            target_mode="historical",
            label_grain="player_fixture",
        )



def test_nonappearance_target_fixture_is_retained_with_zero_points(tmp_path):
    targets = make_targets(points=(3.0, 0.0))
    targets.loc[1, "minutes"] = 0
    report = build(
        tmp_path,
        make_history(),
        targets,
        target_mode="historical",
        label_grain="player_fixture",
    )
    assert report["counts"]["emitted"] == 1
    metadata = pd.read_csv(
        tmp_path / "tensors" / "metadata_player_gw_00000.csv"
    )
    assert metadata.loc[0, "fixture_count"] == 2
    labels = np.load(tmp_path / "tensors" / "y_player_gw_00000.npy")
    assert labels.tolist() == [3.0]
