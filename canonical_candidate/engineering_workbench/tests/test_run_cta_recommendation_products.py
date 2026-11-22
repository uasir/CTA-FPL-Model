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
    positions = ["GKP", "GKP"] + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
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
    personal = result["cta_informed_personal_squad"]
    assert personal["product_id"] == "cta_informed_personal_squad"
    assert personal["forecast"]["horizon_gameweeks"] == 1
    assert personal["decision"]["basis"] == "CTA_MODEL_EXPECTED_POINTS_ONLY"
    assert personal["decision"]["scope"] == "ONE_GAMEWEEK_DIAGNOSTIC_ONLY"
    assert personal["decision"]["action"] == "NOT_DECISION_ELIGIBLE"
    assert personal["decision"]["decision_eligibility"]["status"] == "BLOCKED_PENDING_INDEPENDENT_MULTI_GAMEWEEK_VALIDATION"
    assert personal["release_eligible"] is False
    assert result["guardrails"]["personal_squad_used_first_gameweek_panel"] is True
    assert result["guardrails"]["five_gameweek_total_used_as_single_gameweek_ev"] is False
    assert result["guardrails"]["covar_used"] is False


def test_cta_runner_requires_real_manager_context(monkeypatch):
    monkeypatch.setattr(
        runner, "build_cta_forecast_provider_snapshot",
        lambda *args, **kwargs: copy.deepcopy(_adapter_result()),
    )
    with pytest.raises(runner.CTRecommendationRunError if hasattr(runner, "CTRecommendationRunError") else runner.CTARecommendationRunError):
        runner.run_cta_recommendation_products("/unused-bundle", {})
