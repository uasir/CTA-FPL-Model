from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

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
        abc_source_report={"source_hashes": {"wyscout": "abc123"}},
        fpl_source_report={"source_commit": "pinned", "panel_sha256": "panel123",
                          "source_files": [{"season": "2017-18", "sha256": "file123"}]},
    )
    assert [row["fixture_id"] for row in expected] == ["101", "102"]
    assert expected[0]["season"] == "2017/18"
    assert report["status"] == "PASS"
    assert report["expected_player_fixture_rows"] == 2
    assert report["fpl_panel_sha256"] == "panel123"
    assert report["abc_source_hashes"] == {"wyscout": "abc123"}


def test_reference_universe_reports_missing_abc_double_gameweek_fixture_without_player_keys():
    expected, report = build_expected_fixture_rows(
        [abc("101")],
        [fpl("101"), fpl("102", "5", "75")],
    )
    assert report["status"] == "FAIL_CLOSED"
    assert report["mismatch_reason_counts"]["ABC_FIXTURE_MISSING"] == 1
    assert "fpl_element_id" not in report
    assert expected == [{"season": "2017/18", "fpl_element_id": "10",
                         "gameweek": 7, "fixture_id": "101"},
                        {"season": "2017/18", "fpl_element_id": "10",
                         "gameweek": 7, "fixture_id": "102"}]


def test_reference_universe_reports_target_mismatch_without_player_keys():
    _, report = build_expected_fixture_rows(
        [abc("101", "3", "90")],
        [fpl("101", "4", "90")],
    )
    assert report["status"] == "FAIL_CLOSED"
    assert report["mismatch_reason_counts"]["TARGET_MISMATCH"] == 1


def test_reference_universe_detects_abc_fixture_absent_from_fpl_reference():
    _, report = build_expected_fixture_rows(
        [abc("101"), abc("102", "5", "75")],
        [fpl("101")],
    )
    assert report["status"] == "FAIL_CLOSED"
    assert report["mismatch_reason_counts"]["FPL_REFERENCE_FIXTURE_MISSING"] == 1


def test_reference_universe_requires_player_gameweek_key():
    bad = abc("101")
    bad["fpl_element_id"] = ""
    try:
        build_expected_fixture_rows([bad], [fpl("101")])
    except ValueError as exc:
        assert "FPL element ID" in str(exc)
    else:
        raise AssertionError("Invalid player key must fail")
