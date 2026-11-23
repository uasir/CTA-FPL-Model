"""Reconstruct 286-feature historical states after each completed player fixture.

The historical token is anchored strictly after the conservative availability time
of the player and team match data. Player/team rolling features and ranks are
recomputed at that state time so the just-completed match is included. Match-
specific pre-kickoff context and the archived pre-kickoff market/projection/news
snapshot are retained as context known before that match. The target query remains
a separate pre-deadline vector and is not built by this module.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from rebuild_2pm_fixture_context import (
    rebuild_deadline_team_context,
    rebuild_fixture_context,
    rebuild_player_history_features,
)

POSTMATCH_OPPONENT_CONTEXT = (
    "ar_opp_dc_allowed_3",
    "ar_opp_dc_allowed_5",
    "ar_opp_dc_allowed_10",
    "ar_opp_tackles_allowed_5",
)
PREMATCH_FIXTURE_CONTEXT = ("ar_rest_days", "ar_team_matches_14d")
REQUIRED_STATE_COLUMNS = {
    "season", "gameweek", "fixture", "fpl_code", "kickoff_time",
    "match_available_at", "minutes", "deadline_time", "team_name",
    "opponent_team_name", "source_vintage_status",
}


def build_postmatch_state_vectors(
    candidate_frame: pd.DataFrame,
    player_matches: pd.DataFrame,
    team_matches: pd.DataFrame,
    features_module: Any,
    feature_order: list[str],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build one post-match state vector per actually played player-fixture.

    A single conservative state timestamp is used for both player and team
    sources: max(player match availability, kickoff + 24h) + 1ns. This guarantees
    that the current fixture is eligible under the existing strict '< as-of'
    reconstruction rules, without pretending that its data was available at
    kickoff or immediately at full time.
    """
    if len(feature_order) != 286 or len(set(feature_order)) != 286:
        raise ValueError("The post-match state contract requires 286 unique ordered features")
    missing = sorted((REQUIRED_STATE_COLUMNS | set(feature_order)) - set(candidate_frame.columns))
    if missing:
        raise ValueError(f"Candidate frame is missing required columns: {missing[:25]}")

    out = candidate_frame.copy().reset_index(drop=True)
    out["season"] = out["season"].astype(str)
    out["fixture"] = out["fixture"].astype(str)
    out["kickoff_time"] = pd.to_datetime(out["kickoff_time"], utc=True, errors="coerce")
    out["match_available_at"] = pd.to_datetime(
        out["match_available_at"], utc=True, errors="coerce"
    )
    out["minutes"] = pd.to_numeric(out["minutes"], errors="coerce")
    if out[["kickoff_time", "match_available_at"]].isna().any().any():
        raise ValueError("Every post-match token requires valid kickoff and availability timestamps")
    if out["minutes"].isna().any() or out["minutes"].lt(0).any():
        raise ValueError("minutes must be finite and non-negative")
    if out.duplicated(["season", "fixture", "fpl_code"]).any():
        raise ValueError("Post-match state input must be unique at season-fixture-player grain")
    if not out["minutes"].gt(0).all():
        raise ValueError("Post-match state vectors may only be built for actually played fixtures")
    if out["match_available_at"].le(out["kickoff_time"]).any():
        raise ValueError("Match data availability must be strictly after kickoff")

    # Existing team reconstruction uses a conservative kickoff + 24h bound.
    team_source_available_at = out["kickoff_time"] + pd.Timedelta(hours=24)
    state_as_of = pd.concat(
        [out["match_available_at"], team_source_available_at], axis=1
    ).max(axis=1) + pd.Timedelta(nanoseconds=1)
    out["postmatch_state_as_of_time"] = state_as_of
    out["postmatch_state_semantics"] = "AFTER_MATCH_DATA_AVAILABLE_CONSERVATIVE"
    out["postmatch_source_vintage_status"] = out["source_vintage_status"].astype(str)

    # Rebuilders use deadline_time as their strict point-in-time cutoff. Replace
    # it only in this isolated historical-state frame; retain the original target
    # deadline in a separate audit field.
    out["original_fixture_deadline_time"] = pd.to_datetime(
        out["deadline_time"], utc=True, errors="coerce"
    )
    if out["original_fixture_deadline_time"].isna().any():
        raise ValueError("Historical fixture rows require their original official deadline")
    out["deadline_time"] = state_as_of

    if "season" not in player_matches or "season" not in team_matches:
        raise ValueError("Player and team source histories must carry season keys")
    player_source = player_matches.copy()
    team_source = team_matches.copy()
    player_source["season"] = player_source["season"].astype(str)
    team_source["season"] = team_source["season"].astype(str)
    out["_source_row_order"] = np.arange(len(out), dtype=int)

    # Rebuild each season independently. This prevents an Understat ID shared
    # across seasons from silently importing prior-season player rolling history.
    state_parts = []
    reconstruction_reports = {}
    for season, season_targets in out.groupby("season", sort=False):
        season_player_history = player_source[
            player_source["season"].eq(str(season))
        ].copy()
        season_team_history = team_source[
            team_source["season"].eq(str(season))
        ].copy()
        if season_player_history.empty or season_team_history.empty:
            raise ValueError(f"Missing player or team history for season {season}")

        player_state, player_report = rebuild_player_history_features(
            season_targets, season_player_history, features_module
        )
        team_state, team_report = rebuild_deadline_team_context(
            player_state, season_team_history, features_module
        )
        fixture_state, fixture_report = rebuild_fixture_context(
            team_state, season_player_history
        )

        # Rest and schedule congestion describe the match that has just been
        # played; retain their pre-kickoff values rather than using the match as
        # its own prior fixture. Opponent allowance is refreshed post-match.
        for column in PREMATCH_FIXTURE_CONTEXT:
            if column not in season_targets:
                raise ValueError(
                    f"Historical candidate is missing pre-match context {column}"
                )
            fixture_state[column] = season_targets[column].to_numpy()
        for column in POSTMATCH_OPPONENT_CONTEXT:
            if column not in fixture_state:
                raise ValueError(f"Post-match reconstruction did not produce {column}")

        for column in feature_order:
            if column not in fixture_state:
                raise ValueError(f"Post-match state is missing feature {column}")

        fixture_state["deadline_time"] = season_targets[
            "original_fixture_deadline_time"
        ].to_numpy()
        fixture_state["match_available_at"] = season_targets["match_available_at"].to_numpy()
        fixture_state["postmatch_state_as_of_time"] = season_targets[
            "postmatch_state_as_of_time"
        ].to_numpy()
        fixture_state["original_fixture_deadline_time"] = season_targets[
            "original_fixture_deadline_time"
        ].to_numpy()
        fixture_state["postmatch_state_semantics"] = (
            "AFTER_MATCH_DATA_AVAILABLE_CONSERVATIVE"
        )
        fixture_state["postmatch_source_vintage_status"] = (
            season_targets["source_vintage_status"].astype(str).to_numpy()
        )
        fixture_state["_source_row_order"] = season_targets[
            "_source_row_order"
        ].to_numpy()
        state_parts.append(fixture_state)
        reconstruction_reports[str(season)] = {
            "player_history": player_report,
            "team_and_opponent_context": team_report,
            "fixture_context": fixture_report,
            "source_history_scope": "same_season_only",
        }

    result = (
        pd.concat(state_parts, ignore_index=True)
        .sort_values("_source_row_order", kind="mergesort")
        .drop(columns="_source_row_order")
        .reset_index(drop=True)
    )

    report = {
        "status": "POSTMATCH_STATE_VECTORS_RECONSTRUCTED",
        "admission_status": "NOT_ADMITTED",
        "token_semantics": "286-feature state after the player and team match data are conservatively available",
        "state_as_of_rule": "max(player match_available_at, kickoff_time + 24h) + 1ns",
        "played_fixture_rows": int(len(result)),
        "feature_count": len(feature_order),
        "feature_order": "caller-supplied pinned 286-column schema order",
        "cross_season_history": "excluded; player and team feature histories are rebuilt season by season",
        "reconstruction_reports": reconstruction_reports,
        "preserved_pre_match_context": [
            *PREMATCH_FIXTURE_CONTEXT,
            "is_home_num",
            "value",
            "selected",
            "transfers_balance",
            "ar_ep_next",
            "sig_status_risk",
            "sig_chance_playing",
            "sig_has_news",
        ],
        "refreshed_post_match_context": [
            "player rolling and relevant-point windows",
            "availability history",
            "defensive/player-history rolling features",
            "own-team and opponent rolling features",
            "own-team and opponent league ranks",
            *POSTMATCH_OPPONENT_CONTEXT,
        ],
        "limitations": [
            "The conservative 24-hour team-data bound delays the state timestamp; it does not claim immediate full-time availability.",
            "Archived price, selection, transfer, ep_next and availability/news fields remain the pre-kickoff values for this historical fixture.",
            "Historical source-vintage and feature-level admission remain independent gates.",
            "This module builds historical states only; target queries remain strictly pre-deadline.",
            "Cross-season identity continuity and the five-played-match/21-day selection policy are enforced by the downstream sequence builder, not this module.",
        ],
    }
    return result, report
