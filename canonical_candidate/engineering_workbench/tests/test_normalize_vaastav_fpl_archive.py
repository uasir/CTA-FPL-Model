from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from normalize_vaastav_fpl_archive import normalize_archive


def _inputs():
    roster = [
        {"id": "11", "code": "1001", "element_type": "3", "team": "1", "web_name": "Player A"},
        {"id": "12", "code": "1002", "element_type": "1", "team": "2", "web_name": "Player B"},
    ]
    teams = [
        {"id": "1", "name": "Club A"},
        {"id": "2", "name": "Club B"},
    ]
    merged = [
        {
            "element": "11", "fixture": "501", "round": "1", "position": "MID",
            "team": "Club A", "opponent_team": "2", "kickoff_time": "2026-08-15T14:00:00Z",
            "was_home": "True", "minutes": "90", "total_points": "8", "goals_scored": "1",
        },
        {
            "element": "12", "fixture": "501", "round": "1", "position": "GK",
            "team": "Club B", "opponent_team": "1", "kickoff_time": "2026-08-15T14:00:00Z",
            "was_home": "False", "minutes": "90", "total_points": "2", "goals_scored": "0",
        },
    ]
    return merged, roster, teams


def test_normalizer_uses_stable_code_and_canonical_fixture_grain():
    merged, roster, teams = _inputs()

    rows, report = normalize_archive(merged, roster, teams, "2026-27")

    assert len(rows) == 2
    assert rows[0]["fpl_code"] == "1001"
    assert rows[0]["fpl_element_id"] == "11"
    assert rows[0]["fixture_id"] == "501"
    assert rows[0]["position"] == "MID"
    assert rows[1]["position"] == "GKP"
    assert report["grain"] == ["season", "fixture_id", "fpl_code"]
    assert report["name_matching"] == "NOT_USED"


def test_normalizer_rejects_duplicate_player_fixture_key():
    merged, roster, teams = _inputs()
    merged.append(dict(merged[0]))

    with pytest.raises(ValueError, match="duplicate"):
        normalize_archive(merged, roster, teams, "2026-27")


def test_normalizer_rejects_element_missing_from_season_roster():
    merged, roster, teams = _inputs()
    merged[0]["element"] = "999"

    with pytest.raises(ValueError, match="absent from season roster"):
        normalize_archive(merged, roster, teams, "2026-27")


def test_normalizer_rejects_position_conflict():
    merged, roster, teams = _inputs()
    merged[0]["position"] = "DEF"

    with pytest.raises(ValueError, match="conflicts with roster"):
        normalize_archive(merged, roster, teams, "2026-27")


def test_normalizer_reports_optional_historical_columns_without_fabricating_values():
    merged, roster, teams = _inputs()

    rows, report = normalize_archive(merged, roster, teams, "2026-27")

    assert rows[0]["defensive_contribution"] == ""
    assert "defensive_contribution" in report["unavailable_optional_match_columns"]
    assert rows[0]["goals_scored"] == "1"


def test_normalizer_rejects_unparseable_kickoff():
    merged, roster, teams = _inputs()
    merged[0]["kickoff_time"] = "not-a-date"

    with pytest.raises(ValueError, match="invalid kickoff_time"):
        normalize_archive(merged, roster, teams, "2026-27")


def test_normalizer_excludes_manager_rows_without_treating_them_as_players():
    merged, roster, teams = _inputs()
    roster.append({"id": "99", "code": "", "element_type": "5", "team": "1", "web_name": "Manager"})
    merged.append({
        "element": "99", "fixture": "501", "round": "1", "position": "AM",
        "team": "Club A", "opponent_team": "2", "kickoff_time": "2026-08-15T14:00:00Z",
        "was_home": "True", "minutes": "90", "total_points": "3",
    })
    rows, report = normalize_archive(merged, roster, teams, "2026-27")
    assert len(rows) == 2
    assert report["excluded_non_player_rows"] == 1


def test_normalizer_rejects_duplicate_stable_player_codes():
    merged, roster, teams = _inputs()
    roster[1]["code"] = roster[0]["code"]

    with pytest.raises(ValueError, match="duplicate stable fpl_code"):
        normalize_archive(merged, roster, teams, "2026-27")
