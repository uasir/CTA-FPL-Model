"""Validate chronological train/validation/test partitions for joint FPL forecasts.

This is a dataset contract only. It does not fit a model or establish forecast skill.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence


class JointForecastDatasetError(ValueError):
    """Invalid or temporally contaminated historical forecast dataset."""


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise JointForecastDatasetError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise JointForecastDatasetError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise JointForecastDatasetError(f"{field} must include a timezone")
    return parsed


def validate_joint_forecast_dataset(
    forecasts: Sequence[Mapping[str, Any]],
    split_gameweeks: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """Validate a chronological split manifest and point-in-time forecast rows.

    split_gameweeks must contain non-empty train, validation and test lists.
    Gameweeks, not player rows or individual forecast rows, are the partition
    unit. Multiple forecast snapshots for a Gameweek are allowed but remain
    clustered observations and must not be treated as independent samples.
    """
    required = ("train", "validation", "test")
    if not isinstance(split_gameweeks, Mapping) or set(split_gameweeks) != set(required):
        raise JointForecastDatasetError("split manifest must contain exactly train, validation and test")
    normalized = {}
    owner = {}
    for split in required:
        values = split_gameweeks[split]
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or not values:
            raise JointForecastDatasetError(f"{split} Gameweek list must be non-empty")
        ids = [str(value).strip() for value in values]
        if any(not value for value in ids) or len(ids) != len(set(ids)):
            raise JointForecastDatasetError(f"{split} Gameweek IDs must be non-empty and unique")
        normalized[split] = ids
        for gameweek_id in ids:
            if gameweek_id in owner:
                raise JointForecastDatasetError("a Gameweek cannot appear in more than one split")
            owner[gameweek_id] = split

    if not isinstance(forecasts, Sequence) or isinstance(forecasts, (str, bytes)) or not forecasts:
        raise JointForecastDatasetError("forecasts must be a non-empty sequence")

    seen_forecasts = set()
    kickoff_by_gw = {}
    counts = {split: 0 for split in required}
    for row in forecasts:
        if not isinstance(row, Mapping):
            raise JointForecastDatasetError("each forecast must be an object")
        forecast_id = str(row.get("forecast_id", "")).strip()
        gameweek_id = str(row.get("gameweek_id", "")).strip()
        if not forecast_id or forecast_id in seen_forecasts:
            raise JointForecastDatasetError("forecast IDs must be non-empty and unique")
        seen_forecasts.add(forecast_id)
        if gameweek_id not in owner:
            raise JointForecastDatasetError("every forecast Gameweek must belong to exactly one declared split")
        as_of = _time(row.get("as_of_utc"), "as_of_utc")
        kickoff = _time(row.get("first_kickoff_utc"), "first_kickoff_utc")
        cutoff = _time(row.get("training_cutoff_utc"), "training_cutoff_utc")
        if not cutoff <= as_of < kickoff:
            raise JointForecastDatasetError("training cutoff must not follow forecast as-of, and as-of must precede first kickoff")
        prior = kickoff_by_gw.get(gameweek_id)
        if prior is not None and prior != kickoff:
            raise JointForecastDatasetError("all forecasts for one Gameweek must share its first kickoff timestamp")
        kickoff_by_gw[gameweek_id] = kickoff
        counts[owner[gameweek_id]] += 1

    if set(kickoff_by_gw) != set(owner):
        raise JointForecastDatasetError("every declared Gameweek must have at least one forecast row")

    split_max = {}
    split_min = {}
    for split in required:
        dates = [kickoff_by_gw[gw] for gw in normalized[split]]
        split_min[split], split_max[split] = min(dates), max(dates)
    if not split_max["train"] < split_min["validation"]:
        raise JointForecastDatasetError("train Gameweeks must precede validation Gameweeks chronologically")
    if not split_max["validation"] < split_min["test"]:
        raise JointForecastDatasetError("validation Gameweeks must precede test Gameweeks chronologically")

    return {
        "schema_version": "1.0.0",
        "validation_status": "CHRONOLOGICAL_SPLITS_VALIDATED",
        "split_gameweek_counts": {key: len(value) for key, value in normalized.items()},
        "split_forecast_row_counts": counts,
        "first_kickoff_utc": {key: split_min[key].isoformat() for key in required},
        "last_kickoff_utc": {key: split_max[key].isoformat() for key in required},
        "independence_unit": "GAMEWEEK_CLUSTER",
        "repeated_forecasts_are_independent": False,
        "decision_weight": 0.0,
        "production_eligible": False,
    }
