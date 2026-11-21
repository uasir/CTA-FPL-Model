"""Source-independent intake contract for prospective explicit joint FPL forecasts.

The contract accepts complete joint scenarios supplied by an identified forecast
source. It never estimates probabilities, expands marginals, or assumes fixture
independence. Passing this contract is structural acceptance only.
"""
from __future__ import annotations

from typing import Any, Mapping

from m4_covar_joint_forecast_provenance import (
    JointForecastProvenanceError,
    validate_joint_forecast_provenance,
)


class JointForecastIntakeError(ValueError):
    """A prospective joint forecast is incomplete or invalid."""


SCHEMA_VERSION = "1.0.0"
FORECAST_KIND = "EXPLICIT_JOINT_GAMEWEEK_DISTRIBUTION"


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise JointForecastIntakeError(f"{field} must be a non-empty string")
    return value.strip()


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise JointForecastIntakeError(f"{field} must be finite numeric")
    try:
        import math
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise JointForecastIntakeError(f"{field} must be finite numeric") from exc
    if not math.isfinite(parsed):
        raise JointForecastIntakeError(f"{field} must be finite numeric")
    return parsed


def validate_joint_forecast_intake(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a complete, point-in-time joint forecast document.

    Required top-level keys:
      schema_version, forecast_kind, forecast_id, season, target_gameweek,
      deadline_utc, as_of_utc, player_universe, fixtures, scenarios, provenance.

    Each scenario supplies one explicit probability, one outcome for every
    player in the declared Gameweek universe, and one state for every fixture.
    Player Gameweek FPL points are supplied values; this validator does not
    calculate or infer them. Source/model/config bytes are verified separately
    by the archive verifier.
    """
    if not isinstance(document, Mapping):
        raise JointForecastIntakeError("document must be an object")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise JointForecastIntakeError(f"schema_version must be {SCHEMA_VERSION}")
    if document.get("forecast_kind") != FORECAST_KIND:
        raise JointForecastIntakeError(f"forecast_kind must be {FORECAST_KIND}")
    forecast_id = _required_text(document.get("forecast_id"), "forecast_id")
    season = _required_text(document.get("season"), "season")
    if not season or not season[0:4].isdigit() or "-" not in season:
        raise JointForecastIntakeError("season must use a season label such as 2026-27")
    try:
        gameweek = int(document.get("target_gameweek"))
    except (TypeError, ValueError) as exc:
        raise JointForecastIntakeError("target_gameweek must be a positive integer") from exc
    if isinstance(document.get("target_gameweek"), bool) or gameweek < 1 or str(document.get("target_gameweek")) not in (str(gameweek), f"{gameweek}.0"):
        raise JointForecastIntakeError("target_gameweek must be a positive integer")

    try:
        from datetime import datetime
        deadline = datetime.fromisoformat(_required_text(document.get("deadline_utc"), "deadline_utc").replace("Z", "+00:00"))
        as_of = datetime.fromisoformat(_required_text(document.get("as_of_utc"), "as_of_utc").replace("Z", "+00:00"))
    except ValueError as exc:
        raise JointForecastIntakeError("deadline_utc and as_of_utc must be ISO-8601 timestamps") from exc
    if deadline.tzinfo is None or as_of.tzinfo is None:
        raise JointForecastIntakeError("deadline_utc and as_of_utc must include timezone offsets")
    if as_of >= deadline:
        raise JointForecastIntakeError("forecast as_of_utc must be strictly before the Gameweek deadline")

    players = document.get("player_universe")
    fixtures = document.get("fixtures")
    scenarios = document.get("scenarios")
    if not isinstance(players, list) or not players:
        raise JointForecastIntakeError("player_universe must be a non-empty list")
    if not isinstance(fixtures, list) or not fixtures:
        raise JointForecastIntakeError("fixtures must be a non-empty list")
    if not isinstance(scenarios, list) or not scenarios:
        raise JointForecastIntakeError("scenarios must be a non-empty list")

    player_ids: set[int] = set()
    for player in players:
        if not isinstance(player, Mapping):
            raise JointForecastIntakeError("each player_universe row must be an object")
        raw_id = player.get("player_id")
        if isinstance(raw_id, bool):
            raise JointForecastIntakeError("player_id must be a positive integer")
        try:
            player_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise JointForecastIntakeError("player_id must be a positive integer") from exc
        if player_id < 1 or str(raw_id) not in (str(player_id), f"{player_id}.0") or player_id in player_ids:
            raise JointForecastIntakeError("player IDs must be unique positive integers")
        player_ids.add(player_id)
        _required_text(player.get("team_id"), f"player {player_id}.team_id")

    fixture_ids: set[int] = set()
    for fixture in fixtures:
        if not isinstance(fixture, Mapping):
            raise JointForecastIntakeError("each fixture row must be an object")
        raw_id = fixture.get("fixture_id")
        if isinstance(raw_id, bool):
            raise JointForecastIntakeError("fixture_id must be a positive integer")
        try:
            fixture_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise JointForecastIntakeError("fixture_id must be a positive integer") from exc
        if fixture_id < 1 or str(raw_id) not in (str(fixture_id), f"{fixture_id}.0") or fixture_id in fixture_ids:
            raise JointForecastIntakeError("fixture IDs must be unique positive integers")
        fixture_ids.add(fixture_id)
        _required_text(fixture.get("home_team_id"), f"fixture {fixture_id}.home_team_id")
        _required_text(fixture.get("away_team_id"), f"fixture {fixture_id}.away_team_id")
        if fixture["home_team_id"] == fixture["away_team_id"]:
            raise JointForecastIntakeError(f"fixture {fixture_id} home and away teams must differ")

    seen_scenarios: set[str] = set()
    probability_total = 0.0
    for scenario in scenarios:
        if not isinstance(scenario, Mapping):
            raise JointForecastIntakeError("each scenario must be an object")
        scenario_id = _required_text(scenario.get("scenario_id"), "scenario_id")
        if scenario_id in seen_scenarios:
            raise JointForecastIntakeError("scenario IDs must be unique")
        seen_scenarios.add(scenario_id)
        probability = _finite_number(scenario.get("probability"), f"scenario {scenario_id}.probability")
        if probability <= 0:
            raise JointForecastIntakeError(f"scenario {scenario_id}.probability must be > 0")
        probability_total += probability
        if scenario.get("probability_basis") != "EXPLICIT_SOURCE_SUPPLIED":
            raise JointForecastIntakeError(
                f"scenario {scenario_id} probability_basis must be EXPLICIT_SOURCE_SUPPLIED"
            )

        fixture_states = scenario.get("fixture_states")
        if not isinstance(fixture_states, list) or len(fixture_states) != len(fixture_ids):
            raise JointForecastIntakeError(f"scenario {scenario_id} must provide every fixture state")
        state_ids: set[int] = set()
        for state in fixture_states:
            if not isinstance(state, Mapping):
                raise JointForecastIntakeError("fixture_states rows must be objects")
            raw_fixture_id = state.get("fixture_id")
            try:
                fixture_id = int(raw_fixture_id)
            except (TypeError, ValueError) as exc:
                raise JointForecastIntakeError("fixture state fixture_id must be an integer") from exc
            if fixture_id not in fixture_ids or fixture_id in state_ids:
                raise JointForecastIntakeError(f"scenario {scenario_id} has unknown or duplicate fixture state")
            state_ids.add(fixture_id)
            for field in ("home_goals", "away_goals"):
                goals = _finite_number(state.get(field), f"{scenario_id}.{fixture_id}.{field}")
                if goals < 0 or not goals.is_integer():
                    raise JointForecastIntakeError(f"{scenario_id}.{fixture_id}.{field} must be a non-negative integer")

        outcomes = scenario.get("player_outcomes")
        if not isinstance(outcomes, list) or len(outcomes) != len(player_ids):
            raise JointForecastIntakeError(f"scenario {scenario_id} must provide every player outcome")
        outcome_ids: set[int] = set()
        for outcome in outcomes:
            if not isinstance(outcome, Mapping):
                raise JointForecastIntakeError("player_outcomes rows must be objects")
            try:
                player_id = int(outcome.get("player_id"))
            except (TypeError, ValueError) as exc:
                raise JointForecastIntakeError("player outcome player_id must be an integer") from exc
            if player_id not in player_ids or player_id in outcome_ids:
                raise JointForecastIntakeError(f"scenario {scenario_id} has unknown or duplicate player outcome")
            outcome_ids.add(player_id)
            minutes = _finite_number(outcome.get("minutes"), f"{scenario_id}.{player_id}.minutes")
            if minutes < 0 or minutes > 180:
                raise JointForecastIntakeError(f"{scenario_id}.{player_id}.minutes must be between 0 and 180")
            if not isinstance(outcome.get("played"), bool):
                raise JointForecastIntakeError(f"{scenario_id}.{player_id}.played must be an explicit boolean")
            points = _finite_number(outcome.get("fpl_points"), f"{scenario_id}.{player_id}.fpl_points")
            if points < -100 or points > 100:
                raise JointForecastIntakeError(f"{scenario_id}.{player_id}.fpl_points outside defensive bounds")
            if outcome["played"] != (minutes > 0):
                raise JointForecastIntakeError(
                    f"{scenario_id}.{player_id}.played must agree with supplied aggregate minutes"
                )
    import math
    if not math.isclose(probability_total, 1.0, rel_tol=0, abs_tol=1e-9):
        raise JointForecastIntakeError("explicit joint scenario probabilities must sum to 1")

    provenance_forecast = {
        "forecast_id": forecast_id,
        "as_of_utc": document["as_of_utc"],
        "training_cutoff_utc": document.get("training_cutoff_utc"),
        "provenance": document.get("provenance"),
    }
    try:
        provenance_report = validate_joint_forecast_provenance([provenance_forecast])
    except JointForecastProvenanceError as exc:
        raise JointForecastIntakeError(f"provenance validation failed: {exc}") from exc

    return {
        "schema_version": "1.0.0",
        "forecast_id": forecast_id,
        "season": season,
        "target_gameweek": gameweek,
        "as_of_utc": document["as_of_utc"],
        "deadline_utc": document["deadline_utc"],
        "validation_status": "EXPLICIT_JOINT_FORECAST_INTAKE_ACCEPTED",
        "probability_basis": "EXPLICIT_SOURCE_SUPPLIED",
        "player_count": len(player_ids),
        "fixture_count": len(fixture_ids),
        "scenario_count": len(seen_scenarios),
        "probability_total": probability_total,
        "provenance_validation": provenance_report,
        "joint_distribution_inferred": False,
        "fixture_independence_assumed": False,
        "probabilities_estimated_by_intake": False,
        "decision_weight": 0.0,
        "production_eligible": False,
    }
