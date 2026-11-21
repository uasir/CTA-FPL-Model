import hashlib

import pytest

from canonical_provider_forecast_contract import normalize_provider_snapshot
from canonical_forecast_recommendation_adapter import (
    ForecastAdapterError,
    build_recommendation_forecast_payload,
)


def canonical_snapshot():
    raw = b"frozen provider response"
    return normalize_provider_snapshot({
        "snapshot_id": "gw11-provider-0900z",
        "season": "2026-27",
        "target_gameweek": 11,
        "provider": {"name": "FPL Cat", "product": "published xP", "variant": "API", "version": "v1"},
        "timing": {
            "generated_at_utc": "2026-11-20T08:30:00Z",
            "captured_at_utc": "2026-11-20T09:00:00Z",
            "deadline_utc": "2026-11-21T11:00:00Z",
        },
        "source": {
            "url": "https://provider.example/forecast.json",
            "raw_snapshot_id": "raw-1",
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
        },
        "grain": "player_gameweek",
        "records": [
            {"fpl_element_id": 1, "expected_points": 5.25},
            {"fpl_element_id": 2, "expected_points": 3.75},
        ],
        "coverage": {"row_count": 2, "identity_mapped_count": 2},
    })


def metadata():
    return [
        {"fpl_element_id": 1, "price": 10.5, "position": "MID", "team_id": 1, "expected_minutes": 88},
        {"fpl_element_id": 2, "price": 5.0, "position": "DEF", "team_id": 2, "expected_minutes": 72},
    ]


def test_refuses_partial_or_inconsistent_identity_mapping_coverage():
    snapshot = canonical_snapshot()
    snapshot["coverage"]["identity_mapped_count"] = 1
    with pytest.raises(ForecastAdapterError, match="identity_mapped_count"):
        build_recommendation_forecast_payload(
            snapshot, metadata(), as_of_utc="2026-11-20T10:00:00Z"
        )


def test_refuses_record_count_coverage_mismatch():
    snapshot = canonical_snapshot()
    snapshot["coverage"]["row_count"] = 3
    with pytest.raises(ForecastAdapterError, match="row_count"):
        build_recommendation_forecast_payload(
            snapshot, metadata(), as_of_utc="2026-11-20T10:00:00Z"
        )


def test_adapts_provider_values_without_recalibration():
    result = build_recommendation_forecast_payload(
        canonical_snapshot(), metadata(), as_of_utc="2026-11-20T10:00:00Z"
    )
    assert [row["expected_points"] for row in result["player_forecasts"]] == [5.25, 3.75]
    assert result["player_forecasts"][0]["price"] == 10.5
    assert result["forecast_quality"]["validation_status"] == "EXPLORATORY_ONLY"
    assert result["forecast_quality"]["point_in_time_status"] == "VERIFIED"
    assert result["forecast_quality"]["data_coverage"]["freshness_status"] == "FRESH_WITHIN_24H"
    assert "FPL Cat" in result["model_version"]


def test_stale_snapshot_is_preserved_but_marked_stale():
    result = build_recommendation_forecast_payload(
        canonical_snapshot(), metadata(), as_of_utc="2026-11-21T10:00:00Z"
    )
    assert result["forecast_quality"]["data_coverage"]["freshness_status"] == "STALE_OVER_24H"
    assert result["forecast_quality"]["validation_status"] == "EXPLORATORY_ONLY"


def test_refuses_diagnostic_only_snapshot():
    snapshot = canonical_snapshot()
    snapshot["decision_eligible"] = False
    with pytest.raises(ForecastAdapterError, match="diagnostic-only"):
        build_recommendation_forecast_payload(
            snapshot, metadata(), as_of_utc="2026-11-20T10:00:00Z"
        )


def test_refuses_player_fixture_grain_without_explicit_aggregation():
    snapshot = canonical_snapshot()
    snapshot["grain"] = "player_fixture"
    with pytest.raises(ForecastAdapterError, match="fixture aggregation is not implicit"):
        build_recommendation_forecast_payload(
            snapshot, metadata(), as_of_utc="2026-11-20T10:00:00Z"
        )


def test_refuses_missing_player_metadata():
    with pytest.raises(ForecastAdapterError, match="missing FPL metadata"):
        build_recommendation_forecast_payload(
            canonical_snapshot(), metadata()[:1], as_of_utc="2026-11-20T10:00:00Z"
        )


def test_refuses_missing_minutes_instead_of_inventing_them():
    rows = metadata()
    del rows[0]["expected_minutes"]
    with pytest.raises(ForecastAdapterError, match="expected_minutes"):
        build_recommendation_forecast_payload(
            canonical_snapshot(), rows, as_of_utc="2026-11-20T10:00:00Z"
        )


def test_refuses_duplicate_metadata_ids_and_future_capture():
    rows = metadata() + [metadata()[0]]
    with pytest.raises(ForecastAdapterError, match="duplicate FPL metadata"):
        build_recommendation_forecast_payload(
            canonical_snapshot(), rows, as_of_utc="2026-11-20T10:00:00Z"
        )
    with pytest.raises(ForecastAdapterError, match="later than as_of"):
        build_recommendation_forecast_payload(
            canonical_snapshot(), metadata(), as_of_utc="2026-11-20T08:00:00Z"
        )


def test_refuses_invalid_horizon():
    with pytest.raises(ForecastAdapterError, match="positive integer"):
        build_recommendation_forecast_payload(
            canonical_snapshot(), metadata(), as_of_utc="2026-11-20T10:00:00Z",
            forecast_horizon_gameweeks=True,
        )


def test_refuses_decision_timestamp_at_or_after_deadline():
    with pytest.raises(ForecastAdapterError, match="strictly before the FPL deadline"):
        build_recommendation_forecast_payload(
            canonical_snapshot(), metadata(), as_of_utc="2026-11-21T11:00:00Z"
        )
