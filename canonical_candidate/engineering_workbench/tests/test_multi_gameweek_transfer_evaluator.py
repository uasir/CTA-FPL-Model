from multi_gameweek_transfer_evaluator import (
    MultiGameweekTransferError,
    evaluate_multi_gameweek_transfer,
)


def payload():
    positions = {
        1: "GKP", 2: "GKP",
        3: "DEF", 4: "DEF", 5: "DEF", 6: "DEF", 7: "DEF",
        8: "MID", 9: "MID", 10: "MID", 11: "MID", 12: "MID",
        13: "FWD", 14: "FWD", 15: "FWD",
        16: "DEF",
    }
    teams = {
        1: 10, 2: 11,
        3: 1, 4: 1, 5: 2, 6: 3, 7: 4,
        8: 5, 9: 5, 10: 6, 11: 7, 12: 8,
        13: 9, 14: 9, 15: 10, 16: 1,
    }
    weeks = []
    for gw in range(12, 17):
        rows = []
        for player_id, position in positions.items():
            points = 5.0
            if player_id == 3:
                points = 1.0 if gw == 12 else 4.0
            if player_id == 16:
                points = 2.0 if gw == 12 else 8.0
            rows.append({
                "fpl_element_id": player_id,
                "expected_points": points,
                "expected_minutes": 80,
                "team_id": teams[player_id],
                "position": position,
            })
        weeks.append({"gameweek": gw, "player_forecasts": rows})
    return {
        "gameweeks": weeks,
        "squad_ids": list(range(1, 16)),
        "starting_xi_ids": [1, 3, 4, 5, 6, 8, 9, 10, 13, 14, 15],
        "transfer_out_id": 3,
        "transfer_in_id": 16,
        "free_transfers": 1,
        "hit_cost_points": 4,
    }


def test_multi_gameweek_value_can_justify_transfer_despite_small_first_week_gain():
    result = evaluate_multi_gameweek_transfer(payload())
    assert result["horizon"]["gameweek_count"] == 5
    assert result["weekly_comparison"][0]["incremental_points"] == 1.0
    assert result["net_horizon_expected_points_delta"] == 17.0
    assert result["action"] == "TRANSFER"


def test_incomplete_horizon_fails_closed():
    request = payload()
    request["gameweeks"] = request["gameweeks"][:4]
    try:
        evaluate_multi_gameweek_transfer(request)
    except MultiGameweekTransferError as exc:
        assert "at least five" in str(exc)
    else:
        raise AssertionError("expected incomplete horizon to fail")


def test_non_consecutive_gameweeks_fail_closed():
    request = payload()
    request["gameweeks"][2]["gameweek"] = 20
    try:
        evaluate_multi_gameweek_transfer(request)
    except MultiGameweekTransferError as exc:
        assert "consecutive" in str(exc)
    else:
        raise AssertionError("expected non-consecutive horizon to fail")


def test_team_stacks_are_reported_descriptively_without_correlation_claims():
    result = evaluate_multi_gameweek_transfer(payload())
    stacks = result["team_stacks"]
    assert any(
        row["position_group"] == "DEF"
        and row["team_id"] == 1
        and row["player_count"] >= 2
        for row in stacks
    )
    assert any(
        row["position_group"] == "FWD"
        and row["team_id"] == 9
        and row["player_count"] == 2
        for row in stacks
    )
    assert all(row["probability_or_correlation_estimated"] is False for row in stacks)
    assert result["portfolio_risk"]["covar_used"] is False


def test_hit_cost_is_subtracted_once_from_horizon_total():
    request = payload()
    request["free_transfers"] = 0
    result = evaluate_multi_gameweek_transfer(request)
    assert result["transfer_cost_points"] == 4
    assert result["net_horizon_expected_points_delta"] == 13.0


def test_bench_transfer_displacement_uses_full_horizon_not_first_week_only():
    request = payload()
    request["transfer_out_id"] = 7
    result = evaluate_multi_gameweek_transfer(request)
    # Incoming player 16 displaces the weakest starting defender over the
    # complete horizon, even though the decision is not based on GW12 alone.
    assert 16 in result["transfer_starting_xi_ids"]
    assert len(result["transfer_starting_xi_ids"]) == 11


def test_transfer_that_breaks_three_player_club_limit_is_rejected():
    request = payload()
    for week in request["gameweeks"]:
        for player in week["player_forecasts"]:
            if player["fpl_element_id"] in {5, 6, 7, 16}:
                player["team_id"] = 2
    try:
        evaluate_multi_gameweek_transfer(request)
    except MultiGameweekTransferError as exc:
        assert "three-player club limit" in str(exc)
    else:
        raise AssertionError("expected illegal club stack transfer to fail")



def test_negative_expected_points_are_valid_finite_fpl_forecasts():
    request = payload()
    for week in request["gameweeks"]:
        player = next(row for row in week["player_forecasts"] if row["fpl_element_id"] == 3)
        player["expected_points"] = -0.25
    result = evaluate_multi_gameweek_transfer(request)
    assert result["action"] == "TRANSFER"
    assert result["weekly_comparison"][0]["incremental_points"] == 2.25
