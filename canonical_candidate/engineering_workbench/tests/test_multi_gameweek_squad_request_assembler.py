import pytest
import multi_gameweek_forecast_contract as forecast_contract

from multi_gameweek_squad_request_assembler import (
    MultiGameweekSquadAssemblyError,
    assemble_multi_gameweek_squad_diagnostics,
)


def forecast_payload():
    provider = {"name": "FPL Cat", "product": "published xP", "variant": "fixture xP", "version": "v2"}
    panels = []
    positions = {
        1: "GKP", 2: "GKP",
        3: "DEF", 4: "DEF", 5: "DEF", 6: "DEF", 7: "DEF", 16: "DEF",
        8: "MID", 9: "MID", 10: "MID", 11: "MID", 12: "MID",
        13: "FWD", 14: "FWD", 15: "FWD",
    }
    for offset, gw in enumerate(range(12, 17)):
        fixtures, records, metadata = [], [], []
        for pid in range(1, 17, 2):
            fixture_id = gw * 100 + pid
            home_team, away_team = pid, pid + 1
            fixtures.append({
                "fixture_id": fixture_id, "gameweek": gw,
                "home_team_id": home_team, "away_team_id": away_team,
                "kickoff_time": f"2026-11-27T15:00:00Z" if offset == 0 else f"2026-12-{4 + (offset - 1) * 7:02d}T15:00:00Z",
            })
            for player_id in (pid, pid + 1):
                points = 3.0 + offset
                if player_id == 3:
                    points = 1.0 if offset == 0 else 2.0
                if player_id == 16:
                    points = 5.0
                records.append({
                    "fpl_element_id": player_id, "fixture_id": fixture_id,
                    "expected_points": points, "expected_minutes": 80,
                })
                metadata.append({
                    "fpl_element_id": player_id, "team_id": player_id,
                    "position": positions[player_id],
                })
        deadline = "2026-11-27T18:30:00Z" if offset == 0 else f"2026-12-{4 + (offset - 1) * 7:02d}T18:30:00Z"
        panels.append({
            "snapshot": {
                "snapshot_id": f"immutable-gw{gw}", "season": "2026-27",
                "target_gameweek": gw, "provider": dict(provider),
                "grain": "player_fixture", "decision_eligible": True,
                "timing": {
                    "generated_at_utc": "2026-11-22T05:45:00Z",
                    "captured_at_utc": "2026-11-22T06:00:00Z",
                    "deadline_utc": deadline,
                },
                "records": records,
            },
            "fixtures": fixtures, "player_metadata": metadata,
        })
    return {
        "forecast_bundle_id": "fplcat-test-gw12-gw16",
        "season": "2026-27", "provider_source_id": "test_verified_fixture_provider", "provider": provider,
        "model_version": "fplcat-fixture-xp-v2",
        "decision_as_of_utc": "2026-11-22T07:00:00Z",
        "required_player_ids": list(range(1, 17)), "panels": panels,
    }


def manager_context():
    return {
        "squad_snapshot": [
            {"fpl_element_id": pid, "purchase_price": 5.0 if pid in range(3, 8) else 6.0}
            for pid in range(1, 16)
        ],
        "bank": 1.0, "free_transfers": 1,
    }


def current_player_metadata():
    positions = {
        1: "GKP", 2: "GKP",
        3: "DEF", 4: "DEF", 5: "DEF", 6: "DEF", 7: "DEF", 16: "DEF",
        8: "MID", 9: "MID", 10: "MID", 11: "MID", 12: "MID",
        13: "FWD", 14: "FWD", 15: "FWD",
    }
    return [{
        "fpl_element_id": pid, "position": positions[pid], "team_id": pid,
        "price": 5.0 if pid in range(3, 8) or pid == 16 else 6.0,
    } for pid in range(1, 17)]


def _enable_synthetic_verified_provider(monkeypatch):
    capability = {
        "provider": {"name": "FPL Cat", "product": "published xP", "variant": "fixture xP", "version": "v2"},
        "capture_grain": "player_fixture",
        "max_explicit_gameweeks_per_capture": 5,
        "fixture_ids": True,
        "explicit_multi_gameweek_panels": True,
        "point_in_time_capture": True,
        "authorized_reproducible_access": True,
    }
    monkeypatch.setattr(forecast_contract, "require_multi_gameweek_capture", lambda source_id, required_horizon=5: capability)
    monkeypatch.setattr(forecast_contract, "validate_capture_against_registry", lambda source_id, capture: capability)


def test_assembles_all_affordable_same_position_transfers_from_manager_state(monkeypatch):
    _enable_synthetic_verified_provider(monkeypatch)
    result = assemble_multi_gameweek_squad_diagnostics(
        forecast_payload(), manager_context(),
        [1, 3, 4, 5, 6, 8, 9, 10, 13, 14, 15],
        current_player_metadata(),
    )
    assert result["provider_source_id"] == "test_verified_fixture_provider"
    assert result["provider"]["name"] == "FPL Cat"
    assert result["source_snapshot_ids"] == [f"immutable-gw{gw}" for gw in range(12, 17)]
    assert result["horizon_gameweeks"] == [12, 13, 14, 15, 16]
    assert result["manager_state"]["squad_ids"] == list(range(1, 16))
    assert result["candidate_count"] > 0
    assert result["best_diagnostic"]["transfer"]["out_id"] == 3
    assert result["best_diagnostic"]["transfer"]["in_id"] == 16
    assert result["decision_weight"] == 0
    assert result["production_eligible"] is False


def test_rejects_manager_snapshot_without_purchase_prices(monkeypatch):
    _enable_synthetic_verified_provider(monkeypatch)
    manager = manager_context()
    del manager["squad_snapshot"][2]["purchase_price"]
    with pytest.raises(MultiGameweekSquadAssemblyError, match="purchase_price"):
        assemble_multi_gameweek_squad_diagnostics(
            forecast_payload(), manager,
            [1, 3, 4, 5, 6, 8, 9, 10, 13, 14, 15],
            current_player_metadata(),
        )


def test_rejects_current_metadata_that_disagrees_with_forecast_bundle(monkeypatch):
    _enable_synthetic_verified_provider(monkeypatch)
    metadata = current_player_metadata()
    metadata[-1]["team_id"] = 99
    with pytest.raises(MultiGameweekSquadAssemblyError, match="does not match forecast bundle"):
        assemble_multi_gameweek_squad_diagnostics(
            forecast_payload(), manager_context(),
            [1, 3, 4, 5, 6, 8, 9, 10, 13, 14, 15],
            metadata,
        )


def test_rejects_invalid_forecast_horizon_before_candidate_enumeration(monkeypatch):
    _enable_synthetic_verified_provider(monkeypatch)
    source = forecast_payload()
    source["panels"] = source["panels"][:4]
    with pytest.raises(MultiGameweekSquadAssemblyError, match="forecast bundle rejected"):
        assemble_multi_gameweek_squad_diagnostics(
            source, manager_context(),
            [1, 3, 4, 5, 6, 8, 9, 10, 13, 14, 15],
            current_player_metadata(),
        )
