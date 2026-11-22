"""Attach a fail-closed CoVar research overlay to personal-squad recommendations.

This adapter deliberately does not alter transfer actions, XI selection, EV
rankings or captaincy. Production CoVar weighting remains disabled.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence


class CoVarRecommendationIntegrationError(ValueError):
    """The CoVar report cannot safely be joined to a personal recommendation."""


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise CoVarRecommendationIntegrationError(f"{field} must be a finite number")
    return float(value)


def attach_covar_research_overlay(
    recommendation: Mapping[str, Any],
    covar_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Join candidate-level CoVar diagnostics without changing recommendations.

    The report must be bound to the same forecast snapshot/model and must
    declare explicit joint scenarios and manager-pick-derived field portfolios.
    Metrics are descriptive only; no marginal-EO reconstruction is accepted.
    """
    if not isinstance(recommendation, Mapping) or recommendation.get("system") != "personal_squad":
        raise CoVarRecommendationIntegrationError("CoVar integration is restricted to personal_squad recommendations")
    if not isinstance(covar_report, Mapping):
        raise CoVarRecommendationIntegrationError("covar_report must be an object")
    for field in ("forecast_snapshot_id", "model_version"):
        if not recommendation.get(field) or covar_report.get(field) != recommendation.get(field):
            raise CoVarRecommendationIntegrationError(f"CoVar report {field} does not match recommendation")
    if covar_report.get("mode") not in {"REGULAR_GW", "FREE_HIT"}:
        raise CoVarRecommendationIntegrationError("CoVar mode must be REGULAR_GW or explicitly activated FREE_HIT")
    if covar_report.get("mode") == "FREE_HIT" and covar_report.get("free_hit_explicitly_activated") is not True:
        raise CoVarRecommendationIntegrationError("FREE_HIT mode requires explicit activation")
    if covar_report.get("joint_scenarios_supplied") is not True:
        raise CoVarRecommendationIntegrationError("explicit joint scenarios are required")
    if covar_report.get("field_portfolio_source") != "SAMPLED_MANAGER_PICK_ROWS":
        raise CoVarRecommendationIntegrationError("field portfolios must originate from sampled manager pick rows")
    if covar_report.get("marginal_eo_used_to_reconstruct_joint_portfolios") is not False:
        raise CoVarRecommendationIntegrationError("marginal EO cannot be used to reconstruct joint portfolios")
    if covar_report.get("scenario_set_id") in (None, ""):
        raise CoVarRecommendationIntegrationError("scenario_set_id is required")
    if covar_report.get("decision_weight") != 0 or covar_report.get("production_eligible") is not False:
        raise CoVarRecommendationIntegrationError("CoVar recommendation integration is hard-disabled for production")

    transfer = recommendation.get("transfer_recommendation")
    if not isinstance(transfer, Mapping) or not isinstance(transfer.get("alternatives"), Sequence):
        raise CoVarRecommendationIntegrationError("personal recommendation must include transfer alternatives")
    alternatives = transfer["alternatives"]
    expected_pairs = set()
    for row in alternatives:
        if not isinstance(row, Mapping):
            raise CoVarRecommendationIntegrationError("transfer alternatives must be objects")
        pair = (row.get("transfer_out_id"), row.get("transfer_in_id"))
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in pair):
            raise CoVarRecommendationIntegrationError("transfer alternative IDs must be positive integers")
        if pair in expected_pairs:
            raise CoVarRecommendationIntegrationError("duplicate transfer alternative")
        expected_pairs.add(pair)

    metric_rows = covar_report.get("candidate_metrics")
    if not isinstance(metric_rows, Sequence) or isinstance(metric_rows, (str, bytes)):
        raise CoVarRecommendationIntegrationError("candidate_metrics must be a sequence")
    metrics_by_pair = {}
    for row in metric_rows:
        if not isinstance(row, Mapping):
            raise CoVarRecommendationIntegrationError("candidate CoVar metrics must be objects")
        pair = (row.get("transfer_out_id"), row.get("transfer_in_id"))
        if pair not in expected_pairs:
            raise CoVarRecommendationIntegrationError(f"CoVar metrics contain unknown transfer pair {pair}")
        if pair in metrics_by_pair:
            raise CoVarRecommendationIntegrationError(f"duplicate CoVar metrics for transfer pair {pair}")
        metrics = {}
        for field in ("candidate_variance", "field_variance", "field_relative_upside_delta", "portfolio_covariance_delta"):
            metrics[field] = _finite_number(row.get(field), field)
        if metrics["candidate_variance"] < 0 or metrics["field_variance"] < 0:
            raise CoVarRecommendationIntegrationError("variance metrics must be non-negative")
        metrics_by_pair[pair] = {
            "transfer_out_id": pair[0],
            "transfer_in_id": pair[1],
            **metrics,
        }

    missing = expected_pairs - set(metrics_by_pair)
    if missing:
        raise CoVarRecommendationIntegrationError(f"CoVar metrics missing {len(missing)} transfer alternative(s)")

    result = dict(recommendation)
    result["covar_research_overlay"] = {
        "status": "ATTACHED_RESEARCH_ONLY",
        "mode": covar_report["mode"],
        "scenario_set_id": covar_report["scenario_set_id"],
        "candidate_metrics": [
            metrics_by_pair[(row["transfer_out_id"], row["transfer_in_id"])]
            for row in alternatives
        ],
        "ranking_changed": False,
        "transfer_action_changed": False,
        "starting_xi_changed": False,
        "captaincy_changed": False,
        "decision_weight": 0.0,
        "production_eligible": False,
        "limitations": [
            "CoVar metrics are descriptive research diagnostics, not a recommendation score.",
            "No transfer, XI, captaincy or ranking decision is changed by this overlay.",
            "Historical point-in-time calibration and independent out-of-sample utility remain required before any weighting proposal.",
        ],
    }
    return result
