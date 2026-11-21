from __future__ import annotations

import copy
import pytest

from m4_covar_recommendation_integration import (
    CoVarRecommendationIntegrationError,
    attach_covar_research_overlay,
)


def recommendation():
    return {
        "system": "personal_squad",
        "forecast_snapshot_id": "gw12-snapshot",
        "model_version": "baseline-v1",
        "transfer_recommendation": {
            "action": "TRANSFER",
            "best_candidate": {"transfer_out_id": 4, "transfer_in_id": 19},
            "alternatives": [
                {"transfer_out_id": 4, "transfer_in_id": 19, "net_expected_points_gain": 1.4},
                {"transfer_out_id": 7, "transfer_in_id": 22, "net_expected_points_gain": 0.8},
            ],
        },
        "squad_plan": {"starting_xi": [1, 2, 3]},
    }


def report():
    return {
        "forecast_snapshot_id": "gw12-snapshot",
        "model_version": "baseline-v1",
        "mode": "REGULAR_GW",
        "free_hit_explicitly_activated": False,
        "scenario_set_id": "joint-gw12-v1",
        "joint_scenarios_supplied": True,
        "field_portfolio_source": "SAMPLED_MANAGER_PICK_ROWS",
        "marginal_eo_used_to_reconstruct_joint_portfolios": False,
        "decision_weight": 0,
        "production_eligible": False,
        "candidate_metrics": [
            {"transfer_out_id": 4, "transfer_in_id": 19, "candidate_variance": 8.2,
             "field_variance": 7.1, "field_relative_upside_delta": 0.12, "portfolio_covariance_delta": -0.4},
            {"transfer_out_id": 7, "transfer_in_id": 22, "candidate_variance": 7.8,
             "field_variance": 7.1, "field_relative_upside_delta": 0.08, "portfolio_covariance_delta": -0.2},
        ],
    }


def test_attaches_research_overlay_without_changing_recommendation():
    base = recommendation()
    original = copy.deepcopy(base)
    result = attach_covar_research_overlay(base, report())
    assert result["covar_research_overlay"]["status"] == "ATTACHED_RESEARCH_ONLY"
    assert result["covar_research_overlay"]["decision_weight"] == 0
    assert result["covar_research_overlay"]["production_eligible"] is False
    assert result["covar_research_overlay"]["ranking_changed"] is False
    assert result["transfer_recommendation"] == original["transfer_recommendation"]
    assert result["squad_plan"] == original["squad_plan"]
    assert "covar_research_overlay" not in base


@pytest.mark.parametrize("field,value,message", [
    ("forecast_snapshot_id", "other-snapshot", "does not match"),
    ("model_version", "other-model", "does not match"),
    ("mode", "UNKNOWN", "mode must be"),
    ("joint_scenarios_supplied", False, "joint scenarios"),
    ("field_portfolio_source", "MARGINAL_EO", "sampled manager pick rows"),
    ("marginal_eo_used_to_reconstruct_joint_portfolios", True, "marginal EO"),
    ("decision_weight", 0.1, "hard-disabled"),
    ("production_eligible", True, "hard-disabled"),
])
def test_fails_closed_on_invalid_report_policy(field, value, message):
    bad = report()
    bad[field] = value
    with pytest.raises(CoVarRecommendationIntegrationError, match=message):
        attach_covar_research_overlay(recommendation(), bad)


def test_free_hit_requires_explicit_activation():
    bad = report()
    bad["mode"] = "FREE_HIT"
    bad["free_hit_explicitly_activated"] = False
    with pytest.raises(CoVarRecommendationIntegrationError, match="explicit activation"):
        attach_covar_research_overlay(recommendation(), bad)


def test_rejects_missing_or_unknown_candidate_metrics():
    bad = report()
    bad["candidate_metrics"].pop()
    with pytest.raises(CoVarRecommendationIntegrationError, match="missing 1"):
        attach_covar_research_overlay(recommendation(), bad)
    bad = report()
    bad["candidate_metrics"][0]["transfer_in_id"] = 999
    with pytest.raises(CoVarRecommendationIntegrationError, match="unknown transfer pair"):
        attach_covar_research_overlay(recommendation(), bad)


def test_rejects_duplicate_candidate_metrics_and_invalid_variance():
    bad = report()
    bad["candidate_metrics"].append(copy.deepcopy(bad["candidate_metrics"][0]))
    with pytest.raises(CoVarRecommendationIntegrationError, match="duplicate CoVar metrics"):
        attach_covar_research_overlay(recommendation(), bad)
    bad = report()
    bad["candidate_metrics"][0]["candidate_variance"] = -1
    with pytest.raises(CoVarRecommendationIntegrationError, match="non-negative"):
        attach_covar_research_overlay(recommendation(), bad)


def test_rejects_general_market_recommendations():
    bad = recommendation()
    bad["system"] = "general_market"
    with pytest.raises(CoVarRecommendationIntegrationError, match="restricted to personal_squad"):
        attach_covar_research_overlay(bad, report())
