#!/usr/bin/env python3
"""Build exploratory general and squad-specific recommendations from CTA forecasts.

The general market ranks five-Gameweek cumulative CTA points. The personal
squad preview uses only the first target-Gameweek panel; it never substitutes
the five-Gameweek total for a one-Gameweek expected-points input. Both outputs
remain exploratory while M2 validation is pending.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from build_conventional_squad_product import build_personal_squad_product
from cta_forecast_recommendation_adapter import build_cta_forecast_provider_snapshot
from general_market_engine import recommend_general_market
from personal_squad_engine import recommend_personal_squad


class CTARecommendationRunError(ValueError):
    """Raised when CTA forecasts cannot safely back recommendation previews."""


def _personal_request(shared: Mapping[str, Any], panel: Mapping[str, Any],
                      manager_context: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(manager_context, Mapping):
        raise CTARecommendationRunError("an explicit manager_context is required for personal recommendations")
    required = ("squad_snapshot", "bank", "free_transfers", "personal_risk_profile")
    missing = [field for field in required if field not in manager_context]
    if missing:
        raise CTARecommendationRunError("manager_context is missing: " + ", ".join(missing))
    forecasts = panel.get("player_forecasts")
    if not isinstance(forecasts, list) or not forecasts:
        raise CTARecommendationRunError("target Gameweek panel has no player forecasts")
    shared_quality = shared.get("forecast_quality")
    if not isinstance(shared_quality, Mapping):
        raise CTARecommendationRunError("CTA shared forecast quality is missing")
    return {
        "forecast_snapshot_id": shared["forecast_snapshot_id"],
        "model_version": shared["model_version"],
        "forecast_horizon_gameweeks": 1,
        "forecast_quality": dict(shared_quality),
        "player_forecasts": [dict(row) for row in forecasts],
        **dict(manager_context),
    }


def run_cta_recommendation_products(
    bundle_dir: str | Path,
    manager_context: Mapping[str, Any],
    *,
    eo_snapshot: Mapping[str, Any] | None = None,
    now_utc: str | None = None,
) -> dict[str, Any]:
    adapted = build_cta_forecast_provider_snapshot(
        bundle_dir, eo_snapshot=eo_snapshot, now_utc=now_utc,
    )
    shared = adapted.get("shared_forecast")
    provider_snapshot = adapted.get("provider_snapshot")
    if not isinstance(shared, Mapping) or not isinstance(provider_snapshot, Mapping):
        raise CTARecommendationRunError("CTA adapter did not return its shared forecast and provider snapshot")
    if shared.get("forecast_quality", {}).get("validation_status") != "EXPLORATORY_ONLY":
        raise CTARecommendationRunError("CTA forecast must remain explicitly exploratory")
    if shared.get("forecast_quality", {}).get("data_coverage", {}).get("production_eligible") is not False:
        raise CTARecommendationRunError("CTA forecast must explicitly remain production-ineligible")
    if shared.get("forecast_quality", {}).get("data_coverage", {}).get("decision_weight") != 0:
        raise CTARecommendationRunError("CTA forecast must retain zero decision weight")
    if shared.get("forecast_quality", {}).get("data_coverage", {}).get("covar_used") is not False:
        raise CTARecommendationRunError("CTA recommendation previews cannot consume CoVar")

    # Squad-independent product: five-GW cumulative forecast totals, no manager data.
    general_request = {
        "forecast_snapshot_id": shared["forecast_snapshot_id"],
        "model_version": shared["model_version"],
        "forecast_horizon_gameweeks": shared["forecast_horizon_gameweeks"],
        "forecast_quality": dict(shared["forecast_quality"]),
        "player_forecasts": [dict(row) for row in shared["player_forecasts"]],
        "filters": {},
    }
    general = recommend_general_market(general_request)

    # Personal product: first GW only. Never use the five-GW aggregate as one-GW EV.
    panels = provider_snapshot.get("gameweek_panels")
    if not isinstance(panels, list) or len(panels) != 5:
        raise CTARecommendationRunError("CTA provider snapshot must contain five Gameweek panels")
    gameweeks = provider_snapshot.get("gameweeks")
    if not isinstance(gameweeks, list) or len(gameweeks) != 5:
        raise CTARecommendationRunError("CTA provider snapshot must declare five target Gameweeks")
    target_gw = gameweeks[0]
    target_panel = next(
        (panel for panel in panels if isinstance(panel, Mapping) and panel.get("gameweek") == target_gw),
        None,
    )
    if target_panel is None:
        raise CTARecommendationRunError("first target Gameweek panel is missing")
    personal_request = _personal_request(shared, target_panel, manager_context)
    personal_recommendation = recommend_personal_squad(personal_request)

    timing = provider_snapshot.get("timing", {})
    provenance = provider_snapshot.get("provenance", {})
    source_provenance = {
        "season": provider_snapshot.get("season"),
        "target_gameweek": target_gw,
        "decision_as_of_utc": timing.get("generated_at_utc"),
        "snapshot_id": shared["forecast_snapshot_id"],
        "source_url": "verified-local-cta-candidate-bundle",
        "raw_snapshot_id": provenance.get("source_manifest_sha256"),
        "raw_sha256": provenance.get("source_manifest_sha256"),
        "generated_at_utc": timing.get("generated_at_utc"),
        "captured_at_utc": timing.get("bootstrap_captured_at_utc"),
        "deadline_utc": timing.get("deadline_utc"),
        "point_in_time_status": shared["forecast_quality"]["point_in_time_status"],
    }
    product_run = {
        "run_type": "CTA_MODEL_PERSONAL_SQUAD",
        "run_id": f"CTA-{provider_snapshot.get('season')}-GW{target_gw}-{shared['forecast_snapshot_id']}",
        "provider_identity": dict(provider_snapshot.get("provider", {})),
        "manager_context": {
            "bank": manager_context["bank"],
            "free_transfers": manager_context["free_transfers"],
            "personal_risk_profile": manager_context["personal_risk_profile"],
        },
        "source_provenance": source_provenance,
        "recommendation": personal_recommendation,
        "release_eligible": False,
        "release_blockers": [
            "CTA M2 forecast validation remains pending.",
            "This personal-squad optimiser is a one-Gameweek diagnostic, not a validated multi-Gameweek transfer decision.",
            "Independent M4 recommendation-product evaluation and governed promotion have not passed.",
        ],
    }
    personal_product = build_personal_squad_product(product_run)

    return {
        "status": "PASS_EXPLORATORY_CTA_RECOMMENDATION_PREVIEWS",
        "target": {
            "season": provider_snapshot.get("season"),
            "gameweeks": list(gameweeks),
            "target_gameweek": target_gw,
            "forecast_snapshot_id": shared["forecast_snapshot_id"],
        },
        "general_cta_market": general,
        "cta_informed_personal_squad": personal_product,
        "guardrails": {
            "candidate_only": True,
            "production_eligible": False,
            "decision_weight": 0,
            "covar_used": False,
            "general_market_consumed_personal_context": False,
            "personal_squad_used_first_gameweek_panel": True,
            "five_gameweek_total_used_as_single_gameweek_ev": False,
            "recommendation_status": "EXPLORATORY_ONLY",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--manager-context", type=Path, required=True)
    parser.add_argument("--eo-snapshot", type=Path)
    parser.add_argument("--now-utc")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manager = json.loads(args.manager_context.read_text(encoding="utf-8"))
    eo = None
    if args.eo_snapshot:
        eo = json.loads(args.eo_snapshot.read_text(encoding="utf-8"))
    result = run_cta_recommendation_products(
        args.bundle_dir, manager, eo_snapshot=eo, now_utc=args.now_utc,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": result["status"],
        "target_gameweek": result["target"]["target_gameweek"],
        "general_players_ranked": result["general_cta_market"]["coverage"]["filtered_players"],
        "personal_product_id": result["cta_informed_personal_squad"]["product_id"],
        "personal_decision_eligibility": result["cta_informed_personal_squad"]["decision"]["decision_eligibility"]["status"],
        "production_eligible": False,
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
