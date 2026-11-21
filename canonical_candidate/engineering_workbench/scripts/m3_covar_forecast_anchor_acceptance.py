"""Acceptance contract for the archived M3 conventional forecast anchor.

This contract deliberately does not interpret player-level xP as a joint
Gameweek distribution. It validates archive bytes and the narrow forecast
anchor metadata needed by the CoVar research pipeline.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from typing import Any, Mapping


class M3ForecastAnchorAcceptanceError(ValueError):
    """The archived M3 forecast anchor is malformed or inconsistent."""


def _utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise M3ForecastAnchorAcceptanceError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise M3ForecastAnchorAcceptanceError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise M3ForecastAnchorAcceptanceError(f"{field} must include a timezone")
    return parsed


def _finite_number(value: Any, field: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise M3ForecastAnchorAcceptanceError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise M3ForecastAnchorAcceptanceError(f"{field} must be finite and within its allowed range")
    return result


def accept_m3_forecast_anchor(
    bundle_bytes: bytes, archive_manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Verify exact archived bytes and accept them only as a player forecast anchor."""
    if not isinstance(bundle_bytes, bytes) or not bundle_bytes:
        raise M3ForecastAnchorAcceptanceError("bundle_bytes must be non-empty bytes")
    if not isinstance(archive_manifest, Mapping):
        raise M3ForecastAnchorAcceptanceError("archive_manifest must be an object")

    digest = hashlib.sha256(bundle_bytes).hexdigest()
    if archive_manifest.get("bundle_sha256") != digest:
        raise M3ForecastAnchorAcceptanceError("forecast bundle SHA-256 does not match archive manifest")
    if archive_manifest.get("bundle_bytes") != len(bundle_bytes):
        raise M3ForecastAnchorAcceptanceError("forecast bundle byte count does not match archive manifest")

    try:
        bundle = json.loads(bundle_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise M3ForecastAnchorAcceptanceError("forecast bundle must be valid UTF-8 JSON") from exc
    if not isinstance(bundle, Mapping):
        raise M3ForecastAnchorAcceptanceError("forecast bundle must be a JSON object")

    expected = {
        "archive_type": "PRIVATE_MANAGER_FREE_M3_COVAR_FORECAST_ARCHIVE",
        "schema_version": "1.0.0",
        "decision_weight": 0.0,
        "production_eligible": False,
        "season": bundle.get("season"),
        "target_gameweek": bundle.get("target_gameweek"),
        "forecast_snapshot_id": bundle.get("forecast_snapshot_id"),
        "model_version": bundle.get("model_version"),
    }
    for field, value in expected.items():
        if archive_manifest.get(field) != value:
            raise M3ForecastAnchorAcceptanceError(f"archive manifest {field} does not match forecast bundle")
    if bundle.get("bundle_type") != "M3_CONVENTIONAL_FORECAST_ONLY_COVAR_INPUT":
        raise M3ForecastAnchorAcceptanceError("bundle is not the conventional M3 forecast-only input")
    if bundle.get("mode") != "REGULAR_GW":
        raise M3ForecastAnchorAcceptanceError("M3 forecast anchor must explicitly be a regular Gameweek")
    if bundle.get("point_in_time_status") != "M3_SOURCE_TIMESTAMPS_VALIDATED":
        raise M3ForecastAnchorAcceptanceError("M3 source timestamps are not validated")
    if bundle.get("decision_weight") != 0.0 or bundle.get("production_eligible") is not False:
        raise M3ForecastAnchorAcceptanceError("M3 forecast anchor must remain research-only")

    privacy = bundle.get("privacy")
    required_privacy = (
        "manager_identity_included", "manager_squad_included",
        "bank_or_transfer_state_included", "frozen_decision_included",
    )
    if not isinstance(privacy, Mapping) or any(privacy.get(key) is not False for key in required_privacy):
        raise M3ForecastAnchorAcceptanceError("all manager-specific privacy flags must be false")

    season = bundle.get("season")
    gw = bundle.get("target_gameweek")
    if not isinstance(season, str) or not season.strip():
        raise M3ForecastAnchorAcceptanceError("season is required")
    if isinstance(gw, bool) or not isinstance(gw, int) or gw < 1:
        raise M3ForecastAnchorAcceptanceError("target_gameweek must be a positive integer")
    if archive_manifest.get("archive_type") != "PRIVATE_MANAGER_FREE_M3_COVAR_FORECAST_ARCHIVE":
        raise M3ForecastAnchorAcceptanceError("archive type is not the private manager-free M3 archive")

    as_of = _utc(bundle.get("as_of_utc"), "as_of_utc")
    deadline = _utc(bundle.get("deadline_utc"), "deadline_utc")
    if as_of >= deadline:
        raise M3ForecastAnchorAcceptanceError("forecast as-of must precede the Gameweek deadline")
    if archive_manifest.get("as_of_utc") != bundle.get("as_of_utc"):
        raise M3ForecastAnchorAcceptanceError("archive as-of timestamp does not match bundle")
    if archive_manifest.get("deadline_utc") != bundle.get("deadline_utc"):
        raise M3ForecastAnchorAcceptanceError("archive deadline does not match bundle")

    sources = bundle.get("source_archives")
    manifest_sources = archive_manifest.get("source_archives")
    if not isinstance(sources, list) or len(sources) != 2 or not isinstance(manifest_sources, list) or len(manifest_sources) != 2:
        raise M3ForecastAnchorAcceptanceError("exactly two source archives are required")
    source_types = set()
    for source in sources:
        if not isinstance(source, Mapping):
            raise M3ForecastAnchorAcceptanceError("source archive entries must be objects")
        source_type = source.get("source_type")
        if source_type not in {"provider_forecast", "player_metadata"} or source_type in source_types:
            raise M3ForecastAnchorAcceptanceError("source archives must contain one provider and one metadata source")
        source_types.add(source_type)
        source_hash = source.get("raw_sha256")
        if not isinstance(source_hash, str) or len(source_hash) != 64 or any(c not in "0123456789abcdef" for c in source_hash):
            raise M3ForecastAnchorAcceptanceError("source archive SHA-256 is invalid")
        captured = _utc(source.get("captured_at_utc"), f"{source_type}.captured_at_utc")
        if captured > as_of:
            raise M3ForecastAnchorAcceptanceError(f"{source_type} was captured after forecast as-of")
        if not isinstance(source.get("raw_payload_base64"), str) or not source["raw_payload_base64"]:
            raise M3ForecastAnchorAcceptanceError(f"{source_type} raw source bytes are missing")
        match = [row for row in manifest_sources if isinstance(row, Mapping) and row.get("source_type") == source_type]
        if len(match) != 1:
            raise M3ForecastAnchorAcceptanceError(f"archive manifest is missing unique {source_type} provenance")
        for field in ("source_url", "raw_snapshot_id", "raw_sha256", "captured_at_utc"):
            if match[0].get(field) != source.get(field):
                raise M3ForecastAnchorAcceptanceError(f"archive manifest {source_type} {field} mismatch")
    if source_types != {"provider_forecast", "player_metadata"}:
        raise M3ForecastAnchorAcceptanceError("provider and official player metadata sources are required")
    metadata_source = next(row for row in sources if row["source_type"] == "player_metadata")
    if metadata_source.get("source_url") != "https://fantasy.premierleague.com/api/bootstrap-static/":
        raise M3ForecastAnchorAcceptanceError("player metadata source must be official FPL bootstrap-static")

    forecasts = bundle.get("player_forecasts")
    if not isinstance(forecasts, list) or not forecasts:
        raise M3ForecastAnchorAcceptanceError("player_forecasts must be a non-empty list")
    seen_ids = set()
    for row in forecasts:
        if not isinstance(row, Mapping):
            raise M3ForecastAnchorAcceptanceError("player forecast rows must be objects")
        player_id = row.get("fpl_element_id")
        if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id < 1 or player_id in seen_ids:
            raise M3ForecastAnchorAcceptanceError("player forecast IDs must be unique positive integers")
        seen_ids.add(player_id)
        _finite_number(row.get("expected_points"), f"player {player_id} expected_points")
        minutes = row.get("expected_minutes")
        if minutes is not None:
            _finite_number(minutes, f"player {player_id} expected_minutes", minimum=0)

    # A player xP snapshot is an input anchor only; no joint-state probability is inferred.
    return {
        "schema_version": "1.0.0",
        "acceptance_status": "ACCEPTED_PLAYER_LEVEL_FORECAST_ANCHOR_ONLY",
        "forecast_snapshot_id": bundle["forecast_snapshot_id"],
        "season": season,
        "target_gameweek": gw,
        "player_forecast_count": len(forecasts),
        "source_archive_count": len(sources),
        "bundle_sha256": digest,
        "joint_distribution_available": False,
        "joint_probabilities_inferred": False,
        "decision_weight": 0.0,
        "production_eligible": False,
    }
