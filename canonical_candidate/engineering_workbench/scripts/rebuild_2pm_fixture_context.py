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



def rebuild_deadline_team_context(
    target_frame: pd.DataFrame,
    team_matches: pd.DataFrame,
    features_module,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Rebuild own/opponent rolling team features and ranks as of each deadline.

    Uses Dastan's pinned team/opponent pairing and league-rank definitions, but
    recomputes target snapshots from only team matches whose conservative
    24-hour post-kickoff availability bound is strictly before the deadline.
    """
    required = {
        "season", "deadline_time", "team_name", "opponent_team_name",
    }
    missing = sorted(required - set(target_frame.columns))
    if missing:
        raise ValueError(f"Target frame missing team-context columns: {missing}")

    out = target_frame.copy().reset_index(drop=True)
    out["season"] = out["season"].astype(str)
    out["deadline_time"] = pd.to_datetime(out["deadline_time"], utc=True, errors="coerce")
    if out["deadline_time"].isna().any():
        raise ValueError("Target team context contains invalid deadlines")

    teams = features_module._prepare_team_matches(team_matches)
    teams = features_module.build_opponent_lookup(teams)
    teams["date"] = pd.to_datetime(teams["date"], utc=True, errors="coerce")
    if teams["date"].isna().any():
        raise ValueError("Understat team matches contain invalid dates")
    teams["match_available_at"] = teams["date"] + pd.Timedelta(hours=24)

    # Rank values attached to each historical match are the standings immediately
    # before that match, matching the pinned Dastan feature definition.
    ranks_at_match = features_module.compute_league_ranks(teams)
    date_strings = teams["date"].dt.strftime("%Y-%m-%d %H:%M")
    teams["league_rank"] = [
        ranks_at_match.get((str(team), str(season), str(date)), 10)
        for team, season, date in zip(
            teams["understat_team"], teams["season"], date_strings
        )
    ]
    teams["opp_league_rank"] = [
        (
            ranks_at_match.get((str(opponent), str(season), str(date)), 10)
            if pd.notna(opponent)
            else 10
        )
        for opponent, season, date in zip(
            teams["opponent"], teams["season"], date_strings
        )
    ]

    team_order = {
        season: list(group["understat_team"].dropna().astype(str).unique())
        for season, group in teams.groupby("season", sort=False)
    }
    team_rows = {
        (str(season), str(team)): group.sort_values(
            ["date", "understat_team"], kind="mergesort"
        ).reset_index(drop=True)
        for (season, team), group in teams.groupby(
            ["season", "understat_team"], sort=False
        )
    }

    mapper = features_module.fpl_to_understat
    out["_team_us"] = out["team_name"].map(mapper)
    out["_opponent_us"] = out["opponent_team_name"].map(mapper)
    if out[["_team_us", "_opponent_us"]].isna().any().any():
        raise ValueError("Could not map target team/opponent to Understat names")

    unique_deadlines = out[["season", "deadline_time"]].drop_duplicates()
    deadline_ranks = {}
    for season, deadline in unique_deadlines.itertuples(index=False, name=None):
        season_rows = teams[
            teams["season"].astype(str).eq(str(season))
            & teams["match_available_at"].lt(deadline)
        ]
        order = team_order.get(str(season), [])
        table = pd.DataFrame(index=order)
        if len(season_rows):
            totals = season_rows.groupby("understat_team").agg(
                points=("pts", "sum"),
                goals_for=("scored", "sum"),
                goals_against=("missed", "sum"),
            )
            table = table.join(totals, how="left")
        for column in ("points", "goals_for", "goals_against"):
            if column not in table:
                table[column] = 0.0
            table[column] = table[column].fillna(0.0)
        table["goal_difference"] = table["goals_for"] - table["goals_against"]
        table = table.sort_values(
            ["points", "goal_difference", "goals_for"],
            ascending=[False, False, False],
            kind="mergesort",
        )
        deadline_ranks[(str(season), deadline)] = {
            team: rank for rank, team in enumerate(table.index.astype(str), 1)
        }

    windows = list(features_module.WINDOWS)
    source_map = dict(features_module.TEAM_FEATURES)
    team_feature_names = [
        f"team_{feature}_{window}"
        for feature in source_map.values()
        for window in windows
    ]
    history_cache = {}
    required_teams = set()
    for row in out[["season", "deadline_time", "_team_us", "_opponent_us"]].itertuples(
        index=False, name=None
    ):
        season, deadline, own, opponent = row
        required_teams.add((str(season), deadline, str(own)))
        required_teams.add((str(season), deadline, str(opponent)))

    for season, deadline, team in required_teams:
        group = team_rows.get((season, team))
        if group is None:
            history_cache[(season, deadline, team)] = {
                name: np.nan for name in team_feature_names
            }
            continue
        eligible = group[group["match_available_at"].lt(deadline)].tail(max(windows))
        result = {}
        for source, feature in source_map.items():
            values = pd.to_numeric(eligible[source], errors="coerce")
            for window in windows:
                sample = values.tail(window)
                result[f"team_{feature}_{window}"] = (
                    float(sample.mean()) if len(sample) else np.nan
                )
        history_cache[(season, deadline, team)] = result

    own_records = []
    opponent_records = []
    own_ranks = []
    opponent_ranks = []
    for row in out[[
        "season", "deadline_time", "_team_us", "_opponent_us"
    ]].itertuples(index=False, name=None):
        season, deadline, own, opponent = row
        own_records.append(history_cache[(str(season), deadline, str(own))])
        opponent_records.append(history_cache[(str(season), deadline, str(opponent))])
        ranks = deadline_ranks[(str(season), deadline)]
        own_ranks.append(ranks.get(str(own), 10))
        opponent_ranks.append(ranks.get(str(opponent), 10))

    own_frame = pd.DataFrame(own_records, index=out.index)
    opponent_frame = pd.DataFrame(opponent_records, index=out.index)
    opponent_frame.columns = [
        column.replace("team_", "opp_", 1) for column in opponent_frame.columns
    ]
    rank_frame = pd.DataFrame(
        {
            "status_league_rank": own_ranks,
            "opp_status_league_rank": opponent_ranks,
        },
        index=out.index,
    )
    replaced_columns = [
        *own_frame.columns,
        *opponent_frame.columns,
        "status_league_rank",
        "opp_status_league_rank",
        "_team_us",
        "_opponent_us",
    ]
    out = pd.concat(
        [
            out.drop(columns=replaced_columns, errors="ignore"),
            own_frame,
            opponent_frame,
            rank_frame,
        ],
        axis=1,
    )

    report = {
        "status": "DEADLINE_TEAM_CONTEXT_REBUILT",
        "target_rows": int(len(out)),
        "team_feature_count": len(team_feature_names),
        "opponent_feature_count": len(team_feature_names),
        "direct_rank_columns": ["status_league_rank", "opp_status_league_rank"],
        "unique_season_deadlines": int(len(unique_deadlines)),
        "team_deadline_snapshots_built": int(len(history_cache)),
        "availability_rule": "Understat match date plus 24 hours, strictly before official FPL deadline",
        "rolling_rule": "mean of the last 1/3/5/10/38 eligible completed team matches",
        "rank_rule": "standings from all team matches with conservative availability strictly before the deadline; points, goal difference, goals scored; stable source team order for unresolved ties",
        "admission_status": "NOT_ADMITTED",
    }
    return out, report

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
