from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest
from build_abc_expected_fixture_universe import build_expected_fixture_rows


def abc(fixture, points="3", minutes="90"):
    return {
        "season": "2017/18", "fpl_element_id": "10", "gameweek": "7",
        "fixture_id": fixture, "target_fpl_total_points": points,
        "target_fpl_minutes": minutes,
    }


def fpl(fixture, points="3", minutes="90"):
    return {
        "season": "2017-18", "fpl_element_id": "10", "gameweek": "7",
        "fixture_id": fixture, "target_total_points": points,
        "target_minutes": minutes,
    }


def test_reference_fixture_universe_normalizes_season_and_matches_targets():
    expected, report = build_expected_fixture_rows(
        [abc("101"), abc("102", "5", "75")],
        [fpl("101"), fpl("102", "5", "75")],
    )
    assert [row["fixture_id"] for row in expected] == ["101", "102"]
    assert report["status"] == "PASS"
    assert report["expected_player_fixture_rows"] == 2


def test_reference_universe_detects_missing_abc_double_gameweek_fixture():
    with pytest.raises(ValueError, match="ABC_FIXTURE_MISSING"):
        build_expected_fixture_rows(
            [abc("101")],
            [fpl("101"), fpl("102", "5", "75")],
        )


def test_reference_universe_detects_target_points_or_minutes_mismatch():
    with pytest.raises(ValueError, match="TARGET_MISMATCH"):
        build_expected_fixture_rows(
            [abc("101", "3", "90")],
            [fpl("101", "4", "90")],
        )


def test_reference_universe_detects_abc_fixture_absent_from_fpl_reference():
    with pytest.raises(ValueError, match="FPL_REFERENCE_FIXTURE_MISSING"):
        build_expected_fixture_rows(
            [abc("101"), abc("102", "5", "75")],
            [fpl("101")],
        )


def test_reference_universe_requires_player_gameweek_key():
    bad = abc("101")
    bad["fpl_element_id"] = ""
    with pytest.raises(ValueError, match="FPL element ID"):
        build_expected_fixture_rows([bad], [fpl("101")])
