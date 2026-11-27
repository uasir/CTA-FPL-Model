import numpy as np
import pytest

from two_pm_fold_preprocessing import (
    apply_fold_median_imputer,
    fit_fold_median_imputer,
)


def test_fold_medians_use_training_partition_and_apply_without_validation_refit():
    train = np.array([[[1.0, 10.0]], [[3.0, 30.0]]])
    train_mask = np.ones_like(train, dtype=np.uint8)
    imputer = fit_fold_median_imputer(train, train_mask, ["a", "b"])
    assert imputer["medians"] == [2.0, 20.0]
    assert imputer["observed_counts"] == [2, 2]
    assert imputer["validation_or_test_values_used_for_fit"] is False

    validation = np.array([[[np.nan, 1000.0]]])
    validation_mask = np.array([[[0, 1]]], dtype=np.uint8)
    transformed = apply_fold_median_imputer(
        validation, validation_mask, imputer, ["a", "b"]
    )
    assert transformed.tolist() == [[[2.0, 1000.0]]]


def test_double_gameweek_shared_history_is_counted_once_but_each_query_is_kept():
    values = np.full((2, 2, 6, 2), np.nan, dtype=np.float64)
    observed = np.zeros_like(values, dtype=np.uint8)
    fixture_mask = np.array([[1, 1], [1, 0]], dtype=np.uint8)

    history_a = np.arange(1, 6, dtype=np.float64)
    history_b = np.arange(3, 8, dtype=np.float64)
    values[0, 0, :5, 0] = history_a
    values[0, 1, :5, 0] = history_a
    values[0, 0, 5, 0] = 9.0
    values[0, 1, 5, 0] = 11.0
    values[1, 0, :5, 0] = history_b
    values[1, 0, 5, 0] = 13.0

    values[..., 1] = values[..., 0] * 10.0
    observed[fixture_mask.astype(bool)] = 1
    imputer = fit_fold_median_imputer(
        values,
        observed,
        ["defensive_metric", "scaled_metric"],
        fixture_mask=fixture_mask,
        history_token_count=5,
    )
    assert imputer["shared_history_deduplicated"] is True
    assert imputer["observed_counts"] == [13, 13]
    assert imputer["medians"] == [5.0, 50.0]

    transformed = apply_fold_median_imputer(
        values, observed, imputer, ["defensive_metric", "scaled_metric"],
        fixture_mask=fixture_mask,
    )
    assert np.isfinite(transformed).all()
    assert np.all(transformed[1, 1] == 0.0)


def test_fold_imputer_neutralizes_feature_missing_from_training():
    values = np.array([[[1.0, np.nan]], [[3.0, np.nan]]])
    observed = np.array([[[1, 0]], [[1, 0]]], dtype=np.uint8)
    imputer = fit_fold_median_imputer(values, observed, ["available", "missing"])
    assert imputer["medians"] == [2.0, 0.0]
    assert imputer["observed_counts"] == [2, 0]
    assert imputer["zero_coverage_features"] == ["missing"]
    transformed = apply_fold_median_imputer(
        values, observed, imputer, ["available", "missing"]
    )
    assert transformed[..., 1].tolist() == [[0.0], [0.0]]


def test_fold_imputer_rejects_nonfinite_observed_values_and_invalid_masks():
    values = np.array([[[np.nan]]])
    with pytest.raises(ValueError, match="observed values must be finite"):
        fit_fold_median_imputer(values, np.ones_like(values), ["x"])
    with pytest.raises(ValueError, match="only 0/1"):
        fit_fold_median_imputer(np.array([[[1.0]]]), np.array([[[2]]]), ["x"])


def test_fold_imputer_requires_aligned_feature_order_and_fixture_mask():
    values = np.ones((1, 2, 6, 1), dtype=np.float64)
    observed = np.ones_like(values, dtype=np.uint8)
    with pytest.raises(ValueError, match="require fixture_mask"):
        fit_fold_median_imputer(values, observed, ["x"])
    imputer = fit_fold_median_imputer(
        values, observed, ["x"], fixture_mask=np.array([[1, 1]])
    )
    with pytest.raises(ValueError, match="feature order"):
        apply_fold_median_imputer(
            values, observed, imputer, ["other"], fixture_mask=np.array([[1, 1]])
        )
