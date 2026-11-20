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
    assert best["transfer_out_id"] == 6
    assert best["transfer_in_id"] == 17
    assert result["squad_plan_state"] == "POST_TRANSFER"
    assert 6 in result["current_squad_plan"]["bench_order"]
    assert 6 not in result["squad_plan"]["starting_xi"]
    assert 6 not in result["squad_plan"]["bench_order"]
    assert 17 in result["squad_plan"]["starting_xi"] + result["squad_plan"]["bench_order"]
    assert set(result["squad_plan"]["starting_xi"]) == (
        set(result["current_squad_plan"]["starting_xi"]) - {3}
    ) | {17}
    same_team_replacement = next(
        candidate for candidate in result["transfer_recommendation"]["alternatives"]
        if candidate["transfer_out_id"] == 3 and candidate["transfer_in_id"] == 16
    )
    assert same_team_replacement["selling_price"] == 5.1
    assert same_team_replacement["bank_after_transfer"] == 4.7
    assert result["portfolio_risk"]["covar_used"] is False
    assert result["portfolio_risk"]["risk_profile_applied"] is False


def test_no_transfer_when_only_available_candidate_fails_hit_cost():
    payload = request()
    payload["free_transfers"] = 0
    payload["personal_preferences"] = {"hit_cost_points": 5}
    result = recommend_personal_squad(payload)
    assert result["transfer_recommendation"]["action"] == "HOLD"
    assert result["transfer_recommendation"]["hit_cost_points_applied"] == 5.0


def test_hits_can_be_set_to_zero_explicitly():
    payload = request()
    payload["free_transfers"] = 0
    payload["personal_preferences"] = {"hit_cost_points": 0}
    result = recommend_personal_squad(payload)
    assert result["transfer_recommendation"]["action"] == "TRANSFER"
    assert result["transfer_recommendation"]["hit_cost_points_applied"] == 0


def test_team_limit_and_budget_are_enforced_for_transfer_candidates():
    result = recommend_personal_squad(request())
    alternatives = result["transfer_recommendation"]["alternatives"]
    team_one_replacements = [
        candidate for candidate in alternatives if candidate["transfer_in_id"] == 17
    ]
    assert team_one_replacements
    assert all(candidate["transfer_out_id"] == 6 for candidate in team_one_replacements)
    assert all(candidate["transfer_in_id"] != 18 for candidate in alternatives)


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



def test_personal_squad_stale_snapshot_remains_exploratory():
    payload = request()
    payload["forecast_quality"]["validation_status"] = "VALIDATED"
    payload["forecast_quality"]["point_in_time_status"] = "VERIFIED"
    payload["forecast_quality"]["data_coverage"]["freshness_status"] = "STALE_OVER_24H"
    result = recommend_personal_squad(payload)
    assert result["recommendation_status"] == "EXPLORATORY_ONLY"



def test_personal_squad_validated_status_requires_fresh_verified_forecast():
    payload = request()
    payload["forecast_quality"]["validation_status"] = "VALIDATED"
    payload["forecast_quality"]["point_in_time_status"] = "VERIFIED"
    payload["forecast_quality"]["data_coverage"]["freshness_status"] = "FRESH_WITHIN_24H"
    result = recommend_personal_squad(payload)
    assert result["recommendation_status"] == "VALIDATED"


def test_current_price_floor_is_used_conservatively_when_purchase_price_is_unknown():
    payload = request()
    for row in payload["squad_snapshot"]:
        row["selling_price_floor"] = payload["player_forecasts"][
            next(i for i, forecast in enumerate(payload["player_forecasts"])
                 if forecast["fpl_element_id"] == row["fpl_element_id"])
        ]["price"]
        row.pop("purchase_price")
    result = recommend_personal_squad(payload)
    assert result["transfer_recommendation"]["selling_price_basis"] == "CONSERVATIVE_CURRENT_PRICE_FLOOR"
    assert any(
        candidate["selling_price"] <= next(
            player["price"] for player in payload["player_forecasts"]
            if player["fpl_element_id"] == candidate["transfer_out_id"]
        )
        for candidate in result["transfer_recommendation"]["alternatives"]
    )


def test_bench_upgrade_without_starting_xi_gain_is_not_recommended():
    payload = request()
    for player in payload["player_forecasts"]:
        if player["fpl_element_id"] in {16, 17, 18}:
            player["expected_points"] = 2.0
    result = recommend_personal_squad(payload)
    assert result["transfer_recommendation"]["action"] == "HOLD"
    assert all(
        candidate["starting_xi_expected_points_delta"] <= 0
        for candidate in result["transfer_recommendation"]["alternatives"]
    )


def test_goalkeeper_is_never_a_transfer_candidate():
    result = recommend_personal_squad(request())
    assert all(
        candidate["transfer_out_id"] not in {1, 2}
        for candidate in result["transfer_recommendation"]["alternatives"]
    )


def test_bench_to_starting_xi_upgrade_is_scored_on_starting_xi_gain():
    result = recommend_personal_squad(request())
    best = result["transfer_recommendation"]["best_candidate"]
    assert best["transfer_out_id"] == 6
    assert best["starting_xi_expected_points_delta"] > 0
    assert best["starting_xi_expected_points_delta"] == 8.0 - 3.6


def test_post_transfer_plan_keeps_the_designated_starting_goalkeeper():
    payload = request()
    payload["starting_xi"] = [2, 3, 4, 5, 7, 8, 10, 12, 13, 14, 15]
    payload["player_forecasts"][0]["expected_points"] = 12.0
    result = recommend_personal_squad(payload)
    assert result["transfer_recommendation"]["action"] == "TRANSFER"
    assert 2 in result["current_squad_plan"]["starting_xi"]
    assert 2 in result["squad_plan"]["starting_xi"]
    assert 1 not in result["squad_plan"]["starting_xi"]


def test_bench_transfer_preserves_emergency_order_and_moves_displaced_starter_into_outgoing_slot():
    result = recommend_personal_squad(request())
    assert result["transfer_recommendation"]["action"] == "TRANSFER"
    outgoing = result["transfer_recommendation"]["best_candidate"]["transfer_out_id"]
    assert outgoing in result["current_squad_plan"]["bench_order"]
    displaced = next(
        player_id for player_id in result["current_squad_plan"]["starting_xi"]
        if player_id not in result["squad_plan"]["starting_xi"]
    )
    expected_bench = [
        displaced if player_id == outgoing else player_id
        for player_id in result["current_squad_plan"]["bench_order"]
    ]
    assert result["squad_plan"]["bench_order"] == expected_bench


def test_starter_transfer_keeps_existing_emergency_bench_order():
    payload = request()
    payload["starting_xi"] = [1, 3, 4, 5, 6, 8, 9, 10, 13, 14, 15]
    result = recommend_personal_squad(payload)
    if result["transfer_recommendation"]["action"] == "TRANSFER":
        outgoing = result["transfer_recommendation"]["best_candidate"]["transfer_out_id"]
        if outgoing in result["current_squad_plan"]["starting_xi"]:
            assert result["squad_plan"]["bench_order"] == result["current_squad_plan"]["bench_order"]
