#!/usr/bin/env python3
"""Run one personal-squad recommendation from a frozen external benchmark.

Input JSON shape:
{
  "provider_snapshot": { canonical provider contract input },
  "player_metadata": [ current FPL metadata rows ],
  "manager_context": {
    "squad_snapshot": [...15 FPL element IDs and purchase prices...],
    "bank": 1.2,
    "free_transfers": 1,
    "personal_risk_profile": "aggressive",
    "formation": "4-3-3",
    "personal_preferences": {}
  },
  "as_of_utc": "..."
}

The provider snapshot is normalized and eligibility-checked before the
existing personal-squad engine is called. No project-model forecasts or
cross-provider consensus are used.
"""
from __future__ import annotations

import argparse
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from canonical_provider_forecast_contract import normalize_provider_snapshot
from canonical_forecast_recommendation_adapter import build_recommendation_forecast_payload
from personal_squad_engine import recommend_personal_squad
from squad_decision_context import attach_squad_decision_context
from historical_covar_recommendation_overlay import build_historical_covar_recommendation_overlay


class BenchmarkDecisionRunError(ValueError):
    """Raised when a benchmark-backed decision run is incomplete or unsafe."""


def run_external_benchmark_personal_squad(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise BenchmarkDecisionRunError("run input must be an object")
    required = ("provider_snapshot", "player_metadata", "player_metadata_provenance", "manager_context", "as_of_utc")
    missing = [key for key in required if key not in payload]
    if missing:
        raise BenchmarkDecisionRunError("missing run fields: " + ", ".join(missing))

    snapshot = normalize_provider_snapshot(payload["provider_snapshot"])
    if snapshot["decision_eligible"] is not True:
        raise BenchmarkDecisionRunError(
            "provider snapshot is diagnostic-only: " + snapshot["eligibility_reason"]
        )

    forecast_payload = build_recommendation_forecast_payload(
        snapshot,
        payload["player_metadata"],
        as_of_utc=payload["as_of_utc"],
        forecast_horizon_gameweeks=1,
    )
    metadata_provenance = payload["player_metadata_provenance"]
    if not isinstance(metadata_provenance, Mapping):
        raise BenchmarkDecisionRunError("player_metadata_provenance must be an object")
    provenance_required = ("source_url", "raw_snapshot_id", "raw_sha256", "captured_at_utc", "row_count")
    missing_provenance = [key for key in provenance_required if key not in metadata_provenance]
    if missing_provenance:
        raise BenchmarkDecisionRunError("missing player metadata provenance: " + ", ".join(missing_provenance))
    metadata_hash = metadata_provenance["raw_sha256"]
    if not isinstance(metadata_hash, str) or len(metadata_hash) != 64 or any(c not in "0123456789abcdef" for c in metadata_hash.lower()):
        raise BenchmarkDecisionRunError("player metadata raw_sha256 must be a 64-character SHA-256")
    if metadata_provenance["row_count"] != len(payload["player_metadata"]):
        raise BenchmarkDecisionRunError("player metadata provenance row_count does not match metadata rows")
    try:
        metadata_captured = datetime.fromisoformat(metadata_provenance["captured_at_utc"].replace("Z", "+00:00"))
        as_of = datetime.fromisoformat(payload["as_of_utc"].replace("Z", "+00:00"))
        deadline = datetime.fromisoformat(snapshot["timing"]["deadline_utc"].replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError) as exc:
        raise BenchmarkDecisionRunError("metadata capture and as_of timestamps must be ISO-8601") from exc
    if metadata_captured.tzinfo is None or as_of.tzinfo is None:
        raise BenchmarkDecisionRunError("metadata capture and as_of timestamps must include timezone")
    if metadata_captured.astimezone(timezone.utc) >= deadline.astimezone(timezone.utc):
        raise BenchmarkDecisionRunError("player metadata capture must be strictly before the FPL deadline")
    if metadata_captured > as_of.astimezone(timezone.utc):
        raise BenchmarkDecisionRunError("player metadata capture cannot be later than decision as_of_utc")
    if as_of.astimezone(timezone.utc) >= deadline.astimezone(timezone.utc):
        raise BenchmarkDecisionRunError("decision as_of_utc must be strictly before the FPL deadline")

    manager = payload["manager_context"]
    if not isinstance(manager, Mapping):
        raise BenchmarkDecisionRunError("manager_context must be an object")
    manager_required = ("squad_snapshot", "bank", "free_transfers", "personal_risk_profile")
    missing_manager = [key for key in manager_required if key not in manager]
    if missing_manager:
        raise BenchmarkDecisionRunError(
            "missing manager_context fields: " + ", ".join(missing_manager)
        )

    request = {**forecast_payload, **dict(manager)}
    recommendation = recommend_personal_squad(request)
    if payload.get("field_relative_context") is not None or payload.get("covar_context") is not None:
        recommendation = attach_squad_decision_context(
            recommendation=recommendation,
            field_relative_context=payload.get("field_relative_context"),
            covar_context=payload.get("covar_context"),
            target_gameweek=snapshot["target_gameweek"],
            as_of_utc=payload["as_of_utc"],
            deadline_utc=snapshot["timing"]["deadline_utc"],
        )
    historical_covar = payload.get("historical_covariance_context")
    if historical_covar is not None:
        if not isinstance(historical_covar, Mapping):
            raise BenchmarkDecisionRunError("historical_covariance_context must be an object")
        required_covar = ("covariance_report", "covariance_pairs")
        missing_covar = [key for key in required_covar if key not in historical_covar]
        if missing_covar:
            raise BenchmarkDecisionRunError(
                "missing historical covariance fields: " + ", ".join(missing_covar)
            )
        historical_overlay = build_historical_covar_recommendation_overlay(
            recommendation=recommendation,
            forecast_rows=forecast_payload["player_forecasts"],
            covariance_report=historical_covar["covariance_report"],
            covariance_pairs=historical_covar["covariance_pairs"],
        )
        recommendation = dict(recommendation)
        recommendation["historical_covar_overlay"] = historical_overlay

    coverage = forecast_payload["forecast_quality"]["data_coverage"]
    return {
        "run_contract_version": "1.0.0",
        "run_type": "EXTERNAL_BENCHMARK_PERSONAL_SQUAD",
        "run_id": (
            f"{snapshot['season']}-GW{snapshot['target_gameweek']}-"
            f"{snapshot['provider']['name']}-{snapshot['provider']['product']}-"
            f"{snapshot['provider']['variant']}-{snapshot['snapshot_id']}"
        ),
        "provider_identity": snapshot["provider"],
        "player_metadata_provenance": dict(metadata_provenance),
        "source_provenance": {
            "snapshot_id": snapshot["snapshot_id"],
            "source_url": snapshot["source"]["url"],
            "raw_snapshot_id": snapshot["source"]["raw_snapshot_id"],
            "raw_sha256": snapshot["source"]["raw_sha256"],
            "generated_at_utc": snapshot["timing"]["generated_at_utc"],
            "captured_at_utc": snapshot["timing"]["captured_at_utc"],
            "deadline_utc": snapshot["timing"]["deadline_utc"],
            "point_in_time_status": snapshot["timing"]["point_in_time_status"],
        },
        "coverage": coverage,
        "recommendation": recommendation,
        "release_eligible": False,
        "release_blockers": [
            "M3 decision-run and historical decision-evaluation acceptance gates are not yet complete.",
            "External provider forecast accuracy has not been promoted by this software execution.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    result = run_external_benchmark_personal_squad(payload)
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
