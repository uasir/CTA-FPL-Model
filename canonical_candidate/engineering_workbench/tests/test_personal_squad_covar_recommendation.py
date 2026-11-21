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
