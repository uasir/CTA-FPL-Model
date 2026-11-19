import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from train_fpl_nested_tuned_ridge import evaluate, ALPHA_GRID


def synthetic_rows(gameweeks=10, players=20):
    rows = []
    for gw in range(1, gameweeks + 1):
        for player_id in range(1, players + 1):
            prior = float((gw * 2 + player_id) % 9)
            minutes = float(35 + (player_id % 12) * 5)
            was_home = (gw + player_id) % 2 == 0
            rows.append({
                "fpl_element_id": str(player_id),
                "gameweek": str(gw),
                "prior_gameweeks_count": str(max(0, gw - 1)),
                "prior_gw_points": str(prior),
                "prior3_gw_points_avg": str(prior + 0.3),
                "prior5_gw_points_avg": str(prior + 0.1),
                "prior_gw_minutes": str(minutes),
                "prior3_gw_minutes_avg": str(minutes),
                "prior5_gw_minutes_avg": str(minutes - 2),
                "prior3_gw_xg_avg": "0.4",
                "prior3_gw_xa_avg": "0.2",
                "season_to_date_points_per90": str(0.3 + player_id / 100),
                "was_home": str(was_home),
                "team_difficulty_snapshot": "3",
                "opponent_difficulty_snapshot": "2",
                "target_total_points": str(1.5 + prior * 0.25 + (0.8 if was_home else 0)),
                "target_minutes": str(min(90, minutes + (10 if was_home else 0))),
            })
    return rows


def test_nested_ridge_tuning_selects_alpha_without_using_outer_holdout():
    model, report = evaluate(synthetic_rows())
    assert report["status"] == "EXPLORATORY_ONLY"
    assert report["decision"] == "DO_NOT_PROMOTE"
    assert report["point_in_time_status"] == "NOT_VERIFIED"
    assert report["training_gameweeks"] == [1, 2, 3, 4, 5, 6]
    assert report["validation_gameweeks"] == [7, 8, 9, 10]
    assert report["inner_training_gameweeks"] == [1, 2, 3, 4]
    assert report["inner_validation_gameweeks"] == [5, 6]
    assert report["inner_alpha_selection"]["points"]["selected_alpha"] in ALPHA_GRID
    assert report["inner_alpha_selection"]["minutes"]["selected_alpha"] in ALPHA_GRID
    assert len(model["outer_validation_predictions_tuned"]) == 80


def test_nested_ridge_requires_eight_gameweeks():
    try:
        evaluate(synthetic_rows(gameweeks=7))
    except ValueError as exc:
        assert "At least eight gameweeks" in str(exc)
    else:
        raise AssertionError("Expected a minimum gameweek count error")


def test_nested_ridge_keeps_missing_xg_distinct_from_observed_zero():
    rows = synthetic_rows()
    for row in rows:
        if row["fpl_element_id"] == "1":
            row["prior3_gw_xg_avg"] = ""
    model, report = evaluate(rows)
    xg_index = report["features"].index("prior3_gw_xg_avg")
    assert report["missing_feature_policy"].startswith("Training-only median")
    assert report["outer_training_missing_feature_counts"]["prior3_gw_xg_avg"] == 5
    assert model["fixed_alpha_10"]["points_model"]["imputation_values"][xg_index] > 0
