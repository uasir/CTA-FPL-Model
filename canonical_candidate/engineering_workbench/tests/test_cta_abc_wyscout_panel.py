from build_cta_abc_wyscout_panel import build_panel


def _row():
    return {
        "fpl_element_id": "1", "fixture_id": "1001",
        "kickoff_time_utc": "2017-08-19T14:00:00+00:00",
        "feature_cutoff_time_utc": "2017-08-19T12:00:00+00:00",
        "feature_cutoff_policy": "CONSERVATIVE_EARLIEST_GAMEWEEK_KICKOFF",
        "target_fpl_total_points": "8", "target_fpl_minutes": "90",
        "prior_matches_count": "4", "team_prior_matches_count": "4",
        "progressive_pass_completions_per90_prior_3_avg": "1.5",
        "progressive_carry_attempts_per90_prior_3_avg": "0.5",
        "final_third_entry_pass_attempts_per90_prior_3_avg": "0.8",
        "threat_creation_pass_attempts_per90_prior_3_avg": "2.0",
        "threat_creation_pass_attempts_per90_prior_5_avg": "1.5",
        "key_pass_attempts_per90_prior_3_avg": "1.0",
        "key_pass_attempts_per90_prior_5_avg": "0.8",
        "key_pass_attempts_prior_3_avg": "0.8",
        "shot_attempts_per90_prior_3_avg": "2.0",
        "shot_attempts_prior_3_avg": "2.0",
        "goals_prior_3_avg": "0.2",
        "fpl_minutes_prior_3_avg": "80",
        "fpl_minutes_prior_5_avg": "70",
        "ground_defensive_duels_won_prior_3_avg": "1.0",
        "ground_defensive_duels_lost_prior_3_avg": "1.0",
        "ground_defensive_duel_events_per90_prior_3_avg": "2.0",
        "aerial_duel_events_per90_prior_3_avg": "0.5",
        "clearance_events_per90_prior_3_avg": "0.3",
        "foul_events_per90_prior_3_avg": "0.2",
        "team_final_third_entry_pass_attempts_prior_3_avg": "12",
        "team_ground_defensive_duels_won_prior_3_avg": "4",
        "team_aerial_duels_won_prior_3_avg": "2",
        "team_interception_events_prior_3_avg": "1",
        "opponent_shot_attempts_allowed_prior_3_avg": "10",
        "opponent_threat_creation_pass_attempts_allowed_prior_3_avg": "30",
    }


def test_wyscout_panel_maps_a_b_c_without_inventing_xg_or_receivers():
    rows, report = build_panel([_row()], {"source_hashes": {"wyscout": "abc"}})
    row = rows[0]
    assert row["abc_status"] == "RESEARCH_ONLY"
    assert row["research_eligible_for_analysis"] is True
    assert row["abc_progressive_passes"] == 1.5
    assert row["abc_recent_action_trend"] == 0.5
    assert row["abc_team_final_third_entries"] == 12.0
    assert row["abc_duel_success_rate"] == 0.5
    assert abs(row["abc_defensive_actions"] - 2.8) < 1e-9
    assert row["abc_opponent_threat_allowed"] == 10.0
    assert row["abc_defensive_exposure"] == 30.0
    assert row["abc_team_duels_won"] == 6.0
    assert row["abc_minutes_trend"] == 10.0
    assert row["abc_attacking_involvement"] == 2.8
    assert row["abc_threat_realisation_rate"] == 0.1
    assert row["abc_dangerous_receipts"] == ""
    assert row["abc_player_tracked_xg_rate"] == ""
    assert row["abc_threat_reception_rate"] == ""
    assert row["abc_contextual_threat_score"] == ""
    assert row["target_fpl_total_points"] == 8.0
    assert report["model_training_eligible"] is False
    assert report["point_in_time_status"] == "NOT_VERIFIED"


def test_kickoff_fallback_is_not_research_eligible():
    source = _row()
    source["feature_cutoff_policy"] = "TARGET_KICKOFF_FALLBACK_NOT_POINT_IN_TIME"
    rows, report = build_panel([source], {})
    assert rows[0]["research_eligible_for_analysis"] is False
    assert report["research_eligible_rows"] == 0


def test_missing_provider_features_remain_null_not_zero():
    source = _row()
    source["progressive_pass_completions_per90_prior_3_avg"] = ""
    source["opponent_shot_attempts_allowed_prior_3_avg"] = ""
    rows, _ = build_panel([source], {})
    assert rows[0]["abc_progressive_passes"] == ""
    assert rows[0]["abc_opponent_threat_allowed"] == ""


def test_first_fixture_in_gameweek_can_use_equal_exclusive_cutoff():
    source = _row()
    source["feature_cutoff_time_utc"] = source["kickoff_time_utc"]
    rows, _ = build_panel([source], {})
    assert rows[0]["feature_cutoff_policy"] == "CONSERVATIVE_EARLIEST_GAMEWEEK_KICKOFF"
    assert rows[0]["research_eligible_for_analysis"] is True
