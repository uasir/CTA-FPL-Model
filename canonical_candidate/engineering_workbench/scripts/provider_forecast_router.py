#!/usr/bin/env python3
"""Shared routing boundary for the five active external forecast providers.

Provider snapshots are normalized once, checked against the active registry,
and routed without blending or silently changing provider semantics.
"""
from __future__ import annotations

from typing import Any, Mapping

from canonical_forecast_recommendation_adapter import build_recommendation_forecast_payload
from canonical_provider_forecast_contract import normalize_provider_snapshot
from forecast_provider_registry import ProviderRegistryError, get_active_provider


class ProviderForecastRoutingError(ValueError):
    """Raised when a snapshot cannot be assigned safely to the active interface."""


def _validate_registry_identity(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    provider = snapshot["provider"]
    try:
        spec = get_active_provider(provider["name"])
    except ProviderRegistryError as exc:
        raise ProviderForecastRoutingError(str(exc)) from exc

    if provider["product"] != spec["product"]:
        raise ProviderForecastRoutingError(
            f"provider product mismatch for {spec['name']}: "
            f"expected {spec['product']!r}, received {provider['product']!r}"
        )

    declared_variants = spec.get("forecast_variants")
    allowed = (
        {item["variant_id"] for item in declared_variants}
        if declared_variants
        else {spec["forecast_variant"]}
    )
    if provider["variant"] not in allowed:
        raise ProviderForecastRoutingError(
            f"unregistered forecast variant for {spec['name']}: {provider['variant']!r}"
        )
    return spec


def route_provider_forecast(
    payload: Mapping[str, Any],
    *,
    player_metadata: list[Mapping[str, Any]] | None = None,
    as_of_utc: str | None = None,
    forecast_horizon_gameweeks: int = 1,
) -> dict[str, Any]:
    """Normalize and route one provider snapshot through the shared interface.

    Diagnostic snapshots and fixture-grain snapshots remain available as
    canonical research inputs, but are not passed to the recommendation adapter.
    Player-Gameweek snapshots are adapted only when metadata and an as-of time
    are explicitly supplied.
    """
    try:
        canonical = normalize_provider_snapshot(payload)
    except (TypeError, ValueError) as exc:
        raise ProviderForecastRoutingError(f"invalid provider snapshot: {exc}") from exc

    spec = _validate_registry_identity(canonical)
    result: dict[str, Any] = {
        "interface_version": "1.0.0",
        "provider_id": spec["provider_id"],
        "provider": canonical["provider"],
        "target_gameweek": canonical["target_gameweek"],
        "snapshot_id": canonical["snapshot_id"],
        "grain": canonical["grain"],
        "routing_status": "CANONICAL_ONLY",
        "decision_eligible": False,
        "canonical_snapshot": canonical,
        "recommendation_payload": None,
        "routing_reason": None,
    }

    if not spec.get("decision_capture_eligible", False):
        result["routing_status"] = "DIAGNOSTIC_ONLY"
        result["routing_reason"] = "PROVIDER_NOT_APPROVED_FOR_DECISION_CAPTURE"
        return result

    if not canonical["decision_eligible"]:
        result["routing_status"] = "DIAGNOSTIC_ONLY"
        result["routing_reason"] = canonical["eligibility_reason"]
        return result

    if canonical["grain"] != "player_gameweek":
        result["routing_status"] = "EXPLICIT_PLAYER_GAMEWEEK_TRANSFORM_REQUIRED"
        result["routing_reason"] = (
            "Fixture-grain forecasts are preserved; aggregation must be an "
            "explicit provider-aware transformation before recommendation use."
        )
        return result

    coverage = canonical["coverage"]
    if (
        coverage.get("identity_resolution_status") != "VERIFIED"
        or coverage.get("identity_mapped_count") != coverage.get("row_count")
    ):
        result["routing_status"] = "DIAGNOSTIC_ONLY"
        result["routing_reason"] = "IDENTITY_PROVENANCE_NOT_VERIFIED"
        return result

    result["routing_status"] = "READY_FOR_RECOMMENDATION_ADAPTER"
    result["decision_eligible"] = True
    if player_metadata is not None or as_of_utc is not None:
        if player_metadata is None or as_of_utc is None:
            raise ProviderForecastRoutingError(
                "player_metadata and as_of_utc must be supplied together"
            )
        try:
            result["recommendation_payload"] = build_recommendation_forecast_payload(
                canonical,
                player_metadata,
                as_of_utc=as_of_utc,
                forecast_horizon_gameweeks=forecast_horizon_gameweeks,
            )
        except (TypeError, ValueError, KeyError) as exc:
            raise ProviderForecastRoutingError(
                f"recommendation adapter rejected snapshot: {exc}"
            ) from exc
        result["routing_status"] = "RECOMMENDATION_PAYLOAD_READY"
    return result
