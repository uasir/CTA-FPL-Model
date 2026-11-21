"""Translate full-Gameweek scorer output into personal recommendation CoVar metrics."""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence


class CoVarRecommendationReportAdapterError(ValueError):
    """Scoring output cannot be safely translated into recommendation metrics."""


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise CoVarRecommendationReportAdapterError(f"{label} must be finite numeric")
    return float(value)


def _off_diagonal_covariance(result: Mapping[str, Any], label: str) -> float:
    rows = result.get("variance_decomposition")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise CoVarRecommendationReportAdapterError(f"{label} variance_decomposition is required")
    total = 0.0
    for row in rows:
        if not isinstance(row, Mapping):
            raise CoVarRecommendationReportAdapterError(f"{label} variance decomposition rows must be objects")
        value = _number(row.get("covariance_contribution"), f"{label}.covariance_contribution")
        if str(row.get("player_a")) != str(row.get("player_b")):
            total += value
    return total


def build_personal_recommendation_covar_report(
    *,
    full_gameweek_document: Mapping[str, Any],
    scoring_report: Mapping[str, Any],
    forecast_snapshot_id: str,
    model_version: str,
    scenario_set_id: str,
    baseline_portfolio_id: str,
    transfer_portfolio_ids: Mapping[tuple[int, int], str],
    free_hit_explicitly_activated: bool = False,
) -> dict[str, Any]:
    """Build candidate CoVar diagnostics from the actual full-GW scoring report.

    transfer_portfolio_ids maps (transfer_out_id, transfer_in_id) to the
    corresponding candidate portfolio IDs scored in the same full-GW run.
    Baseline-relative covariance is the change in the sum of off-diagonal
    covariance contributions, not a generic variance proxy.
    """
    if not isinstance(full_gameweek_document, Mapping) or not isinstance(scoring_report, Mapping):
        raise CoVarRecommendationReportAdapterError("full Gameweek document and scoring report are required")
    mode = full_gameweek_document.get("mode", "REGULAR_GW")
    if mode not in {"REGULAR_GW", "FREE_HIT"} or scoring_report.get("mode") != mode:
        raise CoVarRecommendationReportAdapterError("full Gameweek and scoring modes must match")
    if mode == "FREE_HIT" and free_hit_explicitly_activated is not True:
        raise CoVarRecommendationReportAdapterError("FREE_HIT report requires explicit activation")
    if scoring_report.get("production_eligible") is not False or scoring_report.get("decision_weight") != 0:
        raise CoVarRecommendationReportAdapterError("scoring report must remain research-only")
    if not forecast_snapshot_id or not model_version or not scenario_set_id or not baseline_portfolio_id:
        raise CoVarRecommendationReportAdapterError("forecast, model, scenario and baseline identifiers are required")

    metadata = full_gameweek_document.get("metadata")
    portfolios = full_gameweek_document.get("portfolios")
    scenarios = full_gameweek_document.get("scenarios")
    results = scoring_report.get("portfolio_results")
    if not isinstance(metadata, Mapping) or not isinstance(portfolios, Sequence) or not isinstance(scenarios, Sequence) or not scenarios or not isinstance(results, Mapping):
        raise CoVarRecommendationReportAdapterError("full Gameweek metadata, portfolios, scenarios and scoring results are required")
    if metadata.get("manager_entry_ids_retained") is not False:
        raise CoVarRecommendationReportAdapterError("full Gameweek document must confirm manager IDs were discarded")
    if metadata.get("field_evidence_role") != "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE":
        raise CoVarRecommendationReportAdapterError("field portfolios must originate from pre-deadline sampled manager picks")
    field_rows = [row for row in portfolios if isinstance(row, Mapping) and row.get("portfolio_role") == "FIELD"]
    if not field_rows:
        raise CoVarRecommendationReportAdapterError("explicit manager-pick-derived field portfolios are required")
    field_weight_total = sum(_number(row.get("field_weight"), "field_weight") for row in field_rows)
    if not math.isclose(field_weight_total, 1.0, rel_tol=0, abs_tol=1e-8):
        raise CoVarRecommendationReportAdapterError("field portfolio weights must sum to one")
    field_ids = {str(row.get("portfolio_id")) for row in field_rows}
    if any(portfolio_id not in results for portfolio_id in field_ids):
        raise CoVarRecommendationReportAdapterError("scoring report is missing a field portfolio result")
    baseline = results.get(baseline_portfolio_id)
    if not isinstance(baseline, Mapping):
        raise CoVarRecommendationReportAdapterError("baseline portfolio result is missing")
    baseline_covariance = _off_diagonal_covariance(baseline, "baseline")

    weighted_field_variance = sum(
        _number(row.get("field_weight"), "field_weight")
        * _number(results[str(row["portfolio_id"])].get("variance"), "field variance")
        for row in field_rows
    )
    if weighted_field_variance < 0:
        raise CoVarRecommendationReportAdapterError("weighted field variance must be non-negative")

    candidate_metrics = []
    for pair, portfolio_id in transfer_portfolio_ids.items():
        if (not isinstance(pair, tuple) or len(pair) != 2
                or any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in pair)):
            raise CoVarRecommendationReportAdapterError("transfer map keys must be positive integer (out, in) tuples")
        candidate = results.get(str(portfolio_id))
        if not isinstance(candidate, Mapping):
            raise CoVarRecommendationReportAdapterError(f"candidate portfolio result missing: {portfolio_id}")
        if candidate.get("field_comparison") is None:
            raise CoVarRecommendationReportAdapterError(f"candidate {portfolio_id} lacks field comparison")
        field_delta = _number(
            candidate["field_comparison"].get("expected_points_difference_vs_weighted_field"),
            "field relative upside delta",
        )
        variance = _number(candidate.get("variance"), "candidate variance")
        covariance_delta = _off_diagonal_covariance(candidate, str(portfolio_id)) - baseline_covariance
        if variance < 0:
            raise CoVarRecommendationReportAdapterError("candidate variance must be non-negative")
        candidate_metrics.append({
            "transfer_out_id": pair[0],
            "transfer_in_id": pair[1],
            "candidate_variance": variance,
            "field_variance": weighted_field_variance,
            "field_relative_upside_delta": field_delta,
            "portfolio_covariance_delta": covariance_delta,
            "candidate_portfolio_id": str(portfolio_id),
            "baseline_portfolio_id": baseline_portfolio_id,
        })

    if not candidate_metrics:
        raise CoVarRecommendationReportAdapterError("at least one transfer candidate mapping is required")
    return {
        "forecast_snapshot_id": forecast_snapshot_id,
        "model_version": model_version,
        "mode": mode,
        "free_hit_explicitly_activated": bool(free_hit_explicitly_activated),
        "scenario_set_id": scenario_set_id,
        "joint_scenarios_supplied": True,
        "field_portfolio_source": "SAMPLED_MANAGER_PICK_ROWS",
        "marginal_eo_used_to_reconstruct_joint_portfolios": False,
        "candidate_metrics": candidate_metrics,
        "baseline_portfolio_id": baseline_portfolio_id,
        "field_portfolio_count": len(field_rows),
        "scoring_status": scoring_report.get("input_validation_status"),
        "decision_weight": 0.0,
        "production_eligible": False,
        "metric_definitions": {
            "candidate_variance": "Full-Gameweek candidate portfolio point variance across shared joint scenarios.",
            "field_variance": "Field-weighted mean of individual sampled manager portfolio variances.",
            "field_relative_upside_delta": "Candidate expected points minus weighted field expected points from the scorer's explicit field comparison.",
            "portfolio_covariance_delta": "Candidate off-diagonal covariance contribution sum minus the baseline portfolio's off-diagonal covariance contribution sum.",
        },
    }
