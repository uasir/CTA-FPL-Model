#!/usr/bin/env python3
"""Deterministic multi-Gameweek transfer comparison and descriptive team-stack diagnostics.

This module deliberately does not estimate joint probabilities or CoVar. It
requires explicit player forecasts for every Gameweek in the requested horizon.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Mapping


class MultiGameweekTransferError(ValueError):
    """Raised when a multi-Gameweek transfer comparison is incomplete."""


def _finite_number(value: Any, field: str, *, non_negative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise MultiGameweekTransferError(f"{field} must be a finite number")
    result = float(value)
    if non_negative and result < 0:
        raise MultiGameweekTransferError(f"{field} cannot be negative")
    return result


def _validate_week(week: Mapping[str, Any], index: int) -> tuple[int, dict[int, dict[str, Any]]]:
    if not isinstance(week, Mapping):
        raise MultiGameweekTransferError(f"gameweeks[{index}] must be an object")
    gw = week.get("gameweek")
    if isinstance(gw, bool) or not isinstance(gw, int) or gw < 1:
        raise MultiGameweekTransferError(f"gameweeks[{index}].gameweek must be a positive integer")
    rows = week.get("player_forecasts")
    if not isinstance(rows, list) or not rows:
        raise MultiGameweekTransferError(f"gameweeks[{index}].player_forecasts must be a non-empty list")
    by_id: dict[int, dict[str, Any]] = {}
    for row_index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise MultiGameweekTransferError(f"gameweeks[{index}].player_forecasts[{row_index}] must be an object")
        player_id = row.get("fpl_element_id")
        if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id < 1:
            raise MultiGameweekTransferError(f"gameweeks[{index}] contains an invalid FPL element ID")
        if player_id in by_id:
            raise MultiGameweekTransferError(f"gameweeks[{index}] has duplicate player {player_id}")
        points = _finite_number(row.get("expected_points"), f"GW{gw} player {player_id} expected_points", non_negative=True)
        minutes = _finite_number(row.get("expected_minutes"), f"GW{gw} player {player_id} expected_minutes", non_negative=True)
        team_id = row.get("team_id")
        if isinstance(team_id, bool) or not isinstance(team_id, int) or team_id < 1:
            raise MultiGameweekTransferError(f"GW{gw} player {player_id} team_id must be a positive integer")
        position = row.get("position")
        if position not in {"GKP", "DEF", "MID", "FWD"}:
            raise MultiGameweekTransferError(f"GW{gw} player {player_id} has invalid position")
        by_id[player_id] = {
            "fpl_element_id": player_id,
            "expected_points": points,
            "expected_minutes": minutes,
            "team_id": team_id,
            "position": position,
        }
    return gw, by_id


def evaluate_multi_gameweek_transfer(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Compare a fixed-XI HOLD and one-transfer path over >=5 explicit GWs.

    XI expected points are unmultiplied player-point totals (captaincy excluded)
    so this module cannot accidentally assume a captain remains optimal.
    """
    if not isinstance(payload, Mapping):
        raise MultiGameweekTransferError("payload must be an object")
    gameweeks = payload.get("gameweeks")
    if not isinstance(gameweeks, list) or len(gameweeks) < 5:
        raise MultiGameweekTransferError("at least five explicit Gameweek forecast panels are required")
    parsed = [_validate_week(week, i) for i, week in enumerate(gameweeks)]
    gw_numbers = [item[0] for item in parsed]
    if any(b != a + 1 for a, b in zip(gw_numbers, gw_numbers[1:])):
        raise MultiGameweekTransferError("Gameweek panels must be consecutive and ordered")
    squad = payload.get("squad_ids")
    xi = payload.get("starting_xi_ids")
    if (not isinstance(squad, list) or len(squad) != 15
            or any(isinstance(p, bool) or not isinstance(p, int) or p < 1 for p in squad)
            or len(set(squad)) != 15):
        raise MultiGameweekTransferError("squad_ids must contain 15 unique positive integer player IDs")
    if (not isinstance(xi, list) or len(xi) != 11
            or any(isinstance(p, bool) or not isinstance(p, int) or p < 1 for p in xi)
            or len(set(xi)) != 11 or not set(xi).issubset(set(squad))):
        raise MultiGameweekTransferError("starting_xi_ids must contain 11 unique players from squad_ids")
    outgoing = payload.get("transfer_out_id")
    incoming = payload.get("transfer_in_id")
    if (isinstance(outgoing, bool) or not isinstance(outgoing, int) or outgoing not in squad
            or isinstance(incoming, bool) or not isinstance(incoming, int) or incoming < 1 or incoming in squad):
        raise MultiGameweekTransferError("transfer pair must remove one owned player and add one unowned player")
    first = parsed[0][1]
    if outgoing not in first or incoming not in first:
        raise MultiGameweekTransferError("first Gameweek must forecast both transfer players")
    squad_positions = {position: 0 for position in ("GKP", "DEF", "MID", "FWD")}
    for player_id in squad:
        squad_positions[first[player_id]["position"]] += 1
    if squad_positions != {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}:
        raise MultiGameweekTransferError("squad must contain 2 GKP, 5 DEF, 5 MID and 3 FWD")
    xi_positions = {position: 0 for position in ("GKP", "DEF", "MID", "FWD")}
    for player_id in xi:
        xi_positions[first[player_id]["position"]] += 1
    if (xi_positions["GKP"] != 1 or sum(xi_positions.values()) != 11
            or not (3 <= xi_positions["DEF"] <= 5)
            or not (2 <= xi_positions["MID"] <= 5)
            or not (1 <= xi_positions["FWD"] <= 3)):
        raise MultiGameweekTransferError("starting XI must have one goalkeeper and a legal FPL outfield formation")
    if first[outgoing]["position"] == "GKP":
        raise MultiGameweekTransferError("goalkeeper transfers are excluded by this policy")
    if first[outgoing]["position"] != first[incoming]["position"]:
        raise MultiGameweekTransferError("transfer must be position-for-position")
    if any(player_id not in rows for _, rows in parsed for player_id in set(squad) | {incoming}):
        raise MultiGameweekTransferError("every squad player and the incoming player must have forecasts in every Gameweek")
    initial_team_counts: dict[int, int] = defaultdict(int)
    for player_id in squad:
        initial_team_counts[first[player_id]["team_id"]] += 1
    post_team_counts = dict(initial_team_counts)
    post_team_counts[first[outgoing]["team_id"]] -= 1
    post_team_counts[first[incoming]["team_id"]] = post_team_counts.get(first[incoming]["team_id"], 0) + 1
    if max(post_team_counts.values()) > 3:
        raise MultiGameweekTransferError("transfer would exceed the three-player club limit")

    hit_cost = _finite_number(payload.get("hit_cost_points", 0), "hit_cost_points", non_negative=True)
    free_transfers = payload.get("free_transfers", 0)
    if isinstance(free_transfers, bool) or not isinstance(free_transfers, int) or free_transfers < 0:
        raise MultiGameweekTransferError("free_transfers must be a non-negative integer")
    applied_cost = 0.0 if free_transfers > 0 else hit_cost
    transfer_xi = list(xi)
    if outgoing in transfer_xi:
        transfer_xi[transfer_xi.index(outgoing)] = incoming
    else:
        eligible = [p for p in xi if first[p]["position"] == first[incoming]["position"]]
        if not eligible:
            raise MultiGameweekTransferError("no starting player shares incoming player's position")
        horizon_points = {
            player_id: sum(rows[player_id]["expected_points"] for _, rows in parsed)
            for player_id in eligible + [incoming]
        }
        weakest = min(eligible, key=lambda p: (horizon_points[p], p))
        if horizon_points[incoming] > horizon_points[weakest]:
            transfer_xi[transfer_xi.index(weakest)] = incoming

    weekly = []
    for gw, rows in parsed:
        hold_points = sum(rows[p]["expected_points"] for p in xi)
        transfer_points = sum(rows[p]["expected_points"] for p in transfer_xi)
        weekly.append({
            "gameweek": gw,
            "hold_starting_xi_points": round(hold_points, 6),
            "transfer_starting_xi_points": round(transfer_points, 6),
            "incremental_points": round(transfer_points - hold_points, 6),
        })
    gross_delta = sum(row["incremental_points"] for row in weekly)
    net_delta = gross_delta - applied_cost

    # Descriptive stacks only: no probability or correlation is inferred.
    stacks = []
    for gw, rows in parsed:
        selected = set(transfer_xi)
        grouped: dict[tuple[int, str], list[int]] = defaultdict(list)
        for player_id in selected:
            row = rows[player_id]
            if row["position"] in {"DEF", "FWD", "MID"}:
                grouped[(row["team_id"], row["position"])].append(player_id)
        for (team_id, position), ids in sorted(grouped.items()):
            if len(ids) >= 2:
                stacks.append({
                    "gameweek": gw,
                    "team_id": team_id,
                    "position_group": position,
                    "player_ids": sorted(ids),
                    "player_count": len(ids),
                    "expected_points": round(sum(rows[p]["expected_points"] for p in ids), 6),
                    "interpretation": (
                        "shared_clean_sheet_exposure" if position == "DEF"
                        else "shared_attacking_team_exposure"
                    ),
                    "probability_or_correlation_estimated": False,
                })

    return {
        "status": "EXPLORATORY_MULTI_GAMEWEEK_COMPARISON",
        "horizon": {"start_gameweek": gw_numbers[0], "end_gameweek": gw_numbers[-1], "gameweek_count": len(gw_numbers)},
        "transfer": {"out_id": outgoing, "in_id": incoming},
        "hold_starting_xi_ids": list(xi),
        "transfer_starting_xi_ids": transfer_xi,
        "weekly_comparison": weekly,
        "gross_horizon_expected_points_delta": round(gross_delta, 6),
        "transfer_cost_points": round(applied_cost, 6),
        "net_horizon_expected_points_delta": round(net_delta, 6),
        "action": "TRANSFER" if net_delta > 0 else "HOLD",
        "team_stacks": stacks,
        "portfolio_risk": {
            "covar_used": False,
            "joint_probabilities_used": False,
            "status": "DESCRIPTIVE_ONLY",
            "note": "Team stacks identify shared club/position exposure; no player correlation or clean-sheet probability is inferred from marginal xP.",
        },
        "limitations": [
            "Fixed starting-XI comparison; no future lineup, captaincy, chips or transfer-sequence optimisation.",
            "No future price changes or transfer-flexibility value is modelled.",
            "Expected points are summed without captaincy multipliers.",
            "Team-stack output is descriptive only and does not alter the expected-points calculation.",
        ],
    }
