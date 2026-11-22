#!/usr/bin/env python3
"""Machine-readable capability registry for approved forecast capture sources.

Capabilities describe inspected capture contracts, not marketing claims.
Fixture-grain and player-Gameweek-grain multi-GW feeds are deliberately
separate contracts and may never be converted into one another.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


class ProviderCapabilityError(ValueError):
    """Raised when a source is unknown or lacks the required capture capability."""


_REGISTRY: dict[str, dict[str, Any]] = {
    "fpl_cat_public_projections": {
        "provider": {"name": "FPL Cat", "product": "projections", "variant": "provider_native_xp", "version": "api/v1"},
        "capture_grain": "player_gameweek",
        "max_explicit_gameweeks_per_capture": 1,
        "fixture_ids": False,
        "explicit_multi_gameweek_panels": False,
        "point_in_time_capture": True,
        "authorized_reproducible_access": True,
        "multi_gameweek_status": "BLOCKED_SINGLE_GAMEWEEK_PLAYER_GRAIN",
        "evidence": "Inspected public /api/v1/projections capture schema and regression tests.",
    },
    "fpl_cat_partner_projections": {
        "provider": {"name": "FPL Cat", "product": "partner_projections", "variant": "provider_native_xp", "version": "partner-api-v1"},
        "capture_grain": "player_gameweek",
        "max_explicit_gameweeks_per_capture": 6,
        "fixture_ids": False,
        "explicit_multi_gameweek_panels": True,
        "point_in_time_capture": True,
        "authorized_reproducible_access": False,
        "license_required": True,
        "access_status": "PENDING_PARTNER_KEY_AND_LICENSE",
        "multi_gameweek_status": "SUPPORTED_PLAYER_GAMEWEEK_AGGREGATE_ONLY_PENDING_ACCESS",
        "evidence": "Inspected FPL Cat Partner API documentation: six explicit player-Gameweek projections, computed_at, deadline and frozen raw response; licensed key required. Fixture-level xP is not supplied.",
    },
    "sideline_quant_public_next_gw": {
        "provider": {"name": "Sideline Quant", "product": "gameweek_projections", "variant": "provider_native_xp", "version": "1.0"},
        "capture_grain": "player_fixture",
        "max_explicit_gameweeks_per_capture": 1,
        "fixture_ids": True,
        "explicit_multi_gameweek_panels": False,
        "point_in_time_capture": False,
        "authorized_reproducible_access": True,
        "multi_gameweek_status": "BLOCKED_NO_REPRODUCIBLE_MULTI_GAMEWEEK_ACCESS",
        "evidence": "Inspected public /data/gw/{gw}/projections.json feed; one next-GW panel; deadline may be null.",
    },
}


def get_provider_capability(source_id: str) -> dict[str, Any]:
    """Return a defensive copy of a registered source capability."""
    if not isinstance(source_id, str) or source_id not in _REGISTRY:
        raise ProviderCapabilityError(f"unknown provider source: {source_id!r}")
    return deepcopy(_REGISTRY[source_id])


def list_provider_capabilities() -> list[dict[str, Any]]:
    """Return all registered sources in stable source-ID order."""
    return [{"source_id": key, **deepcopy(_REGISTRY[key])} for key in sorted(_REGISTRY)]


def _validate_horizon(required_horizon: int) -> None:
    if isinstance(required_horizon, bool) or not isinstance(required_horizon, int) or required_horizon < 5:
        raise ProviderCapabilityError("required_horizon must be an integer of at least five Gameweeks")


def require_multi_gameweek_capture(
    source_id: str, *, required_horizon: int = 5
) -> dict[str, Any]:
    """Fail closed unless registry approves fixture-level multi-GW capture."""
    capability = get_provider_capability(source_id)
    _validate_horizon(required_horizon)
    checks = (
        capability.get("capture_grain") == "player_fixture",
        capability.get("fixture_ids") is True,
        capability.get("explicit_multi_gameweek_panels") is True,
        isinstance(capability.get("max_explicit_gameweeks_per_capture"), int)
        and capability["max_explicit_gameweeks_per_capture"] >= required_horizon,
        capability.get("point_in_time_capture") is True,
        capability.get("authorized_reproducible_access") is True,
    )
    if not all(checks):
        raise ProviderCapabilityError(
            f"{source_id} is not registered for an explicit {required_horizon}-Gameweek "
            f"fixture-level capture ({capability.get('multi_gameweek_status', 'CAPABILITY_UNVERIFIED')})"
        )
    return capability


def require_player_gameweek_multi_gameweek_capture(
    source_id: str, *, required_horizon: int = 5
) -> dict[str, Any]:
    """Fail closed unless a licensed native player-Gameweek panel is approved."""
    capability = get_provider_capability(source_id)
    _validate_horizon(required_horizon)
    checks = (
        capability.get("capture_grain") == "player_gameweek",
        capability.get("fixture_ids") is False,
        capability.get("explicit_multi_gameweek_panels") is True,
        isinstance(capability.get("max_explicit_gameweeks_per_capture"), int)
        and capability["max_explicit_gameweeks_per_capture"] >= required_horizon,
        capability.get("point_in_time_capture") is True,
        capability.get("authorized_reproducible_access") is True,
    )
    if not all(checks):
        raise ProviderCapabilityError(
            f"{source_id} is not registered for an authorised {required_horizon}-Gameweek "
            f"player-Gameweek capture ({capability.get('access_status', capability.get('multi_gameweek_status', 'CAPABILITY_UNVERIFIED'))})"
        )
    return capability


def validate_capture_against_registry(
    source_id: str, capture: Mapping[str, Any]
) -> dict[str, Any]:
    """Check observed capture grain/provider identity against its registered contract."""
    capability = get_provider_capability(source_id)
    if not isinstance(capture, Mapping):
        raise ProviderCapabilityError("capture must be an object")
    if capture.get("provider") != capability["provider"]:
        raise ProviderCapabilityError("capture provider identity does not match registry")
    if capture.get("grain") != capability["capture_grain"]:
        raise ProviderCapabilityError("capture grain does not match registry")
    if (source_id == "fpl_cat_public_projections"
            and capture.get("multi_gameweek_capability", {}).get("decision_eligible_for_multi_gameweek") is True):
        raise ProviderCapabilityError("single-GW public feed cannot claim multi-Gameweek eligibility")
    return capability
