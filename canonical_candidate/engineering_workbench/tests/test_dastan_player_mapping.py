from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audit_dastan_player_mapping import audit_mapping


def test_mapping_audit_retains_unmapped_roster_players_and_reports_shared_ids():
    roster = [
        {"season": "2026-27", "fpl_code": "100", "element": "1", "player_name": "A", "position": "MID", "team_name": "Club A"},
        {"season": "2026-27", "fpl_code": "200", "element": "2", "player_name": "B", "position": "DEF", "team_name": "Club B"},
        {"season": "2026-27", "fpl_code": "300", "element": "3", "player_name": "C", "position": "FWD", "team_name": "Club C"},
    ]
    mapping = [
        {"fpl_code": "100", "understat_id": "900", "mapping_status": "mapped", "confidence": "HIGH"},
        {"fpl_code": "200", "understat_id": "900", "mapping_status": "mapped", "confidence": "MEDIUM"},
    ]

    report = audit_mapping(roster, mapping, "mapping-release-test")

    assert report["roster_players"] == 3
    assert report["mapped_players"] == 2
    assert report["unmapped_players"] == 1
    assert report["unmapped_fpl_codes"] == ["300"]
    assert report["shared_understat_ids"] == {"900": ["100", "200"]}
    assert report["understat_join_ready"] is False
    assert report["rows"][2]["understat_id"] == ""


def test_mapping_audit_rejects_duplicate_fpl_codes_in_mapping():
    roster = [{"fpl_code": "100"}]
    mapping = [
        {"fpl_code": "100", "understat_id": "900", "mapping_status": "mapped"},
        {"fpl_code": "100", "understat_id": "901", "mapping_status": "mapped"},
    ]

    with pytest.raises(ValueError, match="duplicate fpl_code"):
        audit_mapping(roster, mapping)


def test_mapping_audit_rejects_blank_fpl_code():
    with pytest.raises(ValueError, match="blank fpl_code"):
        audit_mapping([{"fpl_code": ""}], [{"fpl_code": "100", "understat_id": "900"}])
