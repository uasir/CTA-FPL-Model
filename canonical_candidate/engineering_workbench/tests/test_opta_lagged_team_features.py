import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_opta_lagged_team_features import build_crosswalk, build_team_features, parse_time
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
    assert report["fpl_players_without_provider_stats"] == 0
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
