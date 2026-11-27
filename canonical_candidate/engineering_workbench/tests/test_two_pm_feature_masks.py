import json
from pathlib import Path

import numpy as np
import pytest

from two_pm_feature_groups import load_feature_group_manifest
from two_pm_feature_masks import (
    AVAILABLE,
    UNAVAILABLE,
    UNKNOWN,
    build_feature_availability_state,
    build_feature_masks,
    build_observed_value_mask,
)


ROOT = Path(__file__).resolve().parents[1]


def load():
    schema, manifest, _ = load_feature_group_manifest(ROOT)
    return schema["feature_order"], manifest


def test_defensive_source_availability_is_explicit_and_unknown_is_not_available():
    features, manifest = load()
    defensive = set(manifest["feature_groups"]["defensive_regime_dependent"]["feature_order"])
    state_old = build_feature_availability_state("2024-25", features, manifest)
    state_new = build_feature_availability_state("2025-26", features, manifest)
    state_current_unverified = build_feature_availability_state("2026-27", features, manifest)
    for i, name in enumerate(features):
        if name in defensive:
            assert state_old[i] == UNAVAILABLE
            assert state_new[i] == AVAILABLE
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
    observed = build_observed_value_mask(values, features, manifest)
    assert observed[0, indices["ar_ep_next"]] == 0
    assert observed[0, indices["value"]] == 0
    assert observed[0, indices["player_fpl_points_1"]] == 1
    assert observed[0, indices["player_xg_1"]] == 0


def test_structurally_unavailable_numeric_fill_is_not_marked_observed():
    features, manifest = load()
    defensive = manifest["feature_groups"]["defensive_regime_dependent"]["feature_order"]
    values = np.zeros((2, len(features)), dtype=np.float32)
    state = build_feature_availability_state("2024-25", features, manifest)
    observed = build_observed_value_mask(values, features, manifest, state)
    index = {name: i for i, name in enumerate(features)}
    assert all(observed[:, index[name]].tolist() == [0, 0] for name in defensive)
    assert observed[0, index["player_fpl_points_1"]] == 1


def test_masks_are_aligned_and_encode_unknown_separately():
    features, manifest = load()
    defensive = manifest["feature_groups"]["defensive_regime_dependent"]["feature_order"]
    values = np.zeros((2, 6, len(features)), dtype=np.float32)
    values[0, 0, 0] = np.nan
    availability, observed = build_feature_masks(values, "2025-26", features, manifest)
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
        build_observed_value_mask(np.zeros((2, 5)), features, manifest)
