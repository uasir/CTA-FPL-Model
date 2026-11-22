#!/usr/bin/env python3
"""Build an M4 personal-squad product from a source-labelled forecast run.

The M4 squad decision contract is forecast-source independent: conventional
benchmarks and the future CTA-FPL model must produce the same personal-squad
run shape. This adapter publishes the conventional product only.
"""
from __future__ import annotations
from collections.abc import Mapping
from typing import Any

class ConventionalSquadProductError(ValueError):
    """Raised when a forecast run cannot safely back the conventional product."""

SUPPORTED_RUN_TYPES = {
    "EXTERNAL_BENCHMARK_PERSONAL_SQUAD",
    "CTA_MODEL_PERSONAL_SQUAD",
}

def build_conventional_squad_product(run: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(run, Mapping):
        raise ConventionalSquadProductError("forecast run must be an object")
    run_type = run.get("run_type")
    if run_type not in SUPPORTED_RUN_TYPES:
        raise ConventionalSquadProductError("source run type is not supported by the M4 squad contract")
    recommendation = run.get("recommendation")
    if not isinstance(recommendation, Mapping) or recommendation.get("system") != "personal_squad":
        raise ConventionalSquadProductError("source run has no personal-squad recommendation")
    required = ("forecast_snapshot_id", "model_version", "forecast_quality",
                "transfer_recommendation", "current_squad_plan", "squad_plan",
                "manager_context", "limitations")
    missing = [key for key in required if key not in recommendation]
    if missing:
        raise ConventionalSquadProductError("recommendation is missing: " + ", ".join(missing))
    transfer, current_plan, proposed_plan, manager = (
        recommendation["transfer_recommendation"], recommendation["current_squad_plan"],
        recommendation["squad_plan"], recommendation["manager_context"])
    if not all(isinstance(x, Mapping) for x in (transfer, current_plan, proposed_plan, manager)):
        raise ConventionalSquadProductError("decision, squad plans and manager context must be objects")
    if transfer.get("action") not in {"HOLD", "TRANSFER"}:
        raise ConventionalSquadProductError("transfer action must be HOLD or TRANSFER")
    if len(current_plan.get("starting_xi", [])) != 11 or len(proposed_plan.get("starting_xi", [])) != 11:
        raise ConventionalSquadProductError("current and proposed plans must each contain 11 starters")
    source, provider = run.get("source_provenance"), run.get("provider_identity")
    if not isinstance(source, Mapping):
        raise ConventionalSquadProductError("source provenance is required")
    if not isinstance(provider, Mapping):
        raise ConventionalSquadProductError("provider identity is required")
    blockers = list(run.get("release_blockers") or [])
    if run.get("release_eligible") is not True:
        blockers = blockers or ["Forecast source run is not release-eligible."]
    return {
        "product_contract_version": "1.0.0",
        "product_id": ("conventional_personal_squad" if run_type == "EXTERNAL_BENCHMARK_PERSONAL_SQUAD" else "cta_informed_personal_squad"),
        "product_family": "personal_squad",
        "product_status": "EXPLORATORY_PREVIEW",
        "release_eligible": False,
        "release_blockers": blockers,
        "target": {"season": source.get("season"), "gameweek": source.get("target_gameweek"),
                   "deadline_utc": source.get("deadline_utc"), "as_of_utc": source.get("decision_as_of_utc")},
        "forecast": {"snapshot_id": recommendation["forecast_snapshot_id"],
                     "model_version": recommendation["model_version"],
                     "horizon_gameweeks": recommendation.get("forecast_horizon_gameweeks"),
                     "quality": recommendation["forecast_quality"], "provider": dict(provider),
                     "source_run_type": run_type},
        "manager_state": {"bank": manager.get("bank"), "free_transfers": manager.get("free_transfers"),
                          "risk_profile_recorded": manager.get("personal_risk_profile")},
        "decision": {
            "basis": ("CONVENTIONAL_EXPECTED_POINTS_ONLY" if run_type == "EXTERNAL_BENCHMARK_PERSONAL_SQUAD" else "CTA_MODEL_EXPECTED_POINTS_ONLY"), "action": transfer["action"],
            "best_transfer": transfer.get("best_candidate"),
            "transfer_alternatives": transfer.get("alternatives", []),
            "current_squad_plan": dict(current_plan), "recommended_squad_plan": dict(proposed_plan),
            "squad_plan_state": recommendation.get("squad_plan_state"),
            "hit_cost_points_applied": transfer.get("hit_cost_points_applied"),
            "scope": transfer.get("scope"),
        },
        "provenance": {
            "source_run_id": run.get("run_id"), "source_snapshot_id": source.get("snapshot_id"),
            "source_url": source.get("source_url"), "raw_sha256": source.get("raw_sha256"),
            "generated_at_utc": source.get("generated_at_utc"), "captured_at_utc": source.get("captured_at_utc"),
            "deadline_utc": source.get("deadline_utc"), "point_in_time_status": source.get("point_in_time_status"),
            "player_metadata": dict(run.get("player_metadata_provenance") or {}),
        },
        "limitations": list(recommendation["limitations"]),
        "excluded_context": {"field_relative_analysis": "NOT_PART_OF_CONVENTIONAL_SCORE",
                             "covar": "NOT_PART_OF_CONVENTIONAL_SCORE", "cta_model_adjustments": "NOT_APPLIED"},
    }
