from evaluate_wyscout_cta_incremental_value import evaluate


def test_chronological_holdout_uses_only_previously_available_features():
    rows = []
    for i in range(120):
        kickoff = f"2017-{1 + (i // 28):02d}-{1 + (i % 28):02d}T14:00:00+00:00"
        row = {
            "fpl_element_id": str(1 + i % 12),
            "fixture_id": str(1000 + i),
            "kickoff_time_utc": kickoff,
            "prior_matches_count": "3",
            "target_fpl_total_points": str(2 + (i % 5)),
            "fpl_total_points_prior_3_avg": "4",
            "fpl_total_points_prior_5_avg": "3.8",
            "fpl_minutes_prior_3_avg": "75",
            "fpl_minutes_prior_5_avg": "70",
        }
        for feature in (
            "pass_attempts", "pass_completions", "key_pass_attempts",
            "smart_pass_attempts", "through_pass_attempts", "opportunity_pass_attempts",
            "progressive_pass_attempts", "progressive_pass_completions",
            "final_third_entry_pass_attempts", "danger_zone_entry_pass_attempts",
            "threat_creation_pass_attempts", "threat_creation_pass_completions",
            "progressive_carry_attempts", "shot_attempts", "accurate_shot_attempts",
            "shot_opportunity_attempts", "dangerous_ball_losses", "offside_events",
            "duel_events", "duels_won", "duels_lost",
        ):
            row[f"{feature}_prior_3_avg"] = str(i % 7)
            row[f"{feature}_prior_5_avg"] = str(i % 5)
            row[f"{feature}_per90_prior_3_avg"] = str((i % 7) / 1.5)
            row[f"{feature}_per90_prior_5_avg"] = str((i % 5) / 1.5)
        rows.append(row)
    report = evaluate(rows)
    assert report["status"] == "PASS_EXPLORATORY_CHRONOLOGICAL_CTA_COMPARISON"
    assert report["train_rows"] + report["test_rows"] == 120
    assert report["train_latest_kickoff_utc"] < report["test_earliest_kickoff_utc"]
    assert report["cta_feature_count"] > 0
    assert report["decision_use_status"] == "RESEARCH_ONLY_NOT_IN_BASELINE"


def test_evaluator_rejects_insufficient_temporal_coverage():
    rows = [{
        "fpl_element_id": "1",
        "fixture_id": "100",
        "kickoff_time_utc": "2017-08-12T14:00:00+00:00",
        "prior_matches_count": "1",
        "target_fpl_total_points": "4",
        "fpl_total_points_prior_3_avg": "3",
        "fpl_minutes_prior_3_avg": "80",
        "shot_attempts_prior_3_avg": "1",
    }]
    try:
        evaluate(rows)
    except ValueError as exc:
        assert "five distinct" in str(exc)
    else:
        raise AssertionError("insufficient time coverage must fail closed")
