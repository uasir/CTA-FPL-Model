import pytest
from types import SimpleNamespace

import numpy as np
import pandas as pd

from rebuild_2pm_fixture_context import rebuild_player_history_features


def player_row(fixture, kickoff, available, *, points, goals, minutes, home, dc, cbit, recoveries, tackles, starts):
    return {
        "season": "2025-26",
        "fixture": fixture,
        "fpl_code": 100,
        "element": 10,
        "understat_id": 500,
        "position": "MID",
        "is_home": home,
        "kickoff_time": pd.Timestamp(kickoff, tz="UTC"),
        "match_available_at": pd.Timestamp(available, tz="UTC"),
        "minutes": minutes,
        "total_points": points,
        "goals_scored": goals,
        "defensive_contribution": dc,
        "clearances_blocks_interceptions": cbit,
        "recoveries": recoveries,
        "tackles": tackles,
        "starts": starts,
    }


def fake_features():
    return SimpleNamespace(
        WINDOWS=[1, 3, 5, 10, 38],
        PLAYER_FEATURES={
            "total_points": "fpl_points",
            "goals_scored": "goals_scored",
        },
        DC_THRESHOLD={"DEF": 10, "MID": 12, "FWD": 12, "GKP": 99},
        POSITION_BASE_RATES={
            "GKP": {"p_any": 0.50, "p60": 0.48, "e_minutes": 45.0},
            "DEF": {"p_any": 0.55, "p60": 0.42, "e_minutes": 42.0},
            "MID": {"p_any": 0.52, "p60": 0.38, "e_minutes": 38.0},
            "FWD": {"p_any": 0.50, "p60": 0.35, "e_minutes": 35.0},
        },
    )


def test_player_history_rebuild_excludes_matches_not_available_by_deadline():
    history = pd.DataFrame(
        [
            player_row("f1", "2026-01-01", "2026-01-02", points=10, goals=2, minutes=90, home=True, dc=12, cbit=5, recoveries=3, tackles=2, starts=1),
            player_row("f2", "2026-01-05", "2026-01-06", points=0, goals=0, minutes=0, home=False, dc=8, cbit=1, recoveries=1, tackles=0, starts=0),
            # Kicked off before target, but the conservative completion bound is after deadline.
            player_row("f3", "2026-01-08", "2026-01-10", points=99, goals=9, minutes=90, home=True, dc=30, cbit=9, recoveries=9, tackles=9, starts=1),
            player_row("target", "2026-01-10", "2026-01-11", points=5, goals=1, minutes=90, home=True, dc=15, cbit=4, recoveries=2, tackles=2, starts=1),
        ]
    )
    target = pd.DataFrame(
        [{
            "season": "2025-26",
            "fixture": "target",
            "fpl_code": 100,
            "deadline_time": pd.Timestamp("2026-01-09", tz="UTC"),
            "kickoff_time": pd.Timestamp("2026-01-10", tz="UTC"),
        }]
    )
    result, report = rebuild_player_history_features(target, history, fake_features())
    row = result.iloc[0]
    assert row["player_fpl_points_1"] == 0.0
    assert row["player_goals_scored_1"] == 0.0
    assert row["player_goals_scored_3"] == 1.0
    assert row["player_relevant_fpl_points_1"] == 10.0
    assert row["p_any_3"] == 0.5
    assert row["p60_3"] == 0.5
    assert row["e_minutes_3"] == 45.0
    assert row["ar_defensive_contribution_3"] == 10.0
    assert row["ar_cbit_3"] == 3.0
    assert row["ar_dc_hit_rate_3"] == 0.5
    assert row["ar_starts_3"] == 0.5
    assert report["player_rolling_feature_count"] == 15
    assert report["availability_feature_count"] == 9


def test_rejects_played_history_without_match_availability():
    history = pd.DataFrame([
        player_row(
            "f1", "2026-01-01", "2026-01-02",
            points=5, goals=1, minutes=90, home=True,
            dc=12, cbit=5, recoveries=3, tackles=2, starts=1,
        )
    ])
    history["match_available_at"] = pd.NaT
    target = pd.DataFrame([{
        "season": "2025-26",
        "fixture": "target",
        "fpl_code": 100,
        "deadline_time": pd.Timestamp("2026-01-09", tz="UTC"),
        "kickoff_time": pd.Timestamp("2026-01-10", tz="UTC"),
    }])
    with pytest.raises(ValueError, match="require match availability timestamps"):
        rebuild_player_history_features(target, history, fake_features())


def test_rejects_match_availability_at_or_before_kickoff():
    history = pd.DataFrame([
        player_row(
            "f1", "2026-01-01", "2026-01-01",
            points=5, goals=1, minutes=90, home=True,
            dc=12, cbit=5, recoveries=3, tackles=2, starts=1,
        )
    ])
    target = pd.DataFrame([{
        "season": "2025-26",
        "fixture": "target",
        "fpl_code": 100,
        "deadline_time": pd.Timestamp("2026-01-09", tz="UTC"),
        "kickoff_time": pd.Timestamp("2026-01-10", tz="UTC"),
    }])
    with pytest.raises(ValueError, match="strictly after kickoff"):
        rebuild_player_history_features(target, history, fake_features())


def test_rejects_duplicate_player_fixture_history_rows():
    row = player_row(
        "f1", "2026-01-01", "2026-01-02",
        points=5, goals=1, minutes=90, home=True,
        dc=12, cbit=5, recoveries=3, tackles=2, starts=1,
    )
    history = pd.DataFrame([row, row])
    target = pd.DataFrame([{
        "season": "2025-26",
        "fixture": "target",
        "fpl_code": 100,
        "deadline_time": pd.Timestamp("2026-01-09", tz="UTC"),
        "kickoff_time": pd.Timestamp("2026-01-10", tz="UTC"),
    }])
    with pytest.raises(ValueError, match="unique at season-fixture-player grain"):
        rebuild_player_history_features(target, history, fake_features())


def test_availability_uses_position_base_rates_when_no_prior_rows():
    target_history = pd.DataFrame(
        [
            player_row("target", "2026-01-10", "2026-01-11", points=5, goals=1, minutes=90, home=True, dc=15, cbit=4, recoveries=2, tackles=2, starts=1),
        ]
    )
    target_history["match_available_at"] = pd.NaT
    target = pd.DataFrame(
        [{
            "season": "2025-26",
            "fixture": "target",
            "fpl_code": 100,
            "deadline_time": pd.Timestamp("2026-01-09", tz="UTC"),
            "kickoff_time": pd.Timestamp("2026-01-10", tz="UTC"),
        }]
    )
    result, _ = rebuild_player_history_features(target, target_history, fake_features())
    assert result.loc[0, "p_any_3"] == 0.52
    assert result.loc[0, "p60_3"] == 0.38
    assert result.loc[0, "e_minutes_3"] == 38.0
    assert np.isnan(result.loc[0, "ar_defensive_contribution_3"])
