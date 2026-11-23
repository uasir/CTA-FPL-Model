import pytest

from build_cta_abc_11footy_points import build_training_rows, make_features, run


def _match(gw, points, kickoff, player="10"):
    return {
        "join_status": "VERIFIED_IDENTITY_AND_FIXTURE",
        "fpl_element_id": player, "fpl_fixture_id": str(gw),
        "gameweek": str(gw), "match_kickoff_utc": f"2026-01-{kickoff:02d}T12:00:00Z",
        "fpl_total_points": str(points), "minutes_played": "90",
        "key_passes": "2", "tracked_xg_sum": "0.2", "shots": "3",
        "attempts_inside_box": "2", "goals": "0", "fouls_committed": "1",
    }


def test_training_features_use_only_prior_player_matches():
    rows = build_training_rows([_match(1, 2, 1), _match(2, 5, 8), _match(3, 3, 15), _match(4, 8, 22)])
    assert len(rows) == 1
    assert rows[0]["gameweek"] == 4
    assert rows[0]["target_fpl_total_points"] == 8
    assert rows[0]["abc_player_key_pass_rate"] == 2


def test_unverified_player_match_rows_are_excluded():
    panel = [_match(i, i, i * 3) for i in range(1, 5)]
    panel[0]["join_status"] = "PENDING_RESEARCH_ONLY"
    assert build_training_rows(panel) == []


def test_11footy_point_forecast_runs_and_aggregates_gameweek():
    rows = []
    for player in ("10", "20", "30"):
        for gw in range(1, 11):
            row = _match(gw, (gw % 5) + 1, gw * 2, player)
            row["key_passes"] = str((gw % 3) + 1)
            row["tracked_xg_sum"] = str(0.1 + (gw % 4) * 0.05)
            rows.append(row)
    training = build_training_rows(rows)
    upcoming = [{
        "fpl_element_id": "10", "gameweek": "12", "fixture_id": "100", "research_eligible_for_analysis": True,
        "abc_player_key_pass_rate": 1.5, "abc_player_tracked_xg_rate": 0.15,
        "abc_recent_key_pass_trend": 0.0, "abc_recent_xg_trend": 0.0,
        "abc_player_fouls_committed_rate": 1.0, "abc_minutes_trend": 0.0,
        "abc_attacking_involvement": 4.0, "abc_threat_creation_rate": 1.5,
        "abc_threat_reception_rate": None, "abc_threat_realisation_rate": 0.0,
        "abc_attacking_involvement_rate": 5.0,
    }]
    model, forecasts, report, validation = run(training, upcoming, holdout_gameweeks=2)
    assert len(model["coefficients"]) > 1
    assert len(forecasts) == 1
    assert forecasts[0]["gameweek"] == 12
    assert forecasts[0]["predicted_points"] == forecasts[0]["predicted_points"]
    assert report["status"] == "EXPLORATORY_FORECAST_BUILT"
    assert report["validation_player_gameweeks"] > 0



def test_goal_realisation_feature_uses_same_mean_definition_as_inference():
    prior = [
        _match(1, 2, 1),
        {**_match(2, 5, 8), "goals": "1", "tracked_xg_sum": "0.1"},
        {**_match(3, 3, 15), "goals": "0", "tracked_xg_sum": "0.2"},
        {**_match(4, 8, 22), "goals": "0", "tracked_xg_sum": "0.3"},
    ]
    features = make_features(prior)
    assert features["abc_threat_realisation_rate"] == pytest.approx(5 / 3)


def test_double_gameweek_fixtures_share_pre_gameweek_history():
    panel = [_match(1, 2, 1), _match(2, 5, 8), _match(3, 3, 15)]
    panel.extend([
        {**_match(4, 8, 22), "fpl_fixture_id": "gw4-a", "key_passes": "1"},
        {**_match(4, 10, 23), "fpl_fixture_id": "gw4-b", "key_passes": "20"},
    ])
    rows = build_training_rows(panel)
    gw4 = [row for row in rows if row["gameweek"] == 4]
    assert len(gw4) == 2
    assert gw4[0]["abc_player_key_pass_rate"] == gw4[1]["abc_player_key_pass_rate"]
    assert gw4[0]["baseline_prior5_points_per_fixture"] == gw4[1]["baseline_prior5_points_per_fixture"]


def test_validation_report_compares_abc_with_points_baselines():
    rows = []
    for player in ("10", "20", "30"):
        for gw in range(1, 11):
            row = _match(gw, (gw % 5) + 1, gw * 2, player)
            row["key_passes"] = str((gw % 3) + 1)
            row["tracked_xg_sum"] = str(0.1 + (gw % 4) * 0.05)
            rows.append(row)
    training = build_training_rows(rows)
    upcoming = [{
        "fpl_element_id": "10", "gameweek": "12", "fixture_id": "100", "research_eligible_for_analysis": True,
        "abc_player_key_pass_rate": 1.5, "abc_player_tracked_xg_rate": 0.15,
        "abc_recent_key_pass_trend": 0.0, "abc_recent_xg_trend": 0.0,
        "abc_player_fouls_committed_rate": 1.0, "abc_minutes_trend": 0.0,
        "abc_attacking_involvement": 4.0, "abc_threat_creation_rate": 1.5,
        "abc_threat_reception_rate": 2.0, "abc_threat_realisation_rate": 0.0,
        "abc_attacking_involvement_rate": 5.0,
    }]
    _, _, report, validation = run(training, upcoming, holdout_gameweeks=2)
    assert "prior5_player_points" in report["validation_baselines"]
    assert "training_mean" in report["validation_baselines"]
    assert "training_median" in report["validation_baselines"]
    assert report["ridge_tuning"]["method"] == "EXPANDING_GAMEWEEK_FOLDS_WITHIN_OUTER_TRAINING_PERIOD"
    assert report["ridge_tuning"]["selected_lambda"] in {0.1, 1.0, 10.0, 100.0}
    assert not set(report["ridge_tuning"]["validation_gameweeks"]) & set(report["validation_gameweeks"])
    assert all("baseline_prior5_points" in row for row in validation)
