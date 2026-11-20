import copy
import hashlib

import pytest

from canonical_provider_forecast_contract import (
    ForecastContractError,
    normalize_provider_snapshot,
)


def payload():
    raw = b"frozen benchmark forecast"
    return {
        "snapshot_id": "gw11-fplcat-2026-11-20T0900Z",
        "season": "2026-27",
        "target_gameweek": 11,
        "provider": {"name": "FPL Cat", "product": "published xP", "variant": "xP API", "version": "v1"},
        "timing": {
            "generated_at_utc": "2026-11-20T08:30:00Z",
            "captured_at_utc": "2026-11-20T09:00:00Z",
            "deadline_utc": "2026-11-21T11:00:00Z",
        },
        "source": {
            "url": "https://example.test/forecast.json",
            "raw_snapshot_id": "raw-123",
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
        },
        "grain": "player_gameweek",
        "records": [
            {"fpl_element_id": 1, "expected_points": 5.4, "expected_minutes": 80},
            {"fpl_element_id": 2, "expected_points": 3.1, "appearance_probability": 0.72},
        ],
        "coverage": {"row_count": 2, "expected_player_universe": 672, "identity_mapped_count": 2},
    }


def test_normalizes_verified_pre_deadline_provider_snapshot():
    result = normalize_provider_snapshot(payload())
    assert result["decision_eligible"] is True
    assert result["timing"]["point_in_time_status"] == "VERIFIED_PRE_DEADLINE"
    assert result["provider"]["variant"] == "xP API"
    assert result["records"][0]["expected_points"] == 5.4
    assert result["coverage"]["expected_player_universe"] == 672


def test_missing_provider_generation_timestamp_is_diagnostic_only():
    source = payload()
    source["provider"] = {"name": "FPL Lucho", "product": "CSV export", "variant": "served xP"}
    source["timing"]["generated_at_utc"] = None
    result = normalize_provider_snapshot(source)
    assert result["decision_eligible"] is False
    assert result["eligibility_reason"] == "PROVIDER_GENERATION_TIME_NOT_DISCLOSED"
    assert result["provider"]["variant"] == "served xP"


def test_never_infers_lucho_served_xp_is_odds_xp():
    source = payload()
    source["provider"] = {"name": "FPL Lucho", "product": "CSV export", "variant": "served xP"}
    result = normalize_provider_snapshot(source)
    assert result["provider"]["variant"] == "served xP"
    assert "Odds" not in result["provider"]["variant"]


def test_rejects_capture_at_or_after_deadline():
    source = payload()
    source["timing"]["captured_at_utc"] = source["timing"]["deadline_utc"]
    with pytest.raises(ForecastContractError, match="capture must be strictly before"):
        normalize_provider_snapshot(source)


def test_rejects_provider_generation_at_or_after_deadline():
    source = payload()
    source["timing"]["generated_at_utc"] = source["timing"]["deadline_utc"]
    with pytest.raises(ForecastContractError, match="generation timestamp is at or after"):
        normalize_provider_snapshot(source)


def test_rejects_timezone_naive_timestamps():
    source = payload()
    source["timing"]["generated_at_utc"] = "2026-11-20T08:30:00"
    with pytest.raises(ForecastContractError, match="include a timezone"):
        normalize_provider_snapshot(source)


def test_preserves_fixture_grain_and_requires_fixture_identity():
    source = payload()
    source["grain"] = "player_fixture"
    source["records"] = [
        {"fpl_element_id": 1, "fixture_id": 101, "expected_points": 2.1},
        {"fpl_element_id": 1, "fixture_id": 102, "expected_points": 3.3},
    ]
    source["coverage"]["row_count"] = 2
    result = normalize_provider_snapshot(source)
    assert result["grain"] == "player_fixture"
    assert [x["fixture_id"] for x in result["records"]] == [101, 102]
    assert sum(x["expected_points"] for x in result["records"]) == pytest.approx(5.4)


def test_rejects_duplicate_player_gameweek_or_player_fixture_keys():
    source = payload()
    source["records"].append(copy.deepcopy(source["records"][0]))
    source["coverage"]["row_count"] = 3
    with pytest.raises(ForecastContractError, match="duplicate forecast key"):
        normalize_provider_snapshot(source)


def test_rejects_non_finite_or_invalid_probabilities():
    source = payload()
    source["records"][0]["expected_points"] = float("nan")
    with pytest.raises(ForecastContractError, match="must be finite"):
        normalize_provider_snapshot(source)
    source = payload()
    source["records"][0]["appearance_probability"] = 1.1
    with pytest.raises(ForecastContractError, match="must be <= 1"):
        normalize_provider_snapshot(source)


def test_rejects_mismatched_coverage_and_bad_hash():
    source = payload()
    source["coverage"]["row_count"] = 99
    with pytest.raises(ForecastContractError, match="row_count"):
        normalize_provider_snapshot(source)
    source = payload()
    source["source"]["raw_sha256"] = "not-a-hash"
    with pytest.raises(ForecastContractError, match="SHA-256"):
        normalize_provider_snapshot(source)
