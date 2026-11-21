#!/usr/bin/env python3
"""Capture a manager-free conventional M3-compatible forecast for CoVar research.

This uses the same provider capture, normalization and recommendation forecast
adapter consumed by M3, but deliberately does not execute or archive the
personal-squad M3 decision. Only public provider forecasts and FPL metadata are
included. It is not a joint outcome forecast and remains research-only.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from capture_fpl_cat_snapshot import capture_fpl_cat_snapshot
from canonical_provider_forecast_contract import normalize_provider_snapshot
from canonical_forecast_recommendation_adapter import build_recommendation_forecast_payload


class ConventionalForecastCaptureError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def capture_conventional_forecast(
    *, season: str, capture: Callable[..., dict[str, Any]] = capture_fpl_cat_snapshot,
    clock: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    captured = capture(season=season)
    provider = captured.get("provider_snapshot")
    metadata = captured.get("player_metadata")
    archives = captured.get("raw_archives")
    metadata_provenance = captured.get("player_metadata_provenance")
    if not isinstance(provider, dict) or not isinstance(metadata, list) or not isinstance(archives, dict):
        raise ConventionalForecastCaptureError("provider snapshot, player metadata and raw archives are required")
    try:
        provider_raw = base64.b64decode(archives["provider_response_base64"], validate=True)
        bootstrap_raw = base64.b64decode(archives["fpl_bootstrap_response_base64"], validate=True)
    except (KeyError, ValueError, TypeError) as exc:
        raise ConventionalForecastCaptureError("captured source bytes are missing or invalid") from exc
    provider_hash = hashlib.sha256(provider_raw).hexdigest()
    bootstrap_hash = hashlib.sha256(bootstrap_raw).hexdigest()
    if provider.get("source", {}).get("raw_sha256") != provider_hash:
        raise ConventionalForecastCaptureError("provider source hash does not match captured bytes")
    if not isinstance(metadata_provenance, dict) or metadata_provenance.get("raw_sha256") != bootstrap_hash:
        raise ConventionalForecastCaptureError("official bootstrap hash does not match captured bytes")

    normalized = normalize_provider_snapshot(provider)
    if normalized.get("decision_eligible") is not True:
        raise ConventionalForecastCaptureError("provider generation time is undisclosed; forecast is diagnostic-only")
    as_of = clock()
    forecast_payload = build_recommendation_forecast_payload(
        normalized, metadata, as_of_utc=as_of, forecast_horizon_gameweeks=1
    )
    provider_json = json.loads(provider_raw.decode("utf-8"))
    bootstrap_json = json.loads(bootstrap_raw.decode("utf-8"))
    if provider_json.get("gameweek") != normalized["target_gameweek"]:
        raise ConventionalForecastCaptureError("raw provider Gameweek mismatch")
    if not isinstance(bootstrap_json.get("elements"), list):
        raise ConventionalForecastCaptureError("official bootstrap archive has no player universe")

    forecast = {
        "schema_version": "1.0.0",
        "bundle_type": "M3_CONVENTIONAL_FORECAST_ONLY_COVAR_INPUT",
        "season": normalized["season"],
        "target_gameweek": normalized["target_gameweek"],
        "mode": "REGULAR_GW",
        "as_of_utc": as_of,
        "deadline_utc": normalized["timing"]["deadline_utc"],
        "forecast_snapshot_id": forecast_payload["forecast_snapshot_id"],
        "model_version": forecast_payload["model_version"],
        "provider_snapshot": normalized,
        "player_metadata": metadata,
        "player_metadata_provenance": metadata_provenance,
        "player_forecasts": forecast_payload["player_forecasts"],
        "forecast_quality": forecast_payload["forecast_quality"],
        "source_archives": [
            {
                "source_type": "provider_forecast",
                "source_url": normalized["source"]["url"],
                "raw_snapshot_id": normalized["source"]["raw_snapshot_id"],
                "raw_sha256": provider_hash,
                "generated_at_utc": normalized["timing"]["generated_at_utc"],
                "captured_at_utc": normalized["timing"]["captured_at_utc"],
                "raw_payload_base64": base64.b64encode(provider_raw).decode("ascii"),
            },
            {
                "source_type": "player_metadata",
                "source_url": metadata_provenance["source_url"],
                "raw_snapshot_id": metadata_provenance["raw_snapshot_id"],
                "raw_sha256": bootstrap_hash,
                "captured_at_utc": metadata_provenance["captured_at_utc"],
                "raw_payload_base64": base64.b64encode(bootstrap_raw).decode("ascii"),
            },
        ],
        "privacy": {
            "manager_identity_included": False,
            "manager_squad_included": False,
            "bank_or_transfer_state_included": False,
            "frozen_decision_included": False,
        },
        "capture_semantics": "SAME_CONVENTIONAL_PROVIDER_AND_FORECAST_ADAPTER_AS_M3; PERSONAL_M3_DECISION_NOT_EXECUTED",
        "point_in_time_status": "PROVIDER_GENERATION_AND_CAPTURE_PRE_DEADLINE",
        "decision_weight": 0.0,
        "production_eligible": False,
        "limitations": [
            "This is the exact conventional provider forecast adapter used by M3, captured without personal manager state.",
            "It is a player-Gameweek expected-points/minutes snapshot, not a joint outcome distribution.",
            "Provider publication timestamps are source-declared and are not independently authenticated.",
            "The bundle is prospective only; no historical forecast is reconstructed.",
        ],
    }
    return forecast


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = capture_conventional_forecast(season=args.season)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "CAPTURED_RESEARCH_ONLY",
        "season": result["season"],
        "target_gameweek": result["target_gameweek"],
        "forecast_snapshot_id": result["forecast_snapshot_id"],
        "model_version": result["model_version"],
        "player_forecast_count": len(result["player_forecasts"]),
        "provider_sha256": result["source_archives"][0]["raw_sha256"],
        "bootstrap_sha256": result["source_archives"][1]["raw_sha256"],
        "manager_data_included": False,
        "decision_weight": 0.0,
        "production_eligible": False,
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
