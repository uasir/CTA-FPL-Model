"""Reconstruct Dastan fixture-specific context after deadline anchoring.

The upstream Dastan anchor broadcasts rolling player/team history across a
player/Gameweek, but it also broadcasts some fixture-specific ar_* context.
This module rebuilds those context fields against the target fixture without
changing player-history features.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

KEY = ["season", "fixture", "fpl_code"]
CONTEXT_COLUMNS = [
    "ar_rest_days",
    "ar_team_matches_14d",
    "ar_opp_dc_allowed_3",
    "ar_opp_dc_allowed_5",
    "ar_opp_dc_allowed_10",
    "ar_opp_tackles_allowed_5",
]


def rebuild_fixture_context(
    target_frame: pd.DataFrame,
    player_matches: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Rebuild six fixture-context fields using only deadline-eligible history.

    player_matches must include all player-fixture rows and a conservative or
    observed match_available_at timestamp for each fixture. Future fixture
    schedules may be used for congestion because the schedule is known before
    the deadline; future match results may not.
    """
    required_target = {
        *KEY, "gameweek", "deadline_time", "kickoff_time",
        "team_name", "opponent_team_name",
    }
    required_history = {
        "season", "fixture", "fpl_code", "team_name", "opponent_team_name",
        "kickoff_time", "match_available_at", "defensive_contribution", "tackles",
    }
    missing_target = sorted(required_target - set(target_frame.columns))
    missing_history = sorted(required_history - set(player_matches.columns))
    if missing_target:
        raise ValueError(f"Target frame missing context columns: {missing_target}")
    if missing_history:
        raise ValueError(f"Player-match history missing columns: {missing_history}")

    out = target_frame.copy().reset_index(drop=True)
    hist = player_matches.copy()
    for frame in (out, hist):
        frame["season"] = frame["season"].astype(str)
        frame["fixture"] = frame["fixture"].astype(str)
        frame["kickoff_time"] = pd.to_datetime(frame["kickoff_time"], utc=True, errors="coerce")
    out["deadline_time"] = pd.to_datetime(out["deadline_time"], utc=True, errors="coerce")
    hist["match_available_at"] = pd.to_datetime(
        hist["match_available_at"], utc=True, errors="coerce"
    )
    if out[["kickoff_time", "deadline_time"]].isna().any().any():
        raise ValueError("Target context contains invalid kickoff/deadline timestamps")
    if hist[["kickoff_time", "match_available_at"]].isna().any().any():
        raise ValueError("Historical context contains invalid kickoff/availability timestamps")

    fixture_rows = hist[
        ["season", "fixture", "team_name", "opponent_team_name",
         "kickoff_time", "match_available_at"]
    ].drop_duplicates(["season", "fixture", "team_name"])
    if fixture_rows.duplicated(["season", "fixture", "team_name"]).any():
        raise ValueError("Fixture/team context rows are not unique")

    # Rest: latest player fixture available strictly before target deadline.
    player_fixture = hist[
        ["season", "fpl_code", "fixture", "kickoff_time", "match_available_at"]
    ].drop_duplicates(["season", "fpl_code", "fixture"])
    if player_fixture.duplicated(["season", "fpl_code", "fixture"]).any():
        raise ValueError("Player fixture history is not unique")
    left_rest = out[
        ["season", "fpl_code", "deadline_time", "kickoff_time"]
    ].copy()
    left_rest["_row_id"] = np.arange(len(out), dtype=int)
    right_rest = player_fixture[
        ["season", "fpl_code", "match_available_at", "kickoff_time"]
    ].rename(columns={"kickoff_time": "prior_kickoff_time"})
    left_rest = left_rest.sort_values("deadline_time", kind="mergesort")
    right_rest = right_rest.sort_values("match_available_at", kind="mergesort")
    rest_join = pd.merge_asof(
        left_rest,
        right_rest,
        left_on="deadline_time",
        right_on="match_available_at",
        by=["season", "fpl_code"],
        direction="backward",
        allow_exact_matches=False,
    ).sort_values("_row_id", kind="mergesort")
    rest_days = (
        (rest_join["kickoff_time"] - rest_join["prior_kickoff_time"])
        .dt.total_seconds()
        .div(86_400)
        .clip(1, 14)
        .fillna(14)
    )
    rest_values = rest_days.to_numpy(dtype=float)
    out["ar_rest_days"] = rest_values

    # Congestion: count the known team schedule in the 14 days up to target kickoff.
    team_schedule = {}
    for key, group in fixture_rows.groupby(["season", "team_name"], sort=False):
        team_schedule[key] = np.sort(group["kickoff_time"].astype("int64").to_numpy())
    congestion = np.ones(len(out), dtype=float)
    for (season, team), indices in out.groupby(["season", "team_name"], sort=False).groups.items():
        schedule = team_schedule.get((season, team))
        if schedule is None:
            raise ValueError(f"No fixture schedule for team {team!r} in season {season}")
        row_positions = np.asarray(list(indices), dtype=int)
        target_ns = out.loc[row_positions, "kickoff_time"].astype("int64").to_numpy()
        right = np.searchsorted(schedule, target_ns, side="right")
        left = np.searchsorted(
            schedule, target_ns - 14 * 86_400_000_000_000, side="left"
        )
        congestion[row_positions] = right - left
    out["ar_team_matches_14d"] = congestion

    # Attribute each team's DC/tackles to the opponent that conceded them.
    dc = pd.to_numeric(hist["defensive_contribution"], errors="coerce").fillna(0.0)
    tackles = pd.to_numeric(hist["tackles"], errors="coerce").fillna(0.0)
    stat_frame = hist.assign(_dc=dc, _tackles=tackles)
    allowed = (
        stat_frame.groupby(
            ["season", "fixture", "opponent_team_name", "kickoff_time", "match_available_at"],
            as_index=False,
            sort=False,
        )
        .agg(dc_sum=("_dc", "sum"), tackle_sum=("_tackles", "sum"))
        .rename(columns={"opponent_team_name": "conceding_team"})
    )
    allowed_groups = {}
    for key, group in allowed.groupby(["season", "conceding_team"], sort=False):
        group = group.sort_values(
            ["match_available_at", "kickoff_time", "fixture"], kind="mergesort"
        )
        allowed_groups[key] = (
            group["match_available_at"].astype("int64").to_numpy(),
            group["dc_sum"].to_numpy(dtype=float),
            group["tackle_sum"].to_numpy(dtype=float),
        )

    values = {
        column: np.full(len(out), np.nan, dtype=float)
        for column in CONTEXT_COLUMNS[2:]
    }
    for (season, opponent), indices in out.groupby(
        ["season", "opponent_team_name"], sort=False
    ).groups.items():
        group_data = allowed_groups.get((season, opponent))
        if group_data is None:
            continue
        available_ns, dc_sums, tackle_sums = group_data
        row_positions = np.asarray(list(indices), dtype=int)
        deadlines_ns = out.loc[row_positions, "deadline_time"].astype("int64").to_numpy()
        for row_position, deadline_ns in zip(row_positions, deadlines_ns):
            end = np.searchsorted(available_ns, deadline_ns, side="left")
            for window in (3, 5, 10):
                start = max(0, end - window)
                if end > start:
                    values[f"ar_opp_dc_allowed_{window}"][row_position] = float(
                        dc_sums[start:end].mean()
                    )
            start = max(0, end - 5)
            if end > start:
                values["ar_opp_tackles_allowed_5"][row_position] = float(
                    tackle_sums[start:end].mean()
                )
    for column, array in values.items():
        out[column] = array

    multi_fixture_groups = (
        out.groupby(["season", "gameweek", "fpl_code"], sort=False)["fixture"]
        .nunique().gt(1).sum()
    )
    report = {
        "status": "FIXTURE_CONTEXT_REBUILT",
        "target_rows": int(len(out)),
        "fixture_context_columns": CONTEXT_COLUMNS,
        "same_player_gameweek_multi_fixture_groups": int(multi_fixture_groups),
        "reconstructed_non_null_counts": {
            column: int(out[column].notna().sum()) for column in CONTEXT_COLUMNS
        },
        "source_rule": {
            "rest": "latest player fixture whose conservative/observed match availability is strictly before target deadline; kickoff-to-target-kickoff days clipped to [1,14], default 14",
            "team_congestion": "known team fixture schedule in [target kickoff - 14 days, target kickoff], inclusive",
            "opponent_allowance": "rolling mean of the previous 3/5/10 opponent-conceded fixture DC totals and previous 5 tackle totals, with every source fixture available strictly before target deadline",
        },
        "admission_status": "NOT_ADMITTED",
    }
    return out, report
