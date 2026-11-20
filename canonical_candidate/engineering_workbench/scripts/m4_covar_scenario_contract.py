#!/usr/bin/env python3
"""Validate versioned inputs for the exploratory M4 joint-event CoVar prototype.

This contract validates synthetic fixture scenarios only. It does not fetch
forecasts, estimate ownership, score FPL events, optimize squads, or enable CoVar.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Mapping


class CovarScenarioContractError(ValueError):
    pass


CONTRACT_VERSION = "1.0.0"
ALLOWED_DATA_STATUS = {"SYNTHETIC_FIXTURE_ONLY"}


def _number(value: Any, label: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool):
        raise CovarScenarioContractError(f"{label} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise CovarScenarioContractError(f"{label} must be numeric") from exc
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise CovarScenarioContractError(f"{label} must be finite and >= {minimum}")
    return result


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise CovarScenarioContractError(f"{label} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise CovarScenarioContractError(f"{label} must be an integer") from exc
    if str(value).strip() not in (str(parsed), f"{parsed}.0"):
        raise CovarScenarioContractError(f"{label} must be an integer")
    if parsed < minimum:
        raise CovarScenarioContractError(f"{label} must be >= {minimum}")
    return parsed


def _utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise CovarScenarioContractError(f"{label} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CovarScenarioContractError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CovarScenarioContractError(f"{label} must include a timezone")
    return parsed


def validate_scenario_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize a synthetic fixture scenario document."""
    if not isinstance(document, Mapping):
        raise CovarScenarioContractError("document must be an object")
    if document.get("schema_version") != CONTRACT_VERSION:
        raise CovarScenarioContractError(f"schema_version must be {CONTRACT_VERSION}")
    if document.get("data_status") not in ALLOWED_DATA_STATUS:
        raise CovarScenarioContractError("only SYNTHETIC_FIXTURE_ONLY is admitted by this prototype contract")

    metadata = document.get("metadata")
    teams = document.get("teams")
    players = document.get("players")
    scenarios = document.get("scenarios")
    portfolios = document.get("portfolios")
    if not all(isinstance(value, Mapping) for value in (metadata,)):
        raise CovarScenarioContractError("metadata must be an object")
    if not isinstance(teams, list) or len(teams) < 2:
        raise CovarScenarioContractError("at least two fixture teams are required")
    if not isinstance(players, list) or not players:
        raise CovarScenarioContractError("players must be a non-empty list")
    if not isinstance(scenarios, list) or not scenarios:
        raise CovarScenarioContractError("scenarios must be a non-empty list")
    if not isinstance(portfolios, list) or len(portfolios) < 2:
        raise CovarScenarioContractError("at least two comparison portfolios are required")

    required_meta = ("fixture_id", "season", "target_gameweek", "deadline_utc", "as_of_utc")
    if any(not metadata.get(key) for key in required_meta):
        raise CovarScenarioContractError("metadata fixture identity and time fields are required")
    if _integer(metadata["target_gameweek"], "metadata.target_gameweek", minimum=1) < 1:
        raise CovarScenarioContractError("target_gameweek must be positive")
    deadline = _utc(metadata["deadline_utc"], "metadata.deadline_utc")
    as_of = _utc(metadata["as_of_utc"], "metadata.as_of_utc")
    if as_of >= deadline:
        raise CovarScenarioContractError("scenario inputs must be timestamped before the deadline")

    team_ids = [str(row.get("team_id", "")).strip() for row in teams if isinstance(row, Mapping)]
    if len(team_ids) != len(teams) or any(not value for value in team_ids) or len(set(team_ids)) != len(team_ids):
        raise CovarScenarioContractError("teams require unique non-empty team_id values")

    player_by_id: dict[str, dict[str, Any]] = {}
    for row in players:
        if not isinstance(row, Mapping):
            raise CovarScenarioContractError("each player must be an object")
        player_id = str(row.get("player_id", "")).strip()
        team_id = str(row.get("team_id", "")).strip()
        if not player_id or player_id in player_by_id:
            raise CovarScenarioContractError("player IDs must be unique and non-empty")
        if team_id not in team_ids:
            raise CovarScenarioContractError(f"player {player_id} has unknown team_id")
        _number(row.get("expected_points"), f"player {player_id}.expected_points", minimum=0)
        _number(row.get("expected_minutes"), f"player {player_id}.expected_minutes", minimum=0)
        if _number(row.get("expected_minutes"), f"player {player_id}.expected_minutes") > 90:
            raise CovarScenarioContractError(f"player {player_id}.expected_minutes cannot exceed 90")
        for field in ("ownership_pct", "effective_ownership_pct", "captain_pct", "triple_captain_pct"):
            value = row.get(field)
            if value is not None and not 0 <= _number(value, f"player {player_id}.{field}", minimum=0) <= 100:
                raise CovarScenarioContractError(f"player {player_id}.{field} must be between 0 and 100 or null")
        player_by_id[player_id] = dict(row)

    scenario_ids: set[str] = set()
    probability_total = 0.0
    for scenario in scenarios:
        if not isinstance(scenario, Mapping):
            raise CovarScenarioContractError("each scenario must be an object")
        scenario_id = str(scenario.get("scenario_id", "")).strip()
        if not scenario_id or scenario_id in scenario_ids:
            raise CovarScenarioContractError("scenario IDs must be unique and non-empty")
        scenario_ids.add(scenario_id)
        probability = _number(scenario.get("probability"), f"scenario {scenario_id}.probability", minimum=0)
        probability_total += probability
        team_states = scenario.get("team_states")
        outcomes = scenario.get("player_outcomes")
        if not isinstance(team_states, list) or len(team_states) != len(team_ids):
            raise CovarScenarioContractError(f"scenario {scenario_id} must define every fixture team's state")
        state_by_team = {}
        for state in team_states:
            if not isinstance(state, Mapping):
                raise CovarScenarioContractError("team state must be an object")
            team_id = str(state.get("team_id", ""))
            if team_id not in team_ids or team_id in state_by_team:
                raise CovarScenarioContractError(f"scenario {scenario_id} has invalid or duplicate team state")
            goals_for = _integer(state.get("goals_for"), "team_state.goals_for")
            goals_against = _integer(state.get("goals_against"), "team_state.goals_against")
            state_by_team[team_id] = {"goals_for": goals_for, "goals_against": goals_against}
        if not isinstance(outcomes, list):
            raise CovarScenarioContractError(f"scenario {scenario_id}.player_outcomes must be a list")
        outcome_ids = set()
        goals_by_team = {team_id: 0 for team_id in team_ids}
        for outcome in outcomes:
            if not isinstance(outcome, Mapping):
                raise CovarScenarioContractError("player outcome must be an object")
            player_id = str(outcome.get("player_id", ""))
            if player_id not in player_by_id or player_id in outcome_ids:
                raise CovarScenarioContractError(f"scenario {scenario_id} has unknown or duplicate player outcome")
            outcome_ids.add(player_id)
            minutes = _number(outcome.get("minutes"), f"{scenario_id}.{player_id}.minutes", minimum=0)
            if minutes > 120:
                raise CovarScenarioContractError("player minutes cannot exceed 120")
            goals = _integer(outcome.get("goals"), f"{scenario_id}.{player_id}.goals")
            assists = _integer(outcome.get("assists"), f"{scenario_id}.{player_id}.assists")
            # FPL player totals can be negative after cards/own goals; do not clamp them.
            if outcome.get("fpl_points") is not None:
                _number(outcome["fpl_points"], f"{scenario_id}.{player_id}.fpl_points")
            goals_by_team[player_by_id[player_id]["team_id"]] += goals
            if not isinstance(outcome.get("clean_sheet"), bool):
                raise CovarScenarioContractError("clean_sheet must be an explicit boolean")
            team_id = player_by_id[player_id]["team_id"]
            conceded_on_pitch_value = outcome.get("goals_conceded_while_on_pitch")
            conceded_on_pitch = (
                _integer(conceded_on_pitch_value, f"{scenario_id}.{player_id}.goals_conceded_while_on_pitch")
                if conceded_on_pitch_value is not None
                else state_by_team[team_id]["goals_against"]
            )
            if conceded_on_pitch > state_by_team[team_id]["goals_against"]:
                raise CovarScenarioContractError(
                    f"{scenario_id}.{player_id}.goals_conceded_while_on_pitch exceeds team goals conceded"
                )
            if outcome["clean_sheet"] and (minutes < 60 or conceded_on_pitch > 0):
                raise CovarScenarioContractError(
                    f"{scenario_id}.{player_id} has an inconsistent clean-sheet flag"
                )
            if assists > sum(state["goals_for"] for state in state_by_team.values()):
                raise CovarScenarioContractError(f"{scenario_id}.{player_id} assists exceed fixture goals")
        if outcome_ids != set(player_by_id):
            raise CovarScenarioContractError(f"scenario {scenario_id} must include every declared player outcome")
        for team_id, goals in goals_by_team.items():
            if goals > state_by_team[team_id]["goals_for"]:
                raise CovarScenarioContractError(f"scenario {scenario_id} player goals exceed {team_id} team goals")
    if not math.isclose(probability_total, 1.0, rel_tol=0, abs_tol=1e-9):
        raise CovarScenarioContractError("scenario probabilities must sum to 1")

    portfolio_ids: set[str] = set()
    for portfolio in portfolios:
        if not isinstance(portfolio, Mapping):
            raise CovarScenarioContractError("each portfolio must be an object")
        portfolio_id = str(portfolio.get("portfolio_id", "")).strip()
        if not portfolio_id or portfolio_id in portfolio_ids:
            raise CovarScenarioContractError("portfolio IDs must be unique and non-empty")
        portfolio_ids.add(portfolio_id)
        selected = portfolio.get("player_ids")
        if not isinstance(selected, list) or not selected or len(set(map(str, selected))) != len(selected):
            raise CovarScenarioContractError(f"portfolio {portfolio_id} must have unique player_ids")
        if not set(map(str, selected)).issubset(player_by_id):
            raise CovarScenarioContractError(f"portfolio {portfolio_id} contains unknown player IDs")
        if str(portfolio.get("captain_id", "")) not in set(map(str, selected)):
            raise CovarScenarioContractError(f"portfolio {portfolio_id} captain must be selected")
        multiplier = _number(portfolio.get("captain_multiplier", 2), f"portfolio {portfolio_id}.captain_multiplier", minimum=1)
        if multiplier not in (2.0, 3.0):
            raise CovarScenarioContractError("captain_multiplier must be 2 or 3 for this prototype")

    normalized = dict(document)
    normalized["contract_version"] = CONTRACT_VERSION
    normalized["validation_status"] = "VALID_SYNTHETIC_RESEARCH_INPUT"
    normalized["scenario_probability_total"] = probability_total
    normalized["player_count"] = len(player_by_id)
    normalized["scenario_count"] = len(scenario_ids)
    normalized["portfolio_count"] = len(portfolio_ids)
    normalized["production_eligible"] = False
    normalized["decision_weight"] = 0.0
    return normalized
