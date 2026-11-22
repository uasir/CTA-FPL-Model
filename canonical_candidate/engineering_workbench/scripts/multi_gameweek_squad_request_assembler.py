#!/usr/bin/env python3
"""Assemble manager-specific HOLD-vs-one-transfer requests from a validated bundle.

The assembler never invents forecasts or prices. It validates the raw
multi-Gameweek forecast payload through the canonical forecast contract, then
enumerates affordable same-position outfield transfers for the supplied
15-player squad and fixed starting XI.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from multi_gameweek_forecast_contract import (
    MultiGameweekForecastError,
    build_multi_gameweek_forecast_bundle,
)
from multi_gameweek_transfer_evaluator import (
    MultiGameweekTransferError,
    evaluate_multi_gameweek_transfer_bundle,
)


class MultiGameweekSquadAssemblyError(ValueError):
    """Raised when manager state or candidate metadata is incomplete."""


def _money(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value < 0:
        raise MultiGameweekSquadAssemblyError(f"{field} must be a finite non-negative number")
    return round(float(value), 2)


def _selling_price(current_price: float, purchase_price: float) -> float:
    current_tenths = int(round(current_price * 10))
    purchase_tenths = int(round(purchase_price * 10))
    if current_tenths <= purchase_tenths:
        return current_tenths / 10.0
    return (purchase_tenths + (current_tenths - purchase_tenths) // 2) / 10.0


def assemble_multi_gameweek_squad_diagnostics(
    forecast_payload: Mapping[str, Any],
    manager_context: Mapping[str, Any],
    starting_xi_ids: list[int],
    current_player_metadata: list[Mapping[str, Any]],
    *,
    hit_cost_points: float = 4.0,
) -> dict[str, Any]:
    """Validate a forecast payload and evaluate every affordable legal transfer.

    current_player_metadata rows require fpl_element_id, position, team_id and
    current price. Squad rows require fpl_element_id and purchase_price.
    """
    try:
        bundle = build_multi_gameweek_forecast_bundle(forecast_payload)
    except MultiGameweekForecastError as exc:
        raise MultiGameweekSquadAssemblyError(f"forecast bundle rejected: {exc}") from exc
    if not isinstance(manager_context, Mapping):
        raise MultiGameweekSquadAssemblyError("manager_context must be an object")
    squad_rows = manager_context.get("squad_snapshot")
    if not isinstance(squad_rows, list) or len(squad_rows) != 15:
        raise MultiGameweekSquadAssemblyError("manager_context.squad_snapshot must contain exactly 15 players")
    squad_ids = []
    purchase_prices = {}
    for row in squad_rows:
        if not isinstance(row, Mapping):
            raise MultiGameweekSquadAssemblyError("squad_snapshot rows must be objects")
        pid = row.get("fpl_element_id")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1 or pid in purchase_prices:
            raise MultiGameweekSquadAssemblyError("squad_snapshot must contain unique positive FPL element IDs")
        if "purchase_price" not in row:
            raise MultiGameweekSquadAssemblyError(f"squad player {pid} is missing purchase_price")
        purchase_prices[pid] = _money(row["purchase_price"], f"squad player {pid} purchase_price")
        squad_ids.append(pid)
    if not isinstance(starting_xi_ids, list) or len(starting_xi_ids) != 11:
        raise MultiGameweekSquadAssemblyError("starting_xi_ids must contain exactly 11 players")
    if any(isinstance(pid, bool) or not isinstance(pid, int) or pid < 1 for pid in starting_xi_ids):
        raise MultiGameweekSquadAssemblyError("starting_xi_ids must contain positive integer IDs")
    if len(set(starting_xi_ids)) != 11 or not set(starting_xi_ids).issubset(set(squad_ids)):
        raise MultiGameweekSquadAssemblyError("starting_xi_ids must be 11 unique members of the current squad")

    bank = _money(manager_context.get("bank"), "manager_context.bank")
    free_transfers = manager_context.get("free_transfers")
    if isinstance(free_transfers, bool) or not isinstance(free_transfers, int) or free_transfers < 0:
        raise MultiGameweekSquadAssemblyError("manager_context.free_transfers must be a non-negative integer")
    hit_cost = _money(hit_cost_points, "hit_cost_points")
    if not isinstance(current_player_metadata, list) or not current_player_metadata:
        raise MultiGameweekSquadAssemblyError("current_player_metadata must be a non-empty list")

    metadata_by_id = {}
    for row in current_player_metadata:
        if not isinstance(row, Mapping):
            raise MultiGameweekSquadAssemblyError("current_player_metadata rows must be objects")
        pid = row.get("fpl_element_id")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1 or pid in metadata_by_id:
            raise MultiGameweekSquadAssemblyError("current_player_metadata IDs must be unique positive integers")
        position = row.get("position")
        team_id = row.get("team_id")
        if position not in {"GKP", "DEF", "MID", "FWD"}:
            raise MultiGameweekSquadAssemblyError(f"player {pid} has invalid position")
        if isinstance(team_id, bool) or not isinstance(team_id, int) or team_id < 1:
            raise MultiGameweekSquadAssemblyError(f"player {pid} has invalid team_id")
        metadata_by_id[pid] = {
            "position": position, "team_id": team_id,
            "price": _money(row.get("price"), f"player {pid} price"),
        }

    first_week = bundle["horizon_gameweeks"][0]
    forecasts = {
        row["fpl_element_id"]: row for row in bundle["player_gameweek_forecasts"]
        if row["gameweek"] == first_week
    }
    required_ids = set(squad_ids)
    missing_metadata = sorted(required_ids - set(metadata_by_id))
    missing_forecasts = sorted(required_ids - set(forecasts))
    if missing_metadata or missing_forecasts:
        raise MultiGameweekSquadAssemblyError(
            f"current squad metadata/forecast missing; metadata={missing_metadata}, forecasts={missing_forecasts}"
        )
    for pid in required_ids:
        if (metadata_by_id[pid]["position"] != forecasts[pid]["position"]
                or metadata_by_id[pid]["team_id"] != forecasts[pid]["team_id"]):
            raise MultiGameweekSquadAssemblyError(
                f"current metadata position/team does not match forecast bundle for player {pid}"
            )

    for pid in set(metadata_by_id) & set(forecasts):
        if (metadata_by_id[pid]["position"] != forecasts[pid]["position"]
                or metadata_by_id[pid]["team_id"] != forecasts[pid]["team_id"]):
            raise MultiGameweekSquadAssemblyError(
                f"current metadata position/team does not match forecast bundle for candidate {pid}"
            )

    team_counts = {}
    for pid in squad_ids:
        team = forecasts[pid]["team_id"]
        team_counts[team] = team_counts.get(team, 0) + 1

    evaluations = []
    skipped = {"goalkeeper_outgoing": 0, "position_mismatch": 0, "unaffordable": 0, "club_limit": 0}
    for outgoing in squad_ids:
        outgoing_forecast = forecasts[outgoing]
        position = outgoing_forecast["position"]
        if position == "GKP":
            skipped["goalkeeper_outgoing"] += 1
            continue
        sell_price = _selling_price(metadata_by_id[outgoing]["price"], purchase_prices[outgoing])
        available = bank + sell_price
        team_after = dict(team_counts)
        team_after[outgoing_forecast["team_id"]] -= 1
        for incoming, meta in metadata_by_id.items():
            if incoming in required_ids:
                continue
            if incoming not in forecasts:
                continue
            if meta["position"] != position:
                skipped["position_mismatch"] += 1
                continue
            if meta["price"] > available + 1e-9:
                skipped["unaffordable"] += 1
                continue
            if team_after.get(meta["team_id"], 0) >= 3:
                skipped["club_limit"] += 1
                continue
            request = {
                "forecast_bundle": bundle,
                "squad_ids": list(squad_ids),
                "starting_xi_ids": list(starting_xi_ids),
                "transfer_out_id": outgoing,
                "transfer_in_id": incoming,
                "bank": bank,
                "selling_price": sell_price,
                "incoming_price": meta["price"],
                "free_transfers": free_transfers,
                "hit_cost_points": hit_cost,
            }
            try:
                result = evaluate_multi_gameweek_transfer_bundle(request)
            except MultiGameweekTransferError as exc:
                raise MultiGameweekSquadAssemblyError(
                    f"candidate {outgoing}->{incoming} failed evaluator validation: {exc}"
                ) from exc
            evaluations.append(result)

    evaluations.sort(key=lambda row: (
        -row["net_horizon_expected_points_delta"],
        -row["gross_horizon_expected_points_delta"],
        row["transfer"]["out_id"], row["transfer"]["in_id"],
    ))
    best = evaluations[0] if evaluations else None
    return {
        "provider_source_id": bundle["provider_source_id"],
        "provider": dict(bundle["provider"]),
        "forecast_bundle_id": bundle["forecast_bundle_id"],
        "source_snapshot_ids": list(bundle["source_snapshot_ids"]),
        "model_version": bundle["model_version"],
        "contract_version": bundle["contract_version"],
        "status": "EXPLORATORY_MULTI_GAMEWEEK_SQUAD_SWEEP",
        "forecast_bundle_id": bundle["forecast_bundle_id"],
        "forecast_snapshot_id": bundle["forecast_snapshot_id"],
        "horizon_gameweeks": list(bundle["horizon_gameweeks"]),
        "source_snapshot_ids": list(bundle["source_snapshot_ids"]),
        "manager_state": {
            "squad_ids": list(squad_ids), "starting_xi_ids": list(starting_xi_ids),
            "bank": bank, "free_transfers": free_transfers,
        },
        "candidate_count": len(evaluations),
        "skipped_candidate_counts": skipped,
        "best_diagnostic": best,
        "candidate_evaluations": evaluations,
        "decision_weight": 0.0,
        "production_eligible": False,
        "limitations": [
            "Each candidate is compared with HOLD over the same explicit forecast horizon.",
            "Only one position-for-position outfield transfer is evaluated at a time; transfer sequences are not optimized.",
            "The starting XI is fixed except for replacing the outgoing starter or displacing the weakest same-position starter for a bench incoming.",
            "Current player prices and purchase prices are supplied inputs; future price changes and flexibility option value are not modeled.",
            "Results are diagnostic-only and cannot unlock an M4 production decision.",
        ],
    }
