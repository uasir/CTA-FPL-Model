import copy
import json
import subprocess
from pathlib import Path

import pytest

from personal_squad_engine import recommend_personal_squad
from recommendation_contracts import RecommendationContractError


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


def test_personal_squad_builds_legal_xi_and_transfer_recommendation():
    result = recommend_personal_squad(request())
    assert result["system"] == "personal_squad"
    assert result["recommendation_status"] == "EXPLORATORY_ONLY"
    assert result["squad_plan"]["formation"] == "4-3-3"
    assert len(result["squad_plan"]["starting_xi"]) == 11
    assert result["squad_plan"]["captain"] in result["squad_plan"]["starting_xi"]
    assert result["squad_plan"]["vice_captain"] in result["squad_plan"]["starting_xi"]
    assert result["squad_plan"]["reserve_goalkeeper"] not in result["squad_plan"]["starting_xi"]
    assert len(result["squad_plan"]["bench_order"]) == 3
    assert result["transfer_recommendation"]["action"] == "TRANSFER"
    best = result["transfer_recommendation"]["best_candidate"]
    assert best["transfer_out_id"] == 3
    assert best["transfer_in_id"] == 16
    assert best["selling_price"] == 5.1
    assert best["bank_after_transfer"] == 4.7
    assert result["portfolio_risk"]["covar_used"] is False
    assert result["portfolio_risk"]["risk_profile_applied"] is False


def test_no_transfer_when_only_available_candidate_fails_hit_cost():
    payload = request()
    payload["free_transfers"] = 0
    result = recommend_personal_squad(payload)
    assert result["transfer_recommendation"]["action"] == "HOLD"
    assert result["transfer_recommendation"]["hit_cost_points_applied"] == 4.0


def test_hits_can_be_set_to_zero_explicitly():
    payload = request()
    payload["free_transfers"] = 0
    payload["personal_preferences"] = {"hit_cost_points": 0}
    result = recommend_personal_squad(payload)
    assert result["transfer_recommendation"]["action"] == "TRANSFER"
    assert result["transfer_recommendation"]["hit_cost_points_applied"] == 0


def test_team_limit_and_budget_are_enforced_for_transfer_candidates():
    result = recommend_personal_squad(request())
    incoming_ids = {candidate["transfer_in_id"] for candidate in result["transfer_recommendation"]["alternatives"]}
    assert 17 not in incoming_ids
    assert 18 not in incoming_ids


def test_invalid_formation_and_starting_xi_are_rejected():
    payload = request()
    payload["formation"] = "2-4-4"
    with pytest.raises(RecommendationContractError, match="legal FPL"):
        recommend_personal_squad(payload)

    payload = request()
    payload["starting_xi"] = [1] * 11
    with pytest.raises(RecommendationContractError, match="11 unique"):
        recommend_personal_squad(payload)


def test_python_and_javascript_personal_squad_outputs_are_identical():
    test_dir = Path(__file__).parent
    runner = test_dir / "js" / "emit_personal_squad_outputs.mjs"
    completed = subprocess.run(
        ["node", str(runner)],
        check=True,
        capture_output=True,
        text=True,
    )
    javascript = json.loads(completed.stdout)
    python = recommend_personal_squad(request())
    assert javascript == python
