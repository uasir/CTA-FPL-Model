import sys
import pytest
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_opta_lagged_team_features import (
    build_crosswalk, build_team_features, build_historical_player_features, parse_time,
)
from zoneinfo import ZoneInfo


def test_crosswalk_requires_exact_numeric_id_and_team_match():
    elements = [
        {"id": 1, "code": 100, "team": 1, "first_name": "Alex", "second_name": "Player"},
        {"id": 2, "code": 200, "team": 2, "first_name": "Ben", "second_name": "Player"},
    ]
    teams = [{"id": 1, "code": 3, "name": "Arsenal"}, {"id": 2, "code": 7, "name": "Brentford"}]
    provider = [
        {"playerId": 100, "playerName": "A. Player", "team_id": 3,
         "team_name": "Arsenal", "season": "2026-27"},
        {"playerId": 200, "playerName": "B. Player", "team_id": 99,
         "team_name": "Other", "season": "2026-27"},
        {"playerId": 300, "playerName": "Unmatched", "team_id": 7,
         "team_name": "Brentford", "season": "2026-27"},
    ]
    rows, report = build_crosswalk(elements, teams, provider, verified_at="2026-11-18T00:00:00Z")
    assert report["verified_id_and_team_matches"] == 1
    assert report["exact_shared_numeric_ids"] == 2
    assert report["team_mismatches_or_duplicate_ids"] == 1
    assert report["fpl_players_without_provider_season_row"] == 0
    assert rows[0]["verification_status"] == "verified"
    assert rows[0]["fpl_element_id"] == "1"
    assert rows[0]["fpl_team_id"] == "1"
    assert rows[0]["fpl_team_code"] == "3"
    assert rows[1]["verification_status"] == "ambiguous"
    assert rows[2]["verification_status"] == "pending"


def test_team_features_exclude_current_and_future_match_rows():
    bootstrap = {
        "elements": [
            {"id": 1, "code": 100, "team": 1, "first_name": "Alex", "second_name": "Player"},
            {"id": 2, "code": 200, "team": 2, "first_name": "Ben", "second_name": "Player"},
        ],
        "teams": [{"id": 1, "code": 3, "name": "Arsenal"}, {"id": 2, "code": 7, "name": "Brentford"}],
    }
    fixtures = [{
        "id": 11, "event": 2, "kickoff_time": "2026-08-15T12:00:00Z",
        "team_h": 1, "team_a": 2,
    }]
    provider_rows = [
        {"season": "2026-27", "matchId": 10, "kickoff": "2026-08-01T12:00:00Z",
         "team_id": 3, "expectedGoals": "1.0", "accuratePass": "100"},
        {"season": "2026-27", "matchId": 11, "kickoff": "2026-08-15T12:00:00Z",
         "team_id": 3, "expectedGoals": "4.0", "accuratePass": "300"},
        {"season": "2026-27", "matchId": 12, "kickoff": "2026-08-20T12:00:00Z",
         "team_id": 3, "expectedGoals": "6.0", "accuratePass": "500"},
        {"season": "2026-27", "matchId": 10, "kickoff": "2026-08-01T12:00:00Z",
         "team_id": 7, "expectedGoals": "0.5", "accuratePass": "80"},
    ]
    team_rows, player_rows, report = build_team_features(
        fixtures, bootstrap, provider_rows,
        as_of_time=datetime.fromisoformat("2026-08-01T00:00:00+00:00"),
    )
    arsenal = next(row for row in team_rows if row["team_id"] == "1")
    brentford = next(row for row in team_rows if row["team_id"] == "2")
    assert arsenal["opta_prior_matches_count"] == 1
    assert arsenal["opta_prior3_expectedGoals_avg"] == 1.0
    assert arsenal["opta_prior3_accuratePass_avg"] == 100.0
    assert brentford["opta_prior3_expectedGoals_avg"] == 0.5
    assert len(player_rows) == 2
    alex = next(row for row in player_rows if row["fpl_element_id"] == 1)
    assert alex["opta_prior3_expectedGoals_avg"] == 1.0
    assert report["status"] == "PASS_STRUCTURAL_ONLY"
    assert "strictly earlier" in report["leakage_policy"]


def test_postponed_fixture_without_kickoff_emits_blank_features_not_future_data():
    bootstrap = {
        "elements": [{"id": 1, "code": 100, "team": 1, "first_name": "Alex", "second_name": "Player"}],
        "teams": [{"id": 1, "code": 3, "name": "Arsenal"}, {"id": 2, "code": 7, "name": "Brentford"}],
    }
    fixtures = [{"id": 99, "event": None, "kickoff_time": None, "team_h": 1, "team_a": 2}]
    team_rows, player_rows, report = build_team_features(fixtures, bootstrap, [])
    assert len(team_rows) == 2
    assert len(player_rows) == 0
    assert report["fixtures_without_kickoff"] == 1


def test_naive_provider_kickoff_is_interpreted_as_london_local_time():
    value = parse_time("2026-08-21 20:00:00", ZoneInfo("Europe/London"))
    assert value.isoformat() == "2026-08-21T19:00:00+00:00"


def test_historical_player_fixture_sidecar_uses_team_at_fixture_and_no_target_fields():
    team_rows = [
        {"fixture_id": "101", "team_id": "1", "features_as_of": "2026-08-01T12:00:00+00:00",
         "opta_prior_matches_count": 0, "opta_prior3_expectedGoals_avg": ""},
        {"fixture_id": "102", "team_id": "2", "features_as_of": "2026-08-08T12:00:00+00:00",
         "opta_prior_matches_count": 1, "opta_prior3_expectedGoals_avg": 0.8},
    ]
    fpl_rows = [
        {"season": "2026-27", "fpl_element_id": "10", "fixture_id": "101",
         "gameweek": "1", "team_id_at_fixture": "1", "kickoff_time": "2026-08-01T12:00:00Z",
         "target_total_points": "6"},
        {"season": "2026-27", "fpl_element_id": "20", "fixture_id": "102",
         "gameweek": "2", "team_id_at_fixture": "2", "kickoff_time": "2026-08-08T12:00:00Z",
         "target_total_points": "4"},
    ]
    rows, report = build_historical_player_features(team_rows, fpl_rows)
    assert len(rows) == 2
    assert rows[1]["opta_prior3_expectedGoals_avg"] == 0.8
    assert rows[1]["team_id_at_fixture"] == "2"
    assert "target_total_points" not in rows[1]
    assert report["historical_player_fixture_rows_with_team_context"] == 2
    assert report["status"] == "PASS_STRUCTURAL_ONLY"


def test_historical_player_fixture_sidecar_rejects_unmatched_team_fixture():
    with pytest.raises(ValueError, match="Missing Opta team context"):
        build_historical_player_features(
            [{"fixture_id": "101", "team_id": "1"}],
            [{"fixture_id": "101", "team_id_at_fixture": "2", "fpl_element_id": "10"}],
        )


def test_official_gameweek_deadline_excludes_same_gameweek_matches_before_target_kickoff():
    bootstrap = {
        "elements": [{"id": 1, "code": 100, "team": 1, "first_name": "Alex", "second_name": "Player"}],
        "teams": [{"id": 1, "code": 3, "name": "Arsenal"}, {"id": 2, "code": 7, "name": "Brentford"}],
        "events": [{"id": 2, "deadline_time": "2026-08-14T17:00:00Z"}],
    }
    fixtures = [{
        "id": 11, "event": 2, "kickoff_time": "2026-08-16T12:00:00Z",
        "team_h": 1, "team_a": 2,
    }]
    provider_rows = [
        {"season": "2026-27", "matchId": 10, "kickoff": "2026-08-01T12:00:00Z",
         "team_id": 3, "expectedGoals": "1.0", "attemptsIbox": "4"},
        {"season": "2026-27", "matchId": 10, "kickoff": "2026-08-01T12:00:00Z",
         "team_id": 7, "expectedGoals": "0.5", "attemptsIbox": "2"},
        # Played after the GW deadline but before this target fixture: must not leak.
        {"season": "2026-27", "matchId": 12, "kickoff": "2026-08-15T12:00:00Z",
         "team_id": 3, "expectedGoals": "4.0", "attemptsIbox": "9"},
        {"season": "2026-27", "matchId": 12, "kickoff": "2026-08-15T12:00:00Z",
         "team_id": 7, "expectedGoals": "2.0", "attemptsIbox": "6"},
    ]
    team_rows, _, report = build_team_features(fixtures, bootstrap, provider_rows)
    arsenal = next(row for row in team_rows if row["team_id"] == "1")
    assert arsenal["opta_prior_matches_count"] == 1
    assert arsenal["opta_prior3_expectedGoals_avg"] == 1.0
    assert arsenal["opta_prior3_opponentExpectedGoals_avg"] == 0.5
    assert arsenal["opta_prior3_opponentAttemptsIbox_avg"] == 2.0
    assert arsenal["features_as_of"] == "2026-08-14T17:00:00+00:00"
    assert arsenal["feature_cutoff_policy"] == "OFFICIAL_FPL_DEADLINE"
    assert report["deadline_cutoff_fixtures"] == 1
