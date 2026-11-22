import pytest

from team_exposure_correlation import TeamExposureError, build_team_exposure_report


def forecasts():
    rows = []
    for gw in range(12, 17):
        for pid, team, pos, xp in (
            (1, 1, "DEF", 5.0), (2, 1, "DEF", 4.0),
            (3, 2, "MID", 6.0), (4, 2, "FWD", 5.0),
        ):
            rows.append({"fpl_element_id": pid, "team_id": team, "position": pos,
                         "gameweek": gw, "expected_points": xp})
    return rows


def scenarios():
    rows = []
    for gw in range(12, 17):
        for scenario, clean_sheet, goals in (
            ("low", 0.0, 0.0), ("mid", 4.0, 3.0), ("high", 6.0, 8.0),
        ):
            rows.append({
                "gameweek": gw, "scenario_id": scenario,
                "player_points": {
                    1: clean_sheet, 2: clean_sheet, 3: goals, 4: goals * 0.8,
                },
            })
    return rows


def test_five_gameweek_team_stacking_and_joint_covariance_are_reported():
    result = build_team_exposure_report(
        squad_player_ids=[1, 2, 3, 4],
        player_gameweek_forecasts=forecasts(),
        joint_scenarios=scenarios(),
    )
    assert result["horizon_size"] == 5
    assert result["expected_points_are_additive"] is True
    arsenal_like = next(row for row in result["team_exposure"] if row["team_id"] == 1)
    assert arsenal_like["player_count"] == 2
    assert arsenal_like["stack_type"] == "DEFENSIVE_CLEAN_SHEET_EXPOSURE"
    defensive_pair = next(row for row in result["pairwise_player_dependence"]
                          if (row["player_a_id"], row["player_b_id"]) == (1, 2))
    assert defensive_pair["correlation_horizon"] == 1.0
    assert defensive_pair["portfolio_variance_contribution"] > 0
    assert result["decision_weight"] == 0
    assert result["production_eligible"] is False


def test_no_scenarios_does_not_invent_correlation_from_same_team():
    result = build_team_exposure_report(
        squad_player_ids=[1, 2, 3, 4],
        player_gameweek_forecasts=forecasts(),
    )
    pair = next(row for row in result["pairwise_player_dependence"]
                if (row["player_a_id"], row["player_b_id"]) == (1, 2))
    assert pair["correlation_horizon"] is None
    assert pair["status"] == "NOT_ESTIMABLE_INSUFFICIENT_JOINT_SCENARIOS"
    assert result["covariance_status"] == "NOT_AVAILABLE_NO_JOINT_SCENARIOS"


def test_horizon_must_be_at_least_five_gameweeks():
    rows = [row for row in forecasts() if row["gameweek"] < 16]
    with pytest.raises(TeamExposureError, match="at least 5"):
        build_team_exposure_report(squad_player_ids=[1, 2, 3, 4],
                                   player_gameweek_forecasts=rows)


def test_incomplete_player_gameweek_coverage_fails_closed():
    rows = [row for row in forecasts() if not (row["fpl_element_id"] == 1 and row["gameweek"] == 12)]
    with pytest.raises(TeamExposureError, match="coverage is incomplete"):
        build_team_exposure_report(squad_player_ids=[1, 2, 3, 4],
                                   player_gameweek_forecasts=rows)


def test_duplicate_player_gameweek_forecast_is_rejected():
    rows = forecasts()
    rows.append(dict(rows[0]))
    with pytest.raises(TeamExposureError, match="duplicate"):
        build_team_exposure_report(squad_player_ids=[1, 2, 3, 4],
                                   player_gameweek_forecasts=rows)
