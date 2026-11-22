#!/usr/bin/env python3
"""Build an M4 personal-squad product from a source-labelled forecast run.

A one-Gameweek optimiser result is diagnostic only. An actionable transfer
decision requires an explicitly validated five-plus-Gameweek HOLD-vs-TRANSFER
evaluation bound to consecutive, distinct forecast snapshots.
"""
from __future__ import annotations
from collections.abc import Mapping
from typing import Any

from multi_gameweek_squad_request_assembler import (\n    MultiGameweekSquadAssemblyError,\n    assemble_multi_gameweek_squad_diagnostics,\n)\nfrom multi_gameweek_transfer_evaluator import (
    MultiGameweekTransferError,
    evaluate_multi_gameweek_transfer_bundle,
)


class ConventionalSquadProductError(ValueError):
    """Raised when a forecast run cannot safely back the conventional product."""


SUPPORTED_RUN_TYPES = {
    "EXTERNAL_BENCHMARK_PERSONAL_SQUAD",
    "CTA_MODEL_PERSONAL_SQUAD",
}


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

    # Evaluate an explicitly supplied five-plus-GW bundle, but keep the
    # result diagnostic-only until separate forecast/outcome validation and
    # a governed M4 promotion record exist. Caller-supplied status flags are
    # never sufficient to unlock a production decision.
    multi_gw_diagnostic = None
    multi_gw_payload = run.get("multi_gameweek_forecast_payload")
    if multi_gw_payload is not None:
        manager_state = run.get("manager_context")
        current_player_metadata = run.get("current_player_metadata")
        if not isinstance(manager_state, Mapping) or not isinstance(current_player_metadata, list):
            raise ConventionalSquadProductError(
                "multi-Gameweek assembly requires source manager_context and current_player_metadata"
            )
        try:
            multi_gw_diagnostic = assemble_multi_gameweek_squad_diagnostics(
                multi_gw_payload,
                manager_state,
                list(current_plan["starting_xi"]),
                current_player_metadata,
                hit_cost_points=run.get("multi_gameweek_hit_cost_points", 4.0),
            )
        except MultiGameweekSquadAssemblyError as exc:
            raise ConventionalSquadProductError(f"multi-Gameweek assembly rejected: {exc}") from exc
    else:
        # Retain the low-level request hook for focused evaluator contract tests
        # and controlled diagnostics; the manager-aware assembler is preferred.
        multi_gw_request = run.get("multi_gameweek_transfer_request")
        if multi_gw_request is not None:
            try:
                multi_gw_diagnostic = evaluate_multi_gameweek_transfer_bundle(multi_gw_request)
            except MultiGameweekTransferError as exc:
                raise ConventionalSquadProductError(f"multi-Gameweek diagnostic rejected: {exc}") from exc

    forecast_horizon = recommendation.get("forecast_horizon_gameweeks", 1)
    if isinstance(forecast_horizon, bool) or not isinstance(forecast_horizon, int) or forecast_horizon < 1:
        forecast_horizon = 1
    decision = {
        "basis": ("CONVENTIONAL_EXPECTED_POINTS_ONLY" if run_type == "EXTERNAL_BENCHMARK_PERSONAL_SQUAD" else "CTA_MODEL_EXPECTED_POINTS_ONLY"),
        "action": "NOT_DECISION_ELIGIBLE",
        "best_transfer": None,
        "transfer_alternatives": [],
        "current_squad_plan": dict(current_plan),
        "recommended_squad_plan": None,
        "squad_plan_state": "DIAGNOSTIC_ONLY",
        "hit_cost_points_applied": None,
        "scope": "MULTI_GAMEWEEK_DIAGNOSTIC_ONLY" if multi_gw_diagnostic else "ONE_GAMEWEEK_DIAGNOSTIC_ONLY",
        "decision_eligibility": {
            "status": "BLOCKED_PENDING_INDEPENDENT_MULTI_GAMEWEEK_VALIDATION",
            "minimum_horizon_gameweeks": 5,
            "observed_forecast_horizon_gameweeks": (
                len(multi_gw_diagnostic["horizon_gameweeks"]) if multi_gw_diagnostic
                else forecast_horizon
            ),
            "required_evidence": (
                "Independently validated multi-Gameweek forecast accuracy and governed M4 promotion; "
                "a structurally valid bundle/evaluator result alone is insufficient"
            ),
        },
        "one_gameweek_preview": {
            "action": transfer["action"],
            "best_candidate": transfer.get("best_candidate"),
            "alternatives": transfer.get("alternatives", []),
            "proposed_squad_plan": dict(proposed_plan),
            "hit_cost_points_applied": transfer.get("hit_cost_points_applied"),
        },
    }

    return {
        "product_contract_version": "1.3.0",
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
        "multi_gameweek_diagnostic": multi_gw_diagnostic,
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
