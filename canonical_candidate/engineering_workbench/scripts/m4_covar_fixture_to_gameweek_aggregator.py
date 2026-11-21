#!/usr/bin/env python3
"""Aggregate joint fixture outcomes into full-Gameweek outcomes; not a predictor."""
from __future__ import annotations
import math
from typing import Any, Mapping, Sequence

class CovarFixtureAggregationError(ValueError):
    """Invalid fixture-level inputs."""

def aggregate_fixture_scenarios(*, player_ids: Sequence[str], fixture_player_ids: Mapping[str, Sequence[str]], joint_scenarios: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate supplied fixture points/minutes; preserve joint scenario probabilities."""
    universe = [str(x) for x in player_ids]
    if not universe or any(not x for x in universe) or len(set(universe)) != len(universe):
        raise CovarFixtureAggregationError("player_ids must be unique non-empty IDs")
    if not isinstance(fixture_player_ids, Mapping) or not fixture_player_ids:
        raise CovarFixtureAggregationError("fixture_player_ids must declare at least one fixture")
    fixtures = {}
    for raw_id, values in fixture_player_ids.items():
        fid, ids = str(raw_id).strip(), [str(x) for x in values]
        if not fid or not ids or len(ids) != len(set(ids)) or not set(ids).issubset(universe):
            raise CovarFixtureAggregationError("each fixture requires unique known player IDs")
        fixtures[fid] = set(ids)
    if set().union(*fixtures.values()) != set(universe):
        raise CovarFixtureAggregationError("fixture player coverage must equal the declared Gameweek player universe")
    if not isinstance(joint_scenarios, Sequence) or not joint_scenarios:
        raise CovarFixtureAggregationError("joint_scenarios must be non-empty")
    seen, total, result = set(), 0.0, []
    for scenario in joint_scenarios:
        if not isinstance(scenario, Mapping):
            raise CovarFixtureAggregationError("each joint scenario must be an object")
        sid = str(scenario.get("scenario_id", "")).strip()
        if not sid or sid in seen:
            raise CovarFixtureAggregationError("scenario IDs must be unique and non-empty")
        seen.add(sid)
        raw = scenario.get("probability")
        if isinstance(raw, bool):
            raise CovarFixtureAggregationError("scenario probability must be finite and > 0")
        try: probability = float(raw)
        except (TypeError, ValueError) as exc:
            raise CovarFixtureAggregationError("scenario probability must be finite and > 0") from exc
        if not math.isfinite(probability) or probability <= 0:
            raise CovarFixtureAggregationError("scenario probability must be finite and > 0")
        total += probability
        rows = scenario.get("fixtures")
        if not isinstance(rows, list):
            raise CovarFixtureAggregationError(f"scenario {sid} fixtures must be a list")
        by_id = {}
        for row in rows:
            if not isinstance(row, Mapping): raise CovarFixtureAggregationError("fixture row must be an object")
            fid = str(row.get("fixture_id", "")).strip()
            if fid not in fixtures or fid in by_id:
                raise CovarFixtureAggregationError(f"scenario {sid} has unknown or duplicate fixture")
            by_id[fid] = row
        if set(by_id) != set(fixtures):
            raise CovarFixtureAggregationError(f"scenario {sid} must include every declared fixture")
        sums = {pid: {"minutes": 0.0, "yellow_cards": 0, "red_cards": 0, "fpl_points": 0.0} for pid in universe}
        for fid, fixture in by_id.items():
            outcomes = fixture.get("player_outcomes")
            if not isinstance(outcomes, list): raise CovarFixtureAggregationError(f"fixture {fid} player_outcomes must be a list")
            outcome_by_id = {}
            for row in outcomes:
                if not isinstance(row, Mapping): raise CovarFixtureAggregationError("player outcome must be an object")
                pid = str(row.get("player_id", "")).strip()
                if pid not in fixtures[fid] or pid in outcome_by_id:
                    raise CovarFixtureAggregationError(f"fixture {fid} has unknown or duplicate player outcome")
                outcome_by_id[pid] = row
            if set(outcome_by_id) != fixtures[fid]:
                raise CovarFixtureAggregationError(f"fixture {fid} must cover its declared player universe")
            for pid, row in outcome_by_id.items():
                for field in ("minutes", "yellow_cards", "red_cards", "fpl_points"):
                    value = row.get(field)
                    if isinstance(value, bool): raise CovarFixtureAggregationError(f"{fid}.{pid}.{field} must be numeric")
                    try: number = float(value)
                    except (TypeError, ValueError) as exc: raise CovarFixtureAggregationError(f"{fid}.{pid}.{field} must be numeric") from exc
                    if not math.isfinite(number): raise CovarFixtureAggregationError(f"{fid}.{pid}.{field} must be finite")
                    if field in ("minutes", "yellow_cards", "red_cards") and number < 0:
                        raise CovarFixtureAggregationError(f"{fid}.{pid}.{field} cannot be negative")
                    if field == "minutes" and number > 120:
                        raise CovarFixtureAggregationError(f"{fid}.{pid}.minutes cannot exceed 120 per fixture")
                    if field in ("yellow_cards", "red_cards") and not number.is_integer():
                        raise CovarFixtureAggregationError(f"{fid}.{pid}.{field} must be an integer")
                    sums[pid][field] += number
        player_outcomes = []
        for pid in universe:
            row = sums[pid]
            player_outcomes.append({"player_id": pid, "minutes": row["minutes"],
                "played": row["minutes"] > 0 or row["yellow_cards"] > 0 or row["red_cards"] > 0,
                "fpl_points": row["fpl_points"]})
        result.append({"scenario_id": sid, "probability": probability, "player_outcomes": player_outcomes})
    if not math.isclose(total, 1.0, rel_tol=0, abs_tol=1e-9):
        raise CovarFixtureAggregationError("joint scenario probabilities must sum to 1")
    return result
