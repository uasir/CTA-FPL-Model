import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_11footy_player_match_features import (
    build_panel, build_provisional_research_panel, prioritize_candidate_evidence,
)


def _databases():
    main = sqlite3.connect(":memory:")
    main.executescript("""
        CREATE TABLE format_version(built_at TEXT, licence TEXT);
        INSERT INTO format_version VALUES ('2026-11-10T00:00:00Z', 'CC BY-NC 4.0');
        CREATE TABLE seasons(season_id INTEGER, competition_id INTEGER, season INTEGER);
        CREATE TABLE teams(team_id INTEGER, name TEXT);
        CREATE TABLE matches(
            match_id INTEGER, season_id INTEGER, kickoff_utc TEXT, local_date TEXT,
            status TEXT, home_team_id INTEGER, away_team_id INTEGER
        );
        CREATE TABLE player_match_statistics(
            match_id INTEGER, team_id INTEGER, player_id INTEGER, minutes_played INTEGER,
            goals INTEGER, assists INTEGER, own_goals INTEGER, shots INTEGER,
            shots_on_target INTEGER, key_passes INTEGER, fouls_committed INTEGER,
            fouls_suffered INTEGER, offsides INTEGER
        );
        CREATE TABLE player_match_event_counts(
            match_id INTEGER, team_id INTEGER, player_id INTEGER, attempts INTEGER,
            attempts_inside_box INTEGER, attempts_outside_box INTEGER, big_chances INTEGER
        );
        CREATE TABLE shots(
            match_id INTEGER, team_id INTEGER, player_id INTEGER, layer TEXT, xg REAL
        );
        INSERT INTO seasons VALUES (270, 1, 2026);
        INSERT INTO teams VALUES (10, 'Arsenal');
        INSERT INTO teams VALUES (20, 'Liverpool');
        INSERT INTO matches VALUES (
            100, 270, '2026-08-15T12:30:00Z', '2026-08-15',
            'played', 10, 20
        );
        INSERT INTO player_match_statistics VALUES (
            100, 10, 2, 90, 1, 0, 0, 3, 2, 1, 0, 2, 0
        );
        INSERT INTO player_match_event_counts VALUES (
            100, 10, 2, 3, 2, 1, 1
        );
        INSERT INTO shots VALUES (100, 10, 2, 'tracked', 0.2);
    """)

    players = sqlite3.connect(":memory:")
    players.executescript("""
        CREATE TABLE players(player_id INTEGER, name TEXT);
        CREATE TABLE player_merges(retired_id INTEGER, kept_id INTEGER);
        INSERT INTO players VALUES (1, 'Example Player');
        INSERT INTO player_merges VALUES (2, 1);
    """)
    return main, players


def _inputs():
    fixtures = [{
        "season": "2026-27", "fixture_id": "500", "gameweek": "1",
        "kickoff_time": "2026-08-15T12:30:00Z",
        "team_h_id": "1", "team_h_name": "Arsenal",
        "team_a_id": "2", "team_a_name": "Liverpool",
    }]
    fpl_players = [{
        "season": "2026-27", "fpl_element_id": "42",
        "fpl_player_code": "999", "web_name": "Example",
        "team_id": "1", "team_name": "Arsenal",
    }]
    fpl_history = [{
        "season": "2026-27", "fpl_element_id": "42", "fixture_id": "500",
        "was_home": "True", "minutes": "90", "total_points": "8",
        "goals_scored": "1", "assists": "0",
    }]
    candidates = [{
        "season": "2026/27", "competition_id": "1",
        "provider_player_id": "1", "provider_player_name": "Example Player",
        "fpl_element_id": "42", "fpl_player_code": "999", "fpl_player_name": "Example",
        "match_method": "exact_name_team_birth_date",
        "confidence_level": "high", "verification_status": "pending",
    }]
    return fixtures, fpl_players, fpl_history, candidates


def test_pending_identity_is_cross_checked_but_never_enters_model_panel():
    main, players = _databases()
    fixtures, fpl_players, history, candidates = _inputs()
    try:
        panel, evidence, report = build_panel(
            main, players, fixtures, fpl_players, history,
            candidates, [], "2026-27", "1",
            crosswalk_validation_report={"status": "NO_VERIFIED_MAPPINGS"},
        )
    finally:
        main.close()
        players.close()

    assert panel == []
    assert report["source_match_count"] == 1
    assert report["provider_matches_with_fixture_match"] == 1
    assert report["player_match_rows_with_fpl_fixture"] == 1
    assert report["player_match_rows_with_candidate_identity"] == 1
    assert report["verified_crosswalk_rows"] == 0
    assert report["verified_player_match_panel_rows"] == 0
    assert report["join_ready"] is False
    assert report["status"] == "CANDIDATE_REVIEW_READY_NOT_MODEL_JOIN_READY"
    assert evidence[0]["fpl_history_overlap_rows"] == 1
    assert evidence[0]["team_match_rows"] == 1
    assert evidence[0]["minutes_exact_rows"] == 1
    assert evidence[0]["goals_exact_rows"] == 1
    assert evidence[0]["assists_exact_rows"] == 1
    assert evidence[0]["full_signature_exact_rows"] == 1
    assert evidence[0]["statistical_corroboration_level"] == "LIMITED_MATCH_CONSISTENCY_REVIEW"


def test_pending_high_confidence_candidate_enters_separate_research_panel_only():
    main, players = _databases()
    fixtures, fpl_players, history, candidates = _inputs()
    try:
        production_panel, _, production_report = build_panel(
            main, players, fixtures, fpl_players, history,
            candidates, [], "2026-27", "1",
            crosswalk_validation_report={"status": "NO_VERIFIED_MAPPINGS"},
        )
        research_panel, research_report = build_provisional_research_panel(
            main, players, fixtures, fpl_players, history,
            candidates, "2026-27", "1",
        )
    finally:
        main.close()
        players.close()

    assert production_panel == []
    assert production_report["verified_player_match_panel_rows"] == 0
    assert len(research_panel) == 1
    row = research_panel[0]
    assert row["provider_player_id"] == 1
    assert row["fpl_element_id"] == 42
    assert row["fpl_fixture_id"] == 500
    assert row["fpl_total_points"] == "8"
    assert row["match_kickoff_utc"] == "2026-08-15T12:30:00Z"
    assert row["identity_status"] == "PENDING_RESEARCH_ONLY"
    assert row["research_only"] is True
    assert research_report["production_eligible"] is False
    assert research_report["prediction_training_eligible"] is False
    assert research_report["rows"] == 1


def test_verified_crosswalk_creates_common_player_match_row_and_resolves_merged_id():
    main, players = _databases()
    fixtures, fpl_players, history, candidates = _inputs()
    crosswalk = [{
        "season": "2026/27", "competition_id": "1",
        "provider_player_id": "1", "provider_player_name": "Example Player",
        "fpl_element_id": "42", "fpl_player_code": "999",
        "verification_status": "verified", "match_method": "manual_source_verified",
    }]
    try:
        panel, evidence, report = build_panel(
            main, players, fixtures, fpl_players, history,
            candidates, crosswalk, "2026-27", "1",
            crosswalk_validation_report={"status": "PASS"},
        )
    finally:
        main.close()
        players.close()

    assert len(panel) == 1
    row = panel[0]
    assert row["provider_player_id"] == 1
    assert row["fpl_element_id"] == 42
    assert row["fpl_fixture_id"] == 500
    assert row["gameweek"] == "1"
    assert row["minutes_played"] == 90
    assert row["tracked_shots"] == 1
    assert row["tracked_xg_sum"] == 0.2
    assert row["fpl_total_points"] == "8"
    assert row["join_status"] == "VERIFIED_IDENTITY_AND_FIXTURE"
    assert report["join_ready"] is True
    assert report["status"] == "PASS_JOIN_READY"


def test_player_match_fixture_team_mismatch_blocks_verified_training_join():
    main, players = _databases()
    fixtures, fpl_players, history, candidates = _inputs()
    crosswalk = [{
        "season": "2026/27", "competition_id": "1",
        "provider_player_id": "1", "provider_player_name": "Example Player",
        "fpl_element_id": "42", "fpl_player_code": "999",
        "verification_status": "verified", "match_method": "manual_source_verified",
    }]
    history[0]["was_home"] = "False"
    try:
        panel, evidence, report = build_panel(
            main, players, fixtures, fpl_players, history,
            candidates, crosswalk, "2026-27", "1",
            crosswalk_validation_report={"status": "PASS"},
        )
    finally:
        main.close()
        players.close()

    assert panel == []
    assert report["verified_team_mismatch_rows"] == 1
    assert report["join_ready"] is False
    assert report["status"] == "BLOCKED"


def test_candidate_review_queue_prioritizes_evidence_without_verifying_identity():
    rows = [
        {
            "provider_player_id": "4",
            "confidence_level": "high",
            "verification_status": "PENDING",
            "statistical_corroboration_level": "STRONG_MULTI_MATCH_CONSISTENCY_REVIEW",
            "team_mismatch_rows": 0,
            "full_signature_exact_rows": 3,
            "fpl_history_overlap_rows": 3,
        },
        {
            "provider_player_id": "3",
            "confidence_level": "high",
            "verification_status": "PENDING",
            "statistical_corroboration_level": "PARTIAL_MATCH_CONSISTENCY_REVIEW",
            "team_mismatch_rows": 0,
            "full_signature_exact_rows": 1,
            "fpl_history_overlap_rows": 2,
        },
        {
            "provider_player_id": "2",
            "confidence_level": "review",
            "verification_status": "PENDING",
            "statistical_corroboration_level": "NO_MATCH_DATA",
            "team_mismatch_rows": 0,
            "full_signature_exact_rows": 0,
            "fpl_history_overlap_rows": 0,
        },
        {
            "provider_player_id": "1",
            "confidence_level": "high",
            "verification_status": "PENDING",
            "statistical_corroboration_level": "STRONG_MULTI_MATCH_CONSISTENCY_REVIEW",
            "team_mismatch_rows": 1,
            "full_signature_exact_rows": 3,
            "fpl_history_overlap_rows": 3,
        },
    ]

    queue = prioritize_candidate_evidence(rows)

    assert [row["review_priority"] for row in queue] == [
        "P1_STRONG_MULTI_MATCH_REVIEW",
        "P2_HIGH_CONFIDENCE_REVIEW",
        "P3_PARTIAL_EVIDENCE_REVIEW",
        "P4_IDENTITY_REVIEW",
    ]
    assert all(row["verification_status"] == "PENDING" for row in queue)
    assert all("manual review only" in row["review_note"] for row in queue)
