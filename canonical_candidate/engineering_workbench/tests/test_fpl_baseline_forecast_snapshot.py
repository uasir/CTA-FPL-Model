import pytest

from build_fpl_baseline_forecast_snapshot import build_snapshot


def source_metadata():
    return {
        "next_deadline_event_id": 12,
        "next_deadline_time_utc": "2026-11-28T11:00:00Z",
        "fetched_at_utc": "2026-11-27T05:30:00Z",
        "bootstrap_sha256": "bootstrap-hash",
        "fixtures_sha256": "fixtures-hash",
    }


def players():
    return [
        {
            "fpl_element_id": "10", "web_name": "Keeper", "team_name": "Arsenal",
            "ep_next": "4.8", "now_cost": "50", "position": "Goalkeeper",
            "team_id": "1", "chance_of_playing_next_round": "100",
        },
        {
            "fpl_element_id": "11", "web_name": "Forward", "team_name": "Chelsea",
            "ep_next": "6.2", "now_cost": "75", "position": "Forward",
            "team_id": "2", "chance_of_playing_next_round": None,
        },
        {
            "fpl_element_id": "12", "web_name": "Midfielder", "team_name": "Brighton",
            "ep_next": "4.0", "now_cost": "60", "position": "Midfielder",
            "team_id": "3", "chance_of_playing_next_round": "100",
        },
    ]


def gameweek_rows():
    return [
        {"fpl_element_id": "10", "gameweek": "10", "target_minutes": "90", "target_fixtures_count": "1"},
        {"fpl_element_id": "10", "gameweek": "11", "target_minutes": "60", "target_fixtures_count": "1"},
        {"fpl_element_id": "11", "gameweek": "11", "target_minutes": "60", "target_fixtures_count": "1"},
    ]


def fixtures():
    return [
        {"event": 12, "team_h": 1, "team_a": 2},
        {"event": 12, "team_h": 2, "team_a": 3},
    ]


def test_builds_official_ep_next_and_explicit_minutes_proxy():
    snapshot, report = build_snapshot(players(), gameweek_rows(), fixtures(), source_metadata())
    assert snapshot["forecast_horizon_gameweeks"] == 1
    assert snapshot["forecast_quality"]["validation_status"] == "EXPLORATORY_ONLY"
    assert snapshot["forecast_quality"]["point_in_time_status"] == "VERIFIED"
    assert snapshot["forecast_quality"]["data_coverage"]["freshness_status"] == "STALE_OVER_24H"
    by_id = {row["fpl_element_id"]: row for row in snapshot["player_forecasts"]}
    assert by_id[10]["expected_points"] == 4.8
    assert by_id[10]["expected_minutes"] == 60
    assert by_id[10]["minutes_proxy_source"] == "latest_completed_gameweek_per_fixture_scaled_to_target_fixture_count"
    assert by_id[10]["price"] == 5.0
    assert by_id[10]["availability_probability"] == 1.0
    assert by_id[11]["expected_minutes"] == 120
    assert by_id[11]["next_fixtures_count"] == 2
    assert by_id[11]["minutes_proxy_source"] == "latest_completed_gameweek_per_fixture_scaled_to_target_fixture_count"
    assert by_id[12]["expected_minutes"] == 0
    assert by_id[12]["minutes_proxy_source"] == "no_history_zero_fallback"
    assert report["no_minutes_history_ids"] == ["12"]


def test_only_verified_post_lock_eo_is_attached():
    eo_rows = [{
        "gameweek": "12", "fpl_element_id": "10",
        "effective_ownership_pct": "142.5",
    }]
    eo_report = {
        "status": "CAPTURED_POST_DEADLINE_PICKS",
        "picks_lock_verified": True,
        "gameweek": 12,
        "sample_managers": 100,
        "cohort": "overall top-10k rank-stratified sample",
        "rank_cohort_captured_at_utc": "2026-11-28T10:55:00Z",
        "deadline_time_utc": "2026-11-28T11:00:00Z",
        "picks_captured_at_utc": "2026-11-28T11:01:00Z",
    }
    snapshot, report = build_snapshot(players(), gameweek_rows(), fixtures(), source_metadata(), eo_rows, eo_report)
    keeper = next(row for row in snapshot["player_forecasts"] if row["fpl_element_id"] == 10)
    assert keeper["effective_ownership_pct"] == 142.5
    assert report["eo_coverage_players"] == 1


def test_rejects_unverified_eo():
    with pytest.raises(ValueError, match="post-deadline locked picks"):
        build_snapshot(
            players(), gameweek_rows(), fixtures(), source_metadata(),
            [{"gameweek": "12", "fpl_element_id": "10", "effective_ownership_pct": "100"}],
            {"status": "CAPTURED_PRE_DEADLINE_MANAGER_SAMPLE", "picks_lock_verified": False, "gameweek": 12},
        )


def test_rejects_source_snapshot_after_deadline():
    metadata = source_metadata()
    metadata["fetched_at_utc"] = "2026-11-28T11:01:00Z"
    with pytest.raises(ValueError, match="not captured before"):
        build_snapshot(players(), gameweek_rows(), fixtures(), metadata)


def test_requires_source_hashes_for_provenance():
    metadata = source_metadata()
    metadata.pop("bootstrap_sha256")
    with pytest.raises(ValueError, match="SHA-256 hashes"):
        build_snapshot(players(), gameweek_rows(), fixtures(), metadata)



def test_rejects_eo_without_cohort_and_lock_timestamps():
    eo_report = {
        "status": "CAPTURED_POST_DEADLINE_PICKS",
        "picks_lock_verified": True,
        "gameweek": 12,
        "sample_managers": 100,
    }
    with pytest.raises(ValueError, match="cohort/lock provenance"):
        build_snapshot(
            players(), gameweek_rows(), fixtures(), source_metadata(),
            [{"gameweek": "12", "fpl_element_id": "10", "effective_ownership_pct": "100"}],
            eo_report,
        )



def test_snapshot_id_changes_when_forecast_inputs_change():
    first, _ = build_snapshot(players(), gameweek_rows(), fixtures(), source_metadata())
    changed_rows = gameweek_rows()
    changed_rows[-1]["target_minutes"] = "30"
    second, _ = build_snapshot(players(), changed_rows, fixtures(), source_metadata())
    assert first["forecast_snapshot_id"] != second["forecast_snapshot_id"]



def test_snapshot_is_fresh_when_captured_within_24_hours_of_deadline():
    metadata = source_metadata()
    metadata["fetched_at_utc"] = "2026-11-28T05:30:00Z"
    snapshot, _ = build_snapshot(players(), gameweek_rows(), fixtures(), metadata)
    assert snapshot["forecast_quality"]["data_coverage"]["freshness_status"] == "FRESH_WITHIN_24H"
