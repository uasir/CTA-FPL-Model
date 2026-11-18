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
    ]


def gameweek_rows():
    return [
        {"fpl_element_id": "10", "gameweek": "10", "target_minutes": "90"},
        {"fpl_element_id": "10", "gameweek": "11", "target_minutes": "60"},
    ]


def test_builds_official_ep_next_and_explicit_minutes_proxy():
    snapshot, report = build_snapshot(players(), gameweek_rows(), source_metadata())
    assert snapshot["forecast_horizon_gameweeks"] == 1
    assert snapshot["forecast_quality"]["validation_status"] == "EXPLORATORY_ONLY"
    assert snapshot["forecast_quality"]["point_in_time_status"] == "VERIFIED"
    by_id = {row["fpl_element_id"]: row for row in snapshot["player_forecasts"]}
    assert by_id[10]["expected_points"] == 4.8
    assert by_id[10]["expected_minutes"] == 60
    assert by_id[10]["minutes_proxy_source"] == "latest_completed_gameweek_actual"
    assert by_id[10]["price"] == 5.0
    assert by_id[10]["availability_probability"] == 1.0
    assert by_id[11]["expected_minutes"] == 0
    assert by_id[11]["minutes_proxy_source"] == "no_history_zero_fallback"
    assert report["no_minutes_history_ids"] == ["11"]


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
    }
    snapshot, report = build_snapshot(players(), gameweek_rows(), source_metadata(), eo_rows, eo_report)
    keeper = next(row for row in snapshot["player_forecasts"] if row["fpl_element_id"] == 10)
    assert keeper["effective_ownership_pct"] == 142.5
    assert report["eo_coverage_players"] == 1


def test_rejects_unverified_eo():
    with pytest.raises(ValueError, match="post-deadline locked picks"):
        build_snapshot(
            players(), gameweek_rows(), source_metadata(),
            [{"gameweek": "12", "fpl_element_id": "10", "effective_ownership_pct": "100"}],
            {"status": "CAPTURED_PRE_DEADLINE_MANAGER_SAMPLE", "picks_lock_verified": False, "gameweek": 12},
        )


def test_rejects_source_snapshot_after_deadline():
    metadata = source_metadata()
    metadata["fetched_at_utc"] = "2026-11-28T11:01:00Z"
    with pytest.raises(ValueError, match="not captured before"):
        build_snapshot(players(), gameweek_rows(), metadata)


def test_requires_source_hashes_for_provenance():
    metadata = source_metadata()
    metadata.pop("bootstrap_sha256")
    with pytest.raises(ValueError, match="SHA-256 hashes"):
        build_snapshot(players(), gameweek_rows(), metadata)
