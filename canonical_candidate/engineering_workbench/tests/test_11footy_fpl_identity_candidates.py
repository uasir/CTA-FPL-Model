import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_11footy_fpl_identity_candidates import (
    audit_identity_candidates,
    normalize_text,
    normalize_team,
)


def _players_db(rows):
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE players(player_id INTEGER, name TEXT, current_team_name TEXT, birth_date TEXT)"
    )
    db.executemany("INSERT INTO players VALUES (?,?,?,?)", rows)
    return db


def test_exact_name_team_and_birth_date_candidates_are_high_confidence_not_verified():
    db = _players_db([
        (1, "Mohamed Salah", "Liverpool", "1992-06-15"),
        (2, "Erling Haaland", "Manchester City", "2000-07-21"),
        (3, "Unknown Player", None, None),
        (4, "Duplicate Name", "Arsenal", "1995-01-01"),
        (5, "Duplicate Name", "Chelsea", "1995-01-01"),
    ])
    bootstrap = {
        "teams": [
            {"id": 1, "name": "Liverpool"},
            {"id": 2, "name": "Man City"},
            {"id": 3, "name": "Arsenal"},
            {"id": 4, "name": "Chelsea"},
        ],
        "elements": [
            {"id": 100, "code": 1000, "first_name": "Mohamed", "second_name": "Salah", "team": 1, "birth_date": "1992-06-15"},
            {"id": 101, "code": 1001, "first_name": "Erling", "second_name": "Haaland", "team": 2, "birth_date": "2000-07-21"},
            {"id": 102, "code": 1002, "first_name": "Unknown", "second_name": "Player", "team": 1, "birth_date": None},
            {"id": 103, "code": 1003, "first_name": "Duplicate", "second_name": "Name", "team": 3, "birth_date": "1995-01-01"},
            {"id": 104, "code": 1004, "first_name": "Missing", "second_name": "Guy", "team": 4, "birth_date": "1990-01-01"},
        ],
    }

    report, candidates = audit_identity_candidates(db, bootstrap)

    assert report["fpl_player_count"] == 5
    assert report["provider_player_catalogue_count"] == 5
    assert report["exact_normalized_name_and_team_candidates"] == 3
    assert report["high_confidence_name_team_birth_date_candidates"] == 2
    assert report["name_team_candidates_missing_birth_date"] == 1
    assert report["unique_name_only_unverified"] == 1
    assert report["unmatched_fpl_players"] == 1
    assert report["candidate_rows_remaining"] == 3
    assert report["verification_status"] == "CANDIDATES_ONLY_NOT_VERIFIED"
    assert len(candidates) == 3
    assert sum(row["confidence_level"] == "high" for row in candidates) == 2
    assert sum(row["confidence_level"] == "review_required" for row in candidates) == 1
    assert all(row["verification_status"] == "pending" for row in candidates)
    salah = next(row for row in candidates if row["fpl_element_id"] == 100)
    assert salah["provider_player_id"] == 1
    assert salah["fpl_player_code"] == 1000
    assert salah["provider_player_name"] == "Mohamed Salah"
    assert salah["fpl_player_name"] == "Mohamed Salah"
    assert salah["confidence_level"] == "high"
    assert "awaiting independent identity review" in salah["verification_reason"]
    assert salah["provider_release_url"].startswith("https://")
    assert salah["fpl_source_url"].startswith("https://")


def test_duplicate_provider_identity_is_ambiguous_not_auto_joined():
    db = _players_db([
        (1, "Alex Smith", "Arsenal", "1998-01-01"),
        (2, "Alex Smith", "Arsenal", "1998-01-01"),
    ])
    bootstrap = {
        "teams": [{"id": 1, "name": "Arsenal"}],
        "elements": [
            {"id": 100, "code": 1000, "first_name": "Alex", "second_name": "Smith", "team": 1, "birth_date": "1998-01-01"}
        ],
    }

    report, candidates = audit_identity_candidates(db, bootstrap)

    assert report["exact_normalized_name_and_team_candidates"] == 0
    assert report["ambiguous_name_or_duplicate_identity"] == 1
    assert report["candidate_rows_remaining"] == 0
    assert candidates == []


def test_birth_date_conflict_excludes_an_otherwise_exact_name_team_match():
    db = _players_db([(1, "John Doe", "Arsenal", "1990-01-01")])
    bootstrap = {
        "teams": [{"id": 1, "name": "Arsenal"}],
        "elements": [
            {"id": 100, "code": 1000, "first_name": "John", "second_name": "Doe", "team": 1, "birth_date": "1991-01-01"}
        ],
    }

    report, candidates = audit_identity_candidates(db, bootstrap)

    assert report["birth_date_conflicts_excluded"] == 1
    assert report["exact_normalized_name_and_team_candidates"] == 0
    assert report["candidate_rows_remaining"] == 0
    assert candidates == []


def test_name_and_team_normalization_handles_accents_and_aliases():
    assert normalize_text("João Pedro") == "joao pedro"
    assert normalize_team("Man City") == normalize_team("Manchester City")
    assert normalize_team("Nott'm Forest") == normalize_team("Nottingham Forest")
