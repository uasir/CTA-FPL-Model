import pytest

from build_11footy_lagged_research_features import build_lagged_research_features


def cta_row(fixture, kickoff, shots, player="42"):
    return {
        "fpl_element_id": player,
        "fpl_fixture_id": str(fixture),
        "match_kickoff_utc": kickoff,
        "shots": str(shots),
        "minutes_played": "90",
        "key_passes": "2",
        "tracked_xg_sum": "0.2",
        "identity_status": "PENDING_RESEARCH_ONLY",
        "research_only": True,
    }


def fpl_target(fixture, gameweek, deadline, kickoff, points):
    return {
        "season": "2026-27",
        "fpl_element_id": "42",
        "fixture_id": str(fixture),
        "gameweek": str(gameweek),
        "features_as_of_deadline": deadline,
        "kickoff_time": kickoff,
        "target_minutes": "90",
        "target_total_points": str(points),
        "target_goals": "0",
        "target_assists": "0",
    }


def test_cta_features_use_only_matches_strictly_before_each_deadline():
    cta = [
        cta_row(100, "2026-08-01T10:00:00Z", 2),
        cta_row(101, "2026-08-10T10:00:00Z", 4),
        cta_row(102, "2026-08-20T11:00:00Z", 6),  # exactly at GW2 deadline
        cta_row(103, "2026-08-29T10:00:00Z", 8),
        cta_row(502, "2026-08-30T10:00:00Z", 99),  # same target fixture, excluded even before cutoff
    ]
    targets = [
        fpl_target(501, 2, "2026-08-20T11:00:00Z", "2026-08-20T13:00:00Z", 8),
        fpl_target(502, 3, "2026-08-30T11:00:00Z", "2026-08-30T13:00:00Z", 6),
    ]
    output, report = build_lagged_research_features(
        cta, targets, {"point_in_time_status": "NOT_VERIFIED"}
    )
    by_fixture = {row["fixture_id"]: row for row in output}

    gw2 = by_fixture["501"]
    assert gw2["cta_prior_matches_count"] == 2
    assert gw2["cta_prior3_matches_shots_avg"] == 3.0
    assert gw2["target_total_points"] == "8"

    gw3 = by_fixture["502"]
    assert gw3["cta_prior_matches_count"] == 4
    assert gw3["cta_prior3_matches_shots_avg"] == 6.0
    assert gw3["cta_prior5_matches_shots_avg"] == 5.0
    assert gw3["cta_season_to_date_shots_sum"] == 20.0
    assert report["rows_with_prior_cta_history"] == 2
    assert report["fpl_point_in_time_status"] == "NOT_VERIFIED"
    assert report["prediction_training_eligible"] is False
    assert report["production_eligible"] is False


def test_no_prior_cta_history_is_missing_not_zero_and_research_only():
    targets = [
        fpl_target(600, 1, "2026-08-15T11:00:00Z", "2026-08-15T13:00:00Z", 2)
    ]
    output, report = build_lagged_research_features([], targets, {})
    row = output[0]
    assert row["cta_prior_matches_count"] == 0
    assert row["cta_prior3_matches_shots_avg"] == ""
    assert row["identity_status"] == "NO_PROVISIONAL_CTA_HISTORY"
    assert row["research_only"] is True
    assert report["status"] == "NO_PRIOR_CTA_COVERAGE"
    assert report["rows_without_prior_cta_history"] == 1


def test_duplicate_cta_player_fixture_and_target_before_deadline_are_rejected():
    duplicate = [
        cta_row(100, "2026-08-01T10:00:00Z", 2),
        cta_row(100, "2026-08-01T10:00:00Z", 3),
    ]
    target = [fpl_target(500, 2, "2026-08-20T11:00:00Z", "2026-08-20T13:00:00Z", 8)]
    with pytest.raises(ValueError, match="Duplicate provisional CTA"):
        build_lagged_research_features(duplicate, target, {})

    with pytest.raises(ValueError, match="does not kick off after"):
        build_lagged_research_features(
            [], [fpl_target(500, 2, "2026-08-20T11:00:00Z", "2026-08-20T10:59:00Z", 8)], {}
        )
