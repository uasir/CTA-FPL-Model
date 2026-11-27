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
    observed_columns = [f"__observed__{feature}" for feature in feature_order]
    missing = sorted(
        (REQUIRED_STATE_COLUMNS | set(feature_order) | set(observed_columns))
        - set(candidate_frame.columns)
    )
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
    if out["kickoff_time"].isna().any():
        raise ValueError("Every candidate fixture requires a valid kickoff timestamp")
    if out["minutes"].isna().any() or out["minutes"].lt(0).any():
        raise ValueError("minutes must be finite and non-negative")
    if out.duplicated(["season", "fixture", "fpl_code"]).any():
        raise ValueError("Post-match state input must be unique at season-fixture-player grain")
    nonappearance_rows_excluded = int(out["minutes"].le(0).sum())
    out = out[out["minutes"].gt(0)].copy().reset_index(drop=True)
    if out.empty:
        raise ValueError("No played fixture rows are available for post-match state construction")
    if out["match_available_at"].isna().any():
        raise ValueError("Every played fixture requires a valid match data availability timestamp")
    if out["match_available_at"].le(out["kickoff_time"]).any():
        raise ValueError("Match data availability must be strictly after kickoff")
    conservative_team_bound = out["kickoff_time"] + pd.Timedelta(hours=24)
    availability_overrun = out["match_available_at"].gt(conservative_team_bound)
    if availability_overrun.any():
        diagnostic_columns = [
            column for column in (
                "season", "fixture", "fpl_code", "kickoff_time",
                "match_available_at", "completion_time_quality",
            ) if column in out.columns
        ]
        diagnostic = out.loc[availability_overrun, diagnostic_columns].copy()
        diagnostic["allowed_available_at"] = conservative_team_bound.loc[
            availability_overrun
        ]
        diagnostic["overrun_hours"] = (
            diagnostic["match_available_at"] - diagnostic["allowed_available_at"]
        ).dt.total_seconds() / 3600.0
        raise ValueError(
            "Player match availability exceeds the conservative kickoff + 24h "
            "team-data bound for "
            f"{int(availability_overrun.sum())} played rows; maximum overrun "
            f"{diagnostic['overrun_hours'].max():.6f} hours; examples: "
            f"{diagnostic.head(10).to_dict('records')}. "
            "Reconcile fixture kickoff and source-availability provenance; do not "
            "extend the bound or synthesize earlier availability."
        )

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

    # Keep the corrected stable player_uid history available across seasons,
    # matching the pinned Dastan 286 rolling-feature semantics. The downstream
    # sequence builder separately restricts the five token fixtures to the
    # target season. Team/rank builders remain internally season-scoped.
    player_state, player_report = rebuild_player_history_features(
        out, player_matches, features_module
    )
    team_state, team_report = rebuild_deadline_team_context(
        player_state, team_matches, features_module
    )
    fixture_state, fixture_report = rebuild_fixture_context(
        team_state, player_matches
    )

    # Reconstruct rest and schedule congestion at the actual fixture kickoff,
    # not at the FPL Gameweek deadline. This matters for rescheduled fixtures
    # whose kickoff can precede the deadline attached to their historical GW.
    prematch_fixture_frame = out.copy()
    prematch_fixture_frame["deadline_time"] = (
        prematch_fixture_frame["kickoff_time"] - pd.Timedelta(nanoseconds=1)
    )
    prematch_fixture_state, prematch_fixture_report = rebuild_fixture_context(
        prematch_fixture_frame, player_matches
    )
    for column in PREMATCH_FIXTURE_CONTEXT:
        if column not in prematch_fixture_state:
            raise ValueError(f"Pre-match reconstruction did not produce {column}")
        fixture_state[column] = prematch_fixture_state[column].to_numpy()

    # Archived EP, availability/news and market snapshots are valid match-state
    # context only when captured safely before this fixture's kickoff. A snapshot
    # taken after kickoff (possible when the fixture was moved) is not a pre-match
    # input and is replaced by the established -1 missing sentinel.
    snapshot_feature_groups = {
        "ep_next_snapshot_at": ("ar_ep_next",),
        "signals_snapshot_at": (
            "sig_status_risk", "sig_chance_playing", "sig_has_news",
        ),
        "market_snapshot_at": ("value", "selected", "transfers_balance"),
    }
    snapshot_validity = {}
    for snapshot_column, value_columns in snapshot_feature_groups.items():
        if snapshot_column in out:
            captured = pd.to_datetime(
                out[snapshot_column], utc=True, errors="coerce"
            )
            safe = captured.notna() & captured.lt(
                out["kickoff_time"] - pd.Timedelta(minutes=5)
            )
        else:
            safe = pd.Series(False, index=out.index)
        snapshot_validity[snapshot_column] = int(safe.sum())
        for column in value_columns:
            if column not in fixture_state:
                raise ValueError(f"Historical state is missing snapshot feature {column}")
            fixture_state.loc[~safe.to_numpy(), column] = -1.0

    for column in POSTMATCH_OPPONENT_CONTEXT:
        if column not in fixture_state:
            raise ValueError(f"Post-match reconstruction did not produce {column}")

    for column in feature_order:
        if column not in fixture_state:
            raise ValueError(f"Post-match state is missing feature {column}")
    for column in observed_columns:
        if column not in fixture_state:
            raise ValueError(f"Post-match state is missing source-observation sidecar {column}")
        sidecar = pd.to_numeric(fixture_state[column], errors="coerce")
        if sidecar.isna().any() or not sidecar.isin([0, 1]).all():
            raise ValueError(f"Invalid source-observation sidecar values in {column}")

    result = fixture_state.copy()
    result["deadline_time"] = out["original_fixture_deadline_time"]
    result["match_available_at"] = out["match_available_at"]
    result["postmatch_state_as_of_time"] = state_as_of
    result["original_fixture_deadline_time"] = out["original_fixture_deadline_time"]
    result["postmatch_state_semantics"] = "AFTER_MATCH_DATA_AVAILABLE_CONSERVATIVE"
    result["postmatch_source_vintage_status"] = out["source_vintage_status"].astype(str)

    report = {
        "status": "POSTMATCH_STATE_VECTORS_RECONSTRUCTED",
        "admission_status": "NOT_ADMITTED",
        "token_semantics": "286-feature state after the player and team match data are conservatively available",
        "state_as_of_rule": "max(player match_available_at, kickoff_time + 24h) + 1ns",
        "future_fixture_guard": "player match availability may not exceed kickoff + 24h; later-kickoff player/team fixtures therefore cannot enter an earlier post-match state under the conservative source bounds",
        "played_fixture_rows": int(len(result)),
        "nonappearance_rows_excluded": nonappearance_rows_excluded,
        "feature_count": len(feature_order),
        "feature_order": "caller-supplied pinned 286-column schema order",
        "cross_season_history": "corrected stable player_uid rolling history is available across seasons where mapped; the downstream five-token sequence itself is same-season only; team/rank and availability features retain their season-scoped source definitions",
        "reconstruction_reports": {
            "player_history": player_report,
            "team_and_opponent_context": team_report,
            "fixture_context": fixture_report,
        },
        "preserved_pre_match_context": ["is_home_num"],
        "reconstructed_at_fixture_kickoff": list(PREMATCH_FIXTURE_CONTEXT),
        "snapshot_context_valid_rows_before_kickoff": snapshot_validity,
        "pre_match_fixture_context_report": prematch_fixture_report,
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
