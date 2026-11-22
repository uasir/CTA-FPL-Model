import copy
import hashlib
import json
from pathlib import Path
import pytest

from run_external_benchmark_personal_squad import run_external_benchmark_personal_squad
from build_conventional_squad_product import (ConventionalSquadProductError, build_conventional_squad_product, build_personal_squad_product)

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "recommendation_requests.json").read_text())

def _run():
    manager = copy.deepcopy(FIXTURE["personal_squad"])
    forecasts = copy.deepcopy(manager["player_forecasts"])
    forecasts[2]["price"] = 5.2
    forecasts.extend([
        {"fpl_element_id": 16, "expected_points": 7.0, "expected_minutes": 85, "price": 5.0, "position": "DEF", "team_id": 6},
        {"fpl_element_id": 17, "expected_points": 8.0, "expected_minutes": 90, "price": 5.0, "position": "DEF", "team_id": 1},
    ])
    raw = b"m4 conventional product fixture"
    payload = {
        "provider_snapshot": {
            "snapshot_id": "gw11-fplcat-m4-test", "season": "2026-27", "target_gameweek": 11,
            "provider": {"name": "FPL Cat", "product": "projections", "variant": "provider_native_xp", "version": "v1"},
            "timing": {"generated_at_utc": "2026-11-20T08:30:00Z", "captured_at_utc": "2026-11-20T09:00:00Z", "deadline_utc": "2026-11-21T11:00:00Z"},
            "source": {"url": "https://provider.example/forecast.json", "raw_snapshot_id": "raw-m4", "raw_sha256": hashlib.sha256(raw).hexdigest()},
            "grain": "player_gameweek",
            "records": [{"fpl_element_id": row["fpl_element_id"], "expected_points": row["expected_points"]} for row in forecasts],
            "coverage": {"row_count": len(forecasts), "identity_mapped_count": len(forecasts), "identity_resolution_status": "VERIFIED"},
        },
        "player_metadata": [{k: row[k] for k in ("fpl_element_id", "price", "position", "team_id", "expected_minutes")} for row in forecasts],
        "manager_context": {k: manager[k] for k in ("squad_snapshot", "bank", "free_transfers", "personal_risk_profile", "formation")},
        "player_metadata_provenance": {
            "source_url": "https://fantasy.premierleague.com/api/bootstrap-static/",
            "raw_snapshot_id": "sha256:" + hashlib.sha256(b"bootstrap").hexdigest(),
            "raw_sha256": hashlib.sha256(b"bootstrap").hexdigest(),
            "captured_at_utc": "2026-11-20T09:05:00Z", "row_count": len(forecasts),
        },
        "as_of_utc": "2026-11-20T10:00:00Z",
    }
    return run_external_benchmark_personal_squad(payload)

def test_conventional_product_exposes_ev_decision_and_source_provenance_only():
    run = _run()
    product = build_personal_squad_product(run)
    assert build_conventional_squad_product is build_personal_squad_product
    assert product["product_id"] == "conventional_personal_squad"
    assert product["product_status"] == "EXPLORATORY_PREVIEW"
    assert product["release_eligible"] is False
    assert product["decision"]["basis"] == "CONVENTIONAL_EXPECTED_POINTS_ONLY"
    assert product["decision"]["action"] == "NOT_DECISION_ELIGIBLE"
    assert product["decision"]["scope"] == "ONE_GAMEWEEK_DIAGNOSTIC_ONLY"
    assert product["decision"]["best_transfer"] is None
    assert product["decision"]["recommended_squad_plan"] is None
    assert product["decision"]["one_gameweek_preview"]["action"] == run["recommendation"]["transfer_recommendation"]["action"]
    assert product["decision"]["current_squad_plan"] == run["recommendation"]["current_squad_plan"]
    assert product["forecast"]["provider"]["name"] == "FPL Cat"
    assert product["forecast"]["source_run_type"] == "EXTERNAL_BENCHMARK_PERSONAL_SQUAD"
    assert product["provenance"]["raw_sha256"] == run["source_provenance"]["raw_sha256"]
    assert product["excluded_context"]["covar"] == "NOT_PART_OF_CONVENTIONAL_SCORE"
    assert "predeadline_field_analysis" not in product
    assert "historical_covar_overlay" not in product

def test_m4_product_contract_accepts_cta_source_run_shape_without_promoting_it():
    run = _run()
    run["run_type"] = "CTA_MODEL_PERSONAL_SQUAD"
    run["provider_identity"] = {"name": "CTA-FPL", "product": "model_forecast", "variant": "cta_xp", "version": "unvalidated"}
    run["release_eligible"] = False
    run["release_blockers"] = ["CTA forecast validation is pending."]
    product = build_personal_squad_product(run)
    assert product["forecast"]["source_run_type"] == "CTA_MODEL_PERSONAL_SQUAD"
    assert product["product_id"] == "cta_informed_personal_squad"
    assert product["decision"]["basis"] == "CTA_MODEL_EXPECTED_POINTS_ONLY"
    assert product["decision"]["action"] == "NOT_DECISION_ELIGIBLE"
    assert product["decision"]["best_transfer"] is None
    assert product["forecast"]["provider"]["name"] == "CTA-FPL"
    assert product["release_eligible"] is False
    assert "CTA forecast validation is pending." in product["release_blockers"]

def test_conventional_product_rejects_non_personal_or_incomplete_run():
    with pytest.raises(ConventionalSquadProductError, match="source run type is not supported"):
        build_conventional_squad_product({"run_type": "OTHER"})
    broken = copy.deepcopy(_run())
    del broken["recommendation"]["current_squad_plan"]
    with pytest.raises(ConventionalSquadProductError, match="missing"):
        build_conventional_squad_product(broken)

def test_conventional_product_keeps_field_and_covar_out_of_ev_decision():
    run = _run()
    run["recommendation"]["predeadline_field_analysis"] = {"fake": "must not leak"}
    run["recommendation"]["historical_covar_overlay"] = {"fake": "must not leak"}
    product = build_conventional_squad_product(run)
    assert "predeadline_field_analysis" not in product["decision"]
    assert "historical_covar_overlay" not in product["decision"]


def test_m4_attaches_five_gameweek_team_exposure_as_diagnostic_only():
    run = _run()
    run["team_exposure_context"] = {
        "forecast_snapshot_id": run["recommendation"]["forecast_snapshot_id"],
        "horizon_size": 5,
        "expected_points_are_additive": True,
        "decision_weight": 0,
        "production_eligible": False,
        "team_exposure": [{"team_id": 1, "player_count": 2,
                           "stack_type": "DEFENSIVE_CLEAN_SHEET_EXPOSURE"}],
    }
    product = build_personal_squad_product(run)
    assert product["team_exposure_context"]["horizon_size"] == 5
    assert product["excluded_context"]["team_exposure"] == "DIAGNOSTIC_ONLY_NOT_PART_OF_CONVENTIONAL_SCORE"
    assert product["decision"]["action"] == "NOT_DECISION_ELIGIBLE"
    assert product["decision"]["best_transfer"] is None


@pytest.mark.parametrize("mutation, message", [
    ({"horizon_size": 4}, "at least five Gameweeks"),
    ({"forecast_snapshot_id": "other-snapshot"}, "exact forecast snapshot"),
    ({"decision_weight": 0.1}, "diagnostic-only"),
    ({"production_eligible": True}, "diagnostic-only"),
    ({"expected_points_are_additive": False}, "additive expected-points"),
])
def test_m4_rejects_invalid_team_exposure_context(mutation, message):
    run = _run()
    run["team_exposure_context"] = {
        "forecast_snapshot_id": run["recommendation"]["forecast_snapshot_id"],
        "horizon_size": 5,
        "expected_points_are_additive": True,
        "decision_weight": 0,
        "production_eligible": False,
    }
    run["team_exposure_context"].update(mutation)
    with pytest.raises(ConventionalSquadProductError, match=message):
        build_personal_squad_product(run)



def test_five_gameweek_action_requires_explicit_validated_consecutive_snapshot_evidence():
    run = _run()
    run["multi_gameweek_decision_evidence"] = {
        "status": "VALIDATED_FOR_M4_DECISION",
        "decision_eligible": True,
        "horizon_gameweeks": 5,
        "gameweeks": [12, 13, 14, 15, 16],
        "source_snapshot_ids": ["s12", "s13", "s14", "s15", "s16"],
        "decision": {"action": "HOLD", "hit_cost_points_applied": 0},
    }
    product = build_personal_squad_product(run)
    assert product["decision"]["action"] == "HOLD"
    assert product["decision"]["scope"] == "MULTI_GAMEWEEK_HOLD_VS_TRANSFER"
    assert product["decision"]["decision_eligibility"]["status"] == "VALIDATED_FOR_M4_DECISION"
    assert "one_gameweek_preview" not in product["decision"]


@pytest.mark.parametrize("mutation", [
    {"gameweeks": [12, 13, 14, 16, 17]},
    {"source_snapshot_ids": ["same", "same", "s14", "s15", "s16"]},
    {"horizon_gameweeks": 4},
    {"decision_eligible": False},
])
def test_incomplete_multi_gameweek_evidence_cannot_unlock_actionable_transfer(mutation):
    run = _run()
    evidence = {
        "status": "VALIDATED_FOR_M4_DECISION",
        "decision_eligible": True,
        "horizon_gameweeks": 5,
        "gameweeks": [12, 13, 14, 15, 16],
        "source_snapshot_ids": ["s12", "s13", "s14", "s15", "s16"],
        "decision": {"action": "HOLD"},
    }
    evidence.update(mutation)
    run["multi_gameweek_decision_evidence"] = evidence
    product = build_personal_squad_product(run)
    assert product["decision"]["action"] == "NOT_DECISION_ELIGIBLE"
    assert product["decision"]["best_transfer"] is None
