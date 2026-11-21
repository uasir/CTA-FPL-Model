import pytest

from train_fpl_exploratory_ridge import FEATURES, fit_ridge, predict, solve_linear_system, train_and_evaluate


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
                "prior_gw_minutes": str(prior_minutes),
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
    assert "team_difficulty_snapshot" in report["excluded_unverified_features"]
    assert "opponent_difficulty_snapshot" in report["excluded_unverified_features"]
    assert "fixture_count" in report["excluded_unverified_features"]
    assert len(model["points_model"]["coefficients"]) == len(model["points_model"]["feature_names"]) + 1



def test_minutes_predictions_are_bounded_per_fixture_before_dgw_aggregation():
    from train_fpl_exploratory_ridge import aggregate_predictions, FEATURES

    row = {
        "fpl_element_id": "7",
        "gameweek": "9",
        "target_total_points": "4",
        "target_minutes": "90",
        "prior5_gw_points_avg": "5",
        "prior_gw_minutes": "90",
    }
    row.update({name: "0" for name in FEATURES})
    row["fixture_count"] = "2"
    second = dict(row)
    second["target_total_points"] = "2"
    second["target_minutes"] = "45"

    over_90 = {
        "feature_names": list(FEATURES),
        "means": [0.0] * len(FEATURES),
        "scales": [1.0] * len(FEATURES),
        "coefficients": [120.0] + [0.0] * len(FEATURES),
    }
    below_zero = {
        "feature_names": list(FEATURES),
        "means": [0.0] * len(FEATURES),
        "scales": [1.0] * len(FEATURES),
        "coefficients": [-20.0] + [0.0] * len(FEATURES),
    }

    high = aggregate_predictions([row, second], over_90, over_90)[0]
    low = aggregate_predictions([row, second], below_zero, below_zero)[0]

    assert high["predicted_minutes"] == 180.0
    assert low["predicted_minutes"] == 0.0

def test_missing_xg_is_training_median_imputed_with_missingness_indicator():
    rows = [
        {"xg": "0", "target": "1"},
        {"xg": "2", "target": "2"},
        {"xg": "", "target": "3"},
        {"xg": "4", "target": "4"},
    ]
    model = fit_ridge(rows, "target", feature_names=("xg",))
    assert model["source_feature_names"] == ["xg"]
    assert model["feature_names"] == ["xg", "xg__missing"]
    assert model["imputation_values"] == [2.0]
    assert model["missing_value_policy"] == "TRAINING_MEDIAN_PLUS_MISSINGNESS_INDICATOR"
    assert predict(model, {"xg": ""}) != predict(model, {"xg": "0"})
    assert predict(model, {"xg": "0"}) == pytest.approx(predict(model, {"xg": 0.0}))


def test_all_missing_training_feature_fails_closed():
    with pytest.raises(ValueError, match="no observed training values"):
        fit_ridge(
            [{"xg": "", "target": "1"}, {"xg": "", "target": "2"},
             {"xg": "", "target": "3"}],
            "target",
            feature_names=("xg",),
        )


def test_missing_training_target_fails_closed():
    with pytest.raises(ValueError, match="Missing/non-finite training target"):
        fit_ridge(
            [{"xg": "0", "target": "1"}, {"xg": "1", "target": ""},
             {"xg": "2", "target": "3"}],
            "target",
            feature_names=("xg",),
        )


def test_training_report_counts_missing_xg_without_zero_imputation():
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
                "prior_gw_minutes": str(prior_minutes),
                "prior3_gw_minutes_avg": str(prior_minutes),
                "prior5_gw_minutes_avg": str(prior_minutes + 1),
                "prior3_gw_xg_avg": "" if player_id == 1 else ("0" if player_id == 2 else "0.5"),
                "prior3_gw_xa_avg": "0.3",
                "season_to_date_points_per90": str(4 + player_id / 10),
                "was_home": str(was_home),
                "team_difficulty_snapshot": "3",
                "opponent_difficulty_snapshot": "2",
                "target_total_points": str(2 + prior_points * 0.3 + (1 if was_home else 0)),
                "target_minutes": str(min(90, prior_minutes + (5 if was_home else 0))),
            })
    model, report = train_and_evaluate(rows)
    xg_index = FEATURES.index("prior3_gw_xg_avg")
    assert report["points_missing_feature_counts"]["prior3_gw_xg_avg"] == 3
    assert model["points_model"]["imputation_values"][xg_index] > 0
    assert "prior3_gw_xg_avg__missing" in model["points_model"]["feature_names"]

