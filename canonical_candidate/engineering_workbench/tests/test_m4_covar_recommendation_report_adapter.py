from __future__ import annotations

import pytest

from m4_covar_recommendation_report_adapter import (
    CoVarRecommendationReportAdapterError,
    build_personal_recommendation_covar_report,
)
from m4_covar_recommendation_integration import attach_covar_research_overlay


def inputs(mode="REGULAR_GW"):
    document = {
        "mode": mode,
        "metadata": {
            "manager_entry_ids_retained": False,
            "field_evidence_role": "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE",
        },
        "scenarios": [{"scenario_id": "s1", "probability": 0.5}, {"scenario_id": "s2", "probability": 0.5}],
        "portfolios": [
            {"portfolio_id": "baseline", "portfolio_role": "CANDIDATE"},
            {"portfolio_id": "transfer-a", "portfolio_role": "CANDIDATE"},
            {"portfolio_id": "field-1", "portfolio_role": "FIELD", "field_weight": 0.6},
            {"portfolio_id": "field-2", "portfolio_role": "FIELD", "field_weight": 0.4},
        ],
    }
    def result(variance, diagonal, offdiag, field_delta=None):
        row = {
            "variance": variance,
            "variance_decomposition": [
                {"player_a": "1", "player_b": "1", "covariance_contribution": diagonal},
                {"player_a": "1", "player_b": "2", "covariance_contribution": offdiag},
            ],
        }
        if field_delta is not None:
            row["field_comparison"] = {
                "expected_points_difference_vs_weighted_field": field_delta,
            }
        return row
    scoring = {
        "mode": mode,
        "input_validation_status": "VALID_FULL_GAMEWEEK",
        "production_eligible": False,
        "decision_weight": 0,
        "portfolio_results": {
            "baseline": result(10, 8, 2),
            "transfer-a": result(12, 8, 4, 1.25),
            "field-1": result(6, 5, 1),
            "field-2": result(8, 6, 2),
        },
    }
    return document, scoring


def test_builds_candidate_metrics_from_full_gameweek_scorer_and_field_portfolios():
    document, scoring = inputs()
    report = build_personal_recommendation_covar_report(
        full_gameweek_document=document,
        scoring_report=scoring,
        forecast_snapshot_id="snap-1",
        model_version="model-1",
        scenario_set_id="joint-scenarios-1",
        baseline_portfolio_id="baseline",
        transfer_portfolio_ids={(6, 17): "transfer-a"},
    )
    metric = report["candidate_metrics"][0]
    assert metric["candidate_variance"] == 12
    assert metric["field_variance"] == pytest.approx(6.8)
    assert metric["field_relative_upside_delta"] == 1.25
    assert metric["portfolio_covariance_delta"] == 2
    assert report["field_portfolio_source"] == "SAMPLED_MANAGER_PICK_ROWS"
    assert report["decision_weight"] == 0
    recommendation = {
        "system": "personal_squad",
        "forecast_snapshot_id": "snap-1",
        "model_version": "model-1",
        "transfer_recommendation": {"alternatives": [{"transfer_out_id": 6, "transfer_in_id": 17}]},
    }
    attached = attach_covar_research_overlay(recommendation, report)
    assert attached["covar_research_overlay"]["candidate_metrics"][0]["portfolio_covariance_delta"] == 2
    assert attached["covar_research_overlay"]["ranking_changed"] is False


def test_rejects_missing_field_portfolios():
    document, scoring = inputs()
    document["portfolios"] = [row for row in document["portfolios"] if row["portfolio_role"] != "FIELD"]
    with pytest.raises(CoVarRecommendationReportAdapterError, match="field portfolios"):
        build_personal_recommendation_covar_report(
            full_gameweek_document=document, scoring_report=scoring,
            forecast_snapshot_id="snap-1", model_version="model-1",
            scenario_set_id="joint-1", baseline_portfolio_id="baseline",
            transfer_portfolio_ids={(6, 17): "transfer-a"},
        )


def test_free_hit_requires_explicit_activation():
    document, scoring = inputs("FREE_HIT")
    with pytest.raises(CoVarRecommendationReportAdapterError, match="explicit activation"):
        build_personal_recommendation_covar_report(
            full_gameweek_document=document, scoring_report=scoring,
            forecast_snapshot_id="snap-1", model_version="model-1",
            scenario_set_id="joint-1", baseline_portfolio_id="baseline",
            transfer_portfolio_ids={(6, 17): "transfer-a"},
        )


def test_rejects_non_research_scoring_report():
    document, scoring = inputs()
    scoring["production_eligible"] = True
    with pytest.raises(CoVarRecommendationReportAdapterError, match="research-only"):
        build_personal_recommendation_covar_report(
            full_gameweek_document=document, scoring_report=scoring,
            forecast_snapshot_id="snap-1", model_version="model-1",
            scenario_set_id="joint-1", baseline_portfolio_id="baseline",
            transfer_portfolio_ids={(6, 17): "transfer-a"},
        )
