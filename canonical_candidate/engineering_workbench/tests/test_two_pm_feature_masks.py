import json
from pathlib import Path

import numpy as np
import pytest

from two_pm_feature_groups import load_feature_group_manifest
from two_pm_feature_masks import (
    AVAILABLE,
    UNAVAILABLE,
    UNKNOWN,
    apply_manifest_feature_policies,
    build_feature_availability_state,
    build_feature_masks,
    build_observed_value_mask,
    build_scoring_regime_code,
)


ROOT = Path(__file__).resolve().parents[1]


def load():
    schema, manifest, _ = load_feature_group_manifest(ROOT)
    return schema["feature_order"], manifest


def test_defensive_source_availability_is_explicit_and_unknown_is_not_available():
    features, manifest = load()
    defensive = set(manifest["feature_groups"]["defensive_regime_dependent"]["feature_order"])
    understat_player = set(
        manifest["source_availability_groups"]["understat_player_history"]["feature_order"]
    )
    state_old = build_feature_availability_state("2024-25", features, manifest)
    state_new = build_feature_availability_state("2025-26", features, manifest)
    state_current_unverified = build_feature_availability_state("2026-27", features, manifest)
    for i, name in enumerate(features):
        if name in defensive:
            assert state_old[i] == UNAVAILABLE
            assert state_new[i] == AVAILABLE
            assert state_current_unverified[i] == UNKNOWN
        elif name in understat_player:
            assert state_old[i] == UNKNOWN
            assert state_new[i] == UNKNOWN
            assert state_current_unverified[i] == UNKNOWN
        else:
            assert state_old[i] == UNKNOWN
            assert state_new[i] == UNKNOWN


def test_observed_mask_distinguishes_zero_nan_and_snapshot_missing_sentinel():
    features, manifest = load()
    values = np.zeros((1, len(features)), dtype=np.float32)
    indices = {name: i for i, name in enumerate(features)}
    values[0, indices["ar_ep_next"]] = -1.0
    values[0, indices["value"]] = -1.0
    values[0, indices["player_fpl_points_1"]] = 0.0
    values[0, indices["player_xg_1"]] = np.nan
    source_mask = np.ones_like(values, dtype=np.uint8)
    observed = build_observed_value_mask(values, features, manifest, source_observed_mask=source_mask)
    assert observed[0, indices["ar_ep_next"]] == 0
    assert observed[0, indices["value"]] == 0
    assert observed[0, indices["player_fpl_points_1"]] == 1
    assert observed[0, indices["player_xg_1"]] == 0


def test_structurally_unavailable_numeric_fill_is_not_marked_observed():
    features, manifest = load()
    defensive = manifest["feature_groups"]["defensive_regime_dependent"]["feature_order"]
    values = np.zeros((2, len(features)), dtype=np.float32)
    state = build_feature_availability_state("2024-25", features, manifest)
    source_mask = np.ones_like(values, dtype=np.uint8)
    observed = build_observed_value_mask(values, features, manifest, state, source_mask)
    index = {name: i for i, name in enumerate(features)}
    assert all(observed[:, index[name]].tolist() == [0, 0] for name in defensive)
    assert observed[0, index["player_fpl_points_1"]] == 1


def test_masks_are_aligned_and_encode_unknown_separately():
    features, manifest = load()
    defensive = manifest["feature_groups"]["defensive_regime_dependent"]["feature_order"]
    values = np.zeros((2, 6, len(features)), dtype=np.float32)
    values[0, 0, 0] = np.nan
    source_mask = np.ones_like(values, dtype=np.uint8)
    availability, observed = build_feature_masks(values, "2025-26", features, manifest, source_mask)
    assert availability.shape == values.shape
    assert observed.shape == values.shape
    assert availability.dtype == np.uint8
    assert observed.dtype == np.uint8
    index = {name: i for i, name in enumerate(features)}
    assert availability[0, 0, index[defensive[0]]] == AVAILABLE
    assert availability[0, 0, index["player_fpl_points_1"]] == UNKNOWN
    assert observed[0, 0, 0] == 0
    assert np.isin(availability, [UNAVAILABLE, AVAILABLE, UNKNOWN]).all()


def test_mask_rejects_mismatched_feature_axis():
    features, manifest = load()
    with pytest.raises(ValueError, match="final axis"):
        build_observed_value_mask(np.zeros((2, 5)), features, manifest, source_observed_mask=np.zeros((2, 5)))


def test_production_manifest_requires_pre_fill_source_observation_sidecar():
    features, manifest = load()
    values = np.zeros((1, len(features)), dtype=np.float32)
    with pytest.raises(ValueError, match="requires raw-source observation sidecars"):
        build_observed_value_mask(values, features, manifest)


def test_source_observation_sidecar_can_mask_upstream_zero_fills():
    features, manifest = load()
    values = np.zeros((1, len(features)), dtype=np.float32)
    source_mask = np.ones_like(values, dtype=np.uint8)
    index = {name: i for i, name in enumerate(features)}
    # The value is finite zero, but the raw source field was missing before Dastan zero-filled it.
    source_mask[0, index["player_xg_1"]] = 0
    observed = build_observed_value_mask(
        values, features, manifest, source_observed_mask=source_mask
    )
    assert observed[0, index["player_xg_1"]] == 0
    assert observed[0, index["player_fpl_points_1"]] == 1


def test_understat_features_are_forced_unobserved_until_vintage_audit_passes():
    features, manifest = load()
    values = np.zeros((2, len(features)), dtype=np.float32)
    source_mask = np.ones_like(values, dtype=np.uint8)
    observed = build_observed_value_mask(
        values, features, manifest, source_observed_mask=source_mask
    )
    understat = manifest["source_vintage_policies"]["understat"]["feature_order"]
    index = {name: i for i, name in enumerate(features)}
    assert all(observed[:, index[name]].tolist() == [0, 0] for name in understat)
    # Understat source-vintage HOLD also covers the previously omitted player
    # xGChain/xGBuildup and team goals/rank context features.
    newly_held = (
        "player_xgbuildup_1", "player_xgchain_1",
        "team_goals_scored_1", "team_league_rank_1",
        "opp_goals_conceded_1", "opp_league_rank_1",
        "status_league_rank", "opp_status_league_rank",
    )
    assert all(observed[:, index[name]].tolist() == [0, 0] for name in newly_held)
    assert observed[:, index["player_fpl_points_1"]].tolist() == [1, 1]


def test_verified_understat_policy_requires_row_level_vintage_mask():
    features, manifest = load()
    broken = json.loads(json.dumps(manifest))
    broken["source_vintage_policies"]["understat"]["status"] = "VERIFIED"
    broken["source_vintage_policies"]["understat"]["mask_action"] = "APPLY_ROW_LEVEL_MASK"
    values = np.zeros((1, len(features)), dtype=np.float32)
    source_mask = np.ones_like(values, dtype=np.uint8)
    with pytest.raises(ValueError, match="requires a row-level vintage mask"):
        build_observed_value_mask(
            values, features, broken, source_observed_mask=source_mask
        )


def test_2020_21_understat_player_history_is_unavailable_but_team_context_is_unknown():
    features, manifest = load()
    index = {name: i for i, name in enumerate(features)}
    state = build_feature_availability_state("2020-21", features, manifest)
    assert state[index["player_xg_1"]] == UNAVAILABLE
    assert state[index["player_xgbuildup_1"]] == UNAVAILABLE
    assert state[index["player_xgchain_1"]] == UNAVAILABLE
    assert state[index["team_xg_1"]] == UNKNOWN
    assert state[index["team_goals_scored_1"]] == UNKNOWN
    assert state[index["team_league_rank_1"]] == UNKNOWN
    assert state[index["status_league_rank"]] == UNKNOWN
    next_season = build_feature_availability_state("2021-22", features, manifest)
    assert next_season[index["player_xg_1"]] == UNKNOWN


def test_manifest_mask_reconciliation_overrides_stale_understat_tensor_masks():
    features, manifest = load()
    observed = np.ones((1, len(features)), dtype=np.uint8)
    availability = np.full((1, len(features)), UNKNOWN, dtype=np.uint8)

    observed, availability = apply_manifest_feature_policies(
        observed, availability, "2020-21", features, manifest
    )
    index = {name: i for i, name in enumerate(features)}

    # The expanded HOLD wins over stale finite/observed values, while the
    # current manifest also restores the known 2020/21 player-source absence.
    assert observed[0, index["player_xgbuildup_1"]] == 0
    assert availability[0, index["player_xgbuildup_1"]] == UNAVAILABLE
    assert observed[0, index["team_goals_scored_1"]] == 0
    assert availability[0, index["team_goals_scored_1"]] == UNKNOWN
    assert observed[0, index["status_league_rank"]] == 0
    assert observed[0, index["player_fpl_points_1"]] == 1
    assert availability[0, index["player_fpl_points_1"]] == UNKNOWN


def test_manifest_mask_reconciliation_fails_closed_on_unimplemented_vintage_action():
    features, manifest = load()
    broken = json.loads(json.dumps(manifest))
    broken["source_vintage_policies"]["understat"]["status"] = "VERIFIED"
    broken["source_vintage_policies"]["understat"]["mask_action"] = "APPLY_ROW_LEVEL_MASK"
    observed = np.ones((1, len(features)), dtype=np.uint8)
    availability = np.full((1, len(features)), UNKNOWN, dtype=np.uint8)

    with pytest.raises(ValueError, match="Unsupported source-vintage policy"):
        apply_manifest_feature_policies(
            observed, availability, "2024-25", features, broken
        )


def test_scoring_regime_code_is_season_specific_and_fail_closed():
    _, manifest = load()
    assert build_scoring_regime_code("2024-25", manifest) == 0
    assert build_scoring_regime_code("2025-26", manifest) == 1
    assert build_scoring_regime_code("2026-27", manifest) == 1
    with pytest.raises(ValueError, match="exactly one"):
        build_scoring_regime_code("2027-28", manifest)
