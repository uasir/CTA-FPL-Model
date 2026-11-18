import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_wyscout_epl_2017_event_data import audit_wyscout


def _write_zip(path, member, rows):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, json.dumps(rows))


def test_wyscout_event_audit_checks_match_player_team_and_position_coverage(tmp_path):
    events = [
        {
            "id": 1, "matchId": 100, "playerId": 10, "teamId": 1,
            "eventName": "Pass", "subEventName": "Simple pass",
            "matchPeriod": "1H", "positions": [{"x": 20, "y": 40}, {"x": 45, "y": 40}],
            "tags": [{"id": 1801}],
        },
        {
            "id": 2, "matchId": 100, "playerId": 11, "teamId": 2,
            "eventName": "Shot", "subEventName": "Shot",
            "matchPeriod": "2H", "positions": [{"x": 90, "y": 50}],
            "tags": [{"id": 101}],
        },
    ]
    matches = [{"wyId": 100, "label": "Home - Away"}]
    players = [{"wyId": 10}, {"wyId": 11}]
    teams = [{"wyId": 1}, {"wyId": 2}]
    event_zip = tmp_path / "events.zip"
    match_zip = tmp_path / "matches.zip"
    player_json = tmp_path / "players.json"
    team_json = tmp_path / "teams.json"
    _write_zip(event_zip, "events_England.json", events)
    _write_zip(match_zip, "matches_England.json", matches)
    player_json.write_text(json.dumps(players))
    team_json.write_text(json.dumps(teams))

    report = audit_wyscout(event_zip, match_zip, player_json, team_json)

    assert report["events"]["rows"] == 2
    assert report["events"]["unique_matches"] == 1
    assert report["events"]["unique_players"] == 2
    assert report["events"]["rows_with_start_position"] == 2
    assert report["events"]["rows_with_end_position"] == 1
    assert report["matches"]["event_match_ids_missing_from_metadata"] == 0
    assert report["player_metadata"]["event_player_ids_missing_from_metadata"] == 0
    assert report["team_metadata"]["event_team_ids_missing_from_metadata"] == 0
    assert report["events"]["event_types"] == {"Pass": 1, "Shot": 1}
    assert report["prediction_validation"] == "NOT_EVALUATED"
