import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_11footy_premier_league_data import audit_database


def _database():
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE format_version(version TEXT, dataset TEXT, part TEXT, scope TEXT, built_at TEXT, licence TEXT);
        CREATE TABLE competitions(competition_id INTEGER, code TEXT, name TEXT, country TEXT, kind TEXT, time_zone TEXT);
        CREATE TABLE seasons(season_id INTEGER, competition_id INTEGER, season INTEGER, name TEXT, status TEXT);
        CREATE TABLE matches(match_id INTEGER, season_id INTEGER, status TEXT, kickoff_utc TEXT, matchday INTEGER);
        CREATE TABLE teams(team_id INTEGER);
        CREATE TABLE match_events(event_id INTEGER, match_id INTEGER, layer TEXT, kind TEXT);
        CREATE TABLE shots(shot_id INTEGER, match_id INTEGER, layer TEXT, xg REAL, x_m REAL, y_m REAL);
        CREATE TABLE match_players(match_id INTEGER, team_id INTEGER, player_id INTEGER, started INTEGER, minutes_played INTEGER);
        CREATE TABLE player_match_statistics(match_id INTEGER, team_id INTEGER, player_id INTEGER, minutes_played INTEGER, key_passes INTEGER, goals INTEGER);
        CREATE TABLE player_match_event_counts(match_id INTEGER, team_id INTEGER, player_id INTEGER, attempts INTEGER, big_chances INTEGER);
        CREATE TABLE match_team_statistics(match_id INTEGER, team_id INTEGER, layer TEXT);
    """)
    db.execute("INSERT INTO format_version VALUES ('VDF 1','11footy','england/premier-league','PL','2026-11-10T00:00:00Z','CC BY-NC 4.0')")
    db.execute("INSERT INTO competitions VALUES (1,'PL','Premier League','England','league','Europe/London')")
    db.execute("INSERT INTO seasons VALUES (10,1,2026,'2026/27','open')")
    db.execute("INSERT INTO matches VALUES (100,10,'played','2026-08-15T19:00:00Z',1)")
    db.execute("INSERT INTO match_events VALUES (1,100,'play_by_play','goal')")
    db.execute("INSERT INTO shots VALUES (1,100,'tracked',0.25,90.0,34.0)")
    db.execute("INSERT INTO match_players VALUES (100,1,20,1,90)")
    db.execute("INSERT INTO player_match_statistics VALUES (100,1,20,90,2,1)")
    db.execute("INSERT INTO player_match_event_counts VALUES (100,1,20,3,1)")
    db.execute("INSERT INTO match_team_statistics VALUES (100,1,'report')")
    return db


def test_audit_reports_aggregate_coverage_without_identity_join():
    db = _database()
    players = sqlite3.connect(":memory:")
    players.executescript("""
        CREATE TABLE players(player_id INTEGER, name TEXT);
        CREATE TABLE player_merges(retired_id INTEGER, kept_id INTEGER);
    """)
    players.executemany("INSERT INTO players VALUES (?,?)", [(20, "Player One"), (21, "Player Two")])
    players.execute("INSERT INTO player_merges VALUES (22,20)")
    report = audit_database(db, "11footy-2026-11-10", "a" * 64, players, "c" * 64)

    assert report["status"] == "PASS_STRUCTURAL_ONLY"
    assert report["prediction_validation"] == "NOT_EVALUATED"
    assert report["identity_mapping"] == "NOT_ATTEMPTED"
    assert report["season_coverage"][0]["match_rows"] == 1
    assert report["season_coverage"][0]["completed_matches"] == 1
    assert report["match_event_layers_and_kinds"][0]["kind"] == "goal"
    assert report["shot_layers"][0]["rows_with_xg"] == 1
    assert report["player_match_statistics"]["rows"] == 1
    assert report["player_match_event_counts"]["rows_with_big_chances"] == 1
    assert report["lineups"]["starters"] == 1
    assert report["player_catalogue"]["players"] == 2
    assert report["player_catalogue"]["player_merges"] == 1


def test_audit_rejects_missing_required_provider_tables():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE format_version(version TEXT)")
    with pytest.raises(ValueError, match="missing required tables"):
        audit_database(db, "release", "b" * 64)
