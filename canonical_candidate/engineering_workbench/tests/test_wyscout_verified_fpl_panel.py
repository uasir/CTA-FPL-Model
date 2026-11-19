from build_wyscout_verified_fpl_panel import build_verified_panel


def crosswalk(provider_id=101, fpl_id=1, status="VERIFIED_CROSS_PROVIDER_IDENTITY_AND_FPL_HISTORY"):
    return {
        "provider_player_id": str(provider_id),
        "fpl_element_id": str(fpl_id),
        "verification_status": status,
    }


def feature_row(provider_id, match_id, shots, match_date):
    return {
        "provider_player_id": str(provider_id),
        "provider_match_id": str(match_id),
        "match_date": match_date,
        "shots_attempts": str(shots),
        "shot_attempts": str(shots),
        "pass_attempts": "20",
        "progressive_pass_attempts": "4",
        "threat_creation_pass_attempts": "5",
    }


def history(fpl_id, fixture_id, kickoff, points, minutes=90):
    return {
        "element": str(fpl_id),
        "fixture": str(fixture_id),
        "kickoff_time": kickoff,
        "total_points": str(points),
        "minutes": str(minutes),
        "goals_scored": "0",
        "assists": "0",
        "bonus": "0",
        "bps": "10",
    }


def test_only_verified_identity_rows_join_and_features_are_strictly_lagged():
    matches = [
        feature_row(101, 500, 2, "2017-08-12"),
        feature_row(101, 501, 5, "2017-08-19"),
        feature_row(202, 500, 9, "2017-08-12"),
    ]
    crosswalk = [
        crosswalk_row for crosswalk_row in [
            crosswalk(101, 1),
            crosswalk(202, 2, "NOT_VERIFIED"),
        ]
    ]
    fixtures = {500: 1000, 501: 1001}
    fpl = [
        history(1, 1000, "2017-08-12T14:00:00Z", 2),
        history(1, 1001, "2017-08-19T14:00:00Z", 8),
        history(2, 1000, "2017-08-12T14:00:00Z", 1),
    ]
    panel, lagged, report = build_verified_panel(matches, crosswalk, fpl, fixtures)
    assert len(panel) == 2
    assert report["unverified_identity_rows_excluded"] == 1
    assert panel[0]["fpl_element_id"] == 1
    assert panel[1]["fpl_total_points"] == 8.0
    assert lagged[0]["prior_matches_count"] == 0
    assert lagged[1]["prior_matches_count"] == 1
    assert lagged[1]["shot_attempts_prior_3_avg"] == 2.0
    assert lagged[1]["target_fpl_total_points"] == 8.0


def test_same_kickoff_time_is_not_counted_as_prior_history():
    matches = [feature_row(101, 500, 2, "2017-08-12"), feature_row(101, 501, 7, "2017-08-12")]
    fixtures = {500: 1000, 501: 1001}
    fpl = [
        history(1, 1000, "2017-08-12T14:00:00Z", 2),
        history(1, 1001, "2017-08-12T14:00:00Z", 7),
    ]
    _, lagged, _ = build_verified_panel(matches, [crosswalk()], fpl, fixtures)
    assert all(row["prior_matches_count"] == 0 for row in lagged)


def test_duplicate_fpl_player_fixture_rows_fail_closed():
    matches = [feature_row(101, 500, 2, "2017-08-12")]
    fpl = [
        history(1, 1000, "2017-08-12T14:00:00Z", 2),
        history(1, 1000, "2017-08-12T14:00:00Z", 2),
    ]
    try:
        build_verified_panel(matches, [crosswalk()], fpl, {500: 1000})
    except ValueError as exc:
        assert "Duplicate historical FPL" in str(exc)
    else:
        raise AssertionError("duplicate FPL player-fixture rows must fail closed")


def test_duplicate_provider_player_match_rows_fail_closed():
    matches = [feature_row(101, 500, 2, "2017-08-12"), feature_row(101, 500, 2, "2017-08-12")]
    fpl = [history(1, 1000, "2017-08-12T14:00:00Z", 2)]
    try:
        build_verified_panel(matches, [crosswalk()], fpl, {500: 1000})
    except ValueError as exc:
        assert "Duplicate Wyscout player-match" in str(exc)
    else:
        raise AssertionError("duplicate Wyscout player-match rows must fail closed")


def test_invalid_timezone_kickoff_fails_closed():
    matches = [feature_row(101, 500, 2, "2017-08-12")]
    fpl = [history(1, 1000, "2017-08-12T14:00:00", 2)]
    try:
        build_verified_panel(matches, [crosswalk()], fpl, {500: 1000})
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("naive kickoff timestamp must fail closed")
