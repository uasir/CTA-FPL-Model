import copy
import pytest

import player_gameweek_forecast_contract as contract
from player_gameweek_forecast_contract import (
    PlayerGameweekForecastError,
    build_player_gameweek_forecast_bundle,
)


def capture():
    weeks = list(range(12, 18))
    deadlines = {
        "12": "2026-11-27T18:30:00Z",
        "13": "2026-12-04T18:30:00Z",
        "14": "2026-12-11T18:30:00Z",
        "15": "2026-12-18T18:30:00Z",
        "16": "2026-12-25T18:30:00Z",
        "17": "2027-01-01T18:30:00Z",
    }
    rows = []
    for gw in weeks:
        rows.append({
            "fpl_element_id": 1, "gameweek": gw, "team_id": 1, "position": "MID",
            "expected_points": 4.5, "expected_minutes": 80, "fixtures_count": 1,
            "opponents": [{"team": "ARS", "home": False}], "play_chance": 0.9,
            "p_return": 0.4, "p_haul": 0.1, "p_blank": 0.5,
            "xp_q10": 1.0, "xp_q90": 8.0, "breakdown": {},
        })
    return {
        "provider_source_id": "fpl_cat_partner_projections",
        "provider_snapshot": {
            "snapshot_id": "fplcat-partner-abc123",
            "season": "2026-27",
            "provider": {
                "name": "FPL Cat", "product": "partner_projections",
                "variant": "provider_native_xp", "version": "partner-api-v1",
            },
            "grain": "player_gameweek",
            "model_version": "provider_model_version_not_disclosed",
            "gameweeks": weeks,
            "decision_eligible": True,
            "timing": {
                "generated_at_utc": "2026-11-22T05:00:00Z",
                "captured_at_utc": "2026-11-22T06:00:00Z",
                "first_deadline_utc": deadlines["12"],
                "gameweek_deadlines_utc": deadlines,
            },
            "records": rows,
            "source": {"raw_sha256": "a" * 64, "url": "https://fplcat.com/api/v1/partner/projections"},
        },
    }


def _enable_licensed_provider(monkeypatch):
    monkeypatch.setattr(contract, "require_player_gameweek_multi_gameweek_capture", lambda *args, **kwargs: {})


def test_pending_partner_license_fails_closed_by_default():
    with pytest.raises(PlayerGameweekForecastError, match="PENDING_PARTNER_KEY_AND_LICENSE"):
        build_player_gameweek_forecast_bundle(
            capture(), decision_as_of_utc="2026-11-22T07:00:00Z", required_player_ids=[1]
        )


def test_builds_native_player_gameweek_bundle_without_fixture_splits(monkeypatch):
    _enable_licensed_provider(monkeypatch)
    result = build_player_gameweek_forecast_bundle(
        capture(), decision_as_of_utc="2026-11-22T07:00:00Z", required_player_ids=[1]
    )
    assert result["forecast_grain"] == "player_gameweek"
    assert result["horizon_gameweeks"] == [12, 13, 14, 15, 16, 17]
    assert result["source_snapshot_ids"] == ["fplcat-partner-abc123"]
    assert len(result["player_gameweek_forecasts"]) == 6
    assert result["fixture_forecasts"] is None
    assert result["capabilities"]["fixture_level_expected_points"] is False
    assert result["capabilities"]["double_gameweek_fixture_split"] is False
    assert result["player_gameweek_forecasts"][0]["expected_points"] == 4.5


def test_rejects_missing_player_gameweek_row(monkeypatch):
    _enable_licensed_provider(monkeypatch)
    source = capture()
    source["provider_snapshot"]["records"].pop()
    with pytest.raises(PlayerGameweekForecastError, match="missing player-Gameweek"):
        build_player_gameweek_forecast_bundle(
            source, decision_as_of_utc="2026-11-22T07:00:00Z", required_player_ids=[1]
        )


def test_rejects_deadline_crossing_decision_time(monkeypatch):
    _enable_licensed_provider(monkeypatch)
    with pytest.raises(PlayerGameweekForecastError, match="precede every"):
        build_player_gameweek_forecast_bundle(
            capture(), decision_as_of_utc="2026-12-05T07:00:00Z", required_player_ids=[1]
        )


def test_rejects_fixture_grain_or_provider_identity_mutation(monkeypatch):
    _enable_licensed_provider(monkeypatch)
    source = capture()
    source["provider_snapshot"]["grain"] = "player_fixture"
    with pytest.raises(PlayerGameweekForecastError, match="retain player_gameweek"):
        build_player_gameweek_forecast_bundle(
            source, decision_as_of_utc="2026-11-22T07:00:00Z", required_player_ids=[1]
        )
