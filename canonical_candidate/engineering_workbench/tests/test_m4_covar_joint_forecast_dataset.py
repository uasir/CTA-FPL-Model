import pytest

from m4_covar_joint_forecast_dataset import (
    JointForecastDatasetError,
    validate_joint_forecast_dataset,
)


def rows():
    return [
        {"forecast_id": "tr-1", "gameweek_id": "gw1", "as_of_utc": "2025-08-01T10:00:00Z", "first_kickoff_utc": "2025-08-01T12:00:00Z", "training_cutoff_utc": "2025-07-31T23:00:00Z"},
        {"forecast_id": "va-1", "gameweek_id": "gw2", "as_of_utc": "2025-08-08T10:00:00Z", "first_kickoff_utc": "2025-08-08T12:00:00Z", "training_cutoff_utc": "2025-08-07T23:00:00Z"},
        {"forecast_id": "te-1", "gameweek_id": "gw3", "as_of_utc": "2025-08-15T10:00:00Z", "first_kickoff_utc": "2025-08-15T12:00:00Z", "training_cutoff_utc": "2025-08-14T23:00:00Z"},
    ]


def splits():
    return {"train": ["gw1"], "validation": ["gw2"], "test": ["gw3"]}


def test_validates_strict_chronological_gameweek_partitions():
    report = validate_joint_forecast_dataset(rows(), splits())
    assert report["validation_status"] == "CHRONOLOGICAL_SPLITS_VALIDATED"
    assert report["independence_unit"] == "GAMEWEEK_CLUSTER"
    assert report["repeated_forecasts_are_independent"] is False


def test_rejects_gameweek_leakage_between_splits():
    manifest = splits()
    manifest["test"].append("gw2")
    with pytest.raises(JointForecastDatasetError, match="more than one split"):
        validate_joint_forecast_dataset(rows(), manifest)


def test_rejects_non_chronological_split_order():
    manifest = {"train": ["gw2"], "validation": ["gw1"], "test": ["gw3"]}
    with pytest.raises(JointForecastDatasetError, match="chronologically"):
        validate_joint_forecast_dataset(rows(), manifest)


def test_rejects_forecast_after_first_kickoff():
    data = rows()
    data[1]["as_of_utc"] = "2025-08-08T12:01:00Z"
    with pytest.raises(JointForecastDatasetError, match="as-of must precede"):
        validate_joint_forecast_dataset(data, splits())


def test_rejects_future_training_cutoff():
    data = rows()
    data[2]["training_cutoff_utc"] = "2025-08-15T10:30:00Z"
    with pytest.raises(JointForecastDatasetError, match="training cutoff"):
        validate_joint_forecast_dataset(data, splits())


def test_rejects_missing_gameweek_forecast():
    with pytest.raises(JointForecastDatasetError, match="at least one forecast"):
        validate_joint_forecast_dataset(rows()[:2], splits())


def test_allows_multiple_forecasts_but_keeps_gameweek_as_cluster():
    data = rows()
    extra = dict(data[0], forecast_id="tr-2", as_of_utc="2025-08-01T11:00:00Z")
    report = validate_joint_forecast_dataset(data + [extra], splits())
    assert report["split_forecast_row_counts"]["train"] == 2
    assert report["repeated_forecasts_are_independent"] is False


def test_rejects_timezone_naive_timestamp():
    data = rows()
    data[0]["as_of_utc"] = "2025-08-01T10:00:00"
    with pytest.raises(JointForecastDatasetError, match="timezone"):
        validate_joint_forecast_dataset(data, splits())
