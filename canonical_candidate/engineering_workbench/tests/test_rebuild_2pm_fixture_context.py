import pandas as pd
from types import SimpleNamespace

from rebuild_2pm_fixture_context import (
    rebuild_deadline_team_context,
    rebuild_fixture_context,
    rebuild_player_history_features,
)


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
    assert first["ar_team_matches_14d"] == 1
    assert second["ar_team_matches_14d"] == 2
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



def test_unfinished_target_fixture_is_schedule_context_not_historical_result():
    history = pd.DataFrame(
        [
            row("2025-26", "prior", 100, "T", "Q", "2026-01-03", "2026-01-04", 2, 1),
            row("2025-26", "target", 100, "T", "O", "2026-01-10", "2026-01-11", 99, 99),
            row("2025-26", "target", 201, "O", "T", "2026-01-10", "2026-01-11", 1, 1),
        ]
    )
    history.loc[history["fixture"].eq("target"), "match_available_at"] = pd.NaT
    target = pd.DataFrame(
        [{
            "season": "2025-26", "gameweek": 20, "fixture": "target", "fpl_code": 100,
            "deadline_time": pd.Timestamp("2026-01-09", tz="UTC"),
            "kickoff_time": pd.Timestamp("2026-01-10", tz="UTC"),
            "team_name": "T", "opponent_team_name": "O",
        }]
    )
    result, _ = rebuild_fixture_context(target, history)
    assert result.loc[0, "ar_rest_days"] == 7
    assert result.loc[0, "__observed__ar_rest_days"] == 1
    assert result.loc[0, "ar_team_matches_14d"] == 1
    assert result.loc[0, "__observed__ar_team_matches_14d"] == 0
    assert pd.isna(result.loc[0, "ar_opp_dc_allowed_3"])


def test_missing_defensive_stats_do_not_become_zero_or_partial_opponent_totals():
    history = pd.DataFrame(
        [
            row("2025-26", "prior", 201, "A", "O", "2026-01-01", "2026-01-02", 10, 4),
            row("2025-26", "prior", 202, "A", "O", "2026-01-01", "2026-01-02", float("nan"), 2),
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
    assert not pd.isna(result.loc[0, "ar_opp_tackles_allowed_5"])
    assert result.loc[0, "ar_opp_tackles_allowed_5"] == 6
    assert result.loc[0, "__observed__ar_opp_dc_allowed_3"] == 0
    assert result.loc[0, "__observed__ar_opp_tackles_allowed_5"] == 1
    assert result.loc[0, "__observed__ar_rest_days"] == 0
    assert result.loc[0, "__observed__ar_team_matches_14d"] == 0



def test_league_rank_fallbacks_are_unobserved_until_prior_completed_matches_exist():
    def prepare_team_matches(frame):
        return frame.copy()

    def build_opponent_lookup(frame):
        return frame.copy()

    def compute_league_ranks(frame):
        ranks = {}
        for date, day in frame.groupby("date", sort=True):
            for team in day["understat_team"].astype(str):
                ranks[(team, str(day.iloc[0]["season"]), date.strftime("%Y-%m-%d %H:%M"))] = 1
        return ranks

    features = SimpleNamespace(
        WINDOWS=[1],
        TEAM_FEATURES={
            "scored": "goals_scored",
            "missed": "goals_conceded",
            "league_rank": "league_rank",
            "opp_league_rank": "opponent_league_rank",
        },
        fpl_to_understat={"T": "UT", "O": "UO"},
        _prepare_team_matches=prepare_team_matches,
        build_opponent_lookup=build_opponent_lookup,
        compute_league_ranks=compute_league_ranks,
    )
    team_matches = pd.DataFrame([
        {
            "season": "2025-26", "understat_team": "UT", "opponent": "UO",
            "date": pd.Timestamp("2026-01-01", tz="UTC"),
            "scored": 1, "missed": 0, "pts": 3,
        },
        {
            "season": "2025-26", "understat_team": "UO", "opponent": "UT",
            "date": pd.Timestamp("2026-01-01", tz="UTC"),
            "scored": 0, "missed": 1, "pts": 0,
        },
    ])
    targets = pd.DataFrame([
        {
            "season": "2025-26", "fixture": "early", "fpl_code": 10,
            "deadline_time": pd.Timestamp("2026-01-01 12:00", tz="UTC"),
            "team_name": "T", "opponent_team_name": "O",
        },
        {
            "season": "2025-26", "fixture": "later", "fpl_code": 10,
            "deadline_time": pd.Timestamp("2026-01-03", tz="UTC"),
            "team_name": "T", "opponent_team_name": "O",
        },
    ])

    result, _ = rebuild_deadline_team_context(targets, team_matches, features)

    # No completed match by the first deadline: fallback direct ranks are not observations.
    assert result.loc[0, "__observed__status_league_rank"] == 0
    assert result.loc[0, "__observed__opp_status_league_rank"] == 0
    # The first completed match's pre-match rank also had no prior table behind it.
    assert result.loc[1, "__observed__team_league_rank_1"] == 0
    # The direct deadline rank is now based on completed league results.
    assert result.loc[1, "__observed__status_league_rank"] == 1


def test_position_base_rate_fallbacks_are_not_marked_as_player_observations():
    features = SimpleNamespace(
        WINDOWS=[1],
        PLAYER_FEATURES={"total_points": "fpl_points"},
        DC_THRESHOLD={"MID": 10},
        POSITION_BASE_RATES={"MID": {"p_any": 0.72, "p60": 0.61, "e_minutes": 58.0}},
    )
    player_matches = pd.DataFrame([{
        "season": "2025-26", "fixture": "target", "fpl_code": 10,
        "element": 10, "understat_id": 100, "position": "MID", "is_home": True,
        "kickoff_time": pd.Timestamp("2026-01-10", tz="UTC"),
        "match_available_at": pd.NaT, "minutes": 0, "total_points": 0,
    }])
    target = pd.DataFrame([{
        "season": "2025-26", "fixture": "target", "fpl_code": 10,
        "element": 10, "understat_id": 100, "position": "MID", "is_home": True,
        "kickoff_time": pd.Timestamp("2026-01-10", tz="UTC"),
        "deadline_time": pd.Timestamp("2026-01-09", tz="UTC"),
    }])
    result, report = rebuild_player_history_features(target, player_matches, features)
    for prefix, expected in {"p_any": 0.72, "p60": 0.61, "e_minutes": 58.0}.items():
        for window in (3, 5, 10):
            feature = f"{prefix}_{window}"
            assert result.loc[0, feature] == expected
            assert result.loc[0, f"__observed__{feature}"] == 0
    assert "position-specific base rates" in report["availability_semantics"]


def test_rest_days_default_is_unobserved_when_player_has_no_available_prior_fixture():
    history = pd.DataFrame([row(
        "2025-26", "target", 100, "T", "O",
        "2026-01-10", "2026-01-11", 0, 0,
    )])
    target = pd.DataFrame([{
        "season": "2025-26", "gameweek": 20, "fixture": "target", "fpl_code": 100,
        "deadline_time": pd.Timestamp("2026-01-09", tz="UTC"),
        "kickoff_time": pd.Timestamp("2026-01-10", tz="UTC"),
        "team_name": "T", "opponent_team_name": "O",
    }])
    result, _ = rebuild_fixture_context(target, history)
    assert result.loc[0, "ar_rest_days"] == 14
    assert result.loc[0, "__observed__ar_rest_days"] == 0


def test_string_venue_flags_are_parsed_strictly_and_unknown_positions_are_unobserved():
    features = SimpleNamespace(
        WINDOWS=[1],
        PLAYER_FEATURES={"total_points": "fpl_points"},
        DC_THRESHOLD={"MID": 10},
        POSITION_BASE_RATES={"MID": {"p_any": 0.7, "p60": 0.6, "e_minutes": 55.0}},
    )
    player_matches = pd.DataFrame([
        {"season": "2025-26", "fixture": "home", "fpl_code": 10, "element": 10, "understat_id": 100, "position": "UNKNOWN", "is_home": "True", "kickoff_time": pd.Timestamp("2026-01-01", tz="UTC"), "match_available_at": pd.Timestamp("2026-01-02", tz="UTC"), "minutes": 90, "total_points": 10, "defensive_contribution": 12},
        {"season": "2025-26", "fixture": "away", "fpl_code": 10, "element": 10, "understat_id": 100, "position": "UNKNOWN", "is_home": "False", "kickoff_time": pd.Timestamp("2026-01-03", tz="UTC"), "match_available_at": pd.Timestamp("2026-01-04", tz="UTC"), "minutes": 90, "total_points": 4, "defensive_contribution": 12},
        {"season": "2025-26", "fixture": "target", "fpl_code": 10, "element": 10, "understat_id": 100, "position": "UNKNOWN", "is_home": "False", "kickoff_time": pd.Timestamp("2026-01-10", tz="UTC"), "match_available_at": pd.NaT, "minutes": 0, "total_points": 0, "defensive_contribution": 0},
    ])
    target = pd.DataFrame([{
        "season": "2025-26", "fixture": "target", "fpl_code": 10, "element": 10,
        "understat_id": 100, "position": "UNKNOWN", "is_home": "False",
        "kickoff_time": pd.Timestamp("2026-01-10", tz="UTC"),
        "deadline_time": pd.Timestamp("2026-01-09", tz="UTC"),
    }])
    result, _ = rebuild_player_history_features(target, player_matches, features)
    assert result.loc[0, "player_relevant_fpl_points_1"] == 4.0
    assert pd.isna(result.loc[0, "ar_dc_hit_rate_3"])
    assert result.loc[0, "__observed__ar_dc_hit_rate_3"] == 0
