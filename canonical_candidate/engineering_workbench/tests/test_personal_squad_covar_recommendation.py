from __future__ import annotations

import copy
import json
from pathlib import Path

from personal_squad_engine import recommend_personal_squad
from personal_squad_covar_recommendation import recommend_personal_squad_with_covar


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "recommendation_requests.json").read_text(encoding="utf-8")
)


def request():
    payload = copy.deepcopy(FIXTURE["personal_squad"])
    payload["player_forecasts"][2]["price"] = 5.2
    payload["player_forecasts"].extend([
        {"fpl_element_id": 16, "expected_points": 7.0, "expected_minutes": 85,
         "price": 5.0, "position": "DEF", "team_id": 6},
        {"fpl_element_id": 17, "expected_points": 8.0, "expected_minutes": 90,
         "price": 5.0, "position": "DEF", "team_id": 1},
        {"fpl_element_id": 18, "expected_points": 9.0, "expected_minutes": 90,
         "price": 20.0, "position": "DEF", "team_id": 7},
    ])
    return payload


def covar_report(base):
    alternatives = base["transfer_recommendation"]["alternatives"]
    return {
        "forecast_snapshot_id": base["forecast_snapshot_id"],
        "model_version": base["model_version"],
        "mode": "REGULAR_GW",
        "free_hit_explicitly_activated": False,
        "scenario_set_id": "joint-gw12-research-v1",
        "joint_scenarios_supplied": True,
        "field_portfolio_source": "SAMPLED_MANAGER_PICK_ROWS",
        "marginal_eo_used_to_reconstruct_joint_portfolios": False,
        "decision_weight": 0,
        "production_eligible": False,
        "candidate_metrics": [
            {
                "transfer_out_id": row["transfer_out_id"],
                "transfer_in_id": row["transfer_in_id"],
                "candidate_variance": 7.2,
                "field_variance": 6.8,
                "field_relative_upside_delta": 0.06,
                "portfolio_covariance_delta": -0.15,
            }
            for row in alternatives
        ],
    }


def test_integrated_entry_point_returns_canonical_recommendation_without_report():
    payload = request()
    assert recommend_personal_squad_with_covar(payload) == recommend_personal_squad(payload)


def test_integrated_entry_point_attaches_research_metrics_to_real_ev_transfer_alternatives():
    payload = request()
    base = recommend_personal_squad(payload)
    report = covar_report(base)
    integrated = recommend_personal_squad_with_covar(payload, report)
    overlay = integrated["covar_research_overlay"]
    assert overlay["status"] == "ATTACHED_RESEARCH_ONLY"
    assert overlay["decision_weight"] == 0
    assert overlay["production_eligible"] is False
    assert overlay["ranking_changed"] is False
    assert overlay["transfer_action_changed"] is False
    assert overlay["starting_xi_changed"] is False
    assert overlay["captaincy_changed"] is False
    assert integrated["transfer_recommendation"] == base["transfer_recommendation"]
    assert integrated["squad_plan"] == base["squad_plan"]
    assert [row["transfer_in_id"] for row in overlay["candidate_metrics"]] == [
        row["transfer_in_id"] for row in base["transfer_recommendation"]["alternatives"]
    ]


def test_integrated_entry_point_rejects_mismatched_forecast_snapshot():
    payload = request()
    base = recommend_personal_squad(payload)
    report = covar_report(base)
    report["forecast_snapshot_id"] = "different-snapshot"
    try:
        recommend_personal_squad_with_covar(payload, report)
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("mismatched CoVar report was accepted")



def test_end_to_end_full_gameweek_scores_attach_to_canonical_transfer_alternatives():
    from personal_squad_covar_recommendation import recommend_personal_squad_with_full_gameweek_covar

    payload = request()
    base = recommend_personal_squad(payload)
    transfer_map = {
        (row["transfer_out_id"], row["transfer_in_id"]): f"candidate-{index}"
        for index, row in enumerate(base["transfer_recommendation"]["alternatives"])
    }
    portfolios = [
        {"portfolio_id": "baseline", "portfolio_role": "CANDIDATE"},
        *[
            {"portfolio_id": portfolio_id, "portfolio_role": "CANDIDATE"}
            for portfolio_id in transfer_map.values()
        ],
        {"portfolio_id": "field-1", "portfolio_role": "FIELD", "field_weight": 1.0},
    ]
    full_gameweek = {
        "mode": "REGULAR_GW",
        "metadata": {
            "manager_entry_ids_retained": False,
            "field_evidence_role": "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE",
        },
        "scenarios": [{"scenario_id": "s1", "probability": 1.0}],
        "portfolios": portfolios,
    }

    def score(variance, covariance, field_delta=None, *, role="CANDIDATE"):
        result = {
            "portfolio_role": role,
            "variance": variance,
            "variance_decomposition": [
                {"player_a": "1", "player_b": "1", "covariance_contribution": variance-covariance},
                {"player_a": "1", "player_b": "2", "covariance_contribution": covariance},
            ],
            "variance_decomposition_total": variance,
            "variance_decomposition_matches_total": True,
            "scenario_scores": [
                {"scenario_id": "s1", "probability": 1.0,
                 "points": field_delta if field_delta is not None else 0.0},
            ],
        }
        if field_delta is not None:
            result["field_comparison"] = {
                "expected_points_difference_vs_weighted_field": field_delta,
            }
        return result

    portfolio_results = {
        "baseline": score(10, 2),
        "field-1": score(8, 1, role="FIELD"),
    }
    for index, portfolio_id in enumerate(transfer_map.values()):
        portfolio_results[portfolio_id] = score(11 + index, 3 + index, 0.5 + index)
    scoring = {
        "mode": "REGULAR_GW",
        "input_validation_status": "VALID_FULL_GAMEWEEK",
        "production_eligible": False,
        "decision_weight": 0,
        "shared_scenario_ids": ["s1"],
        "portfolio_results": portfolio_results,
    }
    result = recommend_personal_squad_with_full_gameweek_covar(
        payload,
        full_gameweek_document=full_gameweek,
        scoring_report=scoring,
        scenario_set_id="joint-synthetic-test",
        baseline_portfolio_id="baseline",
        transfer_portfolio_ids=transfer_map,
    )
    assert result["covar_research_overlay"]["status"] == "ATTACHED_RESEARCH_ONLY"
    assert len(result["covar_research_overlay"]["candidate_metrics"]) == len(
        base["transfer_recommendation"]["alternatives"]
    )
    assert result["transfer_recommendation"] == base["transfer_recommendation"]
    assert result["squad_plan"] == base["squad_plan"]



def test_historical_covar_proxy_is_attached_without_changing_canonical_recommendation():
    from personal_squad_covar_recommendation import recommend_personal_squad_with_historical_covar

    payload = request()
    base = recommend_personal_squad(payload)
    player_ids = sorted(row["fpl_element_id"] for row in payload["player_forecasts"])
    pairs = []
    for index, left in enumerate(player_ids):
        for right in player_ids[index:]:
            pairs.append({
                "player1_id": str(left),
                "player2_id": str(right),
                "shrunk_covariance": 4.0 if left == right else 0.1,
            })
    report = {
        "status": "EXPLORATORY_ONLY",
        "model_trained": False,
        "point_in_time_status": "NOT_VERIFIED",
        "window_gameweeks": [1, 2, 3, 4, 5],
        "shrinkage": {
            "type": "diagonal",
            "parameter": 0.5,
            "positive_semidefinite_by_construction": True,
        },
    }
    integrated = recommend_personal_squad_with_historical_covar(
        payload, covariance_report=report, covariance_pairs=pairs
    )
    assert integrated["historical_covar_overlay"]["status"] == "AVAILABLE_HISTORICAL_COVAR_PROXY"
    assert integrated["historical_covar_overlay"]["decision_weight"] == 0
    assert integrated["transfer_recommendation"] == base["transfer_recommendation"]
    assert integrated["squad_plan"] == base["squad_plan"]
