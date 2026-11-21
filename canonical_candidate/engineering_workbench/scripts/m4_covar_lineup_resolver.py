#!/usr/bin/env python3
"""Pure deterministic FPL lineup and automatic-substitution resolver for M4.

This module consumes explicit player minutes and FPL points only. It does not
forecast outcomes, fetch data, infer ownership, or enable production decisions.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence


class CovarLineupResolutionError(ValueError):
    """Raised when lineup inputs are incomplete, inconsistent, or invalid."""


POSITIONS = {"GK", "DEF", "MID", "FWD"}
MINIMUM_OUTFIELD = {"DEF": 3, "MID": 2, "FWD": 1}
ALLOWED_CHIPS = {"", "3xc", "bboost", "freehit", "wildcard"}
ALLOWED_MODES = {"REGULAR_GW", "FREE_HIT"}


def _finite_number(value: Any, label: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool):
        raise CovarLineupResolutionError(f"{label} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CovarLineupResolutionError(f"{label} must be numeric") from exc
    if not math.isfinite(number) or (minimum is not None and number < minimum):
        raise CovarLineupResolutionError(f"{label} must be finite and >= {minimum}")
    return number


def _validate_lineup(
    *,
    player_ids: Sequence[str],
    starting_player_ids: Sequence[str],
    starting_goalkeeper_id: str,
    reserve_goalkeeper_id: str,
    bench_order: Sequence[str],
    player_positions: Mapping[str, str],
    captain_id: str,
    vice_captain_id: str,
) -> tuple[list[str], list[str], dict[str, str]]:
    if not isinstance(player_ids, (list, tuple)) or len(player_ids) != 15:
        raise CovarLineupResolutionError("player_ids must contain exactly 15 players")
    players = [str(value) for value in player_ids]
    if any(not value for value in players) or len(set(players)) != 15:
        raise CovarLineupResolutionError("player_ids must be 15 unique non-empty IDs")

    if not isinstance(starting_player_ids, (list, tuple)) or len(starting_player_ids) != 11:
        raise CovarLineupResolutionError("starting_player_ids must contain exactly 11 players")
    starters = [str(value) for value in starting_player_ids]
    if len(set(starters)) != 11 or not set(starters).issubset(players):
        raise CovarLineupResolutionError("starting_player_ids must be 11 unique squad members")

    if not isinstance(bench_order, (list, tuple)) or len(bench_order) != 3:
        raise CovarLineupResolutionError("bench_order must contain exactly three outfield substitutes")
    bench = [str(value) for value in bench_order]
    if len(set(bench)) != 3 or not set(bench).issubset(players):
        raise CovarLineupResolutionError("bench_order must contain three unique squad members")
    if set(starters).intersection(bench):
        raise CovarLineupResolutionError("starting XI and outfield bench must be disjoint")

    goalkeeper = str(starting_goalkeeper_id)
    reserve_goalkeeper = str(reserve_goalkeeper_id)
    if goalkeeper not in starters or reserve_goalkeeper not in players:
        raise CovarLineupResolutionError("starting and reserve goalkeeper IDs must belong to the squad")
    if reserve_goalkeeper in starters or reserve_goalkeeper in bench:
        raise CovarLineupResolutionError("reserve goalkeeper must be separate from starters and outfield bench")
    if set(players) != set(starters) | {reserve_goalkeeper} | set(bench):
        raise CovarLineupResolutionError("starting XI, reserve goalkeeper and outfield bench must cover all 15 players")

    if not isinstance(player_positions, Mapping) or set(map(str, player_positions)) != set(players):
        raise CovarLineupResolutionError("player_positions must define all 15 squad players exactly")
    positions = {str(pid): str(position).upper() for pid, position in player_positions.items()}
    if any(position not in POSITIONS for position in positions.values()):
        raise CovarLineupResolutionError("player positions must be GK, DEF, MID, or FWD")
    if positions[goalkeeper] != "GK" or positions[reserve_goalkeeper] != "GK":
        raise CovarLineupResolutionError("starting goalkeeper and reserve goalkeeper must both be GK")
    if sum(positions[pid] == "GK" for pid in starters) != 1:
        raise CovarLineupResolutionError("starting XI must contain exactly one goalkeeper")
    if any(positions[pid] == "GK" for pid in bench):
        raise CovarLineupResolutionError("outfield bench cannot contain a goalkeeper")
    if any(positions[pid] == "GK" for pid in players if pid not in {goalkeeper, reserve_goalkeeper}):
        raise CovarLineupResolutionError("squad cannot contain additional goalkeepers outside the two GK slots")

    formation = {position: sum(positions[pid] == position for pid in starters) for position in MINIMUM_OUTFIELD}
    if sum(formation.values()) != 10 or any(
        formation[position] < minimum for position, minimum in MINIMUM_OUTFIELD.items()
    ):
        raise CovarLineupResolutionError("starting XI does not satisfy legal FPL formation minimums")

    captain = str(captain_id)
    vice = str(vice_captain_id)
    if captain not in starters or vice not in starters or captain == vice:
        raise CovarLineupResolutionError("captain and vice-captain must be distinct starting XI players")
    return starters, bench, positions


def resolve_fpl_lineup(
    *,
    player_ids: Sequence[str],
    starting_player_ids: Sequence[str],
    starting_goalkeeper_id: str,
    reserve_goalkeeper_id: str,
    bench_order: Sequence[str],
    player_positions: Mapping[str, str],
    captain_id: str,
    vice_captain_id: str,
    player_minutes: Mapping[str, Any],
    player_points: Mapping[str, Any],
    active_chip: str | None = None,
    mode: str = "REGULAR_GW",
) -> dict[str, Any]:
    """Resolve one FPL squad for one explicit scenario.

    Outfield substitutes are considered in bench order. Each enters for the
    earliest absent starting outfielder whose replacement preserves the
    minimum legal formation. A player with any minutes is never subbed off.
    """
    if mode not in ALLOWED_MODES:
        raise CovarLineupResolutionError("mode must be REGULAR_GW or explicitly FREE_HIT")
    chip = str(active_chip or "").strip().lower()
    if chip not in ALLOWED_CHIPS:
        raise CovarLineupResolutionError("active_chip is unsupported")

    starters, bench, positions = _validate_lineup(
        player_ids=player_ids,
        starting_player_ids=starting_player_ids,
        starting_goalkeeper_id=starting_goalkeeper_id,
        reserve_goalkeeper_id=reserve_goalkeeper_id,
        bench_order=bench_order,
        player_positions=player_positions,
        captain_id=captain_id,
        vice_captain_id=vice_captain_id,
    )
    squad = [str(pid) for pid in player_ids]
    expected = set(squad)
    if not isinstance(player_minutes, Mapping) or set(map(str, player_minutes)) != expected:
        raise CovarLineupResolutionError("player_minutes must explicitly cover all 15 squad players")
    if not isinstance(player_points, Mapping) or set(map(str, player_points)) != expected:
        raise CovarLineupResolutionError("player_points must explicitly cover all 15 squad players")

    minutes = {
        str(pid): _finite_number(value, f"player_minutes[{pid}]", minimum=0)
        for pid, value in player_minutes.items()
    }
    if any(value > 120 for value in minutes.values()):
        raise CovarLineupResolutionError("player minutes cannot exceed 120")
    points = {
        str(pid): _finite_number(value, f"player_points[{pid}]")
        for pid, value in player_points.items()
    }

    resolved = list(starters)
    substitutions: list[dict[str, str]] = []
    starting_gk = str(starting_goalkeeper_id)
    reserve_gk = str(reserve_goalkeeper_id)
    if minutes[starting_gk] == 0 and minutes[reserve_gk] > 0:
        resolved[resolved.index(starting_gk)] = reserve_gk
        substitutions.append({
            "out": starting_gk, "in": reserve_gk, "type": "GOALKEEPER",
        })

    for substitute in bench:
        if minutes[substitute] <= 0:
            continue
        absent_starters = [
            pid for pid in starters
            if pid != starting_gk and minutes[pid] == 0 and pid in resolved
        ]
        for absent in absent_starters:
            trial = list(resolved)
            trial[trial.index(absent)] = substitute
            counts = {
                position: sum(positions[pid] == position for pid in trial)
                for position in MINIMUM_OUTFIELD
            }
            if all(counts[position] >= minimum for position, minimum in MINIMUM_OUTFIELD.items()):
                resolved = trial
                substitutions.append({
                    "out": absent, "in": substitute, "type": "OUTFIELD",
                })
                break

    active_captain = None
    if minutes[str(captain_id)] > 0:
        active_captain = str(captain_id)
    elif minutes[str(vice_captain_id)] > 0:
        active_captain = str(vice_captain_id)

    captain_total_multiplier = 3 if chip == "3xc" else 2
    score_all_bench = chip == "bboost"
    scoring_ids = squad if score_all_bench else resolved
    contributions: dict[str, float] = {}
    for pid in scoring_ids:
        multiplier = (
            captain_total_multiplier
            if pid == active_captain
            else 1
        )
        contributions[pid] = points[pid] * multiplier

    total_points = sum(contributions.values())
    return {
        "mode": mode,
        "active_chip": chip or None,
        "starting_player_ids": starters,
        "resolved_starting_xi": resolved,
        "substitutions": substitutions,
        "active_captain_id": active_captain,
        "captain_multiplier": captain_total_multiplier if active_captain else 1,
        "bench_boost_active": score_all_bench,
        "scoring_player_ids": scoring_ids,
        "player_contributions": contributions,
        "total_points": total_points,
        "production_eligible": False,
        "decision_weight": 0.0,
    }
