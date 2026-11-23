import pytest

from build_cta_abc_11footy_only_panel import build_panel


def _row(**overrides):
    row = {
        "season": "2026-27", "fpl_element_id": "10", "fixture_id": "101",
        "gameweek": "12", "kickoff_time": "2026-11-28T12:30:00Z",
        "features_as_of_deadline": "2026-11-28T11:00:00Z",
        "cta_snapshot_available_as_of_deadline": "True",
        "cta_source_snapshot_as_of": "2026-11-10T12:21:18Z",
        "identity_verified": "True", "cta_prior_matches_count": "5",
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
    row.update(overrides)
    return row


def _report():
    return {
        "source_built_at": "2026-11-10T12:21:18Z",
        "source_hashes": {"11footy_match_database_sha256": "a" * 64},
        "attribution": "11footy; CC BY-NC 4.0; non-commercial use only.",
    }


def test_builds_abc_contract_without_any_opta_input():
    rows, report = build_panel([_row()], _report())
    row = rows[0]
    assert row["abc_status"] == "RESEARCH_ONLY"
    assert row["research_eligible_for_analysis"] is True
    assert row["abc_player_key_pass_rate"] == pytest.approx(1.8)
    assert row["abc_team_final_third_entries"] == ""
    assert row["abc_team_interceptions"] == ""
    assert row["abc_player_fouls_committed_rate"] == pytest.approx(0.75)
    assert row["abc_minutes_trend"] == pytest.approx(10)
    assert row["abc_threat_realisation_rate"] == pytest.approx(2 / 3)
    assert report["opta_dependency"] is False
    assert report["opta_features_used"] is False
    assert report["model_training_eligible"] is False
    assert report["prediction_validation"] == "NOT_EVALUATED"


def test_unverified_identity_never_becomes_analysis_eligible():
    rows, report = build_panel([_row(identity_verified="False")], _report())
    assert rows[0]["research_eligible_for_analysis"] is False
    assert report["verified_identity_rows"] == 0
    assert report["analysis_eligible_rows"] == 0


def test_snapshot_after_deadline_suppresses_all_11footy_features():
    row = _row(
        cta_snapshot_available_as_of_deadline="False",
        cta_source_snapshot_as_of="2026-11-29T00:00:00Z",
    )
    report = _report()
    report["source_built_at"] = "2026-11-29T00:00:00Z"
    rows, summary = build_panel([row], report)
    assert rows[0]["research_eligible_for_analysis"] is False
    assert rows[0]["abc_player_key_pass_rate"] == ""
    assert rows[0]["abc_minutes_trend"] == ""
    assert summary["snapshot_available_rows"] == 0


def test_duplicate_player_fixture_targets_are_rejected():
    with pytest.raises(ValueError, match="Duplicate 11footy"):
        build_panel([_row(), _row()], _report())


def test_target_fixture_must_follow_deadline():
    with pytest.raises(ValueError, match="kick off after"):
        build_panel([_row(kickoff_time="2026-11-28T10:59:00Z")], _report())



def test_reports_per90_values_with_low_minute_denominators():
    row = _row(
        cta_prior3_matches_minutes_played_avg="1",
        cta_prior3_matches_key_passes_avg="3",
        cta_prior3_matches_tracked_xg_sum_avg="0.5",
        cta_prior3_matches_shots_avg="1",
        cta_prior3_matches_fouls_committed_avg="1",
    )
    rows, report = build_panel([row], _report())
    assert rows[0]["abc_player_key_pass_rate"] == pytest.approx(270)
    diagnostic = report["per90_exposure_diagnostics"]["abc_player_key_pass_rate"]
    assert diagnostic["observed_rows"] == 1
    assert diagnostic["denominator_le_5_minutes_rows"] == 1
    assert diagnostic["largest_examples"][0]["numerator_prior3_avg"] == pytest.approx(3)
    assert diagnostic["largest_examples"][0]["minutes_prior3_avg"] == pytest.approx(1)
    assert diagnostic["largest_examples"][0]["per90_value"] == pytest.approx(270)


def test_source_snapshot_must_match_panel_row_snapshot():
    with pytest.raises(ValueError, match="disagrees"):
        build_panel([_row(cta_source_snapshot_as_of="2026-11-09T12:00:00Z")], _report())
