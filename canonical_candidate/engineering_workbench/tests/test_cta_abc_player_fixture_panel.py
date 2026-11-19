from build_cta_abc_player_fixture_panel import build_panel


def _cta_row():
    return {
        "season": "2026-27", "fpl_element_id": "10", "fixture_id": "101",
        "gameweek": "11", "kickoff_time": "2026-11-21T12:30:00Z",
        "features_as_of_deadline": "2026-11-21T11:00:00Z",
        "cta_snapshot_available_as_of_deadline": "True",
        "cta_source_snapshot_as_of": "2026-11-10T12:21:18Z",
        "identity_verified": "True", "team_id": "1", "opponent_team_id": "2",
        "cta_prior3_matches_minutes_played_avg": "60",
        "cta_prior5_matches_minutes_played_avg": "50",
        "cta_prior3_matches_key_passes_avg": "1.2",
        "cta_prior5_matches_key_passes_avg": "1.0",
        "cta_prior3_matches_tracked_xg_sum_avg": "0.3",
        "cta_prior5_matches_tracked_xg_sum_avg": "0.2",
        "cta_prior3_matches_shots_avg": "0.8",
        "cta_prior3_matches_attempts_inside_box_avg": "0.5",
        "cta_prior3_matches_goals_avg": "0.2",
        "cta_prior3_matches_fouls_committed_avg": "0.5",
    }


def _opta_rows(policy="OFFICIAL_FPL_DEADLINE"):
    common = {
        "features_as_of": "2026-11-21T11:00:00Z",
        "feature_cutoff_policy": policy,
        "opta_prior3_finalThirdEntries_avg": "15",
        "opta_prior3_successfulDribbles_avg": "8",
        "opta_prior3_opponentExpectedGoals_avg": "1.2",
        "opta_prior3_opponentAttemptsIbox_avg": "5",
        "opta_prior3_interception_avg": "3",
        "opta_prior3_tacklesWon_avg": "2",
        "opta_prior3_ballRecovery_avg": "6",
        "opta_prior3_recoveries_avg": "7",
        "opta_prior3_duelWon_avg": "9",
    }
    return [
        {"fixture_id": "101", "team_id": "1", **common},
        {"fixture_id": "101", "team_id": "2", **common},
    ]


def _reports(opta_as_of="2026-11-09T21:54:16Z"):
    return (
        {"source_built_at": "2026-11-10T12:21:18Z"},
        {"team_features": {"source_snapshot_as_of": opta_as_of}},
    )


def test_integrates_a_b_c_with_explicit_missingness_and_deadline_guards():
    rows, report = build_panel([_cta_row()], _opta_rows(), *_reports())
    row = rows[0]
    assert row["abc_status"] == "RESEARCH_ONLY"
    assert row["research_eligible_for_analysis"] is True
    assert row["abc_team_final_third_entries"] == 15.0
    assert row["abc_opponent_threat_allowed"] == 1.2
    assert row["abc_opponent_box_attempts_allowed"] == 5.0
    assert row["abc_minutes_trend"] == 10.0
    assert abs(row["abc_threat_realisation_rate"] - (2 / 3)) < 1e-9
    assert row["abc_progressive_passes"] == ""
    assert row["abc_contextual_threat_score"] == ""
    assert "target_total_points" not in row
    assert report["model_training_eligible"] is False
    assert report["prediction_validation"] == "NOT_EVALUATED"


def test_opta_kickoff_fallback_is_not_research_eligible_for_deadline_prediction():
    rows, _ = build_panel([_cta_row()], _opta_rows("TARGET_KICKOFF_FALLBACK"), *_reports())
    row = rows[0]
    assert row["opta_deadline_cutoff_verified"] is False
    assert row["research_eligible_for_analysis"] is False
    assert row["abc_team_final_third_entries"] == ""


def test_provider_snapshot_after_deadline_cannot_supply_player_features():
    cta = _cta_row()
    cta["cta_source_snapshot_as_of"] = "2026-11-22T00:00:00Z"
    cta["cta_snapshot_available_as_of_deadline"] = "False"
    cta_report, opta_report = _reports()
    cta_report["source_built_at"] = "2026-11-22T00:00:00Z"
    rows, _ = build_panel([cta], _opta_rows(), cta_report, opta_report)
    row = rows[0]
    assert row["cta_snapshot_available_as_of_deadline"] is False
    assert row["abc_player_key_pass_rate"] == ""
    assert row["abc_minutes_trend"] == ""
