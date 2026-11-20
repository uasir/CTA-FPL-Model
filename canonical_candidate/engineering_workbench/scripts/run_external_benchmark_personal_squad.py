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
from pathlib import Path
from typing import Any, Mapping

from canonical_provider_forecast_contract import normalize_provider_snapshot
from canonical_forecast_recommendation_adapter import build_recommendation_forecast_payload
from personal_squad_engine import recommend_personal_squad


class BenchmarkDecisionRunError(ValueError):
    """Raised when a benchmark-backed decision run is incomplete or unsafe."""


def run_external_benchmark_personal_squad(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise BenchmarkDecisionRunError("run input must be an object")
    required = ("provider_snapshot", "player_metadata", "manager_context", "as_of_utc")
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
