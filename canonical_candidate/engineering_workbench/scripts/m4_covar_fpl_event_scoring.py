#!/usr/bin/env python3
"""Synthetic 2026/27 FPL event-to-points scoring for M4 CoVar scenarios.

Bonus points are explicit scenario inputs because reproducing the official BPS
requires the full event/stat feed and match-level tie resolution. No live data
or forecasts are fetched here.
"""
from __future__ import annotations

import copy
from typing import Any, Mapping

from m4_covar_scenario_contract import (
    CovarScenarioContractError,
    validate_scenario_document,
)


class CovarEventScoringError(ValueError):
    """Raised when event inputs cannot be scored deterministically."""


SCORING_VERSION = "FPL_2026_27"


def _count(events: Mapping[str, Any], key: str) -> int:
    if key not in events:
        raise CovarEventScoringError(f"{key} must be explicitly supplied; missing is not zero")
    value = events[key]
    if isinstance(value, bool):
        raise CovarEventScoringError(f"{key} must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise CovarEventScoringError(f"{key} must be a non-negative integer") from exc
    if parsed < 0 or str(value).strip() not in (str(parsed), f"{parsed}.0"):
        raise CovarEventScoringError(f"{key} must be a non-negative integer")
    return parsed


def calculate_fpl_points_2026_27(position: str, events: Mapping[str, Any]) -> dict[str, Any]:
    """Calculate a player's FPL points from explicit single-match events."""
    if position not in ("GK", "DEF", "MID", "FWD"):
        raise CovarEventScoringError("position must be GK, DEF, MID or FWD")

    minutes = _count(events, "minutes")
    if minutes > 120:
        raise CovarEventScoringError("minutes cannot exceed 120")
    goals = _count(events, "goals")
    assists = _count(events, "assists")
    saves = _count(events, "saves")
    penalty_saves = _count(events, "penalty_saves")
    defensive_count = _count(events, "defensive_contribution_count")
    penalty_misses = _count(events, "penalty_misses")
    bonus = _count(events, "bonus_points")
    if "goals_conceded_while_on_pitch" not in events:
        raise CovarEventScoringError(
            "goals_conceded_while_on_pitch must be explicit for each player"
        )
    goals_conceded = _count(events, "goals_conceded_while_on_pitch")
    yellow_cards = _count(events, "yellow_cards")
    red_cards = _count(events, "red_cards")
    own_goals = _count(events, "own_goals")

    if bonus > 3:
        raise CovarEventScoringError("bonus_points must be between 0 and 3")
    goalkeeping_duties = events.get("goalkeeping_duties", position == "GK")
    if not isinstance(goalkeeping_duties, bool):
        raise CovarEventScoringError("goalkeeping_duties must be an explicit boolean")
    is_goalkeeper_in_match = position == "GK" or goalkeeping_duties
    if (saves or penalty_saves) and not is_goalkeeper_in_match:
        raise CovarEventScoringError("save events require goalkeeping duties")
    if position not in ("GK", "DEF") and goals_conceded:
        raise CovarEventScoringError("goals-conceded deductions apply only to GK and DEF")
    if not isinstance(events.get("clean_sheet"), bool):
        raise CovarEventScoringError("clean_sheet must be an explicit boolean")
    if events["clean_sheet"] and goals_conceded > 0:
        raise CovarEventScoringError(
            "clean_sheet cannot be true when a goal was conceded while the player was on pitch"
        )

    points: dict[str, int] = {}
    points["appearance"] = 2 if minutes >= 60 else (1 if minutes > 0 else 0)
    goal_value = {"GK": 10, "DEF": 6, "MID": 5, "FWD": 4}[position]
    points["goals"] = goals * goal_value
    points["assists"] = assists * 3

    clean_sheet_value = {"GK": 4, "DEF": 4, "MID": 1, "FWD": 0}[position]
    clean_sheet_awarded = bool(
        events["clean_sheet"] and minutes >= 60 and clean_sheet_value > 0
    )
    points["clean_sheet"] = clean_sheet_value if clean_sheet_awarded else 0
    points["saves"] = saves // 3 if is_goalkeeper_in_match else 0
    points["penalty_saves"] = penalty_saves * 5 if is_goalkeeper_in_match else 0

    threshold = 10 if position == "DEF" else (12 if position in ("MID", "FWD") else None)
    points["defensive_contribution"] = (
        2 if threshold is not None and defensive_count >= threshold else 0
    )
    points["penalty_misses"] = penalty_misses * -2
    points["bonus"] = bonus
    points["goals_conceded"] = -(goals_conceded // 2) if position in ("GK", "DEF") else 0
    points["yellow_cards"] = yellow_cards * -1
    points["red_cards"] = red_cards * -3
    points["own_goals"] = own_goals * -2

    return {
        "scoring_version": SCORING_VERSION,
        "position": position,
        "minutes": minutes,
        "point_breakdown": points,
        "fpl_points": sum(points.values()),
    }


def score_scenario_events(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy with each scenario player's FPL points event-calculated.

    Required player rows must include position. Each player outcome must
    include the explicit event fields consumed by calculate_fpl_points_2026_27.
    The original fpl_points field is replaced, never trusted as the result.
    """
    validate_scenario_document(document)
    if document["metadata"].get("season") != "2026-27":
        raise CovarEventScoringError(
            "FPL_2026_27 scoring can only be applied to season 2026-27"
        )
    players = {str(row["player_id"]): row for row in document["players"]}
    scored = copy.deepcopy(dict(document))
    for scenario in scored["scenarios"]:
        for outcome in scenario["player_outcomes"]:
            player_id = str(outcome["player_id"])
            player = players[player_id]
            if "position" not in player:
                raise CovarEventScoringError(
                    f"player {player_id} requires a position for event scoring"
                )
            result = calculate_fpl_points_2026_27(
                str(player["position"]), outcome
            )
            outcome["fpl_points"] = result["fpl_points"]
            outcome["point_breakdown"] = result["point_breakdown"]
            outcome["scoring_version"] = SCORING_VERSION
    return scored
