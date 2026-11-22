import copy
import pytest

from multi_gameweek_transfer_evaluator import (
    MultiGameweekTransferError,
    evaluate_multi_gameweek_transfer_bundle,
)


def bundle():
    positions = {
        1: "GKP", 2: "GKP",
        3: "DEF", 4: "DEF", 5: "DEF", 6: "DEF", 7: "DEF",
        8: "MID", 9: "MID", 10: "MID", 11: "MID", 12: "MID",
        13: "FWD", 14: "FWD", 15: "FWD", 16: "DEF",
    }
    teams = {
        1: 10, 2: 11,
        3: 1, 4: 1, 5: 2, 6: 3, 7: 4, 16: 11,
        8: 5, 9: 5, 10: 6, 11: 7, 12: 8,
        13: 9, 14: 9, 15: 10,
    }
    player_rows, fixture_rows = [], []
    for gw in range(12, 17):
        for pid, position in positions.items():
            points = 5.0
            if pid == 3:
                points = 1.0 if gw == 12 else 4.0
            if pid == 16:
                points = 2.0 if gw == 12 else 8.0
            player_rows.append({
                "fpl_element_id": pid, "gameweek": gw,
                "team_id": teams[pid], "position": position,
                "expected_points": points, "expected_minutes": 80,
                "fixture_count": 1,
            })
            fixture_rows.append({
                "fpl_element_id": pid, "gameweek": gw,
                "fixture_id": 1000 + gw * 100 + pid,
                "team_id": teams[pid], "position": position,
                "opponent_team_id": 99, "kickoff_time": "2026-11-27T15:00:00Z",
                "expected_points": points, "expected_minutes": 80,
            })
    return {
        "forecast_bundle_id": "fplcat-gw12-gw16-bundle",
        "forecast_snapshot_id": "fplcat-gw12-gw16-bundle",
        "model_version": "fplcat-fixture-xp-v2",
        "horizon_gameweeks": [12, 13, 14, 15, 16],
        "source_snapshot_ids": [f"gw{gw}-immutable" for gw in range(12, 17)],
        "player_gameweek_forecasts": player_rows,
        "fixture_forecasts": fixture_rows,
    }


def request():
    return {
        "forecast_bundle": bundle(),
        "squad_ids": list(range(1, 16)),
        "starting_xi_ids": [1, 3, 4, 5, 6, 8, 9, 10, 13, 14, 15],
        "transfer_out_id": 3,
        "transfer_in_id": 16,
        "bank": 1.8,
        "selling_price": 5.7,
        "incoming_price": 5.2,
        "free_transfers": 1,
        "hit_cost_points": 4,
    }


def test_compares_transfer_over_five_gameweeks_not_only_first_week():
    result = evaluate_multi_gameweek_transfer_bundle(request())
    assert result["horizon_gameweeks"] == [12, 13, 14, 15, 16]
    assert result["weekly_comparison"][0]["incremental_expected_points"] == 1
    assert result["gross_horizon_expected_points_delta"] == 17
    assert result["net_horizon_expected_points_delta"] == 17
    assert result["action"] == "TRANSFER"
    assert result["decision_weight"] == 0
    assert result["production_eligible"] is False


def test_hit_cost_is_subtracted_once_from_horizon_gain():
    source = request()
    source["free_transfers"] = 0
    result = evaluate_multi_gameweek_transfer_bundle(source)
    assert result["transfer"]["hit_cost_points_applied"] == 4
    assert result["net_horizon_expected_points_delta"] == 13


def test_rejects_incomplete_horizon():
    source = request()
    source["forecast_bundle"]["horizon_gameweeks"] = [12, 13, 14, 15]
    with pytest.raises(MultiGameweekTransferError, match="at least five"):
        evaluate_multi_gameweek_transfer_bundle(source)


def test_rejects_mismatched_bundle_and_snapshot_ids():
    source = request()
    source["forecast_bundle"]["forecast_snapshot_id"] = "different"
    with pytest.raises(MultiGameweekTransferError, match="inconsistent"):
        evaluate_multi_gameweek_transfer_bundle(source)


def test_rejects_missing_player_forecast_in_any_gameweek():
    source = request()
    source["forecast_bundle"]["player_gameweek_forecasts"] = [
        row for row in source["forecast_bundle"]["player_gameweek_forecasts"]
        if not (row["fpl_element_id"] == 16 and row["gameweek"] == 14)
    ]
    with pytest.raises(MultiGameweekTransferError, match="missing player forecasts"):
        evaluate_multi_gameweek_transfer_bundle(source)


def test_rejects_fixture_xp_that_does_not_reconcile_to_gameweek_total():
    source = request()
    source["forecast_bundle"]["fixture_forecasts"][0]["expected_points"] += 1
    with pytest.raises(MultiGameweekTransferError, match="does not reconcile"):
        evaluate_multi_gameweek_transfer_bundle(source)


def test_rejects_unaffordable_incoming_player():
    source = request()
    source["incoming_price"] = 8.0
    with pytest.raises(MultiGameweekTransferError, match="unaffordable"):
        evaluate_multi_gameweek_transfer_bundle(source)


def test_rejects_transfer_that_exceeds_three_player_club_limit():
    source = request()
    for row in source["forecast_bundle"]["player_gameweek_forecasts"]:
        if row["fpl_element_id"] in {4, 5, 6, 16}:
            row["team_id"] = 1
        if row["fpl_element_id"] == 3:
            row["team_id"] = 2
    for row in source["forecast_bundle"]["fixture_forecasts"]:
        if row["fpl_element_id"] in {4, 5, 6, 16}:
            row["team_id"] = 1
        if row["fpl_element_id"] == 3:
            row["team_id"] = 2
    with pytest.raises(MultiGameweekTransferError, match="three-player"):
        evaluate_multi_gameweek_transfer_bundle(source)


def test_bench_transfer_must_improve_horizon_starting_xi_to_add_value():
    source = request()
    source["transfer_out_id"] = 7
    result = evaluate_multi_gameweek_transfer_bundle(source)
    assert result["transfer"]["displaced_starting_player_id"] == 3
    assert 16 in result["transfer_starting_xi_ids"]
    assert len(result["transfer_starting_xi_ids"]) == 11


def test_rejects_duplicate_provider_snapshot_ids():
    source = request()
    source["forecast_bundle"]["source_snapshot_ids"][1] = source["forecast_bundle"]["source_snapshot_ids"][0]
    with pytest.raises(MultiGameweekTransferError, match="unique immutable"):
        evaluate_multi_gameweek_transfer_bundle(source)
