#!/usr/bin/env python3
"""Authoritative registry for the five active conventional forecast providers.

The registry describes integration readiness; it does not imply that a live
capture exists or that a provider is approved for production decisions.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


ACTIVE_PROVIDER_SPECS: tuple[dict[str, Any], ...] = (
    {
        "provider_id": "fpl_cat",
        "name": "FPL Cat",
        "product": "projections",
        "native_grain": "player_gameweek",
        "forecast_variant": "provider_native_xp",
        "integration_state": "existing_adapter",
        "strict_pit_status": "provider_timestamp_supported",
        "data_policy": "existing_source_terms",
    },
    {
        "provider_id": "sideline_quant",
        "name": "Sideline Quant",
        "product": "gameweek_projections",
        "native_grain": "player_fixture",
        "forecast_variant": "provider_native_xp",
        "integration_state": "raw_capture_and_parser_implemented_live_capture_unverified",
        "strict_pit_status": "provider_generation_timestamp_required",
        "data_policy": "cc_by_4_0_with_attribution_for_provider_data",
    },
    {
        "provider_id": "fplrogue",
        "name": "FPLRogue",
        "product": "accepted_projections_release",
        "native_grain": "player_gameweek",
        "forecast_variant": "provider_native_xpts",
        "integration_state": "raw_capture_implemented_schema_mapping_pending",
        "strict_pit_status": "generation_timestamp_semantics_unverified",
        "data_policy": "source_terms_review_required_before_redistribution",
    },
    {
        "provider_id": "fpl_lucho",
        "name": "FPL Lucho",
        "product": "forecast_csv",
        "native_grain": "player_gameweek",
        "forecast_variant": "served_odds_anchored_xp",
        "integration_state": "private_raw_intake_implemented_live_schema_unverified",
        "strict_pit_status": "served_forecast_generation_timestamp_unverified",
        "data_policy": "private_access_controlled_intake_no_public_payloads",
    },
    {
        "provider_id": "fpl_wildcard",
        "name": "FPL Wildcard",
        "product": "projection_csv",
        "native_grain": "player_gameweek",
        "forecast_variant": "provider_native_xpts",
        "integration_state": "private_parser_implemented_live_payload_unverified",
        "strict_pit_status": "provider_generation_timestamp_required",
        "data_policy": "private_internal_handling_no_redistribution_or_public_artifacts",
    },
)

EXCLUDED_PROVIDERS: tuple[str, ...] = ("FPL Forecaster", "FPL Review")
RESEARCH_ONLY_CANDIDATES: tuple[str, ...] = ("FPLWise", "RotoWire")

_BY_ID = {spec["provider_id"]: spec for spec in ACTIVE_PROVIDER_SPECS}
_BY_NAME = {spec["name"].casefold(): spec for spec in ACTIVE_PROVIDER_SPECS}


class ProviderRegistryError(ValueError):
    """Raised when a provider is outside the agreed active integration set."""


def list_active_providers() -> list[dict[str, Any]]:
    """Return a defensive copy of the five active provider specifications."""
    return deepcopy(list(ACTIVE_PROVIDER_SPECS))


def get_active_provider(provider: str) -> dict[str, Any]:
    """Resolve an active provider by stable ID or exact display name."""
    if not isinstance(provider, str) or not provider.strip():
        raise ProviderRegistryError("provider must be a non-empty name or provider_id")
    key = provider.strip().casefold()
    spec = _BY_ID.get(key) or _BY_NAME.get(key)
    if spec is None:
        raise ProviderRegistryError(f"provider is not in the active five-provider set: {provider}")
    return deepcopy(spec)


def require_active_provider(provider: str) -> str:
    """Validate provider identity and return its canonical display name."""
    return get_active_provider(provider)["name"]
