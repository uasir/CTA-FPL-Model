import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_11footy_fpl_identity_candidates import (
    audit_identity_candidates,
    normalize_name,
    normalize_team,
)


def _players_db(rows):
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE players(player_id INTEGER, name TEXT, current_team_name TEXT)"
    )
    db.executemany("INSERT INTO players VALUES (?,?,?)", rows)
    return db


def test_exact_normalized_name_and_team_candidates_are_separated_from_verification():
    db = _players_db([
        (1, "Mohamed Salah", "Liverpool"),
        (2, "Erling Haaland", "Manchester City"),
        (3, "Unknown Player", None),
        (4, "Duplicate Name", "Arsenal"),
        (5, "Duplicate Name", "Chelsea"),
    ])
    bootstrap = {
        "teams": [
            {"id": 1, "name": "Liverpool"},
            {"id": 2, "name": "Man City"},
            {"id": 3, "name": "Arsenal"},
            {"id": 4, "name": "Chelsea"},
        ],
        "elements": [
            {"id": 100, "code": 1000, "first_name": "Mohamed", "second_name": "Salah", "team": 1},
            {"id": 101, "code": 1001, "first_name": "Erling", "second_name": "Haaland", "team": 2},
            {"id": 102, "code": 1002, "first_name": "Unknown", "second_name": "Player", "team": 1},
            {"id": 103, "code": 1003, "first_name": "Duplicate", "second_name": "Name", "team": 3},
            {"id": 104, "code": 1004, "first_name": "Missing", "second_name": "Guy", "team": 4},
        ],
    }

    report = audit_identity_candidates(db, bootstrap)

    assert report["fpl_player_count"] == 5
    assert report["provider_player_catalogue_count"] == 5
    assert report["exact_normalized_name_and_team_candidates"] == 3
    assert report["unique_name_only_unverified"] == 1
    assert report["unmatched_fpl_players"] == 1
    assert report["candidate_rows_remaining"] == 3
    assert report["verification_status"] == "CANDIDATES_ONLY_NOT_VERIFIED"
    assert all(
        row["verification_status"] == "CANDIDATE_REQUIRES_REVIEW"
        for row in report["candidate_crosswalk"]
    )


def test_duplicate_provider_identity_is_ambiguous_not_auto_joined():
    db = _players_db([
        (1, "Alex Smith", "Arsenal"),
        (2, "Alex Smith", "Arsenal"),
    ])
    bootstrap = {
        "teams": [{"id": 1, "name": "Arsenal"}],
        "elements": [
            {"id": 100, "code": 1000, "first_name": "Alex", "second_name": "Smith", "team": 1}
        ],
    }

    report = audit_identity_candidates(db, bootstrap)

    assert report["exact_normalized_name_and_team_candidates"] == 0
    assert report["ambiguous_name_or_duplicate_identity"] == 1
    assert report["candidate_rows_remaining"] == 0


def test_name_and_team_normalization_handles_accents_and_aliases():
    assert normalize_name("João Pedro") == "joao pedro"
    assert normalize_team("Man City") == normalize_team("Manchester City")
    assert normalize_team("Nott'm Forest") == normalize_team("Nottingham Forest")
