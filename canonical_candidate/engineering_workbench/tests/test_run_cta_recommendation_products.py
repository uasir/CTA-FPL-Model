from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_cta_recommendation_products as runner


def _adapter_result():
    positions = (
        ["GKP", "GKP"] + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
    )
    players = []
    panels = {gw: [] for gw in range(12, 17)}
    for index, position in enumerate(positions, start=1):
        team_id = ((index - 1) % 5) + 1
        one_gw_points = float(index) / 2
        row = {
            "fpl_element_id": index,
            "expected_points": one_gw_points * 5,
            "expected_minutes": 85.0,
            "price": 5.0,
            "position": position,
            "team_id": team_id,
            "display_name": f"Player {index}",
        }
        players.append(row)
        for offset, gw in enumerate(panels):
            panels[gw].append({
                **row,
                "expected_points": one_gw_points + offset * 0.1,
            })
    quality = {
        "validation_status": "EXPLORATORY_ONLY",
        "point_in_time_status": "VERIFIED",
        "data_coverage": {
            "freshness_status": "FRESH_WITHIN_24H",
            "production_eligible": False,
            "decision_weight": 0,
            "covar_used": False,
        },
        "limitations": ["CTA M2 validation pending."],
    }
    return {
        "shared_forecast": {
            "forecast_snapshot_id": "cta-snapshot-test",
            "model_version": "cta-test-model-v1",
            "forecast_horizon_gameweeks": 5,
            "forecast_quality": quality,
            "player_forecasts": players,
        },
        "provider_snapshot": {
            "provider": {
                "name": "CTA-FPL",
                "product": "CTA-owned points",
                "variant": "five-gw-candidate",
            },
            "forecast_snapshot_id": "cta-snapshot-test",
            "season": "2026-27",
            "gameweeks": [12, 13, 14, 15, 16],
            "gameweek_panels": [
                {"gameweek": gw, "player_forecasts": rows}
                for gw, rows in panels.items()
            ],
            "timing": {
                "generated_at_utc": "2026-11-22T12:00:00Z",
                "bootstrap_captured_at_utc": "2026-11-22T11:59:00Z",
                "deadline_utc": "2026-11-27T18:30:00Z",
            },
            "provenance": {"source_manifest_sha256": "a" * 64},
        },
    }


def _manager_context():
    return {
        "squad_snapshot": [
            {"fpl_element_id": index, "purchase_price": 5.0}
            for index in range(1, 16)
        ],
        "bank": 0.0,
        "free_transfers": 1,
        "personal_risk_profile": "aggressive",
        "formation": "4-3-3",
        "personal_preferences": {"max_transfer_alternatives": 5},
    }




def _conventional_run(manager_context=None):
    manager = copy.deepcopy(manager_context or _manager_context())
    return {
        "run_type": "EXTERNAL_BENCHMARK_PERSONAL_SQUAD",
        "source_provenance": {
            "season": "2026-27",
            "target_gameweek": 12,
            "deadline_utc": "2026-11-27T18:30:00Z",
        },
        "manager_context": manager,
        "recommendation": {"manager_context": copy.deepcopy(manager)},
    }


def test_cta_runner_emits_both_products_with_correct_forecast_horizons(monkeypatch):
    adapted = _adapter_result()
    monkeypatch.setattr(
        runner, "build_cta_forecast_provider_snapshot",
        lambda *args, **kwargs: copy.deepcopy(adapted),
    )
    result = runner.run_cta_recommendation_products(
        "/unused-bundle", _manager_context(),
    )
    assert result["status"] == "PASS_EXPLORATORY_CTA_RECOMMENDATION_PREVIEWS"
    assert result["general_cta_market"]["system"] == "general_market"
    assert result["general_cta_market"]["forecast_horizon_gameweeks"] == 5
    assert result["general_cta_market"]["categories"]["overall"][0]["fpl_element_id"] == 15
    assert "captaincy" not in result["general_cta_market"]["categories"]
    assert [row["gameweek"] for row in result["gameweek_cta_markets"]] == [12, 13, 14, 15, 16]
    assert all(row["recommendations"]["forecast_horizon_gameweeks"] == 1
               for row in result["gameweek_cta_markets"])
    assert all("captaincy" in row["recommendations"]["categories"]
               for row in result["gameweek_cta_markets"])
    personal = result["cta_informed_personal_squad"]
    assert personal["product_id"] == "cta_informed_personal_squad"
    assert personal["forecast"]["horizon_gameweeks"] == 1
    assert personal["decision"]["basis"] == "CTA_MODEL_EXPECTED_POINTS_ONLY"
    assert personal["decision"]["scope"] == "ONE_GAMEWEEK_DIAGNOSTIC_ONLY"
    assert personal["decision"]["action"] == "NOT_DECISION_ELIGIBLE"
    assert personal["decision"]["decision_eligibility"]["status"] == "BLOCKED_PENDING_INDEPENDENT_MULTI_GAMEWEEK_VALIDATION"
    assert personal["release_eligible"] is False
    assert result["guardrails"]["personal_squad_emitted"] is True
    assert result["guardrails"]["personal_squad_used_first_gameweek_panel"] is True
    assert result["guardrails"]["five_gameweek_total_used_as_single_gameweek_ev"] is False
    assert result["guardrails"]["covar_used"] is False


def test_general_cta_product_runs_without_manager_context(monkeypatch):
    adapted = _adapter_result()
    monkeypatch.setattr(
        runner, "build_cta_forecast_provider_snapshot",
        lambda *args, **kwargs: copy.deepcopy(adapted),
    )
    result = runner.run_cta_recommendation_products("/unused-bundle")
    assert result["general_cta_market"]["forecast_horizon_gameweeks"] == 5
    assert result["cta_informed_personal_squad"]["status"] == "NOT_REQUESTED"
    assert result["cta_informed_personal_squad"]["enabled"] is False
    assert result["guardrails"]["personal_squad_emitted"] is False
    assert result["guardrails"]["personal_squad_used_first_gameweek_panel"] is False


def test_general_cta_rankings_are_invariant_to_manager_context(monkeypatch):
    adapted = _adapter_result()
    monkeypatch.setattr(
        runner, "build_cta_forecast_provider_snapshot",
        lambda *args, **kwargs: copy.deepcopy(adapted),
    )
    general_only_result = runner.run_cta_recommendation_products("/unused-bundle")
    general_only = general_only_result["general_cta_market"]
    weekly_only = general_only_result["gameweek_cta_markets"]
    manager_a = _manager_context()
    manager_b = _manager_context()
    manager_b["bank"] = 12.3
    manager_b["free_transfers"] = 5
    manager_b["personal_risk_profile"] = "conservative"
    manager_b["squad_snapshot"] = list(reversed(manager_b["squad_snapshot"]))
    result_a = runner.run_cta_recommendation_products("/unused-bundle", manager_a)
    result_b = runner.run_cta_recommendation_products("/unused-bundle", manager_b)
    assert general_only == result_a["general_cta_market"] == result_b["general_cta_market"]
    assert weekly_only == result_a["gameweek_cta_markets"] == result_b["gameweek_cta_markets"]


def test_cta_runner_rejects_incomplete_manager_context(monkeypatch):
    monkeypatch.setattr(
        runner, "build_cta_forecast_provider_snapshot",
        lambda *args, **kwargs: copy.deepcopy(_adapter_result()),
    )
    with pytest.raises(runner.CTARecommendationRunError, match="manager_context is missing"):
        runner.run_cta_recommendation_products("/unused-bundle", {})


def test_cta_personal_preview_can_reuse_same_gw_conventional_manager_state(monkeypatch):
    adapted = _adapter_result()
    monkeypatch.setattr(
        runner, "build_cta_forecast_provider_snapshot",
        lambda *args, **kwargs: copy.deepcopy(adapted),
    )
    result = runner.run_cta_recommendation_products(
        "/unused-bundle", conventional_run=_conventional_run(),
    )
    personal = result["cta_informed_personal_squad"]
    assert personal["product_id"] == "cta_informed_personal_squad"
    assert personal["forecast"]["horizon_gameweeks"] == 1
    assert personal["manager_state"]["bank"] == 0.0
    assert personal["manager_state"]["free_transfers"] == 1
    assert result["guardrails"]["personal_squad_emitted"] is True


@pytest.mark.parametrize("field,value,message", [
    ("season", "2025-26", "season does not match"),
    ("target_gameweek", 13, "target Gameweek does not match"),
    ("deadline_utc", "2026-11-28T18:30:00Z", "deadline does not match"),
])
def test_cta_personal_preview_rejects_misaligned_conventional_manager_state(
    monkeypatch, field, value, message,
):
    adapted = _adapter_result()
    monkeypatch.setattr(
        runner, "build_cta_forecast_provider_snapshot",
        lambda *args, **kwargs: copy.deepcopy(adapted),
    )
    conventional = _conventional_run()
    conventional["source_provenance"][field] = value
    with pytest.raises(runner.CTARecommendationRunError, match=message):
        runner.run_cta_recommendation_products(
            "/unused-bundle", conventional_run=conventional,
        )


def test_cta_personal_preview_rejects_conventional_manager_state_disagreement(monkeypatch):
    adapted = _adapter_result()
    monkeypatch.setattr(
        runner, "build_cta_forecast_provider_snapshot",
        lambda *args, **kwargs: copy.deepcopy(adapted),
    )
    conventional = _conventional_run()
    conventional["recommendation"]["manager_context"]["bank"] = 4.0
    with pytest.raises(runner.CTARecommendationRunError, match="disagrees"):
        runner.run_cta_recommendation_products(
            "/unused-bundle", conventional_run=conventional,
        )


def test_cta_runner_rejects_two_competing_manager_context_sources(monkeypatch):
    monkeypatch.setattr(
        runner, "build_cta_forecast_provider_snapshot",
        lambda *args, **kwargs: copy.deepcopy(_adapter_result()),
    )
    with pytest.raises(runner.CTARecommendationRunError, match="either manager_context or conventional_run"):
        runner.run_cta_recommendation_products(
            "/unused-bundle", _manager_context(), conventional_run=_conventional_run(),
        )


def test_conventional_deadline_accepts_equivalent_utc_offset(monkeypatch):
    adapted = _adapter_result()
    monkeypatch.setattr(
        runner, "build_cta_forecast_provider_snapshot",
        lambda *args, **kwargs: copy.deepcopy(adapted),
    )
    conventional = _conventional_run()
    conventional["source_provenance"]["deadline_utc"] = "2026-11-27T18:30:00+00:00"
    result = runner.run_cta_recommendation_products(
        "/unused-bundle", conventional_run=conventional,
    )
    assert result["guardrails"]["personal_squad_emitted"] is True
