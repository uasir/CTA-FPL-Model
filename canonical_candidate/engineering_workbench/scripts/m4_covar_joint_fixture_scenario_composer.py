#!/usr/bin/env python3
"""Compose explicit joint fixture scenarios without assuming fixture independence.

This module does not sample, forecast, multiply marginal probabilities, or
create a Cartesian product. Dependence is supplied by explicit joint rows.
"""
from __future__ import annotations
import math
from typing import Any, Mapping, Sequence

class CovarJointScenarioCompositionError(ValueError):
    """Invalid joint fixture scenario references or weights."""

def compose_joint_fixture_scenarios(
    *,
    fixture_catalogs: Mapping[str, Sequence[Mapping[str, Any]]],
    joint_scenarios: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve explicit fixture-scenario references into aggregator inputs.

    fixture_catalogs maps fixture ID -> catalog rows. Each catalog row has a
    unique scenario_id and complete player_outcomes. Each joint row explicitly
    maps every fixture ID to one catalog scenario ID and supplies its own
    probability. No independence or Cartesian-product assumption is made.
    """
    if not isinstance(fixture_catalogs, Mapping) or not fixture_catalogs:
        raise CovarJointScenarioCompositionError("fixture_catalogs must declare fixtures")
    catalogs: dict[str, dict[str, Mapping[str, Any]]] = {}
    fixture_player_sets: dict[str, set[str]] = {}
    for raw_fixture_id, rows in fixture_catalogs.items():
        fixture_id = str(raw_fixture_id).strip()
        if not fixture_id or fixture_id in catalogs or not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or not rows:
            raise CovarJointScenarioCompositionError("each fixture requires a non-empty scenario catalog")
        by_scenario: dict[str, Mapping[str, Any]] = {}
        expected_players: set[str] | None = None
        for row in rows:
            if not isinstance(row, Mapping):
                raise CovarJointScenarioCompositionError("fixture catalog rows must be objects")
            scenario_id = str(row.get("scenario_id", "")).strip()
            if not scenario_id or scenario_id in by_scenario:
                raise CovarJointScenarioCompositionError(f"fixture {fixture_id} scenario IDs must be unique and non-empty")
            outcomes = row.get("player_outcomes")
            if not isinstance(outcomes, list) or not outcomes:
                raise CovarJointScenarioCompositionError(f"fixture {fixture_id} scenario {scenario_id} requires player_outcomes")
            player_ids: set[str] = set()
            for outcome in outcomes:
                if not isinstance(outcome, Mapping):
                    raise CovarJointScenarioCompositionError("player outcomes must be objects")
                player_id = str(outcome.get("player_id", "")).strip()
                if not player_id or player_id in player_ids:
                    raise CovarJointScenarioCompositionError(f"fixture {fixture_id} has empty or duplicate player IDs")
                player_ids.add(player_id)
                for field in ("minutes", "yellow_cards", "red_cards", "fpl_points"):
                    value = outcome.get(field)
                    if isinstance(value, bool):
                        raise CovarJointScenarioCompositionError(f"{fixture_id}.{scenario_id}.{player_id}.{field} must be numeric")
                    try:
                        number = float(value)
                    except (TypeError, ValueError) as exc:
                        raise CovarJointScenarioCompositionError(f"{fixture_id}.{scenario_id}.{player_id}.{field} must be numeric") from exc
                    if not math.isfinite(number):
                        raise CovarJointScenarioCompositionError(f"{fixture_id}.{scenario_id}.{player_id}.{field} must be finite")
                    if field in ("minutes", "yellow_cards", "red_cards") and number < 0:
                        raise CovarJointScenarioCompositionError(f"{fixture_id}.{scenario_id}.{player_id}.{field} cannot be negative")
                    if field == "minutes" and number > 120:
                        raise CovarJointScenarioCompositionError(f"{fixture_id}.{scenario_id}.{player_id}.minutes cannot exceed 120")
                    if field in ("yellow_cards", "red_cards") and not number.is_integer():
                        raise CovarJointScenarioCompositionError(f"{fixture_id}.{scenario_id}.{player_id}.{field} must be an integer")
            if expected_players is None:
                expected_players = player_ids
            elif player_ids != expected_players:
                raise CovarJointScenarioCompositionError(f"fixture {fixture_id} scenario catalogs must share identical player coverage")
            by_scenario[scenario_id] = row
        catalogs[fixture_id] = by_scenario
        fixture_player_sets[fixture_id] = expected_players or set()

    if not isinstance(joint_scenarios, Sequence) or isinstance(joint_scenarios, (str, bytes)) or not joint_scenarios:
        raise CovarJointScenarioCompositionError("joint_scenarios must be a non-empty sequence")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    probability_total = 0.0
    for joint in joint_scenarios:
        if not isinstance(joint, Mapping):
            raise CovarJointScenarioCompositionError("joint scenario rows must be objects")
        joint_id = str(joint.get("scenario_id", "")).strip()
        if not joint_id or joint_id in seen:
            raise CovarJointScenarioCompositionError("joint scenario IDs must be unique and non-empty")
        seen.add(joint_id)
        raw_probability = joint.get("probability")
        if isinstance(raw_probability, bool):
            raise CovarJointScenarioCompositionError("joint scenario probability must be finite and > 0")
        try:
            probability = float(raw_probability)
        except (TypeError, ValueError) as exc:
            raise CovarJointScenarioCompositionError("joint scenario probability must be finite and > 0") from exc
        if not math.isfinite(probability) or probability <= 0:
            raise CovarJointScenarioCompositionError("joint scenario probability must be finite and > 0")
        probability_total += probability
        refs = joint.get("fixture_scenario_ids")
        if not isinstance(refs, Mapping) or set(map(str, refs.keys())) != set(catalogs):
            raise CovarJointScenarioCompositionError(f"joint scenario {joint_id} must reference every declared fixture exactly once")
        fixture_rows = []
        for fixture_id in catalogs:
            selected_id = str(refs[fixture_id]).strip()
            selected = catalogs[fixture_id].get(selected_id)
            if selected is None:
                raise CovarJointScenarioCompositionError(f"joint scenario {joint_id} references unknown scenario {selected_id!r} for fixture {fixture_id}")
            fixture_rows.append({
                "fixture_id": fixture_id,
                "player_outcomes": [dict(row) for row in selected["player_outcomes"]],
            })
        result.append({"scenario_id": joint_id, "probability": probability, "fixtures": fixture_rows})
    if not math.isclose(probability_total, 1.0, rel_tol=0, abs_tol=1e-9):
        raise CovarJointScenarioCompositionError("joint scenario probabilities must sum to 1")
    return result
