from __future__ import annotations

from test_run_external_benchmark_personal_squad import run_input
from run_external_benchmark_personal_squad import run_external_benchmark_personal_squad


def _historical_context(payload):
    ids = [row["fpl_element_id"] for row in payload["provider_snapshot"]["records"]]
    pairs = []
    for index, left in enumerate(ids):
        for right in ids[index:]:
            pairs.append({
                "player1_id": str(left),
                "player2_id": str(right),
                "shrunk_covariance": 4.0 if left == right else 0.1,
            })
    return {
        "covariance_report": {
            "status": "EXPLORATORY_ONSIDE_ACTUALS_ONLY",
            "production_use": False,
            "model_trained": False,
            "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_FINAL_SCORING_AUDIT",
            "window_gameweeks": [1, 2, 3, 4, 5],
            "window_size": 5,
            "shrinkage": {
                "type": "diagonal",
                "parameter": 0.5,
                "positive_semidefinite_by_construction": True,
            },
        },
        "covariance_pairs": pairs,
    }


def test_runner_invokes_historical_covar_without_changing_ev_decision():
    payload = run_input()
    baseline = run_external_benchmark_personal_squad(payload)
    payload["historical_covariance_context"] = _historical_context(payload)
    enriched = run_external_benchmark_personal_squad(payload)

    base_recommendation = baseline["recommendation"]
    recommendation = enriched["recommendation"]
    assert recommendation["historical_covar_overlay"]["status"] == "AVAILABLE_HISTORICAL_COVAR_PROXY"
    assert recommendation["historical_covar_overlay"]["decision_weight"] == 0
    assert recommendation["historical_covar_overlay"]["production_eligible"] is False
    assert recommendation["historical_covar_overlay"]["field_comparison_status"] == "NOT_AVAILABLE_NO_JOINT_FIELD_PORTFOLIOS"
    assert recommendation["transfer_recommendation"] == base_recommendation["transfer_recommendation"]
    assert recommendation["squad_plan"] == base_recommendation["squad_plan"]


def test_runner_rejects_incomplete_historical_covariance_payload_shape():
    payload = run_input()
    payload["historical_covariance_context"] = {"covariance_report": {}}
    try:
        run_external_benchmark_personal_squad(payload)
    except ValueError as exc:
        assert "missing historical covariance fields" in str(exc)
    else:
        raise AssertionError("incomplete historical covariance context was accepted")



def test_runner_rejects_covariance_artifact_marked_for_production_use():
    payload = run_input()
    context = _historical_context(payload)
    context["covariance_report"]["production_use"] = True
    payload["historical_covariance_context"] = context
    try:
        run_external_benchmark_personal_squad(payload)
    except ValueError as exc:
        assert "must remain research-only" in str(exc)
    else:
        raise AssertionError("production-use covariance artifact was accepted")
