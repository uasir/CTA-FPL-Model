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
    manifest_path = tmp_path / "feature_group_manifest.json"
    manifest_path.write_text(json.dumps({
        "feature_source_availability": {"state_codes": {"UNAVAILABLE": 0, "AVAILABLE": 1, "UNKNOWN": 2}, "default_state": "UNKNOWN", "groups": {"defensive_regime_dependent": {"2024-25": "UNAVAILABLE"}}},
        "snapshot_missing_sentinel_features": [],
        "feature_groups": {"defensive_regime_dependent": {"feature_order": ["feature_000"]}},
    }))
    return history_path, targets_path, schema_path, manifest_path


def build(tmp_path, history, targets, **kwargs):
    history_path, targets_path, schema_path, manifest_path = write_inputs(tmp_path, history, targets)
    return build_player_gameweek_sequence_tensors(
        history_path,
        targets_path,
        schema_path,
        tmp_path / "tensors",
        tmp_path / "report.json",
        target_season=kwargs.pop("target_season", "2026-27"),
        target_gameweek=6,
        feature_group_manifest_path=manifest_path,
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
    availability = np.load(tmp_path / "tensors" / "source_availability_state_00000.npy")
    observed = np.load(tmp_path / "tensors" / "observed_value_mask_00000.npy")
    assert tensor.shape == (1, 2, 6, 286)
    assert mask.tolist() == [[1, 1]]
    assert availability.shape == tensor.shape
    assert observed.shape == tensor.shape
    assert np.all(availability == 2)
    assert np.all(observed == 1)
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



def test_rejects_target_source_capture_at_deadline(tmp_path):
    targets = make_targets()
    targets["source_as_of_time"] = targets["deadline_time"]
    with pytest.raises(ValueError, match="captured at/after its deadline"):
        build(
            tmp_path,
            make_history(),
            targets,
            target_mode="historical",
            label_grain="player_fixture",
        )



def test_pinned_dastan_metadata_selects_fixture_grain_and_sums_once(tmp_path):
    targets = make_targets(points=(4.0, 2.0))
    targets["target_label_grain"] = "player_fixture"
    targets["target_points_semantics"] = "FPL_POINTS_SCORED_IN_THIS_FIXTURE"
    report = build(
        tmp_path,
        make_history(),
        targets,
        target_mode="historical",
        label_grain=None,
    )
    assert report["label_grain"] == "player_fixture"
    labels = np.load(tmp_path / "tensors" / "y_player_gw_00000.npy")
    assert labels.tolist() == [6.0]


def test_explicit_label_grain_cannot_override_pinned_dastan_metadata(tmp_path):
    targets = make_targets(points=(4.0, 2.0))
    targets["target_label_grain"] = "player_fixture"
    targets["target_points_semantics"] = "FPL_POINTS_SCORED_IN_THIS_FIXTURE"
    with pytest.raises(ValueError, match="conflicts with target frame"):
        build(
            tmp_path,
            make_history(),
            targets,
            target_mode="historical",
            label_grain="player_gameweek",
        )



def test_fixture_grain_auto_detection_requires_complete_semantics_metadata(tmp_path):
    targets = make_targets()
    targets["target_label_grain"] = "player_fixture"
    with pytest.raises(ValueError, match="explicit label_grain"):
        build(
            tmp_path,
            make_history(),
            targets,
            target_mode="historical",
            label_grain=None,
        )



def test_rejects_missing_source_as_of_timestamp_when_column_is_present(tmp_path):
    targets = make_targets()
    targets["source_as_of_time"] = pd.NaT
    with pytest.raises(ValueError, match="missing or invalid capture timestamps"):
        build(
            tmp_path,
            make_history(),
            targets,
            target_mode="historical",
            label_grain="player_fixture",
        )


def test_rejects_real_market_values_without_snapshot_provenance(tmp_path):
    targets = make_targets()
    targets["value"] = 55.0
    targets["selected"] = 12.5
    targets["transfers_balance"] = 100
    targets["market_snapshot_at"] = pd.NaT
    with pytest.raises(ValueError, match="feature values are not all -1 sentinels"):
        build(
            tmp_path,
            make_history(),
            targets,
            target_mode="historical",
            label_grain="player_fixture",
        )


def test_accepts_missing_market_snapshot_only_with_missing_sentinels(tmp_path):
    targets = make_targets()
    targets["value"] = -1.0
    targets["selected"] = -1.0
    targets["transfers_balance"] = -1.0
    targets["market_snapshot_at"] = pd.NaT
    report = build(
        tmp_path,
        make_history(),
        targets,
        target_mode="historical",
        label_grain="player_fixture",
    )
    assert report["counts"]["emitted"] == 1


def test_accepts_snapshot_exactly_five_minutes_before_deadline(tmp_path):
    targets = make_targets()
    targets["market_snapshot_at"] = targets["deadline_time"] - pd.Timedelta(minutes=5)
    targets["value"] = 55.0
    targets["selected"] = 12.5
    targets["transfers_balance"] = 100
    report = build(
        tmp_path,
        make_history(),
        targets,
        target_mode="historical",
        label_grain="player_fixture",
    )
    assert report["counts"]["emitted"] == 1


def test_tensor_builder_emits_structural_absence_separately_from_numeric_zero(tmp_path):
    report = build(
        tmp_path,
        make_history(season="2024-25"),
        make_targets(season="2024-25"),
        target_season="2024-25",
        target_mode="historical",
        label_grain="player_fixture",
    )
    assert report["counts"]["emitted"] == 1
    tensor = np.load(tmp_path / "tensors" / "X_player_gw_00000.npy")
    availability = np.load(tmp_path / "tensors" / "source_availability_state_00000.npy")
    observed = np.load(tmp_path / "tensors" / "observed_value_mask_00000.npy")
    # The fixture contains finite numeric values, but the pinned source policy
    # says this feature was structurally unavailable in 2024/25.
    assert np.isfinite(tensor[..., 0]).all()
    assert np.all(availability[..., 0] == 0)
    assert np.all(observed[..., 0] == 0)
    assert np.all(availability[..., 1:] == 2)


def test_sequence_tensor_uses_raw_source_observation_sidecars(tmp_path):
    history = make_history()
    targets = make_targets(points=(3.0, 4.0))
    for feature in FEATURES:
        history[f"__observed__{feature}"] = 1
        targets[f"__observed__{feature}"] = 1
    # Finite values were produced from missing raw source data for this feature.
    history["__observed__feature_000"] = 0

    history_path, targets_path, schema_path, manifest_path = write_inputs(
        tmp_path, history, targets
    )
    manifest = json.loads(manifest_path.read_text())
    manifest["require_source_observed_sidecars"] = True
    manifest_path.write_text(json.dumps(manifest))

    report = build_player_gameweek_sequence_tensors(
        history_path,
        targets_path,
        schema_path,
        tmp_path / "tensors",
        tmp_path / "report.json",
        target_season="2026-27",
        target_gameweek=6,
        target_mode="historical",
        label_grain="player_fixture",
        feature_group_manifest_path=manifest_path,
    )
    assert report["counts"]["emitted"] == 1
    observed = np.load(tmp_path / "tensors" / "observed_value_mask_00000.npy")
    assert observed.shape == (1, 2, 6, 286)
    assert np.all(observed[0, :, :5, 0] == 0)
    assert np.all(observed[0, :, 5, 0] == 1)


def test_production_sequence_builder_rejects_missing_raw_source_sidecars(tmp_path):
    history_path, targets_path, schema_path, manifest_path = write_inputs(
        tmp_path, make_history(), make_targets()
    )
    manifest = json.loads(manifest_path.read_text())
    manifest["require_source_observed_sidecars"] = True
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="requires pre-fill observation sidecars"):
        build_player_gameweek_sequence_tensors(
            history_path,
            targets_path,
            schema_path,
            tmp_path / "tensors",
            tmp_path / "report.json",
            target_season="2026-27",
            target_gameweek=6,
            target_mode="historical",
            label_grain="player_fixture",
            feature_group_manifest_path=manifest_path,
        )
