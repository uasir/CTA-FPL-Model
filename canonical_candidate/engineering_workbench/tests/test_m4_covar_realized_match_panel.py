from __future__ import annotations
import os
import pytest
from m4_covar_realized_match_panel import (
    RealizedMatchPanelError, build_realized_match_panel, write_private_match_panel,
)

def inputs():
    fixtures = [{
        "season": "2026-27", "gameweek": 1, "fixture_id": 100,
        "home_team_id": 1, "away_team_id": 2, "home_goals": 2, "away_goals": 1,
        "finished_provisional": True,
    }]
    players = [
        {"season": "2026-27", "gameweek": 1, "fixture_id": 100, "fpl_element_id": 10,
         "team_id_at_fixture": 1, "opponent_team_id": 2, "was_home": True,
         "fixture_finished_provisional": True, "minutes": 90, "total_points": 8},
        {"season": "2026-27", "gameweek": 1, "fixture_id": 100, "fpl_element_id": 20,
         "team_id_at_fixture": 2, "opponent_team_id": 1, "was_home": False,
         "fixture_finished_provisional": True, "minutes": 90, "total_points": 2},
    ]
    return players, fixtures

def test_joins_player_outcomes_to_exact_fixture_state():
    players, fixtures = inputs()
    rows, report = build_realized_match_panel(
        player_fixture_rows=players, fixture_state_rows=fixtures, season="2026-27")
    assert len(rows) == 2
    assert rows[0]["home_goals"] == 2
    assert rows[1]["fixture_result"] == "H"
    assert report["fixture_state_join"].startswith("EXACT_FIXTURE_ID")
    assert report["finality_status"] == "INHERITED_FROM_UPSTREAM_AUDIT_NOT_RECHECKED"

@pytest.mark.parametrize("mutate,match", [
    (lambda p,f: p[0].update(gameweek=2), "Gameweek mismatch"),
    (lambda p,f: p[0].update(team_id_at_fixture=2), "orientation mismatch"),
    (lambda p,f: p[0].update(fixture_finished_provisional=False), "provisional flag mismatch"),
    (lambda p,f: p.append(dict(p[0])), "duplicate player-fixture"),
    (lambda p,f: f[0].update(home_goals=-1), "goals cannot be negative"),
])
def test_rejects_mismatched_or_duplicate_rows(mutate, match):
    players, fixtures = inputs()
    mutate(players, fixtures)
    with pytest.raises(RealizedMatchPanelError, match=match):
        build_realized_match_panel(player_fixture_rows=players, fixture_state_rows=fixtures, season="2026-27")

def test_writes_private_hashed_match_panel(tmp_path):
    players, fixtures = inputs()
    rows, report = build_realized_match_panel(player_fixture_rows=players, fixture_state_rows=fixtures, season="2026-27")
    output = tmp_path / "private" / "panel"
    saved = write_private_match_panel(rows, report, output)
    assert os.stat(output).st_mode & 0o777 == 0o700
    assert os.stat(output / "match_panel_report.json").st_mode & 0o777 == 0o600
    assert saved["panel_sha256"]
