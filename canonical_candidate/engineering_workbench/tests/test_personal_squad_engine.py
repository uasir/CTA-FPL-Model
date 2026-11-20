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





def request_with_cta():
    payload = request()
    for player in payload["player_forecasts"]:
        player["cta"] = {
            "identity_verified": True,
            "identity_status": "VERIFIED_IDENTITY_AND_PRIOR_CTA_HISTORY",
            "coverage_status": "HAS_PRIOR_VERIFIED_HISTORY",
            "source_snapshot_as_of": "2026-11-10T12:21:18+00:00",
            "composite": None,
            "decision_use_status": "RESEARCH_ONLY_NOT_IN_BASELINE",
            "target_gameweek": 11,
            "fixtures": [{
                "fixture_id": "501",
                "prior_matches_count": 3,
                "prior3_matches_count": 3,
                "snapshot_available_as_of_deadline": True,
                "identity_verified": True,
                "features": {
                    "cta_prior3_matches_shots_avg": 2.5,
                    "cta_prior3_matches_key_passes_avg": 1.2,
                    "cta_prior3_matches_tracked_xg_sum_avg": 0.3,
                },
            }],
        }
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
    payload["personal_preferences"] = {"hit_cost_points": 9}
    result = recommend_personal_squad(payload)
    assert result["transfer_recommendation"]["action"] == "HOLD"
    assert result["transfer_recommendation"]["hit_cost_points_applied"] == 9.0


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


def test_bench_only_upgrade_is_not_misreported_as_starting_xi_gain():
    payload = copy.deepcopy(FIXTURE["personal_squad"])
    payload["player_forecasts"].append({
        "fpl_element_id": 19, "expected_points": 3.8, "expected_minutes": 80,
        "price": 6.0, "position": "MID", "team_id": 6,
    })
    result = recommend_personal_squad(payload)
    assert result["transfer_recommendation"]["action"] == "HOLD"
    candidate = next(
        row for row in result["transfer_recommendation"]["alternatives"]
        if row["transfer_out_id"] == 12 and row["transfer_in_id"] == 19
    )
    assert candidate["player_expected_points_delta"] == pytest.approx(0.2)
    assert candidate["starting_xi_expected_points_delta"] == pytest.approx(0.0)
    assert candidate["captaincy_expected_points_delta"] == pytest.approx(0.0)
    assert candidate["expected_points_delta"] == pytest.approx(0.0)
    assert candidate["bench_depth_expected_points_delta"] == pytest.approx(0.2)
    assert candidate["net_expected_points_gain"] == pytest.approx(0.0)


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






def test_cta_context_is_exposed_for_squad_and_transfer_candidates_without_changing_scores():
    baseline = recommend_personal_squad(request())
    payload = request_with_cta()
    result = recommend_personal_squad(payload)
    assert result["squad_plan"]["starting_xi"] == baseline["squad_plan"]["starting_xi"]
    assert result["squad_plan"]["expected_starting_points"] == baseline["squad_plan"]["expected_starting_points"]
    assert result["transfer_recommendation"]["best_candidate"]["transfer_in_id"] == baseline["transfer_recommendation"]["best_candidate"]["transfer_in_id"]
    assert len(result["squad_plan"]["owned_squad_cta_context"]) == 15
    assert len(result["squad_plan"]["starting_xi_cta_context"]) == 11
    assert len(result["squad_plan"]["bench_cta_context"]) == 3
    best = result["transfer_recommendation"]["best_candidate"]
    assert best["cta_context"]["outgoing"]["cta"]["composite"] is None
    assert best["cta_context"]["incoming"]["cta"]["coverage_status"] == "HAS_PRIOR_VERIFIED_HISTORY"
    evidence = best["cta_context"]["incoming"]["cta_evidence_summary"]
    assert evidence["status"] == "RESEARCH_ONLY_EVIDENCE_AVAILABLE"
    assert evidence["feature_averages"]["shots_per_match"] == 2.5
    assert evidence["feature_averages"]["tracked_xg_per_match"] == 0.3
    assert evidence["decision_weight"] == 0.0
    assert evidence["ranking_effect"] == "NONE"
    assert result["squad_plan"]["cta_context_status"] == "RESEARCH_ONLY_NOT_IN_BASELINE"



def test_python_and_javascript_cta_context_outputs_are_identical():
    test_dir = Path(__file__).parent
    runner = test_dir / "js" / "emit_personal_squad_cta_outputs.mjs"
    completed = subprocess.run(
        ["node", str(runner)],
        check=True,
        capture_output=True,
        text=True,
    )
    javascript = json.loads(completed.stdout)
    python = recommend_personal_squad(request_with_cta())
    assert javascript == python


def test_personal_squad_reports_two_strong_bench_options_without_routine_rotation():
    result = recommend_personal_squad(request())
    support = result["squad_plan"]["bench_depth"]
    assert support["outfield_bench_count"] == 3
    assert len(support["top_two_outfield_bench_ids"]) == 2
    assert support["policy"] == "DESCRIPTIVE_ONLY_FIXED_STARTING_XI_NO_ROUTINE_ROTATION"
    assert result["squad_plan"]["formation"] == "4-3-3"


def test_personal_squad_preserves_missing_eo_and_reports_coverage():
    payload = request()
    payload["player_forecasts"][0]["effective_ownership_pct"] = 42.5
    payload["player_forecasts"][1]["effective_ownership_pct"] = 18.0
    result = recommend_personal_squad(payload)
    eo = result["squad_plan"]["effective_ownership_context"]
    assert eo["owned_players_with_eo"] == 2
    assert eo["owned_player_eo_coverage"] == pytest.approx(2 / 15)
    assert eo["decision_role"] == "FIELD_REFERENCE_ONLY_NOT_A_CTA_PREREQUISITE"
    assert eo["missing_eo_policy"] == "PRESERVE_MISSING_AND_REPORT_COVERAGE"


def test_personal_squad_freezes_transfer_and_captaincy_decision_records():
    result = recommend_personal_squad(request())
    audit = result["decision_audit"]
    assert audit["decision_record_status"] == "AUDIT_PAYLOAD_READY_AWAITING_DEADLINE_LOCK_AND_ARCHIVAL"
    assert audit["transfer_decision"]["chosen_option_id"].startswith("TRANSFER:")
    assert audit["transfer_decision"]["options"][0]["option_id"] == "HOLD"
    assert audit["transfer_decision"]["realised_utility"] is None
    assert audit["squad_snapshot"] and len(audit["squad_snapshot"]) == 15
    assert audit["starting_xi_decision"]["formation"] == "4-3-3"
    assert audit["captaincy_decision"]["chosen_option_id"] == str(result["squad_plan"]["captain"])
    assert len(audit["captaincy_decision"]["options"]) == 11


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



def test_cta_evidence_summary_does_not_turn_missing_features_into_zero():
    payload = request_with_cta()
    for player in payload["player_forecasts"]:
        player["cta"]["fixtures"][0]["features"] = {}
    result = recommend_personal_squad(payload)
    best = result["transfer_recommendation"]["best_candidate"]
    evidence = best["cta_context"]["incoming"]["cta_evidence_summary"]
    assert evidence["status"] == "VERIFIED_IDENTITY_NO_FEATURE_VALUES"
    assert evidence["feature_averages"] == {}
