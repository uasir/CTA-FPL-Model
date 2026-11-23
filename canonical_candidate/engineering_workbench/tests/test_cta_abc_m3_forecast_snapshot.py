from __future__ import annotations

import pytest

from build_cta_abc_m3_forecast_snapshot import build_snapshot


def fixture_inputs():
    players = [
        {"id": "10", "team": "1", "element_type": "3", "now_cost": "75", "web_name": "Player A"},
        {"id": "20", "team": "2", "element_type": "2", "now_cost": "50", "web_name": "Player B"},
    ]
    fixtures = []
    predictions = []
    minutes = []
    for gw in range(12, 17):
        fixture_id = str(1000 + gw)
        fixtures.append({
            "id": fixture_id, "event": str(gw), "team_h": "1", "team_a": "2",
            "kickoff_time": f"2026-12-{gw:02d}T15:00:00Z",
        })
        for element, points, mins in (("10", 3.5, 70), ("20", 2.0, 80)):
            predictions.append({
                "fpl_element_id": element, "gameweek": str(gw),
                "fpl_fixture_id": fixture_id, "expected_points": str(points),
                "model_version": "abc-points-ridge-v1",
            })
            minutes.append({
                "fpl_element_id": element, "gameweek": str(gw),
                "fixture_id": fixture_id, "expected_minutes": str(mins),
            })
    model = {"model_version": "abc-points-ridge-v1"}
    manifest = {
        "model_version": "abc-points-ridge-v1",
        "production_eligible": False,
        "decision_weight": 0.0,
        "point_in_time_status": "RETROSPECTIVE_SOURCE_VINTAGES_NOT_VERIFIED",
    }
    return predictions, minutes, players, fixtures, model, manifest


def test_builds_existing_m3_contract_and_five_gw_aggregates():
    args = fixture_inputs()
    snapshot, tables, report = build_snapshot(
        *args, "2026-11-23T10:00:00Z", [12, 13, 14, 15, 16],
        {"model_sha256": "test"},
    )
    assert snapshot["forecast_horizon_gameweeks"] == 5
    assert snapshot["forecast_quality"]["validation_status"] == "EXPLORATORY_ONLY"
    assert snapshot["forecast_quality"]["point_in_time_status"] == "NOT_VERIFIED"
    assert len(snapshot["player_forecasts"]) == 2
    player_a = snapshot["player_forecasts"][0]
    assert player_a == {
        "fpl_element_id": 10, "expected_points": 17.5, "expected_minutes": 350.0,
        "price": 7.5, "position": "MID", "team_id": 1,
    }
    assert len(tables["fixture"]) == 10
    assert len(tables["gameweek"]) == 10
    assert report["production_eligible"] is False
    assert report["decision_weight"] == 0.0


def test_rejects_prediction_without_matching_dastan_minutes():
    args = fixture_inputs()
    args[1].pop()
    with pytest.raises(ValueError, match="fixture universes differ"):
        build_snapshot(*args, "2026-11-23T10:00:00Z", [12, 13, 14, 15, 16])


def test_rejects_player_not_in_fixture():
    args = fixture_inputs()
    args[0][0]["fpl_fixture_id"] = "9999"
    with pytest.raises(ValueError, match="unknown FPL player/fixture"):
        build_snapshot(*args, "2026-11-23T10:00:00Z", [12, 13, 14, 15, 16])


def test_rejects_non_consecutive_horizon():
    args = fixture_inputs()
    with pytest.raises(ValueError, match="five consecutive"):
        build_snapshot(*args, "2026-11-23T10:00:00Z", [12, 13, 15, 16, 17])


def test_rejects_nonzero_decision_weight():
    args = fixture_inputs()
    args[5]["decision_weight"] = 0.2
    with pytest.raises(ValueError, match="research-only"):
        build_snapshot(*args, "2026-11-23T10:00:00Z", [12, 13, 14, 15, 16])


def test_rejects_fixture_before_as_of():
    args = fixture_inputs()
    with pytest.raises(ValueError, match="not after forecast as-of"):
        build_snapshot(*args, "2026-12-12T16:00:00Z", [12, 13, 14, 15, 16])


def test_rejects_missing_player_fixture_from_both_prediction_inputs():
    args = fixture_inputs()
    args[0].pop()
    args[1].pop()
    with pytest.raises(ValueError, match="complete official FPL player-fixture universe"):
        build_snapshot(*args, "2026-11-23T10:00:00Z", [12, 13, 14, 15, 16])
