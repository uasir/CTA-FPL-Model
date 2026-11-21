"""Integrated personal-squad recommendation entry point with optional CoVar overlay."""
from __future__ import annotations

from typing import Any, Mapping

from personal_squad_engine import recommend_personal_squad
from m4_covar_recommendation_integration import attach_covar_research_overlay


def recommend_personal_squad_with_covar(
    payload: Mapping[str, Any],
    covar_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the canonical personal recommender and optionally attach CoVar research.

    The canonical EV/EO recommendation is always produced first and remains
    authoritative. If a CoVar report is supplied, the fail-closed adapter
    validates and attaches descriptive candidate metrics only.
    """
    recommendation = recommend_personal_squad(payload)
    if covar_report is None:
        return recommendation
    return attach_covar_research_overlay(recommendation, covar_report)
