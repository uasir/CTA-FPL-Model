"""Integrated personal-squad recommendation entry point with optional CoVar overlay."""
from __future__ import annotations

from typing import Any, Mapping

from personal_squad_engine import recommend_personal_squad
from m4_covar_recommendation_integration import attach_covar_research_overlay
from m4_covar_recommendation_report_adapter import build_personal_recommendation_covar_report


def recommend_personal_squad_with_covar(
    payload: Mapping[str, Any],
    covar_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run canonical personal recommendations and optionally attach diagnostics."""
    recommendation = recommend_personal_squad(payload)
    if covar_report is None:
        return recommendation
    return attach_covar_research_overlay(recommendation, covar_report)


def recommend_personal_squad_with_full_gameweek_covar(
    payload: Mapping[str, Any],
    *,
    full_gameweek_document: Mapping[str, Any],
    scoring_report: Mapping[str, Any],
    scenario_set_id: str,
    baseline_portfolio_id: str,
    transfer_portfolio_ids: Mapping[tuple[int, int], str],
    free_hit_explicitly_activated: bool = False,
) -> dict[str, Any]:
    """End-to-end entry point from full-GW portfolio scoring to recommendation.

    The caller supplies the exact portfolio IDs used to score each transfer
    alternative. The canonical EV recommendation is computed first; CoVar is
    then translated into candidate diagnostics and attached without changing
    any recommendation decision.
    """
    recommendation = recommend_personal_squad(payload)
    report = build_personal_recommendation_covar_report(
        full_gameweek_document=full_gameweek_document,
        scoring_report=scoring_report,
        forecast_snapshot_id=recommendation["forecast_snapshot_id"],
        model_version=recommendation["model_version"],
        scenario_set_id=scenario_set_id,
        baseline_portfolio_id=baseline_portfolio_id,
        transfer_portfolio_ids=transfer_portfolio_ids,
        free_hit_explicitly_activated=free_hit_explicitly_activated,
    )
    return attach_covar_research_overlay(recommendation, report)
