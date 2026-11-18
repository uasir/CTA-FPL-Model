#!/usr/bin/env python3
"""Strict input-boundary contracts for CTA's independent recommendation systems.

This module validates request shape only. It deliberately does not generate
rankings or recommendations while the shared forecast layer is not validated.
"""
from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

CONTRACT_VERSION = "1.0.0"

GENERAL_FORBIDDEN_FIELDS = frozenset({
    "squad", "squad_snapshot", "bank", "free_transfers", "chips",
    "formation", "starting_xi", "bench_order", "manager_rank",
    "rank_target", "personal_risk_profile", "personal_preferences",
    "manager_id", "manager_entry_id", "team_id_for_manager",
})

SHARED_REQUIRED_FIELDS = (
    "forecast_snapshot_id",
    "model_version",
    "forecast_horizon_gameweeks",
    "forecast_quality",
    "player_forecasts",
)

PERSONAL_REQUIRED_FIELDS = (
    "squad_snapshot",
    "bank",
    "free_transfers",
    "personal_risk_profile",
)


class RecommendationContractError(ValueError):
    """Raised when a recommendation request violates its system contract."""


def _require_mapping(payload: Mapping[str, Any], name: str) -> None:
    if not isinstance(payload, Mapping):
        raise RecommendationContractError(f"{name} must be a mapping")


def _nested_forbidden_fields(value: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            if key_text in GENERAL_FORBIDDEN_FIELDS:
                found.append(child_path)
            found.extend(_nested_forbidden_fields(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_nested_forbidden_fields(child, f"{path}[{index}]"))
    return found


def _validate_shared(payload: Mapping[str, Any]) -> None:
    missing = [field for field in SHARED_REQUIRED_FIELDS if field not in payload]
    if missing:
        raise RecommendationContractError(
            f"Missing shared forecast fields: {', '.join(missing)}"
        )
    for field in ("forecast_snapshot_id", "model_version"):
        if not isinstance(payload[field], str) or not payload[field].strip():
            raise RecommendationContractError(f"{field} must be a non-empty string")
    horizon = payload["forecast_horizon_gameweeks"]
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise RecommendationContractError(
            "forecast_horizon_gameweeks must be a positive integer"
        )
    quality = payload["forecast_quality"]
    if not isinstance(quality, Mapping):
        raise RecommendationContractError("forecast_quality must be a mapping")
    if not isinstance(quality.get("validation_status"), str) or quality["validation_status"] not in {"EXPLORATORY_ONLY", "VALIDATED", "UNAVAILABLE"}:
        raise RecommendationContractError("forecast_quality.validation_status is invalid")
    if not isinstance(quality.get("point_in_time_status"), str) or quality["point_in_time_status"] not in {"VERIFIED", "NOT_VERIFIED", "NOT_APPLICABLE"}:
        raise RecommendationContractError("forecast_quality.point_in_time_status is invalid")
    if not isinstance(quality.get("data_coverage"), Mapping):
        raise RecommendationContractError("forecast_quality.data_coverage must be a mapping")
    if not isinstance(quality.get("limitations"), list):
        raise RecommendationContractError("forecast_quality.limitations must be a list")
    forecasts = payload["player_forecasts"]
    if not isinstance(forecasts, list) or not forecasts:
        raise RecommendationContractError("player_forecasts must be a non-empty list")
    seen: set[str] = set()
    for index, player in enumerate(forecasts):
        if not isinstance(player, Mapping):
            raise RecommendationContractError(
                f"player_forecasts[{index}] must be a mapping"
            )
        element_id = player.get("fpl_element_id")
        if element_id is None or str(element_id).strip() == "":
            raise RecommendationContractError(
                f"player_forecasts[{index}] is missing fpl_element_id"
            )
        if isinstance(element_id, bool) or not isinstance(element_id, int) or element_id < 1:
            raise RecommendationContractError(
                f"player_forecasts[{index}].fpl_element_id must be a positive integer"
            )
        key = str(element_id)
        if key in seen:
            raise RecommendationContractError(
                f"Duplicate forecast for FPL element ID {key}"
            )
        seen.add(key)
        expected_points = player.get("expected_points")
        expected_minutes = player.get("expected_minutes")
        price = player.get("price")
        team_id = player.get("team_id")
        position = player.get("position")
        for field, value in (
            ("expected_points", expected_points),
            ("expected_minutes", expected_minutes),
            ("price", price),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise RecommendationContractError(
                    f"player_forecasts[{index}].{field} must be a finite number"
                )
        if expected_minutes < 0:
            raise RecommendationContractError(
                f"player_forecasts[{index}].expected_minutes cannot be negative"
            )
        if price <= 0:
            raise RecommendationContractError(
                f"player_forecasts[{index}].price must be positive"
            )
        if isinstance(team_id, bool) or not isinstance(team_id, int) or team_id < 1:
            raise RecommendationContractError(
                f"player_forecasts[{index}].team_id must be a positive integer"
            )
        if not isinstance(position, str) or position not in {"GKP", "DEF", "MID", "FWD"}:
            raise RecommendationContractError(
                f"player_forecasts[{index}].position is invalid"
            )
        if "effective_ownership_pct" in player:
            value = player["effective_ownership_pct"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value < 0:
                raise RecommendationContractError(
                    f"player_forecasts[{index}].effective_ownership_pct must be non-negative"
                )
        if "points_variance" in player:
            value = player["points_variance"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value < 0:
                raise RecommendationContractError(
                    f"player_forecasts[{index}].points_variance must be non-negative"
                )
        if "availability_probability" in player:
            value = player["availability_probability"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or not 0 <= value <= 1:
                raise RecommendationContractError(
                    f"player_forecasts[{index}].availability_probability must be between 0 and 1"
                )


def validate_general_market_request(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a squad-independent market-ranking request."""
    _require_mapping(payload, "general_market request")
    forbidden = sorted(_nested_forbidden_fields(payload))
    if forbidden:
        raise RecommendationContractError(
            "general_market must not receive personal fields: " + ", ".join(forbidden)
        )
    _validate_shared(payload)
    filters = payload.get("filters", {})
    if not isinstance(filters, Mapping):
        raise RecommendationContractError("filters must be a mapping")
    return {
        "system": "general_market",
        "contract_version": CONTRACT_VERSION,
        "forecast_snapshot_id": payload["forecast_snapshot_id"],
        "model_version": payload["model_version"],
        "forecast_horizon_gameweeks": payload["forecast_horizon_gameweeks"],
        "forecast_quality": payload["forecast_quality"],
        "player_forecasts": payload["player_forecasts"],
        "filters": filters,
    }


def validate_personal_squad_request(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a manager-specific squad optimisation request."""
    _require_mapping(payload, "personal_squad request")
    _validate_shared(payload)
    missing = [field for field in PERSONAL_REQUIRED_FIELDS if field not in payload]
    if missing:
        raise RecommendationContractError(
            f"Missing personal squad fields: {', '.join(missing)}"
        )

    squad = payload["squad_snapshot"]
    if not isinstance(squad, list) or len(squad) != 15:
        raise RecommendationContractError("squad_snapshot must contain exactly 15 players")
    ids: set[str] = set()
    for index, player in enumerate(squad):
        if not isinstance(player, Mapping):
            raise RecommendationContractError(f"squad_snapshot[{index}] must be a mapping")
        element_id = player.get("fpl_element_id")
        purchase_price = player.get("purchase_price")
        if isinstance(element_id, bool) or not isinstance(element_id, int) or element_id < 1:
            raise RecommendationContractError(
                f"squad_snapshot[{index}].fpl_element_id must be a positive integer"
            )
        key = str(element_id)
        if key in ids:
            raise RecommendationContractError(f"Duplicate squad FPL element ID {key}")
        ids.add(key)
        if (isinstance(purchase_price, bool)
                or not isinstance(purchase_price, (int, float))
                or not math.isfinite(float(purchase_price))):
            raise RecommendationContractError(
                f"squad_snapshot[{index}].purchase_price must be numeric"
            )
        if purchase_price <= 0:
            raise RecommendationContractError(
                f"squad_snapshot[{index}].purchase_price must be positive"
            )

    forecast_by_id = {
        player["fpl_element_id"]: player for player in payload["player_forecasts"]
    }
    position_counts = {"GKP": 0, "DEF": 0, "MID": 0, "FWD": 0}
    team_counts: dict[int, int] = {}
    for player in squad:
        element_id = player["fpl_element_id"]
        forecast = forecast_by_id.get(element_id)
        if forecast is None:
            raise RecommendationContractError(
                f"Missing forecast for owned FPL element ID {element_id}"
            )
        position_counts[forecast["position"]] += 1
        team_id = forecast["team_id"]
        team_counts[team_id] = team_counts.get(team_id, 0) + 1
    expected_positions = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
    if position_counts != expected_positions:
        raise RecommendationContractError(
            "squad position composition must be 2 GKP, 5 DEF, 5 MID and 3 FWD"
        )
    if any(count > 3 for count in team_counts.values()):
        raise RecommendationContractError("squad cannot contain more than 3 players from one team")

    bank = payload["bank"]
    if (isinstance(bank, bool) or not isinstance(bank, (int, float))
            or not math.isfinite(float(bank)) or bank < 0):
        raise RecommendationContractError("bank must be a non-negative number")
    transfers = payload["free_transfers"]
    if isinstance(transfers, bool) or not isinstance(transfers, int) or transfers < 0:
        raise RecommendationContractError("free_transfers must be a non-negative integer")
    risk = payload["personal_risk_profile"]
    if not isinstance(risk, (str, Mapping)) or (isinstance(risk, str) and not risk.strip()):
        raise RecommendationContractError(
            "personal_risk_profile must be a non-empty string or mapping"
        )

    return {
        "system": "personal_squad",
        "contract_version": CONTRACT_VERSION,
        "forecast_snapshot_id": payload["forecast_snapshot_id"],
        "model_version": payload["model_version"],
        "forecast_horizon_gameweeks": payload["forecast_horizon_gameweeks"],
        "forecast_quality": payload["forecast_quality"],
        "player_forecasts": payload["player_forecasts"],
        "squad_snapshot": payload["squad_snapshot"],
        "bank": bank,
        "free_transfers": transfers,
        "personal_risk_profile": risk,
        "chips": payload.get("chips", []),
        "formation": payload.get("formation"),
        "starting_xi": payload.get("starting_xi"),
        "bench_order": payload.get("bench_order"),
        "manager_rank": payload.get("manager_rank"),
        "rank_target": payload.get("rank_target"),
        "personal_preferences": payload.get("personal_preferences", {}),
    }
