#!/usr/bin/env python3
"""Fail-closed contract for synthetic full-Gameweek M4 CoVar scenarios.

Unlike the fixture-slice contract, this contract requires explicit outcomes
for the complete union of every candidate and field 15-player squad.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Mapping


class CovarFullGameweekContractError(ValueError):
    """Raised when a synthetic full-Gameweek document is incomplete or invalid."""


CONTRACT_VERSION = "1.0.0"
POSITIONS = {"GK", "DEF", "MID", "FWD"}
MINIMUM_OUTFIELD = {"DEF": 3, "MID": 2, "FWD": 1}
ALLOWED_CHIPS = {"", "3xc", "bboost", "freehit", "wildcard"}
ALLOWED_MODES = {"REGULAR_GW", "FREE_HIT"}


def _number(value: Any, label: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool):
        raise CovarFullGameweekContractError(f"{label} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise CovarFullGameweekContractError(f"{label} must be numeric") from exc
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise CovarFullGameweekContractError(f"{label} must be finite and >= {minimum}")
    return result


def _utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise CovarFullGameweekContractError(f"{label} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CovarFullGameweekContractError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CovarFullGameweekContractError(f"{label} must include a timezone")
    return parsed


def _validate_portfolio(
    portfolio: Mapping[str, Any],
    player_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[str, set[str], str]:
    portfolio_id = str(portfolio.get("portfolio_id", "")).strip()
    if not portfolio_id:
        raise CovarFullGameweekContractError("portfolio_id is required")
    role = portfolio.get("portfolio_role", "CANDIDATE")
    if role not in ("CANDIDATE", "FIELD"):
        raise CovarFullGameweekContractError("portfolio_role must be CANDIDATE or FIELD")

    selected = portfolio.get("player_ids")
    if not isinstance(selected, list) or len(selected) != 15:
        raise CovarFullGameweekContractError(f"portfolio {portfolio_id} must contain exactly 15 players")
    player_ids = [str(value) for value in selected]
    if any(not value for value in player_ids) or len(set(player_ids)) != 15:
        raise CovarFullGameweekContractError(f"portfolio {portfolio_id} must contain 15 unique non-empty players")
    if not set(player_ids).issubset(player_by_id):
        raise CovarFullGameweekContractError(f"portfolio {portfolio_id} contains players outside the scenario universe")

    starters_value = portfolio.get("starting_player_ids")
    bench_value = portfolio.get("bench_order")
    if not isinstance(starters_value, list) or len(starters_value) != 11:
        raise CovarFullGameweekContractError(f"portfolio {portfolio_id} starting XI must contain 11 players")
    if not isinstance(bench_value, list) or len(bench_value) != 3:
        raise CovarFullGameweekContractError(f"portfolio {portfolio_id} bench_order must contain three outfield substitutes")
    starters = [str(value) for value in starters_value]
    bench = [str(value) for value in bench_value]
    reserve_gk = str(portfolio.get("reserve_goalkeeper_id") or "")
    starting_gk = str(portfolio.get("starting_goalkeeper_id") or "")
    if len(set(starters)) != 11 or not set(starters).issubset(player_ids):
        raise CovarFullGameweekContractError(f"portfolio {portfolio_id} starting XI must be 11 unique squad members")
    if len(set(bench)) != 3 or not set(bench).issubset(player_ids):
        raise CovarFullGameweekContractError(f"portfolio {portfolio_id} bench must contain three unique squad members")
    if set(starters).intersection(bench):
        raise CovarFullGameweekContractError(f"portfolio {portfolio_id} starting XI and outfield bench must be disjoint")
    if starting_gk not in starters or reserve_gk not in player_ids:
        raise CovarFullGameweekContractError(f"portfolio {portfolio_id} must identify its starting and reserve goalkeeper")
    if reserve_gk in starters or reserve_gk in bench:
        raise CovarFullGameweekContractError(f"portfolio {portfolio_id} reserve goalkeeper must be separate from starters and outfield bench")
    if set(player_ids) != set(starters) | {reserve_gk} | set(bench):
        raise CovarFullGameweekContractError(f"portfolio {portfolio_id} lineup fields must cover all 15 players")

    positions_value = portfolio.get("player_positions")
    if not isinstance(positions_value, Mapping) or set(map(str, positions_value)) != set(player_ids):
        raise CovarFullGameweekContractError(f"portfolio {portfolio_id} player_positions must cover all 15 players")
    positions = {str(pid): str(value).upper() for pid, value in positions_value.items()}
    if any(value not in POSITIONS for value in positions.values()):
        raise CovarFullGameweekContractError(f"portfolio {portfolio_id} has an invalid player position")
    for pid, position in positions.items():
        if position != str(player_by_id[pid]["position"]).upper():
            raise CovarFullGameweekContractError(f"portfolio {portfolio_id} position for {pid} conflicts with player metadata")
    if positions[starting_gk] != "GK" or positions[reserve_gk] != "GK":
        raise CovarFullGameweekContractError(f"portfolio {portfolio_id} starting and reserve goalkeeper must be GK")
    if sum(positions[pid] == "GK" for pid in starters) != 1:
        raise CovarFullGameweekContractError(f"portfolio {portfolio_id} starting XI must contain exactly one goalkeeper")
    if any(positions[pid] == "GK" for pid in bench):
        raise CovarFullGameweekContractError(f"portfolio {portfolio_id} outfield bench cannot contain a goalkeeper")
    formation = {
        position: sum(positions[pid] == position for pid in starters)
        for position in MINIMUM_OUTFIELD
    }
    if sum(formation.values()) != 10 or any(
        formation[position] < minimum for position, minimum in MINIMUM_OUTFIELD.items()
    ):
        raise CovarFullGameweekContractError(f"portfolio {portfolio_id} starting XI is not a legal FPL formation")

    captain = str(portfolio.get("captain_id") or "")
    vice = str(portfolio.get("vice_captain_id") or "")
    if captain not in starters or vice not in starters or captain == vice:
        raise CovarFullGameweekContractError(f"portfolio {portfolio_id} captain and vice-captain must be distinct starters")
    chip = str(portfolio.get("active_chip") or "").strip().lower()
    if chip not in ALLOWED_CHIPS:
        raise CovarFullGameweekContractError(f"portfolio {portfolio_id} has an unsupported active_chip")
    if role == "FIELD":
        weight = _number(portfolio.get("field_weight"), f"portfolio {portfolio_id}.field_weight", minimum=0)
        if weight <= 0:
            raise CovarFullGameweekContractError("field portfolio weights must be > 0")
    return portfolio_id, set(player_ids), role


def validate_full_gameweek_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one complete synthetic full-Gameweek scenario document."""
    if not isinstance(document, Mapping):
        raise CovarFullGameweekContractError("document must be an object")
    if document.get("schema_version") != CONTRACT_VERSION:
        raise CovarFullGameweekContractError(f"schema_version must be {CONTRACT_VERSION}")
    if document.get("data_status") != "SYNTHETIC_FULL_GAMEWEEK_ONLY":
        raise CovarFullGameweekContractError("only SYNTHETIC_FULL_GAMEWEEK_ONLY data is admitted")
    if document.get("scenario_scope") != "FULL_GAMEWEEK":
        raise CovarFullGameweekContractError("scenario_scope must be FULL_GAMEWEEK")
    mode = document.get("mode", "REGULAR_GW")
    if mode not in ALLOWED_MODES:
        raise CovarFullGameweekContractError("mode must be REGULAR_GW or explicitly FREE_HIT")

    metadata = document.get("metadata")
    players = document.get("players")
    scenarios = document.get("scenarios")
    portfolios = document.get("portfolios")
    if not isinstance(metadata, Mapping):
        raise CovarFullGameweekContractError("metadata must be an object")
    if not isinstance(players, list) or not players:
        raise CovarFullGameweekContractError("players must be a non-empty list")
    if not isinstance(scenarios, list) or not scenarios:
        raise CovarFullGameweekContractError("scenarios must be a non-empty list")
    if not isinstance(portfolios, list) or len(portfolios) < 2:
        raise CovarFullGameweekContractError("at least two complete comparison portfolios are required")
    if not metadata.get("season") or not metadata.get("target_gameweek"):
        raise CovarFullGameweekContractError("metadata season and target_gameweek are required")
    try:
        gameweek = int(metadata["target_gameweek"])
    except (TypeError, ValueError) as exc:
        raise CovarFullGameweekContractError("target_gameweek must be a positive integer") from exc
    if isinstance(metadata["target_gameweek"], bool) or gameweek < 1 or str(metadata["target_gameweek"]).strip() not in (str(gameweek), f"{gameweek}.0"):
        raise CovarFullGameweekContractError("target_gameweek must be a positive integer")
    deadline = _utc(metadata.get("deadline_utc"), "metadata.deadline_utc")
    as_of = _utc(metadata.get("as_of_utc"), "metadata.as_of_utc")
    if as_of >= deadline:
        raise CovarFullGameweekContractError("scenario inputs must be timestamped before the deadline")

    player_by_id: dict[str, dict[str, Any]] = {}
    for row in players:
        if not isinstance(row, Mapping):
            raise CovarFullGameweekContractError("each player must be an object")
        player_id = str(row.get("player_id", "")).strip()
        position = str(row.get("position", "")).upper()
        if not player_id or player_id in player_by_id:
            raise CovarFullGameweekContractError("player IDs must be unique and non-empty")
        if position not in POSITIONS:
            raise CovarFullGameweekContractError(f"player {player_id} has an invalid position")
        player_by_id[player_id] = dict(row)

    portfolio_ids: set[str] = set()
    portfolio_player_union: set[str] = set()
    field_weights: list[float] = []
    candidate_count = 0
    for portfolio in portfolios:
        if not isinstance(portfolio, Mapping):
            raise CovarFullGameweekContractError("each portfolio must be an object")
        portfolio_id, selected, role = _validate_portfolio(portfolio, player_by_id)
        if portfolio_id in portfolio_ids:
            raise CovarFullGameweekContractError("portfolio IDs must be unique")
        portfolio_ids.add(portfolio_id)
        portfolio_player_union.update(selected)
        if role == "CANDIDATE":
            candidate_count += 1
        else:
            field_weights.append(float(portfolio["field_weight"]))
    if candidate_count < 1:
        raise CovarFullGameweekContractError("at least one CANDIDATE portfolio is required")
    if portfolio_player_union != set(player_by_id):
        raise CovarFullGameweekContractError("player universe must equal the union of all complete portfolio squads")
    if field_weights and not math.isclose(sum(field_weights), 1.0, rel_tol=0, abs_tol=1e-9):
        raise CovarFullGameweekContractError("field portfolio weights must sum to 1")

    scenario_ids: set[str] = set()
    probability_total = 0.0
    for scenario in scenarios:
        if not isinstance(scenario, Mapping):
            raise CovarFullGameweekContractError("each scenario must be an object")
        scenario_id = str(scenario.get("scenario_id", "")).strip()
        if not scenario_id or scenario_id in scenario_ids:
            raise CovarFullGameweekContractError("scenario IDs must be unique and non-empty")
        scenario_ids.add(scenario_id)
        probability = _number(scenario.get("probability"), f"scenario {scenario_id}.probability", minimum=0)
        probability_total += probability
        outcomes = scenario.get("player_outcomes")
        if not isinstance(outcomes, list):
            raise CovarFullGameweekContractError(f"scenario {scenario_id}.player_outcomes must be a list")
        outcome_by_id: dict[str, Mapping[str, Any]] = {}
        for outcome in outcomes:
            if not isinstance(outcome, Mapping):
                raise CovarFullGameweekContractError("each player outcome must be an object")
            player_id = str(outcome.get("player_id", "")).strip()
            if player_id not in player_by_id or player_id in outcome_by_id:
                raise CovarFullGameweekContractError(f"scenario {scenario_id} has an unknown or duplicate player outcome")
            minutes = _number(outcome.get("minutes"), f"{scenario_id}.{player_id}.minutes", minimum=0)
            if minutes > 120:
                raise CovarFullGameweekContractError(f"{scenario_id}.{player_id}.minutes cannot exceed 120")
            played = outcome.get("played")
            if not isinstance(played, bool):
                raise CovarFullGameweekContractError(f"{scenario_id}.{player_id}.played must be an explicit boolean")
            if minutes > 0 and not played:
                raise CovarFullGameweekContractError(f"{scenario_id}.{player_id} with positive minutes must be marked played")
            _number(outcome.get("fpl_points"), f"{scenario_id}.{player_id}.fpl_points")
            outcome_by_id[player_id] = outcome
        if set(outcome_by_id) != set(player_by_id):
            missing = len(set(player_by_id) - set(outcome_by_id))
            raise CovarFullGameweekContractError(
                f"scenario {scenario_id} must include every player in the full-Gameweek universe; missing {missing}"
            )
    if not math.isclose(probability_total, 1.0, rel_tol=0, abs_tol=1e-9):
        raise CovarFullGameweekContractError("scenario probabilities must sum to 1")

    normalized = dict(document)
    normalized["mode"] = mode
    normalized["contract_version"] = CONTRACT_VERSION
    normalized["validation_status"] = "VALID_SYNTHETIC_FULL_GAMEWEEK_INPUT"
    normalized["player_count"] = len(player_by_id)
    normalized["scenario_count"] = len(scenario_ids)
    normalized["portfolio_count"] = len(portfolio_ids)
    normalized["field_portfolio_count"] = len(field_weights)
    normalized["production_eligible"] = False
    normalized["decision_weight"] = 0.0
    return normalized
