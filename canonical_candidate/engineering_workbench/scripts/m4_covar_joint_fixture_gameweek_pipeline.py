#!/usr/bin/env python3
"""Compose explicit joint fixture scenarios and aggregate them to Gameweek rows."""
from __future__ import annotations
from typing import Any, Mapping, Sequence
from m4_covar_fixture_to_gameweek_aggregator import aggregate_fixture_scenarios
from m4_covar_joint_fixture_scenario_composer import compose_joint_fixture_scenarios

def build_joint_gameweek_scenarios(
    *,
    player_ids: Sequence[str],
    fixture_catalogs: Mapping[str, Sequence[Mapping[str, Any]]],
    joint_scenarios: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return full-GW outcomes using only explicitly supplied joint scenarios."""
    composed = compose_joint_fixture_scenarios(
        fixture_catalogs=fixture_catalogs,
        joint_scenarios=joint_scenarios,
    )
    fixture_player_ids = {
        fixture_id: list(catalog[0]["player_outcomes"][i]["player_id"] for i in range(len(catalog[0]["player_outcomes"])))
        for fixture_id, catalog in fixture_catalogs.items()
    }
    return aggregate_fixture_scenarios(
        player_ids=player_ids,
        fixture_player_ids=fixture_player_ids,
        joint_scenarios=composed,
    )
