import pytest

from build_11footy_lagged_verified_features import (
    build_lagged_verified_features,
    build_upcoming_targets,
)


def cta_row(fixture, kickoff, shots, player="42", join_status="VERIFIED_IDENTITY_AND_FIXTURE"):
    return {
        "fpl_element_id": player,
        "fpl_fixture_id": str(fixture),
        "match_kickoff_utc": kickoff,
        "shots": str(shots),
        "minutes_played": "90",
        "key_passes": "2",
        "tracked_xg_sum": "0.2",
        "join_status": join_status,
    }


def target(fixture, gameweek, deadline, kickoff, player="42"):
    return {
        "season": "2026-27",
        "fpl_element_id": player,
        "fpl_player_code": "12345",
        "fpl_player_name": "Example Player",
        "fixture_id": str(fixture),
        "gameweek": str(gameweek),
        "features_as_of_deadline": deadline,
        "kickoff_time": kickoff,
        "team_id": "1",
        "opponent_team_id": "2",
        "was_home": True,
    }


def source_report(built_at="2026-08-01T00:00:00Z"):
    return {
        "join_ready": True,
        "verified_crosswalk_rows": 340,
        "verified_player_match_panel_rows": 5000,
        "source_built_at": built_at,
        "source_hashes": {"11footy_match_database_sha256": "a" * 64},
        "attribution": "11footy; CC BY-NC 4.0; non-commercial use only.",
    }


def test_verified_cta_features_use_only_prior_matches_and_verified_rows():
    cta = [
        cta_row(100, "2026-08-01T10:00:00Z", 2),
        cta_row(101, "2026-08-10T10:00:00Z", 4),
        cta_row(102, "2026-08-20T11:00:00Z", 6),  # exactly at deadline
        cta_row(103, "2026-08-29T10:00:00Z", 8),
        cta_row(502, "2026-08-30T10:00:00Z", 99),  # same target fixture
        cta_row(104, "2026-08-05T10:00:00Z", 88, join_status="PENDING"),
    ]
    targets = [
        target(501, 2, "2026-08-20T11:00:00Z", "2026-08-20T13:00:00Z"),
        target(502, 3, "2026-08-30T11:00:00Z", "2026-08-30T13:00:00Z"),
    ]
    output, report = build_lagged_verified_features(
        cta, targets, source_report(), {"fetched_at_utc": "2026-08-19T00:00:00Z"}, {"42"}
    )
    by_fixture = {row["fixture_id"]: row for row in output}
    gw2 = by_fixture["501"]
    assert gw2["cta_prior_matches_count"] == 2
    assert gw2["cta_prior3_matches_shots_avg"] == 3.0
    assert gw2["identity_status"] == "VERIFIED_IDENTITY_AND_PRIOR_CTA_HISTORY"
    assert gw2["team_id"] == "1"
    assert gw2["opponent_team_id"] == "2"
    assert gw2["was_home"] is True
    gw3 = by_fixture["502"]
    assert gw3["cta_prior_matches_count"] == 4
    assert gw3["cta_prior3_matches_shots_avg"] == 6.0
    assert gw3["cta_prior5_matches_shots_avg"] == 5.0
    assert gw3["cta_season_to_date_shots_sum"] == 20.0
    assert report["rows_with_prior_cta_history"] == 2
    assert report["source_cta_rows_skipped"]["not_verified_identity_and_fixture"] == 1
    assert report["prediction_training_eligible"] is False
    assert report["production_eligible"] is False


def test_provider_snapshot_after_deadline_is_excluded():
    output, report = build_lagged_verified_features(
        [cta_row(100, "2026-08-01T10:00:00Z", 2)],
        [target(501, 2, "2026-08-20T11:00:00Z", "2026-08-20T13:00:00Z")],
        source_report("2026-08-21T00:00:00Z"), None, {"42"}
    )
    row = output[0]
    assert row["cta_prior_matches_count"] == 0
    assert row["cta_snapshot_available_as_of_deadline"] is False
    assert row["identity_status"] == "SOURCE_SNAPSHOT_AFTER_DEADLINE"
    assert report["rows_without_source_snapshot_available_as_of_deadline"] == 1
    assert report["rows_with_prior_cta_history"] == 0


def test_missing_source_snapshot_timestamp_fails_closed():
    output, report = build_lagged_verified_features(
        [cta_row(100, "2026-08-01T10:00:00Z", 2)],
        [target(501, 2, "2026-08-20T11:00:00Z", "2026-08-20T13:00:00Z")],
        source_report(""), None, {"42"}
    )
    assert output[0]["cta_prior_matches_count"] == 0
    assert report["status"] == "BLOCKED_UNKNOWN_SOURCE_SNAPSHOT_TIME"



def test_verified_identity_without_prior_history_is_distinguished_from_unmapped():
    mapped, _ = build_lagged_verified_features(
        [], [target(501, 2, "2026-08-20T11:00:00Z", "2026-08-20T13:00:00Z")],
        source_report(), None, {"42"},
    )
    assert mapped[0]["identity_verified"] is True
    assert mapped[0]["identity_status"] == "VERIFIED_IDENTITY_NO_PRIOR_HISTORY"
    unmapped, _ = build_lagged_verified_features(
        [], [target(501, 2, "2026-08-20T11:00:00Z", "2026-08-20T13:00:00Z")],
        source_report(), None, set(),
    )
    assert unmapped[0]["identity_verified"] is False
    assert unmapped[0]["identity_status"] == "NO_VERIFIED_IDENTITY"

def test_duplicate_verified_cta_or_target_keys_are_rejected():
    duplicate_cta = [
        cta_row(100, "2026-08-01T10:00:00Z", 2),
        cta_row(100, "2026-08-01T10:00:00Z", 3),
    ]
    with pytest.raises(ValueError, match="Duplicate verified CTA"):
        build_lagged_verified_features(
            duplicate_cta,
            [target(501, 2, "2026-08-20T11:00:00Z", "2026-08-20T13:00:00Z")],
            source_report(),
        )
    duplicate_targets = [
        target(501, 2, "2026-08-20T11:00:00Z", "2026-08-20T13:00:00Z"),
        target(501, 2, "2026-08-20T11:00:00Z", "2026-08-20T13:00:00Z"),
    ]
    with pytest.raises(ValueError, match="Duplicate FPL target"):
        build_lagged_verified_features([], duplicate_targets, source_report())


def test_target_kickoff_must_follow_deadline_and_identity_join_must_be_ready():
    with pytest.raises(ValueError, match="does not kick off after"):
        build_lagged_verified_features(
            [], [target(501, 2, "2026-08-20T11:00:00Z", "2026-08-20T10:59:00Z")],
            source_report(),
        )
    bad_report = source_report()
    bad_report["join_ready"] = False
    with pytest.raises(ValueError, match="not join-ready"):
        build_lagged_verified_features(
            [], [target(501, 2, "2026-08-20T11:00:00Z", "2026-08-20T13:00:00Z")],
            bad_report,
        )


def test_build_upcoming_targets_uses_next_deadline_and_team_rosters():
    players = [
        {"season": "2026-27", "fpl_element_id": "1", "fpl_player_code": "11", "player_name": "Home Player", "team_id": "1"},
        {"season": "2026-27", "fpl_element_id": "2", "fpl_player_code": "22", "player_name": "Away Player", "team_id": "2"},
        {"season": "2026-27", "fpl_element_id": "3", "fpl_player_code": "33", "player_name": "Other Player", "team_id": "3"},
    ]
    fixtures = [
        {"fixture_id": "501", "gameweek": "11", "kickoff_time": "2026-11-21T12:00:00Z", "team_h_id": "1", "team_a_id": "2"},
        {"fixture_id": "502", "gameweek": "12", "kickoff_time": "2026-11-28T12:00:00Z", "team_h_id": "2", "team_a_id": "3"},
    ]
    bootstrap = {"events": [{"id": 11, "deadline_time": "2026-11-21T11:00:00Z"}]}
    metadata = {"fetched_at_utc": "2026-11-19T05:00:00Z", "next_deadline_event_id": 11}
    rows, report = build_upcoming_targets(players, fixtures, bootstrap, metadata)
    assert len(rows) == 2
    assert {row["fpl_element_id"] for row in rows} == {"1", "2"}
    assert report["target_gameweek"] == 11
    assert report["target_fixture_count"] == 1
    assert report["target_player_fixture_rows"] == 2
