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
OBSERVED_PREFIX = "__observed__"
CONTEXT_COLUMNS = [
    "ar_rest_days",
    "ar_team_matches_14d",
    "ar_opp_dc_allowed_3",
    "ar_opp_dc_allowed_5",
    "ar_opp_dc_allowed_10",
    "ar_opp_tackles_allowed_5",
]





def _utc_ns(series: pd.Series) -> pd.Series:
    """Normalize timestamps to nanosecond UTC so int64 comparisons share units."""
    return pd.to_datetime(series, utc=True, errors="coerce").astype("datetime64[ns, UTC]")



def rebuild_player_history_features(
    target_frame: pd.DataFrame,
    player_matches: pd.DataFrame,
    features_module,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Recompute player rolling, availability and defensive-history inputs at deadline."""
    required_history = {
        "season", "fixture", "fpl_code", "element", "understat_id", "position",
        "is_home", "kickoff_time", "match_available_at", "minutes", "total_points",
    }
    missing = sorted(required_history - set(player_matches.columns))
    if missing:
        raise ValueError(f"Player history missing identity/source columns: {missing}")

    out = target_frame.copy().reset_index(drop=True)
    hist = player_matches.copy()
    for frame in (out, hist):
        frame["season"] = frame["season"].astype(str)
        frame["fixture"] = frame["fixture"].astype(str)
        frame["kickoff_time"] = _utc_ns(frame["kickoff_time"])
    out["deadline_time"] = _utc_ns(out["deadline_time"])
    hist["match_available_at"] = _utc_ns(hist["match_available_at"])
    if out["deadline_time"].isna().any() or hist["kickoff_time"].isna().any():
        raise ValueError("Player history/target contains invalid timestamps")
    # A source timestamp at or before kickoff cannot represent post-match data.
    # Fail closed rather than allowing a malformed vintage to enter any later
    # historical state. Future target fixtures may legitimately have NaT.
    observed_availability = hist["match_available_at"].notna()
    played_rows = pd.to_numeric(hist["minutes"], errors="coerce").gt(0)
    if hist.loc[played_rows, "match_available_at"].isna().any():
        raise ValueError("Played player-history rows require match availability timestamps")
    if (
        hist.loc[observed_availability, "match_available_at"]
        .le(hist.loc[observed_availability, "kickoff_time"])
        .any()
    ):
        raise ValueError("Player match availability must be strictly after kickoff")
    duplicate_keys = hist.duplicated(["season", "fixture", "fpl_code"], keep=False)
    if duplicate_keys.any():
        raise ValueError(
            "Player history must be unique at season-fixture-player grain; "
            "duplicate source rows cannot be silently collapsed"
        )
    # Future target fixtures legitimately have no completion availability yet.

    # Match Dastan's player_uid construction exactly: Understat ID where mapped,
    # otherwise season-scoped FPL element ID.
    hist["_player_uid"] = hist["understat_id"].where(
        hist["understat_id"].notna(),
        hist["element"].astype(str) + "_" + hist["season"].astype(str),
    ).astype(str)
    identity = hist[
        ["season", "fixture", "fpl_code", "element", "understat_id", "position", "is_home", "_player_uid"]
    ].drop_duplicates(["season", "fixture", "fpl_code"])
    if identity.duplicated(["season", "fixture", "fpl_code"]).any():
        raise ValueError("Player identity rows are not unique at player-fixture grain")
    target_meta = out[["season", "fixture", "fpl_code"]].merge(
        identity,
        on=["season", "fixture", "fpl_code"],
        how="left",
        validate="one_to_one",
    )
    if target_meta["_player_uid"].isna().any():
        raise ValueError("Target rows lack canonical player identity")

    windows = list(features_module.WINDOWS)
    player_map = dict(features_module.PLAYER_FEATURES)
    player_columns = [
        f"player_{feature}_{window}"
        for feature in player_map.values()
        for window in windows
    ]
    relevant_columns = [
        f"player_relevant_fpl_points_{window}" for window in windows
    ]
    defensive_sources = {
        "defensive_contribution": "defensive_contribution",
        "cbit": "clearances_blocks_interceptions",
        "recoveries": "recoveries",
        "tackles": "tackles",
    }
    defensive_columns = [
        f"ar_{feature}_{window}"
        for feature in defensive_sources
        for window in (3, 5, 10, 38)
    ]
    rate_columns = [
        f"ar_{kind}_{window}"
        for kind in ("dc_hit_rate", "dc_near_rate", "starts")
        for window in (3, 5, 10)
    ]
    availability_columns = [
        f"{prefix}_{window}"
        for prefix in ("p_any", "p60", "e_minutes")
        for window in (3, 5, 10)
    ]
    history_columns = (
        player_columns + relevant_columns + defensive_columns + rate_columns
        + ["ar_dc_ppg_5"] + availability_columns
    )
    values = {column: np.full(len(out), np.nan, dtype=float) for column in history_columns}
    observed_values = {column: np.zeros(len(out), dtype=np.uint8) for column in history_columns}

    # Keep raw per-player arrays in kickoff order. At each target query we
    # explicitly select only rows whose availability is strictly pre-deadline;
    # this avoids assuming that a completion timestamp is a sorted prefix.
    history_groups = {}
    for uid, group in hist.groupby("_player_uid", sort=False):
        group = group.sort_values(["kickoff_time", "fixture"], kind="mergesort").reset_index(drop=True)
        available_ns = group["match_available_at"].astype("int64").to_numpy(copy=True)
        available_ns[group["match_available_at"].isna().to_numpy()] = np.iinfo(np.int64).max
        player_arrays = {}
        player_observed_arrays = {}
        for source in player_map:
            series = (
                pd.to_numeric(group[source], errors="coerce")
                if source in group else pd.Series(np.nan, index=group.index)
            )
            player_observed_arrays[source] = np.isfinite(series.to_numpy(dtype=float))
            # Understat missing match rows are ignored by the rolling mean. FPL
            # fields retain zero-fill value semantics, but raw presence is carried
            # separately so a filled zero is never mistaken for an observation.
            if source.startswith("us_"):
                player_arrays[source] = series.to_numpy(dtype=float)
            else:
                player_arrays[source] = series.fillna(0.0).to_numpy(dtype=float)

        total_points_raw = pd.to_numeric(group["total_points"], errors="coerce")
        total_points_observed = np.isfinite(total_points_raw.to_numpy(dtype=float))
        total_points = total_points_raw.fillna(0.0).to_numpy(dtype=float)
        home_values = group["is_home"].astype(bool).to_numpy()
        venue = {
            home: (
                available_ns[home_values == home],
                total_points[home_values == home],
                total_points_observed[home_values == home],
            )
            for home in (False, True)
        }

        defensive_arrays = {}
        for feature, source in defensive_sources.items():
            column = source
            if feature == "cbit" and column not in group and "cbit" in group:
                column = "cbit"
            series = (
                pd.to_numeric(group[column], errors="coerce")
                if column in group else pd.Series(np.nan, index=group.index)
            )
            defensive_arrays[feature] = series.to_numpy(dtype=float)

        dc = defensive_arrays["defensive_contribution"]
        positions = group["position"].astype(str).to_numpy()
        thresholds = np.array(
            [features_module.DC_THRESHOLD.get(position, 99) for position in positions],
            dtype=float,
        )
        hit = (dc >= thresholds).astype(float)
        near = ((dc >= thresholds - 3) & (dc < thresholds)).astype(float)
        hit[~np.isfinite(dc)] = np.nan
        near[~np.isfinite(dc)] = np.nan
        starts = (
            pd.to_numeric(group["starts"], errors="coerce").to_numpy(dtype=float)
            if "starts" in group else np.full(len(group), np.nan)
        )
        history_groups[str(uid)] = {
            "available_ns": available_ns,
            "player_arrays": player_arrays,
            "player_observed_arrays": player_observed_arrays,
            "venue_arrays": venue,
            "defensive_arrays": defensive_arrays,
            "rate_arrays": {
                "dc_hit_rate": hit,
                "dc_near_rate": near,
                "starts": starts,
            },
        }

    # Availability histories are season-scoped and use the last 3/5/10 player rows.
    availability_groups = {}
    for (season, code), group in hist.groupby(["season", "fpl_code"], sort=False):
        group = group.sort_values(["kickoff_time", "fixture"], kind="mergesort")
        minutes = pd.to_numeric(group["minutes"], errors="coerce")
        availability_groups[(str(season), int(code))] = {
            "available_ns": np.where(
                group["match_available_at"].notna().to_numpy(),
                group["match_available_at"].astype("int64").to_numpy(),
                np.iinfo(np.int64).max,
            ),
            "played": minutes.gt(0).astype(float).to_numpy(),
            "played60": minutes.ge(60).astype(float).to_numpy(),
            "minutes": minutes.fillna(0.0).to_numpy(dtype=float),
            "minutes_observed": np.isfinite(minutes.to_numpy(dtype=float)),
        }

    base_rates = features_module.POSITION_BASE_RATES

    def tail_mean(array: np.ndarray, indices: np.ndarray, window: int, *, ignore_nan: bool = False) -> float:
        selected = array[indices[-window:]]
        if not len(selected):
            return float("nan")
        if ignore_nan:
            selected = selected[np.isfinite(selected)]
            return float(selected.mean()) if len(selected) else float("nan")
        return float(selected.mean())

    for row_position, row in enumerate(
        target_meta[["_player_uid", "season", "fpl_code", "position", "is_home"]].itertuples(index=False, name=None)
    ):
        uid, season, code, position, is_home = row
        deadline_ns = int(out.loc[row_position, "deadline_time"].value)
        history = history_groups[str(uid)]
        eligible = np.flatnonzero(history["available_ns"] < deadline_ns)

        for source, feature in player_map.items():
            array = history["player_arrays"][source]
            source_observed = history["player_observed_arrays"][source]
            for window in windows:
                sample_indices = eligible[-window:]
                values[f"player_{feature}_{window}"][row_position] = tail_mean(
                    array, eligible, window, ignore_nan=source.startswith("us_")
                )
                if len(sample_indices):
                    observed_values[f"player_{feature}_{window}"][row_position] = int(
                        source_observed[sample_indices].any()
                        if source.startswith("us_")
                        else source_observed[sample_indices].all()
                    )

        venue_available, venue_values, venue_observed = history["venue_arrays"][bool(is_home)]
        venue_eligible = np.flatnonzero(venue_available < deadline_ns)
        for window in windows:
            sample_indices = venue_eligible[-window:]
            values[f"player_relevant_fpl_points_{window}"][row_position] = tail_mean(
                venue_values, venue_eligible, window
            )
            if len(sample_indices):
                observed_values[f"player_relevant_fpl_points_{window}"][row_position] = int(
                    venue_observed[sample_indices].all()
                )

        for feature, array in history["defensive_arrays"].items():
            for window in (3, 5, 10, 38):
                sample_indices = eligible[-window:]
                values[f"ar_{feature}_{window}"][row_position] = tail_mean(
                    array, eligible, window, ignore_nan=True
                )
                if len(sample_indices):
                    observed_values[f"ar_{feature}_{window}"][row_position] = int(
                        np.isfinite(array[sample_indices]).any()
                    )
        for feature, array in history["rate_arrays"].items():
            for window in (3, 5, 10):
                sample_indices = eligible[-window:]
                values[f"ar_{feature}_{window}"][row_position] = tail_mean(
                    array, eligible, window, ignore_nan=True
                )
                if len(sample_indices):
                    observed_values[f"ar_{feature}_{window}"][row_position] = int(
                        np.isfinite(array[sample_indices]).any()
                    )
        values["ar_dc_ppg_5"][row_position] = (
            2.0 * values["ar_dc_hit_rate_5"][row_position]
        )
        observed_values["ar_dc_ppg_5"][row_position] = observed_values[
            "ar_dc_hit_rate_5"
        ][row_position]

        availability = availability_groups.get((str(season), int(code)))
        defaults = base_rates.get(str(position), base_rates.get("MID"))
        if availability is None:
            availability_eligible = np.array([], dtype=int)
            availability_arrays = {}
        else:
            availability_eligible = np.flatnonzero(
                availability["available_ns"] < deadline_ns
            )
            availability_arrays = availability
        for window in (3, 5, 10):
            for source in ("p_any", "p60", "e_minutes"):
                if not len(availability_eligible):
                    values[f"{source}_{window}"][row_position] = defaults[source]
                    observed_values[f"{source}_{window}"][row_position] = 1
                else:
                    array = availability_arrays[
                        {"p_any": "played", "p60": "played60", "e_minutes": "minutes"}[source]
                    ]
                    sample_indices = availability_eligible[-window:]
                    values[f"{source}_{window}"][row_position] = tail_mean(
                        array, availability_eligible, window
                    )
                    observed_values[f"{source}_{window}"][row_position] = int(
                        availability_arrays["minutes_observed"][sample_indices].all()
                    )

    feature_frame = pd.DataFrame(values, index=out.index)
    observed_frame = pd.DataFrame(
        {f"{OBSERVED_PREFIX}{name}": mask for name, mask in observed_values.items()},
        index=out.index,
    )
    out = pd.concat(
        [
            out.drop(columns=feature_frame.columns, errors="ignore"),
            feature_frame,
            observed_frame,
        ],
        axis=1,
    )
    report = {
        "status": "PLAYER_HISTORY_REBUILT",
        "target_rows": int(len(out)),
        "player_rolling_feature_count": len(player_columns) + len(relevant_columns),
        "availability_feature_count": 9,
        "defensive_player_history_feature_count": len(defensive_columns) + len(rate_columns) + 1,
        "history_identity": "Dastan player_uid: Understat ID where mapped, else element_id + season",
        "rolling_window_semantics": "previous player fixture rows before deadline; player rolling features include non-appearance rows, while sequence tokens separately require minutes > 0",
        "availability_semantics": "previous season-scoped FPL player fixture rows before deadline; position-specific base rates when no history",
        "defensive_history_semantics": "previous player_uid fixture rows before deadline; NaN source values are ignored by rolling means",
        "admission_status": "NOT_ADMITTED",
    }
    return out, report

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
    out["deadline_time"] = _utc_ns(out["deadline_time"])
    if out["deadline_time"].isna().any():
        raise ValueError("Target team context contains invalid deadlines")

    teams = features_module._prepare_team_matches(team_matches)
    teams = features_module.build_opponent_lookup(teams)
    teams["date"] = _utc_ns(teams["date"])
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
        "season", "fixture", "fpl_code", "element", "understat_id",
        "team_name", "opponent_team_name", "kickoff_time", "match_available_at",
        "defensive_contribution", "tackles",
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
        frame["kickoff_time"] = _utc_ns(frame["kickoff_time"])
    out["deadline_time"] = _utc_ns(out["deadline_time"])
    hist["match_available_at"] = _utc_ns(hist["match_available_at"])
    if out[["kickoff_time", "deadline_time"]].isna().any().any():
        raise ValueError("Target context contains invalid kickoff/deadline timestamps")
    if hist["kickoff_time"].isna().any():
        raise ValueError("Historical context contains invalid kickoff timestamps")
    # NaT availability is expected for future target fixtures in the active season.

    fixture_rows = hist[
        ["season", "fixture", "team_name", "opponent_team_name",
         "kickoff_time", "match_available_at"]
    ].drop_duplicates(["season", "fixture", "team_name"])
    if fixture_rows.duplicated(["season", "fixture", "team_name"]).any():
        raise ValueError("Fixture/team context rows are not unique")

    # Rest: latest player_uid fixture available strictly before target deadline.
    # This mirrors Dastan's Understat-ID identity and season-scoped fallback.
    hist["_player_uid"] = hist["understat_id"].where(
        hist["understat_id"].notna(),
        hist["element"].astype(str) + "_" + hist["season"].astype(str),
    ).astype(str)
    identity = hist[
        ["season", "fixture", "fpl_code", "_player_uid"]
    ].drop_duplicates(["season", "fixture", "fpl_code"])
    target_identity = out[["season", "fixture", "fpl_code"]].merge(
        identity,
        on=["season", "fixture", "fpl_code"],
        how="left",
        validate="one_to_one",
    )
    if target_identity["_player_uid"].isna().any():
        raise ValueError("Target rows lack Dastan player_uid identity for rest calculation")
    player_fixture = hist[
        ["_player_uid", "fixture", "kickoff_time", "match_available_at"]
    ].drop_duplicates(["_player_uid", "fixture"])
    player_fixture = player_fixture[player_fixture["match_available_at"].notna()]
    if player_fixture.duplicated(["_player_uid", "fixture"]).any():
        raise ValueError("Player fixture history is not unique")
    left_rest = out[
        ["deadline_time", "kickoff_time"]
    ].copy()
    left_rest["_row_id"] = np.arange(len(out), dtype=int)
    left_rest["_player_uid"] = target_identity["_player_uid"].to_numpy()
    right_rest = player_fixture[
        ["_player_uid", "match_available_at", "kickoff_time"]
    ].rename(columns={"kickoff_time": "prior_kickoff_time"})
    left_rest = left_rest.sort_values("deadline_time", kind="mergesort")
    right_rest = right_rest.sort_values("match_available_at", kind="mergesort")
    rest_join = pd.merge_asof(
        left_rest,
        right_rest,
        left_on="deadline_time",
        right_on="match_available_at",
        by="_player_uid",
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
    # Missing defensive-stat rows are not zero-event performances. Preserve
    # fixture totals as missing unless every player row for that team-fixture
    # has a source value; otherwise a partial sum would understate the opponent
    # allowance and silently fabricate historical coverage.
    dc = pd.to_numeric(hist["defensive_contribution"], errors="coerce")
    tackles = pd.to_numeric(hist["tackles"], errors="coerce")
    stat_frame = hist.loc[hist["match_available_at"].notna()].assign(
        _dc=dc.loc[hist["match_available_at"].notna()],
        _tackles=tackles.loc[hist["match_available_at"].notna()],
    )
    allowed = (
        stat_frame.groupby(
            ["season", "fixture", "opponent_team_name", "kickoff_time", "match_available_at"],
            as_index=False,
            sort=False,
        )
        .agg(
            dc_sum=("_dc", "sum"),
            tackle_sum=("_tackles", "sum"),
            dc_rows=("_dc", "count"),
            tackle_rows=("_tackles", "count"),
            player_rows=("_dc", "size"),
        )
        .rename(columns={"opponent_team_name": "conceding_team"})
    )
    allowed.loc[allowed["dc_rows"].ne(allowed["player_rows"]), "dc_sum"] = np.nan
    allowed.loc[allowed["tackle_rows"].ne(allowed["player_rows"]), "tackle_sum"] = np.nan
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
                    sample = dc_sums[start:end]
                    if np.isfinite(sample).all():
                        values[f"ar_opp_dc_allowed_{window}"][row_position] = float(
                            sample.mean()
                        )
            start = max(0, end - 5)
            if end > start:
                sample = tackle_sums[start:end]
                if np.isfinite(sample).all():
                    values["ar_opp_tackles_allowed_5"][row_position] = float(
                        sample.mean()
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
