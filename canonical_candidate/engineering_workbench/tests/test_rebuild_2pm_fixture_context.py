import pandas as pd

from rebuild_2pm_fixture_context import rebuild_fixture_context


def row(season, fixture, code, team, opponent, kickoff, available, dc, tackles):
    return {
        "season": season,
        "fixture": fixture,
        "fpl_code": code,
        "element": code,
        "understat_id": code * 10,
        "team_name": team,
        "opponent_team_name": opponent,
        "kickoff_time": pd.Timestamp(kickoff, tz="UTC"),
        "match_available_at": pd.Timestamp(available, tz="UTC"),
        "defensive_contribution": dc,
        "tackles": tackles,
    }


def test_rebuilds_rest_congestion_and_opponent_allowance_per_target_fixture():
    history = pd.DataFrame(
        [
            # Player's previous team fixture.
            row("2025-26", "f0", 100, "T", "Q", "2026-01-03", "2026-01-04", 1, 1),
            # Two prior fixtures played by O; their opponents' DC/tackles are attributed to O.
            row("2025-26", "o1", 201, "A", "O", "2026-01-01", "2026-01-02", 10, 4),
            row("2025-26", "o1", 202, "O", "A", "2026-01-01", "2026-01-02", 3, 2),
            row("2025-26", "o2", 301, "B", "O", "2026-01-05", "2026-01-06", 20, 8),
            row("2025-26", "o2", 302, "O", "B", "2026-01-05", "2026-01-06", 4, 2),
            # One prior fixture played by P.
            row("2025-26", "p1", 401, "C", "P", "2026-01-06", "2026-01-07", 30, 12),
            row("2025-26", "p1", 402, "P", "C", "2026-01-06", "2026-01-07", 5, 2),
            # Target fixtures are included in the known schedule but are not available by deadline.
            row("2025-26", "t1", 100, "T", "O", "2026-01-10", "2026-01-11", 0, 0),
            row("2025-26", "t2", 100, "T", "P", "2026-01-14", "2026-01-15", 0, 0),
        ]
    )
    target = pd.DataFrame(
        [
            {
                "season": "2025-26", "gameweek": 20, "fixture": "t1", "fpl_code": 100,
                "deadline_time": pd.Timestamp("2026-01-09", tz="UTC"),
                "kickoff_time": pd.Timestamp("2026-01-10", tz="UTC"),
                "team_name": "T", "opponent_team_name": "O",
            },
            {
                "season": "2025-26", "gameweek": 20, "fixture": "t2", "fpl_code": 100,
                "deadline_time": pd.Timestamp("2026-01-09", tz="UTC"),
                "kickoff_time": pd.Timestamp("2026-01-14", tz="UTC"),
                "team_name": "T", "opponent_team_name": "P",
            },
        ]
    )
    result, report = rebuild_fixture_context(target, history)
    first, second = result.iloc[0], result.iloc[1]
    assert first["ar_rest_days"] == 7
    assert second["ar_rest_days"] == 11
    assert first["ar_team_matches_14d"] == 2
    assert second["ar_team_matches_14d"] == 3
    assert first["ar_opp_dc_allowed_3"] == 15
    assert first["ar_opp_dc_allowed_5"] == 15
    assert first["ar_opp_tackles_allowed_5"] == 6
    assert second["ar_opp_dc_allowed_3"] == 30
    assert second["ar_opp_tackles_allowed_5"] == 12
    assert report["same_player_gameweek_multi_fixture_groups"] == 1


def test_opponent_allowance_excludes_matches_not_available_before_deadline():
    history = pd.DataFrame(
        [
            row("2025-26", "future", 201, "A", "O", "2026-01-08", "2026-01-10", 99, 99),
            row("2025-26", "future", 202, "O", "A", "2026-01-08", "2026-01-10", 1, 1),
            row("2025-26", "target", 100, "T", "O", "2026-01-10", "2026-01-11", 0, 0),
        ]
    )
    target = pd.DataFrame(
        [{
            "season": "2025-26", "gameweek": 20, "fixture": "target", "fpl_code": 100,
            "deadline_time": pd.Timestamp("2026-01-09", tz="UTC"),
            "kickoff_time": pd.Timestamp("2026-01-10", tz="UTC"),
            "team_name": "T", "opponent_team_name": "O",
        }]
    )
    result, _ = rebuild_fixture_context(target, history)
    assert pd.isna(result.loc[0, "ar_opp_dc_allowed_3"])
    assert pd.isna(result.loc[0, "ar_opp_tackles_allowed_5"])
