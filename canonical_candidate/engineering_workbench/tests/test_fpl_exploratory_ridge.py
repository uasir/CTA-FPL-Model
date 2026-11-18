import pytest

from train_fpl_exploratory_ridge import solve_linear_system, train_and_evaluate


def test_gaussian_elimination_solver():
    result = solve_linear_system([[3, 2], [1, 2]], [5, 5])
    assert result == pytest.approx([0.0, 2.5], abs=1e-12)


def test_ridge_pipeline_uses_temporal_holdout_and_stays_exploratory():
    rows = []
    for gameweek in range(1, 9):
        for player_id in range(1, 6):
            prior_points = float(gameweek + player_id)
            prior_minutes = float(30 + player_id * 5)
            was_home = (gameweek + player_id) % 2 == 0
            rows.append({
                "fpl_element_id": str(player_id),
                "gameweek": str(gameweek),
                "prior_gameweeks_count": str(max(0, gameweek - 1)),
                "prior_gw_points": str(prior_points),
                "prior3_gw_points_avg": str(prior_points + 0.2),
                "prior5_gw_points_avg": str(prior_points + 0.4),
                "prior3_gw_minutes_avg": str(prior_minutes),
                "prior5_gw_minutes_avg": str(prior_minutes + 1),
                "prior3_gw_xg_avg": "0.5",
                "prior3_gw_xa_avg": "0.3",
                "season_to_date_points_per90": str(4 + player_id / 10),
                "was_home": str(was_home),
                "team_difficulty_snapshot": "3",
                "opponent_difficulty_snapshot": "2",
                "target_total_points": str(2 + prior_points * 0.3 + (1 if was_home else 0)),
                "target_minutes": str(min(90, prior_minutes + (5 if was_home else 0))),
            })
    model, report = train_and_evaluate(rows)
    assert report["status"] == "EXPLORATORY_ONLY"
    assert report["point_in_time_status"] == "NOT_VERIFIED"
    assert report["training_gameweeks"] == [1, 2, 3, 4]
    assert report["validation_gameweeks"] == [5, 6, 7, 8]
    assert report["validation_player_gameweek_rows"] == 20
    assert report["decision"] == "DO_NOT_PROMOTE"
    assert len(model["points_model"]["coefficients"]) == len(model["points_model"]["feature_names"]) + 1
