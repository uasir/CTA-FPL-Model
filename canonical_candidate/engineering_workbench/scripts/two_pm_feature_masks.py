"""Provenance-aware structural-availability and observed-value masks for 2PM."""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np

UNAVAILABLE = np.uint8(0)
AVAILABLE = np.uint8(1)
UNKNOWN = np.uint8(2)


def build_feature_availability_state(
    season: str,
    feature_order: Sequence[str],
    manifest: dict[str, Any],
) -> np.ndarray:
    """Return one 0/1/2 source-availability state per feature.

    0 = source structurally unavailable in the pinned vintage.
    1 = source availability verified for the pinned vintage.
    2 = unresolved; never interpret as verified available.
    """
    state_codes = manifest.get("feature_source_availability", {}).get("state_codes", {})
    expected_codes = {"UNAVAILABLE": 0, "AVAILABLE": 1, "UNKNOWN": 2}
    if state_codes != expected_codes:
        raise ValueError(f"Unexpected feature availability state codes: {state_codes}")
    policy = manifest["feature_source_availability"]
    default_name = policy.get("default_state")
    if default_name not in expected_codes:
        raise ValueError(f"Unknown default feature availability state: {default_name}")
    states = np.full(len(feature_order), expected_codes[default_name], dtype=np.uint8)
    index = {name: i for i, name in enumerate(feature_order)}
    if len(index) != len(feature_order):
        raise ValueError("Feature order contains duplicate names")
    for group_name, season_policy in policy.get("groups", {}).items():
        group = manifest.get("feature_groups", {}).get(group_name)
        if group is None:
            raise ValueError(f"Availability policy references unknown group: {group_name}")
        state_name = season_policy.get(str(season), default_name)
        if state_name not in expected_codes:
            raise ValueError(
                f"Unknown availability state {state_name!r} for {group_name}/{season}"
            )
        state_value = expected_codes[state_name]
        for feature in group.get("feature_order", []):
            if feature not in index:
                raise ValueError(f"Availability policy feature is outside schema: {feature}")
            states[index[feature]] = state_value
    return states


def build_observed_value_mask(
    values: np.ndarray,
    feature_order: Sequence[str],
    manifest: dict[str, Any],
    availability_state: np.ndarray | None = None,
) -> np.ndarray:
    """Mark actual finite, non-sentinel observations, excluding structural absence."""
    array = np.asarray(values)
    if array.ndim < 1 or array.shape[-1] != len(feature_order):
        raise ValueError("Feature values' final axis must match feature_order")
    observed = np.isfinite(array)
    sentinel_features = set(
        manifest.get("snapshot_missing_sentinel_features", [])
    )
    unknown_sentinels = sentinel_features - set(feature_order)
    if unknown_sentinels:
        raise ValueError(f"Missing-snapshot sentinel features outside schema: {sorted(unknown_sentinels)}")
    if sentinel_features:
        sentinel_indices = [i for i, name in enumerate(feature_order) if name in sentinel_features]
        observed[..., sentinel_indices] &= array[..., sentinel_indices] != -1.0
    if availability_state is not None:
        state = np.asarray(availability_state, dtype=np.uint8)
        if state.shape == (len(feature_order),):
            state = np.broadcast_to(state, array.shape)
        elif state.shape != array.shape:
            raise ValueError("availability_state must match values or contain one state per feature")
        observed &= state != UNAVAILABLE
    return observed.astype(np.uint8)


def build_feature_masks(
    values: np.ndarray,
    season: str,
    feature_order: Sequence[str],
    manifest: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    """Build aligned source-availability-state and observed-value masks."""
    state_vector = build_feature_availability_state(season, feature_order, manifest)
    state = np.broadcast_to(state_vector, np.asarray(values).shape).copy()
    observed = build_observed_value_mask(values, feature_order, manifest, state)
    return state, observed
