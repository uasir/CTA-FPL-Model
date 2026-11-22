import copy
import pytest
import multi_gameweek_forecast_contract as contract

from multi_gameweek_forecast_contract import (
    MultiGameweekForecastError,
    build_multi_gameweek_forecast_bundle,
)


def payload():
    provider = {"name": "FPL Cat", "product": "published xP", "variant": "fixture xP", "version": "v2"}
    panels = []
    for offset, gw in enumerate(range(12, 17)):
        fixture_id = 900 + gw
        kickoff_day = 27 + offset * 7
        # Keep fixture kickoff dates valid within December for later GWs.
        kickoff = f"2026-11-27T15:00:00Z" if offset == 0 else f"2026-12-{4 + (offset - 1) * 7:02d}T15:00:00Z"
        deadline_day = 27 + offset * 7
        deadline = f"2026-11-27T18:30:00Z" if offset == 0 else f"2026-12-{4 + (offset - 1) * 7:02d}T18:30:00Z"
        panels.append({
            "snapshot": {
                "snapshot_id": f"fplcat-gw{gw}-immutable",
                "season": "2026-27",
                "target_gameweek": gw,
                "provider": dict(provider),
                "grain": "player_fixture",
                "decision_eligible": True,
                "timing": {
                    "generated_at_utc": "2026-11-22T05:45:00Z",
                    "captured_at_utc": "2026-11-22T06:00:00Z",
                    "deadline_utc": deadline,
                },
                "records": [
                    {"fpl_element_id": 1, "fixture_id": fixture_id, "expected_points": 4 + offset, "expected_minutes": 88},
                    {"fpl_element_id": 2, "fixture_id": fixture_id, "expected_points": 3 + offset, "expected_minutes": 82},
                ],
            },
            "fixtures": [{
                "fixture_id": fixture_id, "gameweek": gw,
                "home_team_id": 10, "away_team_id": 20, "kickoff_time": kickoff,
            }],
            "player_metadata": [
                {"fpl_element_id": 1, "team_id": 10, "position": "DEF"},
                {"fpl_element_id": 2, "team_id": 20, "position": "FWD"},
            ],
        })
    return {
        "forecast_bundle_id": "fplcat-2026-27-gw12-gw16-asof-20261122T0600Z",
        "season": "2026-27",
        "provider_source_id": "test_verified_fixture_provider",
        "provider": provider,
        "model_version": "fplcat-fixture-xp-v2",
        "decision_as_of_utc": "2026-11-22T07:00:00Z",
        "required_player_ids": [1, 2],
        "panels": panels,
    }


def _enable_synthetic_verified_provider(monkeypatch):
    capability = {
        "provider": {"name": "FPL Cat", "product": "published xP", "variant": "fixture xP", "version": "v2"},
        "capture_grain": "player_fixture",
        "max_explicit_gameweeks_per_capture": 5,
        "fixture_ids": True,
        "explicit_multi_gameweek_panels": True,
        "point_in_time_capture": True,
        "authorized_reproducible_access": True,
        "multi_gameweek_status": "TEST_ONLY_SYNTHETIC_FIXTURE",
    }
    monkeypatch.setattr(contract, "require_multi_gameweek_capture", lambda source_id, required_horizon=5: capability)
    monkeypatch.setattr(contract, "validate_capture_against_registry", lambda source_id, capture: capability)


def test_builds_complete_five_gameweek_fixture_level_bundle(monkeypatch):
    _enable_synthetic_verified_provider(monkeypatch)
    result = build_multi_gameweek_forecast_bundle(payload())
    assert result["horizon_gameweeks"] == [12, 13, 14, 15, 16]
    assert result["forecast_snapshot_id"] == result["forecast_bundle_id"]
    assert len(result["source_snapshot_ids"]) == 5
    assert len(result["fixture_forecasts"]) == 10
    assert len(result["player_gameweek_forecasts"]) == 10
    gw12_player1 = next(row for row in result["player_gameweek_forecasts"]
                        if row["fpl_element_id"] == 1 and row["gameweek"] == 12)
    assert gw12_player1["expected_points"] == 4
    assert gw12_player1["expected_minutes"] == 88
    assert result["forecast_coverage"]["blank_gameweeks_inferred_from_schedule"] == []


def test_rejects_four_gameweek_horizon(monkeypatch):
    _enable_synthetic_verified_provider(monkeypatch)
    source = payload()
    source["panels"] = source["panels"][:4]
    with pytest.raises(MultiGameweekForecastError, match="at least 5"):
        build_multi_gameweek_forecast_bundle(source)


def test_rejects_non_consecutive_gameweeks(monkeypatch):
    _enable_synthetic_verified_provider(monkeypatch)
    source = payload()
    source["panels"][2]["snapshot"]["target_gameweek"] = 20
    source["panels"][2]["fixtures"][0]["gameweek"] = 20
    with pytest.raises(MultiGameweekForecastError, match="consecutive"):
        build_multi_gameweek_forecast_bundle(source)


def test_rejects_mismatched_provider_or_version_across_panels(monkeypatch):
    _enable_synthetic_verified_provider(monkeypatch)
    source = payload()
    source["panels"][2]["snapshot"]["provider"]["version"] = "v3"
    with pytest.raises(MultiGameweekForecastError, match="provider identity/version"):
        build_multi_gameweek_forecast_bundle(source)


def test_rejects_stale_future_gameweek_snapshot(monkeypatch):
    _enable_synthetic_verified_provider(monkeypatch)
    source = payload()
    source["panels"][1]["snapshot"]["timing"]["captured_at_utc"] = "2026-11-20T06:00:00Z"
    source["panels"][1]["snapshot"]["timing"]["generated_at_utc"] = "2026-11-20T05:45:00Z"
    with pytest.raises(MultiGameweekForecastError, match="stale"):
        build_multi_gameweek_forecast_bundle(source)


def test_rejects_missing_player_metadata(monkeypatch):
    _enable_synthetic_verified_provider(monkeypatch)
    source = payload()
    source["panels"][3]["player_metadata"] = source["panels"][3]["player_metadata"][:1]
    with pytest.raises(MultiGameweekForecastError, match="missing player metadata"):
        build_multi_gameweek_forecast_bundle(source)


def test_rejects_missing_fixture_forecast_for_player_with_scheduled_match(monkeypatch):
    _enable_synthetic_verified_provider(monkeypatch)
    source = payload()
    source["panels"][0]["snapshot"]["records"] = source["panels"][0]["snapshot"]["records"][:1]
    with pytest.raises(MultiGameweekForecastError, match="missing fixture forecasts"):
        build_multi_gameweek_forecast_bundle(source)


def test_rejects_mismatched_snapshot_ids(monkeypatch):
    _enable_synthetic_verified_provider(monkeypatch)
    source = payload()
    source["panels"][1]["snapshot"]["snapshot_id"] = source["panels"][0]["snapshot"]["snapshot_id"]
    with pytest.raises(MultiGameweekForecastError, match="unique"):
        build_multi_gameweek_forecast_bundle(source)


def test_rejects_wrong_fixture_team_assignment(monkeypatch):
    _enable_synthetic_verified_provider(monkeypatch)
    source = payload()
    source["panels"][0]["player_metadata"][0]["team_id"] = 99
    with pytest.raises(MultiGameweekForecastError, match="does not participate"):
        build_multi_gameweek_forecast_bundle(source)


def test_blank_gameweek_zero_requires_confirmed_no_club_fixture(monkeypatch):
    _enable_synthetic_verified_provider(monkeypatch)
    source = payload()
    source["panels"][0]["fixtures"] = [{
        "fixture_id": 999, "gameweek": 12,
        "home_team_id": 30, "away_team_id": 40, "kickoff_time": "2026-11-27T15:00:00Z",
    }]
    source["panels"][0]["snapshot"]["records"] = [
        {"fpl_element_id": 999, "fixture_id": 999, "expected_points": 2.0, "expected_minutes": 90}
    ]
    result = build_multi_gameweek_forecast_bundle(source)
    blank = [row for row in result["forecast_coverage"]["blank_gameweeks_inferred_from_schedule"]
             if row["gameweek"] == 12]
    assert {row["fpl_element_id"] for row in blank} == {1, 2}
    assert all(row["expected_points"] == 0 and row["expected_minutes"] == 0
               for row in result["player_gameweek_forecasts"] if row["gameweek"] == 12)


def test_bundle_rejects_current_single_gameweek_providers():
    source = payload()
    source["provider_source_id"] = "fpl_cat_public_projections"
    with pytest.raises(MultiGameweekForecastError, match="capability gate rejected"):
        build_multi_gameweek_forecast_bundle(source)


def test_bundle_rejects_unknown_provider_source():
    source = payload()
    source["provider_source_id"] = "unregistered_provider"
    with pytest.raises(MultiGameweekForecastError, match="capability gate rejected"):
        build_multi_gameweek_forecast_bundle(source)


def test_bundle_requires_registry_source_id():
    source = payload()
    source.pop("provider_source_id")
    with pytest.raises(MultiGameweekForecastError, match="provider_source_id"):
        build_multi_gameweek_forecast_bundle(source)
