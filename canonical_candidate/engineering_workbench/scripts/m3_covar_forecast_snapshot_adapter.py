#!/usr/bin/env python3
"""Extract a manager-free, exact M3 forecast bundle for CoVar research.

The adapter consumes the sealed M3 evidence and its result, validates source
hashes/timestamps, rebuilds the same conventional M3 player forecast payload,
and emits only forecast inputs. Manager IDs, squads, bank, transfers and frozen
decisions are deliberately excluded.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Mapping

from canonical_provider_forecast_contract import normalize_provider_snapshot
from canonical_forecast_recommendation_adapter import build_recommendation_forecast_payload


class M3CoVarForecastAdapterError(ValueError):
    """The M3 forecast bundle cannot be extracted safely."""


def _utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise M3CoVarForecastAdapterError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise M3CoVarForecastAdapterError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise M3CoVarForecastAdapterError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _decode_source(source: Mapping[str, Any], source_type: str) -> tuple[bytes, dict[str, Any]]:
    if source.get("source_type") != source_type:
        raise M3CoVarForecastAdapterError(f"expected {source_type} source archive")
    encoded = source.get("raw_payload_base64")
    if not isinstance(encoded, str) or not encoded:
        raise M3CoVarForecastAdapterError(f"{source_type} raw payload is missing")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise M3CoVarForecastAdapterError(f"{source_type} raw payload is not valid base64") from exc
    digest = hashlib.sha256(raw).hexdigest()
    if source.get("raw_sha256") != digest:
        raise M3CoVarForecastAdapterError(f"{source_type} raw payload SHA-256 mismatch")
    if not isinstance(source.get("raw_snapshot_id"), str) or not source["raw_snapshot_id"].strip():
        raise M3CoVarForecastAdapterError(f"{source_type} raw_snapshot_id is required")
    if not isinstance(source.get("source_url"), str) or not source["source_url"].strip():
        raise M3CoVarForecastAdapterError(f"{source_type} source_url is required")
    captured = _utc(source.get("captured_at_utc"), f"{source_type}.captured_at_utc")
    return raw, {
        "source_type": source_type,
        "source_url": source["source_url"],
        "raw_snapshot_id": source["raw_snapshot_id"],
        "raw_sha256": digest,
        "captured_at_utc": captured.isoformat(),
        "raw_payload_base64": encoded,
    }


def extract_m3_covar_forecast_bundle(
    evidence_bundle: Mapping[str, Any],
    m3_run_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a sanitized CoVar forecast bundle from one frozen M3 run."""
    if not isinstance(evidence_bundle, Mapping) or len(evidence_bundle) != 1:
        raise M3CoVarForecastAdapterError("evidence bundle must contain exactly one Gameweek manifest")
    if not isinstance(m3_run_result, Mapping):
        raise M3CoVarForecastAdapterError("m3_run_result must be an object")
    if m3_run_result.get("run_type") != "M3_CONVENTIONAL_PERSONAL_SQUAD_RECOMMENDATION":
        raise M3CoVarForecastAdapterError("run result is not the conventional M3 recommendation")
    gw_key, manifest = next(iter(evidence_bundle.items()))
    if not isinstance(manifest, Mapping):
        raise M3CoVarForecastAdapterError("Gameweek manifest must be an object")
    try:
        gw = int(gw_key)
        manifest_gw = int(manifest.get("target_gameweek"))
    except (TypeError, ValueError) as exc:
        raise M3CoVarForecastAdapterError("target Gameweek must be an integer") from exc
    if gw < 1 or manifest_gw != gw or m3_run_result.get("target_gameweek") != gw:
        raise M3CoVarForecastAdapterError("evidence and M3 result Gameweek do not match")
    season = manifest.get("season")
    if not isinstance(season, str) or not season.strip() or m3_run_result.get("season", season) != season:
        raise M3CoVarForecastAdapterError("season must match between evidence and M3 result")
    provider = manifest.get("provider_snapshot")
    metadata = manifest.get("player_metadata")
    metadata_provenance = manifest.get("player_metadata_provenance")
    sources = manifest.get("sources")
    if not isinstance(provider, Mapping) or not isinstance(metadata, list) or not isinstance(metadata_provenance, Mapping):
        raise M3CoVarForecastAdapterError("M3 provider snapshot and FPL metadata are required")
    if not isinstance(sources, list):
        raise M3CoVarForecastAdapterError("M3 source archive list is required")

    source_by_type = {}
    for source in sources:
        if not isinstance(source, Mapping):
            raise M3CoVarForecastAdapterError("each M3 source archive must be an object")
        source_type = source.get("source_type")
        if source_type in source_by_type:
            raise M3CoVarForecastAdapterError(f"duplicate M3 source archive type {source_type}")
        source_by_type[source_type] = source
    if "provider_forecast" not in source_by_type or "player_metadata" not in source_by_type:
        raise M3CoVarForecastAdapterError("provider_forecast and player_metadata source archives are required")

    provider_raw, provider_archive = _decode_source(source_by_type["provider_forecast"], "provider_forecast")
    metadata_raw, metadata_archive = _decode_source(source_by_type["player_metadata"], "player_metadata")
    normalized = normalize_provider_snapshot(provider)
    if normalized.get("decision_eligible") is not True:
        raise M3CoVarForecastAdapterError("M3 provider forecast is not point-in-time decision eligible")
    if normalized.get("snapshot_id") != m3_run_result.get("provider_snapshot_id"):
        raise M3CoVarForecastAdapterError("provider snapshot ID does not match frozen M3 result")
    if normalized.get("source", {}).get("raw_sha256") != provider_archive["raw_sha256"]:
        raise M3CoVarForecastAdapterError("provider source hash does not match M3 source archive")
    if normalized.get("source", {}).get("raw_snapshot_id") != provider_archive["raw_snapshot_id"]:
        raise M3CoVarForecastAdapterError("provider source snapshot ID does not match M3 source archive")
    if normalized.get("source", {}).get("url") != provider_archive["source_url"]:
        raise M3CoVarForecastAdapterError("provider source URL does not match M3 source archive")
    if _utc(normalized["timing"]["captured_at_utc"], "provider.captured_at_utc") != _utc(provider_archive["captured_at_utc"], "provider archive captured_at_utc"):
        raise M3CoVarForecastAdapterError("provider capture time does not match M3 source archive")
    if _utc(normalized["timing"]["generated_at_utc"], "provider.generated_at_utc") != _utc(source_by_type["provider_forecast"].get("generated_at_utc"), "provider archive generated_at_utc"):
        raise M3CoVarForecastAdapterError("provider generation time does not match M3 source archive")

    metadata_hash = metadata_provenance.get("raw_sha256")
    if metadata_hash != metadata_archive["raw_sha256"]:
        raise M3CoVarForecastAdapterError("FPL metadata hash does not match M3 source archive")
    if metadata_provenance.get("raw_snapshot_id") != metadata_archive["raw_snapshot_id"]:
        raise M3CoVarForecastAdapterError("FPL metadata snapshot ID does not match M3 source archive")
    if metadata_provenance.get("source_url") != metadata_archive["source_url"]:
        raise M3CoVarForecastAdapterError("FPL metadata source URL does not match M3 source archive")
    metadata_captured = _utc(metadata_provenance.get("captured_at_utc"), "player_metadata_provenance.captured_at_utc")
    if metadata_captured != _utc(metadata_archive["captured_at_utc"], "player_metadata.captured_at_utc"):
        raise M3CoVarForecastAdapterError("FPL metadata capture time does not match M3 source archive")
    if metadata_archive["source_url"] != "https://fantasy.premierleague.com/api/bootstrap-static/":
        raise M3CoVarForecastAdapterError("FPL metadata archive must be official bootstrap-static")
    if metadata_provenance.get("row_count") != len(metadata):
        raise M3CoVarForecastAdapterError("FPL metadata row_count does not match metadata rows")
    try:
        bootstrap_raw = json.loads(metadata_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise M3CoVarForecastAdapterError("archived FPL metadata bytes are not valid JSON") from exc
    raw_elements = bootstrap_raw.get("elements") if isinstance(bootstrap_raw, Mapping) else None
    if not isinstance(raw_elements, list):
        raise M3CoVarForecastAdapterError("archived bootstrap-static payload has no elements list")
    raw_by_id = {}
    for raw_row in raw_elements:
        if not isinstance(raw_row, Mapping):
            raise M3CoVarForecastAdapterError("archived bootstrap contains a malformed player row")
        raw_id = raw_row.get("id")
        if isinstance(raw_id, bool) or not isinstance(raw_id, int) or raw_id in raw_by_id:
            raise M3CoVarForecastAdapterError("archived bootstrap contains invalid or duplicate player IDs")
        raw_by_id[raw_id] = raw_row
    position_names = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
    seen_metadata_ids = set()
    for row in metadata:
        if not isinstance(row, Mapping):
            raise M3CoVarForecastAdapterError("each FPL metadata row must be an object")
        pid = row.get("fpl_element_id")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid in seen_metadata_ids:
            raise M3CoVarForecastAdapterError("FPL metadata contains invalid or duplicate player IDs")
        seen_metadata_ids.add(pid)
        raw_row = raw_by_id.get(pid)
        if raw_row is None:
            raise M3CoVarForecastAdapterError(f"FPL metadata player {pid} missing from archived bootstrap")
        if row.get("team_id") != raw_row.get("team") or row.get("position") != position_names.get(raw_row.get("element_type")):
            raise M3CoVarForecastAdapterError(f"FPL metadata identity mismatch for player {pid}")
        price = row.get("price")
        now_cost = raw_row.get("now_cost")
        if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(float(price)):
            raise M3CoVarForecastAdapterError(f"FPL metadata price is invalid for player {pid}")
        if isinstance(now_cost, bool) or not isinstance(now_cost, int) or abs(float(price) - now_cost / 10.0) > 1e-9:
            raise M3CoVarForecastAdapterError(f"FPL metadata price mismatch for player {pid}")

    as_of = _utc(manifest.get("decision_as_of_utc"), "decision_as_of_utc")
    deadline = _utc(manifest.get("deadline_utc"), "deadline_utc")
    if as_of >= deadline:
        raise M3CoVarForecastAdapterError("M3 decision as-of must precede the FPL deadline")
    if _utc(m3_run_result.get("decision_as_of_utc"), "M3 result decision_as_of_utc") != as_of:
        raise M3CoVarForecastAdapterError("M3 result decision-as-of does not match evidence")
    if _utc(m3_run_result.get("deadline_utc"), "M3 result deadline_utc") != deadline:
        raise M3CoVarForecastAdapterError("M3 result deadline does not match evidence")
    for name, source in (("provider_forecast", provider_archive), ("player_metadata", metadata_archive)):
        captured = _utc(source["captured_at_utc"], f"{name}.captured_at_utc")
        if captured > as_of:
            raise M3CoVarForecastAdapterError(f"{name} source was captured after M3 decision as-of")
    provider_generated = _utc(normalized["timing"]["generated_at_utc"], "provider.generated_at_utc")
    if provider_generated > as_of:
        raise M3CoVarForecastAdapterError("provider forecast was generated after M3 decision as-of")

    recommendation = m3_run_result.get("recommendation")
    if not isinstance(recommendation, Mapping):
        raise M3CoVarForecastAdapterError("M3 result recommendation is required")
    forecast_id = recommendation.get("forecast_snapshot_id")
    model_version = recommendation.get("model_version")
    if forecast_id != normalized["snapshot_id"]:
        raise M3CoVarForecastAdapterError("M3 recommendation forecast_snapshot_id does not match provider snapshot")
    if not isinstance(model_version, str) or not model_version.strip():
        raise M3CoVarForecastAdapterError("M3 recommendation model_version is required")

    forecast_payload = build_recommendation_forecast_payload(
        normalized, metadata, as_of_utc=manifest["decision_as_of_utc"],
        forecast_horizon_gameweeks=1,
    )
    if forecast_payload.get("forecast_snapshot_id") != forecast_id or forecast_payload.get("model_version") != model_version:
        raise M3CoVarForecastAdapterError("reconstructed M3 forecast identity differs from frozen recommendation")

    return {
        "schema_version": "1.0.0",
        "bundle_type": "M3_CONVENTIONAL_FORECAST_ONLY_COVAR_INPUT",
        "season": season,
        "target_gameweek": gw,
        "mode": "REGULAR_GW",
        "as_of_utc": as_of.isoformat(),
        "deadline_utc": deadline.isoformat(),
        "forecast_snapshot_id": forecast_id,
        "model_version": model_version,
        "provider_snapshot": dict(provider),
        "player_metadata": [dict(row) for row in metadata],
        "player_metadata_provenance": {
            key: metadata_provenance[key]
            for key in ("source_url", "raw_snapshot_id", "raw_sha256", "captured_at_utc", "row_count")
        },
        "player_forecasts": forecast_payload["player_forecasts"],
        "forecast_quality": forecast_payload["forecast_quality"],
        "source_archives": [provider_archive, metadata_archive],
        "privacy": {
            "manager_identity_included": False,
            "manager_squad_included": False,
            "bank_or_transfer_state_included": False,
            "frozen_decision_included": False,
        },
        "point_in_time_status": "M3_SOURCE_TIMESTAMPS_VALIDATED",
        "decision_weight": 0.0,
        "production_eligible": False,
        "limitations": [
            "This is the exact conventional forecast input consumed by the M3 recommendation run.",
            "It is a player-level expected-points/minutes snapshot, not a joint outcome distribution.",
            "M3 provider source bytes are hash-verified against the sealed evidence bundle; the provider's publication time is not independently authenticated here.",
            "The bundle intentionally excludes manager-specific state and recommendation decisions.",
        ],
    }
