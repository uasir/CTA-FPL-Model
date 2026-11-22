#!/usr/bin/env python3
"""Build an M4 personal-squad product from a source-labelled forecast run.

A one-Gameweek optimiser result is diagnostic only. An actionable transfer
decision requires an explicitly validated five-plus-Gameweek HOLD-vs-TRANSFER
evaluation bound to consecutive, distinct forecast snapshots.
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


def _validated_multi_gameweek_decision(evidence: Any) -> Mapping[str, Any] | None:
    """Return an eligible multi-GW decision only when its evidence is complete."""
    if not isinstance(evidence, Mapping):
        return None
    if evidence.get("status") != "VALIDATED_FOR_M4_DECISION" or evidence.get("decision_eligible") is not True:
        return None
    horizon = evidence.get("horizon_gameweeks")
    gameweeks = evidence.get("gameweeks")
    snapshot_ids = evidence.get("source_snapshot_ids")
    decision = evidence.get("decision")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 5:
        return None
    if not isinstance(gameweeks, list) or len(gameweeks) != horizon:
        return None
    if any(isinstance(gw, bool) or not isinstance(gw, int) for gw in gameweeks):
        return None
    if gameweeks != list(range(gameweeks[0], gameweeks[0] + horizon)):
        return None
    if not isinstance(snapshot_ids, list) or len(snapshot_ids) != horizon:
        return None
    if any(not isinstance(value, str) or not value.strip() for value in snapshot_ids):
        return None
    if len(set(snapshot_ids)) != horizon:
        return None
    if not isinstance(decision, Mapping) or decision.get("action") not in {"HOLD", "TRANSFER"}:
        return None
    if decision.get("action") == "TRANSFER":
        candidate = decision.get("best_transfer")
        if not isinstance(candidate, Mapping):
            return None
    return evidence


def build_personal_squad_product(run: Mapping[str, Any]) -> dict[str, Any]:
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
    team_exposure = run.get("team_exposure_context")
    if team_exposure is not None:
        if not isinstance(team_exposure, Mapping):
            raise ConventionalSquadProductError("team_exposure_context must be an object")
        if team_exposure.get("forecast_snapshot_id") != recommendation["forecast_snapshot_id"]:
            raise ConventionalSquadProductError("team exposure must bind to the exact forecast snapshot")
        if (isinstance(team_exposure.get("horizon_size"), bool)
                or not isinstance(team_exposure.get("horizon_size"), int)
                or team_exposure["horizon_size"] < 5):
            raise ConventionalSquadProductError("team exposure must cover at least five Gameweeks")
        if team_exposure.get("decision_weight") != 0 or team_exposure.get("production_eligible") is not False:
            raise ConventionalSquadProductError("team exposure must remain diagnostic-only with zero decision weight")
        if team_exposure.get("expected_points_are_additive") is not True:
            raise ConventionalSquadProductError("team exposure must preserve additive expected-points accounting")
    blockers = list(run.get("release_blockers") or [])
    if run.get("release_eligible") is not True:
        blockers = blockers or ["Forecast source run is not release-eligible."]

    multi_gw = _validated_multi_gameweek_decision(run.get("multi_gameweek_decision_evidence"))
    forecast_horizon = recommendation.get("forecast_horizon_gameweeks", 1)
    if isinstance(forecast_horizon, bool) or not isinstance(forecast_horizon, int) or forecast_horizon < 1:
        forecast_horizon = 1
    if multi_gw is None:
        decision = {
            "basis": ("CONVENTIONAL_EXPECTED_POINTS_ONLY" if run_type == "EXTERNAL_BENCHMARK_PERSONAL_SQUAD" else "CTA_MODEL_EXPECTED_POINTS_ONLY"),
            "action": "NOT_DECISION_ELIGIBLE",
            "best_transfer": None,
            "transfer_alternatives": [],
            "current_squad_plan": dict(current_plan),
            "recommended_squad_plan": None,
            "squad_plan_state": "DIAGNOSTIC_ONLY",
            "hit_cost_points_applied": None,
            "scope": "ONE_GAMEWEEK_DIAGNOSTIC_ONLY",
            "decision_eligibility": {
                "status": "BLOCKED_INSUFFICIENT_MULTI_GAMEWEEK_EVIDENCE",
                "minimum_horizon_gameweeks": 5,
                "observed_forecast_horizon_gameweeks": forecast_horizon,
                "required_evidence": "VALIDATED_FOR_M4_DECISION with consecutive Gameweeks and distinct source snapshots",
            },
            "one_gameweek_preview": {
                "action": transfer["action"],
                "best_candidate": transfer.get("best_candidate"),
                "alternatives": transfer.get("alternatives", []),
                "proposed_squad_plan": dict(proposed_plan),
                "hit_cost_points_applied": transfer.get("hit_cost_points_applied"),
            },
        }
    else:
        evaluated = multi_gw["decision"]
        decision = {
            "basis": ("CONVENTIONAL_EXPECTED_POINTS_ONLY" if run_type == "EXTERNAL_BENCHMARK_PERSONAL_SQUAD" else "CTA_MODEL_EXPECTED_POINTS_ONLY"),
            "action": evaluated["action"],
            "best_transfer": evaluated.get("best_transfer"),
            "transfer_alternatives": evaluated.get("transfer_alternatives", []),
            "current_squad_plan": dict(current_plan),
            "recommended_squad_plan": evaluated.get("recommended_squad_plan"),
            "squad_plan_state": "VALIDATED_MULTI_GAMEWEEK_DECISION",
            "hit_cost_points_applied": evaluated.get("hit_cost_points_applied"),
            "scope": "MULTI_GAMEWEEK_HOLD_VS_TRANSFER",
            "decision_eligibility": {
                "status": "VALIDATED_FOR_M4_DECISION",
                "minimum_horizon_gameweeks": 5,
                "observed_forecast_horizon_gameweeks": multi_gw["horizon_gameweeks"],
                "gameweeks": list(multi_gw["gameweeks"]),
                "source_snapshot_ids": list(multi_gw["source_snapshot_ids"]),
            },
        }

    return {
        "product_contract_version": "1.1.0",
        "product_id": ("conventional_personal_squad" if run_type == "EXTERNAL_BENCHMARK_PERSONAL_SQUAD" else "cta_informed_personal_squad"),
        "product_family": "personal_squad",
        "product_status": "EXPLORATORY_PREVIEW",
        "release_eligible": False,
        "release_blockers": blockers,
        "target": {"season": source.get("season"), "gameweek": source.get("target_gameweek"),
                   "deadline_utc": source.get("deadline_utc"), "as_of_utc": source.get("decision_as_of_utc")},
        "forecast": {"snapshot_id": recommendation["forecast_snapshot_id"],
                     "model_version": recommendation["model_version"],
                     "horizon_gameweeks": recommendation.get("forecast_horizon_gameweeks"), "quality": recommendation["forecast_quality"], "provider": dict(provider),
                     "source_run_type": run_type},
        "manager_state": {"bank": manager.get("bank"), "free_transfers": manager.get("free_transfers"),
                          "risk_profile_recorded": manager.get("personal_risk_profile")},
        "decision": decision,
        "provenance": {
            "source_run_id": run.get("run_id"), "source_snapshot_id": source.get("snapshot_id"),
            "source_url": source.get("source_url"), "raw_sha256": source.get("raw_sha256"),
            "generated_at_utc": source.get("generated_at_utc"), "captured_at_utc": source.get("captured_at_utc"),
            "deadline_utc": source.get("deadline_utc"), "point_in_time_status": source.get("point_in_time_status"),
            "player_metadata": dict(run.get("player_metadata_provenance") or {}),
        },
        "limitations": list(recommendation["limitations"]),
        "team_exposure_context": dict(team_exposure) if team_exposure is not None else {
            "status": "NOT_ATTACHED_MULTI_GAMEWEEK_INPUTS_REQUIRED",
            "minimum_horizon_gameweeks": 5,
            "decision_weight": 0.0,
            "production_eligible": False,
        },
        "excluded_context": {"field_relative_analysis": "NOT_PART_OF_CONVENTIONAL_SCORE",
                             "covar": "NOT_PART_OF_CONVENTIONAL_SCORE",
                             "team_exposure": "DIAGNOSTIC_ONLY_NOT_PART_OF_CONVENTIONAL_SCORE",
                             "cta_model_adjustments": "NOT_APPLIED"},
    }


# Backwards-compatible alias; the adapter emits distinct conventional/CTA products.
build_conventional_squad_product = build_personal_squad_product
