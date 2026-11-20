#!/usr/bin/env python3
"""Strict adapter from canonical external forecasts to recommendation inputs.

This adapter joins provider values to a separately captured FPL player metadata
snapshot. It does not alter xP, aggregate fixture rows, infer missing minutes,
or claim that an external forecast has been validated by CTA.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from canonical_provider_forecast_contract import ForecastContractError


class ForecastAdapterError(ValueError):
    """Raised when a canonical forecast cannot safely feed a decision engine."""


def _utc(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ForecastAdapterError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ForecastAdapterError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ForecastAdapterError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def build_recommendation_forecast_payload(
    snapshot: Mapping[str, Any],
    player_metadata: list[Mapping[str, Any]],
    *,
    as_of_utc: str,
    forecast_horizon_gameweeks: int = 1,
) -> dict[str, Any]:
    """Join one eligible player-GW snapshot to explicit FPL metadata.

    Metadata rows require fpl_element_id, price (in £), position, team_id and
    expected_minutes. Provider expected_points are copied unchanged.
    """
    if not isinstance(snapshot, Mapping):
        raise ForecastAdapterError("snapshot must be a mapping")
    if snapshot.get("grain") != "player_gameweek":
        raise ForecastAdapterError(
            "decision adapter requires player_gameweek grain; fixture aggregation is not implicit"
        )
    if snapshot.get("decision_eligible") is not True:
        raise ForecastAdapterError("snapshot is diagnostic-only and cannot feed a strict decision run")
    if isinstance(forecast_horizon_gameweeks, bool) or not isinstance(forecast_horizon_gameweeks, int) or forecast_horizon_gameweeks < 1:
        raise ForecastAdapterError("forecast_horizon_gameweeks must be a positive integer")

    captured = _utc(snapshot["timing"]["captured_at_utc"], "snapshot.timing.captured_at_utc")
    as_of = _utc(as_of_utc, "as_of_utc")
    if captured > as_of:
        raise ForecastAdapterError("snapshot capture cannot be later than as_of_utc")
    deadline = _utc(snapshot["timing"]["deadline_utc"], "snapshot.timing.deadline_utc")
    if as_of >= deadline:
        raise ForecastAdapterError("decision as_of_utc must be strictly before the FPL deadline")
    age_hours = (as_of - captured).total_seconds() / 3600
    freshness = "FRESH_WITHIN_24H" if age_hours <= 24 else "STALE_OVER_24H"

    if not isinstance(player_metadata, list) or not player_metadata:
        raise ForecastAdapterError("player_metadata must be a non-empty list")
    metadata_by_id: dict[int, Mapping[str, Any]] = {}
    for index, row in enumerate(player_metadata):
        if not isinstance(row, Mapping):
            raise ForecastAdapterError(f"player_metadata[{index}] must be a mapping")
        player_id = row.get("fpl_element_id")
        if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id < 1:
            raise ForecastAdapterError(f"player_metadata[{index}].fpl_element_id must be a positive integer")
        if player_id in metadata_by_id:
            raise ForecastAdapterError(f"duplicate FPL metadata ID: {player_id}")
        metadata_by_id[player_id] = row

    players = []
    missing_metadata = []
    for record in snapshot["records"]:
        player_id = record["fpl_element_id"]
        meta = metadata_by_id.get(player_id)
        if meta is None:
            missing_metadata.append(player_id)
            continue
        required = ("price", "position", "team_id", "expected_minutes")
        missing = [field for field in required if field not in meta or meta[field] is None]
        if missing:
            raise ForecastAdapterError(
                f"metadata for FPL element {player_id} missing: {', '.join(missing)}"
            )
        players.append({
            "fpl_element_id": player_id,
            "expected_points": record["expected_points"],
            "expected_minutes": meta["expected_minutes"],
            "price": meta["price"],
            "position": meta["position"],
            "team_id": meta["team_id"],
        })

    if missing_metadata:
        raise ForecastAdapterError(
            "missing FPL metadata for forecast IDs: " + ", ".join(map(str, missing_metadata[:20]))
        )
    if not players:
        raise ForecastAdapterError("no forecast rows joined to FPL metadata")

    provider = snapshot["provider"]
    version = provider.get("version") or "version-unreported"
    model_version = (
        f"external:{provider['name']}:{provider['product']}:"
        f"{provider['variant']}:{version}"
    )
    point_in_time = (
        "VERIFIED" if snapshot["timing"]["point_in_time_status"] == "VERIFIED_PRE_DEADLINE"
        else "NOT_VERIFIED"
    )
    limitations = [
        "External provider forecast values are preserved without CTA recalibration.",
        "CTA has not independently validated or promoted this provider forecast through M2.",
        "This adapter does not aggregate player-fixture forecasts or infer missing player metadata.",
    ]
    if freshness != "FRESH_WITHIN_24H":
        limitations.append("Snapshot is older than 24 hours at decision time.")

    return {
        "forecast_snapshot_id": snapshot["snapshot_id"],
        "model_version": model_version,
        "forecast_horizon_gameweeks": forecast_horizon_gameweeks,
        "forecast_quality": {
            "validation_status": "EXPLORATORY_ONLY",
            "point_in_time_status": point_in_time,
            "data_coverage": {
                "provider": provider["name"],
                "product": provider["product"],
                "variant": provider["variant"],
                "provider_version": provider.get("version"),
                "season": snapshot["season"],
                "target_gameweek": snapshot["target_gameweek"],
                "provider_generated_at_utc": snapshot["timing"]["generated_at_utc"],
                "captured_at_utc": snapshot["timing"]["captured_at_utc"],
                "target_deadline_utc": snapshot["timing"]["deadline_utc"],
                "freshness_status": freshness,
                "source_url": snapshot["source"]["url"],
                "raw_snapshot_id": snapshot["source"]["raw_snapshot_id"],
                "raw_sha256": snapshot["source"]["raw_sha256"],
                "input_row_count": len(snapshot["records"]),
                "joined_player_count": len(players),
                "missing_metadata_count": len(missing_metadata),
            },
            "limitations": limitations,
        },
        "player_forecasts": players,
    }
