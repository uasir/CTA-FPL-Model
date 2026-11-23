from merge_cta_abc_fpl_baseline_features import merge


def test_merge_builds_pre_deadline_fpl_baselines_and_excludes_target_gw():
    history = []
    values = [(1, 4, 90), (2, 6, 80), (3, 2, 30), (4, 10, 90), (5, 100, 90)]
    for gw, points, minutes in values:
        history.append({
            "fpl_element_id": "10", "gameweek": str(gw),
            "kickoff_time": f"2017-08-{10 + gw:02d}T14:00:00Z",
            "target_total_points": str(points), "target_minutes": str(minutes),
        })
    deadline = "2017-09-15T18:00:00+00:00"
    abc_rows = [
        {"fpl_element_id": "10", "fixture_id": "501", "gameweek": "5",
         "features_as_of_deadline": deadline, "kickoff_time": "2017-09-16T14:00:00Z",
         "abc_player_key_pass_rate": "0.4"},
        {"fpl_element_id": "10", "fixture_id": "502", "gameweek": "5",
         "features_as_of_deadline": deadline, "kickoff_time": "2017-09-17T14:00:00Z",
         "abc_player_key_pass_rate": "0.4"},
    ]
    metadata = {
        "next_deadline_event_id": 5,
        "next_deadline_time_utc": deadline,
        "fetched_at_utc": "2017-09-15T17:00:00+00:00",
    }

    rows, report = merge(abc_rows, history, metadata)

    assert len(rows) == 2
    assert rows[0]["fpl_total_points_prior_3_avg"] == 6.0
    assert rows[0]["fpl_total_points_prior_5_avg"] == 5.5
    assert abs(rows[0]["fpl_minutes_prior_3_avg"] - 66.6666666667) < 1e-8
    assert rows[0]["fpl_minutes_prior_5_avg"] == 72.5
    assert report["baseline_complete_rows"] == 2
    assert report["point_in_time_status"].startswith("CURRENT_SNAPSHOT_FETCHED_PRE_DEADLINE")


def test_merge_rejects_fpl_snapshot_after_deadline():
    metadata = {
        "next_deadline_event_id": 5,
        "next_deadline_time_utc": "2017-09-15T18:00:00Z",
        "fetched_at_utc": "2017-09-15T19:00:00Z",
    }
    abc_rows = [{
        "fpl_element_id": "10", "fixture_id": "501", "gameweek": "5",
        "features_as_of_deadline": "2017-09-15T18:00:00Z",
        "kickoff_time": "2017-09-16T14:00:00Z",
    }]
    import pytest
    with pytest.raises(ValueError, match="at/after the target deadline"):
        merge(abc_rows, [], metadata)


def test_merge_rejects_duplicate_upcoming_player_fixture():
    deadline = "2017-09-15T18:00:00Z"
    row = {
        "fpl_element_id": "10", "fixture_id": "501", "gameweek": "5",
        "features_as_of_deadline": deadline, "kickoff_time": "2017-09-16T14:00:00Z",
    }
    metadata = {
        "next_deadline_event_id": 5,
        "next_deadline_time_utc": deadline,
        "fetched_at_utc": "2017-09-15T17:00:00Z",
    }
    import pytest
    with pytest.raises(ValueError, match="Duplicate upcoming"):
        merge([row, row], [], metadata)
