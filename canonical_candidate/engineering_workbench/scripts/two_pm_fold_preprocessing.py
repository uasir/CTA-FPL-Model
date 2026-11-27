"""Training-fold-only preprocessing for the independent 2PM Transformer."""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np


IMPUTER_VERSION = "1.0.0"


def _validate_values_and_mask(
    values: np.ndarray,
    observed_mask: np.ndarray,
    feature_order: Sequence[str],
) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(values, dtype=np.float64)
    observed = np.asarray(observed_mask)
    if x.ndim not in (3, 4) or x.shape[-1] != len(feature_order):
        raise ValueError("values must be [sample, sequence, feature] or [sample, fixture, sequence, feature]")
    if observed.shape != x.shape:
        raise ValueError("observed_mask must match values")
    if not np.isin(observed, [0, 1, False, True]).all():
        raise ValueError("observed_mask must contain only 0/1")
    if np.isinf(x).any():
        raise ValueError("values must not contain infinite entries")
    observed = observed.astype(bool)
    if not np.isfinite(x[observed]).all():
        raise ValueError("observed values must be finite")
    if len(feature_order) != len(set(feature_order)):
        raise ValueError("feature_order must contain unique names")
    if x.shape[0] == 0:
        raise ValueError("at least one training sample is required")
    return x, observed


def _fit_observation_mask(
    observed: np.ndarray,
    fixture_mask: np.ndarray | None,
    *,
    history_token_count: int,
) -> tuple[np.ndarray, bool]:
    if observed.ndim == 3:
        if fixture_mask is not None:
            raise ValueError("fixture_mask is only valid for four-dimensional grouped tensors")
        return observed.copy(), False

    if fixture_mask is None:
        raise ValueError("four-dimensional grouped tensors require fixture_mask")
    fixtures = np.asarray(fixture_mask)
    if fixtures.shape != observed.shape[:2]:
        raise ValueError("fixture_mask must match [sample, fixture]")
    if not np.isin(fixtures, [0, 1, False, True]).all():
        raise ValueError("fixture_mask must contain only 0/1")
    fixtures = fixtures.astype(bool)
    if not fixtures.any(axis=1).all():
        raise ValueError("every player-Gameweek sample must contain at least one fixture")
    if history_token_count < 0 or history_token_count >= observed.shape[2]:
        raise ValueError("history_token_count must leave at least one target query token")

    selected = observed & fixtures[..., None, None]
    # Each target fixture repeats the same five player-history states. Include
    # those shared states once per player-Gameweek; retain every fixture query.
    for sample_index in range(selected.shape[0]):
        valid_fixtures = np.flatnonzero(fixtures[sample_index])
        for fixture_index in valid_fixtures[1:]:
            selected[sample_index, fixture_index, :history_token_count, :] = False
    return selected, True


def fit_fold_median_imputer(
    training_values: np.ndarray,
    training_observed_mask: np.ndarray,
    feature_order: Sequence[str],
    *,
    fixture_mask: np.ndarray | None = None,
    history_token_count: int = 5,
) -> dict[str, Any]:
    """Fit medians on training data only, deduplicating shared DGW histories."""
    x, observed = _validate_values_and_mask(
        training_values, training_observed_mask, feature_order
    )
    selected, deduplicated = _fit_observation_mask(
        observed, fixture_mask, history_token_count=history_token_count
    )
    medians: list[float] = []
    counts: list[int] = []
    missing_features: list[str] = []
    for index, name in enumerate(feature_order):
        values = x[..., index][selected[..., index]]
        counts.append(int(values.size))
        if values.size == 0:
            missing_features.append(str(name))
            medians.append(float("nan"))
        else:
            medians.append(float(np.median(values)))
    if missing_features:
        raise ValueError(
            "training fold has no observed values for features: "
            + ", ".join(missing_features[:20])
        )
    return {
        "imputer_version": IMPUTER_VERSION,
        "method": "training_fold_feature_median",
        "feature_order": [str(name) for name in feature_order],
        "feature_count": len(feature_order),
        "medians": medians,
        "observed_counts": counts,
        "training_sample_count": int(x.shape[0]),
        "shared_history_deduplicated": deduplicated,
        "history_token_count": int(history_token_count) if deduplicated else None,
        "validation_or_test_values_used_for_fit": False,
    }


def apply_fold_median_imputer(
    values: np.ndarray,
    observed_mask: np.ndarray,
    imputer: dict[str, Any],
    feature_order: Sequence[str],
    *,
    fixture_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Apply frozen training-fold medians; never refit on validation/test data."""
    x, observed = _validate_values_and_mask(values, observed_mask, feature_order)
    if imputer.get("imputer_version") != IMPUTER_VERSION:
        raise ValueError("unsupported fold imputer version")
    if imputer.get("feature_order") != [str(name) for name in feature_order]:
        raise ValueError("imputer feature order does not match tensor feature order")
    medians = np.asarray(imputer.get("medians", []), dtype=np.float64)
    if medians.shape != (len(feature_order),) or not np.isfinite(medians).all():
        raise ValueError("imputer medians are missing or invalid")

    result = x.astype(np.float32, copy=True)
    for index, median in enumerate(medians):
        feature_values = result[..., index]
        feature_observed = observed[..., index]
        feature_values[~feature_observed] = np.float32(median)

    if result.ndim == 4:
        if fixture_mask is None:
            raise ValueError("four-dimensional grouped tensors require fixture_mask")
        fixtures = np.asarray(fixture_mask)
        if fixtures.shape != result.shape[:2] or not np.isin(fixtures, [0, 1, False, True]).all():
            raise ValueError("fixture_mask must be binary and match [sample, fixture]")
        result[~fixtures.astype(bool)] = 0.0
    elif fixture_mask is not None:
        raise ValueError("fixture_mask is only valid for four-dimensional grouped tensors")
    if not np.isfinite(result).all():
        raise ValueError("fold imputation did not produce a finite model input")
    return result
