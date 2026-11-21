from __future__ import annotations

import pytest

from m4_covar_realized_fpl_dataset import (
    RealizedFplDatasetError,
    build_realized_panel,
)


def _inputs():
    players = [
        {"season": "2026-27", "fpl_element_id": "10"},
        {"season": "2026-27", "fpl_element_id": "11"},
    ]
    fixtures = [
        {"season": "2026-27", "fixture_id": "100", "gameweek": "1",
         "kickoff_time": "2026-08-10T15:00:00Z", "team_h_id": "1",
         "team_a_id": "2", "finished": "True", "finished_provisional": "False"},
        {"season": "2026-27", "fixture_id": "101", "gameweek": "1",
         "kickoff_time": "2026-08-12T19:00:00Z", "team_h_id": "3",
         "team_a_id": "1", "finished": "True", "finished_provisional": "False"},
        {"season": "2026-27", "fixture_id": "102", "gameweek": "2",
         "kickoff_time": "2026-08-20T19:00:00Z", "team_h_id": "2",
         "team_a_id": "3", "finished": "False", "finished_provisional": "False"},
    ]
    def row(pid, fid, gw, minutes, points, was_home, **extra):
        base = {
            "season": "2026-27", "fpl_element_id": str(pid), "fixture_id": str(fid),
            "gameweek": str(gw), "minutes": str(minutes), "total_points": str(points),
            "was_home": str(was_home),
        }
        for field in (
            "goals_scored", "assists", "clean_sheets", "goals_conceded", "own_goals",
            "penalties_saved", "penalties_missed", "yellow_cards", "red_cards",
            "saves", "bonus", "bps",
        ):
            base[field] = str(extra.get(field, 0))
        return base
    history = [
        row(10, 100, 1, 90, 6, True, goals_scored=1),
        row(10, 101, 1, 30, 2, False, assists=1),
        row(11, 100, 1, 0, 0, False),
    ]
    return players, fixtures, history


def test_builds_fixture_and_gameweek_rows_and_sums_double_gameweek():
    players, fixtures, history = _inputs()
    fixture_rows, gw_rows, report = build_realized_panel(
        players, fixtures, history, season="2026-27"
    )
    assert len(fixture_rows) == 3
    assert len(gw_rows) == 2
    player10 = next(row for row in gw_rows if row["fpl_element_id"] == 10)
    assert player10["fixtures_count"] == 2
    assert player10["minutes"] == 120
    assert player10["total_points"] == 8
    assert player10["goals_scored"] == 1
    assert player10["assists"] == 1
    assert player10["played_any_fixture"] is True
    assert report["point_in_time_status"] == "NOT_VERIFIED_RETROSPECTIVE_OFFICIAL_API_HISTORY"


def test_zero_row_is_preserved_when_officially_present():
    players, fixtures, history = _inputs()
    fixture_rows, _, _ = build_realized_panel(players, fixtures, history, season="2026-27")
    row = next(x for x in fixture_rows if x["fpl_element_id"] == 11)
    assert row["minutes"] == 0
    assert row["total_points"] == 0
    assert row["played"] is False


def test_missing_player_fixture_is_not_synthesized():
    players, fixtures, history = _inputs()
    _, gw_rows, report = build_realized_panel(players, fixtures, history, season="2026-27")
    assert len(gw_rows) == 2
    assert report["missing_player_fixture_rows_zero_filled"] == 0
    assert report["unique_players_with_observed_rows"] == 2


def test_duplicate_player_fixture_key_rejected():
    players, fixtures, history = _inputs()
    with pytest.raises(RealizedFplDatasetError, match="duplicate"):
        build_realized_panel(players, fixtures, history + [history[0]], season="2026-27")


def test_unknown_player_rejected():
    players, fixtures, history = _inputs()
    history[0]["fpl_element_id"] = "999"
    with pytest.raises(RealizedFplDatasetError, match="unknown"):
        build_realized_panel(players, fixtures, history, season="2026-27")


def test_fixture_gameweek_mismatch_rejected():
    players, fixtures, history = _inputs()
    history[0]["gameweek"] = "2"
    with pytest.raises(RealizedFplDatasetError, match="Gameweek disagrees"):
        build_realized_panel(players, fixtures, history, season="2026-27")


def test_unfinished_fixture_history_is_not_a_target():
    players, fixtures, history = _inputs()
    history.append({
        **history[0], "fixture_id": "102", "gameweek": "2",
    })
    fixture_rows, _, report = build_realized_panel(players, fixtures, history, season="2026-27")
    assert all(row["fixture_id"] != 102 for row in fixture_rows)
    assert report["ignored_unfinished_or_unassigned_player_fixture_rows"] == 1


def test_cross_season_rows_rejected():
    players, fixtures, history = _inputs()
    history[0]["season"] = "2025-26"
    with pytest.raises(RealizedFplDatasetError, match="season mismatch"):
        build_realized_panel(players, fixtures, history, season="2026-27")


def test_fixture_minutes_bounds_rejected():
    players, fixtures, history = _inputs()
    history[0]["minutes"] = "121"
    with pytest.raises(RealizedFplDatasetError, match="minutes outside"):
        build_realized_panel(players, fixtures, history, season="2026-27")



def test_unknown_fixture_reference_rejected():
    players, fixtures, history = _inputs()
    history[0]["fixture_id"] = "999"
    with pytest.raises(RealizedFplDatasetError, match="unknown season fixture"):
        build_realized_panel(players, fixtures, history, season="2026-27")


def test_provisional_flag_is_preserved_without_discarding_completed_fixture():
    players, fixtures, history = _inputs()
    fixtures[0]["finished_provisional"] = "True"
    fixture_rows, _, report = build_realized_panel(players, fixtures, history, season="2026-27")
    rows = [row for row in fixture_rows if row["fixture_id"] == 100]
    assert len(rows) == 2
    assert all(row["fixture_finished_provisional"] is True for row in rows)
    assert report["fixtures_marked_finished_provisional"] == 1
    assert report["outcome_finality_status"] == "REQUIRES_FINALITY_RECONCILIATION"


def test_missing_official_stat_is_rejected_not_zero_filled():
    players, fixtures, history = _inputs()
    del history[0]["bonus"]
    with pytest.raises(RealizedFplDatasetError, match="bonus must be an integer"):
        build_realized_panel(players, fixtures, history, season="2026-27")



def test_card_only_appearance_counts_as_played_and_negative_bps_is_preserved():
    players, fixtures, history = _inputs()
    history[0]["minutes"] = "0"
    history[0]["yellow_cards"] = "1"
    history[0]["bps"] = "-2"
    fixture_rows, _, _ = build_realized_panel(players, fixtures, history, season="2026-27")
    row = next(x for x in fixture_rows if x["fpl_element_id"] == 10 and x["fixture_id"] == 100)
    assert row["played"] is True
    assert row["bps"] == -2
