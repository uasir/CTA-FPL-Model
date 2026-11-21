from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from personal_squad_engine import recommend_personal_squad
from squad_decision_context import SquadDecisionContextError, attach_squad_decision_context


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "recommendation_requests.json").read_text(encoding="utf-8")
)


def recommendation():
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
    return recommend_personal_squad(payload)


def candidate_rows(base, **metrics):
    rows = [{"candidate_type": "HOLD", "transfer_out_id": None, "transfer_in_id": None, **metrics}]
    rows.extend({
        "candidate_type": "TRANSFER",
        "transfer_out_id": item["transfer_out_id"],
        "transfer_in_id": item["transfer_in_id"],
        **metrics,
    } for item in base["transfer_recommendation"]["alternatives"])
    return rows


def field_artifact(base):
    return {
        "artifact_id": "field-gw11-0900z",
        "forecast_snapshot_id": base["forecast_snapshot_id"],
        "model_version": base["model_version"],
        "target_gameweek": 11,
        "captured_at_utc": "2026-11-20T09:30:00Z",
        "source_type": "OBSERVED_EO",
        "sample_size": 10000,
        "coverage_fraction": 0.97,
        "missingness_reported": True,
        "uncertainty_note": "Sampled field estimate; not a census.",
        "candidate_metrics": candidate_rows(
            base, field_relative_expected_points_delta=0.2, field_relative_upside_delta=0.04
        ),
    }


def covar_artifact(base):
    return {
        "artifact_id": "covar-gw11-historical-v1",
        "forecast_snapshot_id": base["forecast_snapshot_id"],
        "model_version": base["model_version"],
        "target_gameweek": 11,
        "captured_at_utc": "2026-11-20T09:30:00Z",
        "method": "HISTORICAL_PLAYER_COVARIANCE_PROXY",
        "decision_weight": 0,
        "production_eligible": False,
        "marginal_eo_used_to_reconstruct_joint_portfolios": False,
        "candidate_metrics": candidate_rows(
            base, candidate_variance=7.2, field_variance=6.8,
            field_relative_upside_delta=0.04, portfolio_covariance_delta=-0.15
        ),
    }


def attach(base, field=None, covar=None):
    return attach_squad_decision_context(
        recommendation=base,
        field_relative_context=field,
        covar_context=covar,
        target_gameweek=11,
        as_of_utc="2026-11-20T10:00:00Z",
        deadline_utc="2026-11-21T11:00:00Z",
    )


def test_field_and_covar_attach_inside_squad_recommendation_without_changing_ev_decision():
    base = recommendation()
    result = attach(base, field_artifact(base), covar_artifact(base))
    assert result["field_relative_context"]["status"] == "ATTACHED_CONTEXT_ONLY"
    assert result["covar_research_context"]["status"] == "ATTACHED_RESEARCH_ONLY"
    assert len(result["field_relative_context"]["candidate_metrics"]) == len(base["transfer_recommendation"]["alternatives"]) + 1
    assert len(result["covar_research_context"]["candidate_metrics"]) == len(base["transfer_recommendation"]["alternatives"]) + 1
    for key in ("transfer_recommendation", "current_squad_plan", "squad_plan", "squad_plan_state"):
        assert result[key] == base[key]
    assert result["covar_research_context"]["decision_weight"] == 0
    assert result["covar_research_context"]["production_eligible"] is False


def test_field_artifact_with_wrong_snapshot_is_rejected():
    base = recommendation()
    field = field_artifact(base)
    field["forecast_snapshot_id"] = "wrong"
    with pytest.raises(SquadDecisionContextError, match="forecast_snapshot_id"):
        attach(base, field=field)


def test_field_artifact_after_deadline_is_rejected():
    base = recommendation()
    field = field_artifact(base)
    field["captured_at_utc"] = "2026-11-21T11:00:00Z"
    with pytest.raises(SquadDecisionContextError, match="strictly pre-deadline"):
        attach(base, field=field)


def test_incomplete_candidate_coverage_is_rejected():
    base = recommendation()
    field = field_artifact(base)
    field["candidate_metrics"].pop()
    with pytest.raises(SquadDecisionContextError, match="missing 1 candidate"):
        attach(base, field=field)


def test_covar_cannot_receive_production_weight():
    base = recommendation()
    covar = covar_artifact(base)
    covar["decision_weight"] = 0.1
    with pytest.raises(SquadDecisionContextError, match="research-only"):
        attach(base, covar=covar)


def test_marginal_eo_cannot_reconstruct_joint_portfolios():
    base = recommendation()
    covar = covar_artifact(base)
    covar["marginal_eo_used_to_reconstruct_joint_portfolios"] = True
    with pytest.raises(SquadDecisionContextError, match="marginal EO"):
        attach(base, covar=covar)


def test_context_artifact_cannot_be_from_future_of_decision():
    base = recommendation()
    field = field_artifact(base)
    field["captured_at_utc"] = "2026-11-20T10:01:00Z"
    with pytest.raises(SquadDecisionContextError, match="later than decision"):
        attach(base, field=field)
