from __future__ import annotations
import hashlib
import json
import os
import pytest
from m4_covar_realized_fixture_state_dataset import (
    RealizedFixtureStateError, build_realized_fixture_states, build_from_ingestion_directory,
)

def fixtures():
    return [
        {"id": 1, "event": 1, "kickoff_time": "2026-08-15T14:00:00Z", "team_h": 1, "team_a": 2,
         "finished": True, "finished_provisional": True, "team_h_score": 2, "team_a_score": 0},
        {"id": 2, "event": 1, "kickoff_time": "2026-08-16T14:00:00Z", "team_h": 3, "team_a": 4,
         "finished": True, "finished_provisional": False, "team_h_score": 1, "team_a_score": 1},
        {"id": 3, "event": 2, "kickoff_time": "2026-08-22T14:00:00Z", "team_h": 5, "team_a": 6,
         "finished": False, "finished_provisional": False, "team_h_score": None, "team_a_score": None},
    ]

def test_builds_realized_fixture_states_and_gameweek_summaries():
    rows, summaries, report = build_realized_fixture_states(fixtures(), season="2026-27")
    assert len(rows) == 2
    assert rows[0]["result"] == "H"
    assert rows[0]["total_goals"] == 2
    assert rows[1]["result"] == "D"
    assert summaries == [{
        "season": "2026-27", "gameweek": 1, "fixture_count": 2,
        "home_goals": 3, "away_goals": 1, "total_goals": 4,
        "home_wins": 1, "draws": 1, "away_wins": 0,
    }]
    assert report["finality_status"] == "REQUIRES_OFFICIAL_EVENT_LIVE_RECONCILIATION"
    assert report["decision_weight"] == 0.0

@pytest.mark.parametrize("mutate,match", [
    (lambda x: x[0].update(team_h_score=None), "team_h_score"),
    (lambda x: x[0].update(kickoff_time="2026-08-15T14:00:00"), "timezone"),
    (lambda x: x[0].update(team_a=1), "identical home and away"),
    (lambda x: x[0].update(team_h_score=-1), "integer >= 0"),
])
def test_rejects_invalid_fixture_states(mutate, match):
    data = fixtures()
    mutate(data)
    with pytest.raises(RealizedFixtureStateError, match=match):
        build_realized_fixture_states(data, season="2026-27")

def test_rejects_duplicate_fixture_ids():
    data = fixtures()
    data[1]["id"] = data[0]["id"]
    with pytest.raises(RealizedFixtureStateError, match="duplicate fixture ID"):
        build_realized_fixture_states(data, season="2026-27")

def test_private_ingestion_directory_pipeline_and_hashes(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    fixture_data = fixtures()
    (source / "fixtures.json").write_text(json.dumps(fixture_data), encoding="utf-8")
    ingestion = {"status": "PASS", "season": "2026-27"}
    (source / "ingestion_report.json").write_text(json.dumps(ingestion), encoding="utf-8")
    canonical = hashlib.sha256(json.dumps(fixture_data, sort_keys=True).encode()).hexdigest()
    metadata = {"season": "2026-27", "fixtures_sha256": canonical}
    (source / "source_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    output = tmp_path / "private" / "fixture-states"
    report = build_from_ingestion_directory(source, output)
    assert report["status"] == "PASS_STRUCTURAL_ONLY"
    assert os.stat(output).st_mode & 0o777 == 0o700
    assert os.stat(output / "fixture_state_report.json").st_mode & 0o777 == 0o600
    assert report["fixture_state_output_sha256"] == hashlib.sha256(
        (output / "fpl_realized_fixture_states.csv").read_bytes()).hexdigest()

def test_rejects_tampered_fixtures_against_source_metadata(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    fixture_data = fixtures()
    (source / "fixtures.json").write_text(json.dumps(fixture_data), encoding="utf-8")
    (source / "ingestion_report.json").write_text(json.dumps({"status": "PASS", "season": "2026-27"}), encoding="utf-8")
    (source / "source_metadata.json").write_text(json.dumps({"season": "2026-27", "fixtures_sha256": "0" * 64}), encoding="utf-8")
    with pytest.raises(RealizedFixtureStateError, match="metadata hash"):
        build_from_ingestion_directory(source, tmp_path / "out")
