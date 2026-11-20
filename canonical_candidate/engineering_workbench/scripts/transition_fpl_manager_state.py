#!/usr/bin/env python3
"""Deterministic FPL manager-state transitions for sequential policy replay.

This module transitions one manager's state from one deadline to the next.
It does not forecast, choose transfers, or score player outcomes.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from typing import Mapping

POSITIONS = {"GKP", "DEF", "MID", "FWD"}
REQUIRED_SQUAD = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
CHIPS = {"wildcard", "free_hit", "bench_boost", "triple_captain"}
PERIOD_KEYS = {"first_half_remaining", "second_half_remaining"}
MAX_FREE_TRANSFERS = 5
HIT_PER_TRANSFER = 4


def _int(value, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _utc(value, label: str) -> datetime:
    if not value:
        raise ValueError(f"Missing {label}")
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid {label}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def calculate_selling_price_tenths(purchase_price_tenths: int, current_price_tenths: int) -> int:
    """Official FPL sell price: retain half a rise, rounded down to £0.1m."""
    purchase = _int(purchase_price_tenths, "purchase_price_tenths", 1)
    current = _int(current_price_tenths, "current_price_tenths", 1)
    if current <= purchase:
        return current
    return purchase + (current - purchase) // 2


def _validate_squad(squad: list[dict], label: str) -> dict[str, dict]:
    if not isinstance(squad, list) or len(squad) != 15:
        raise ValueError(f"{label} must contain exactly 15 players")
    players = {}
    for player in squad:
        player_id = str(player.get("player_id", "")).strip()
        if not player_id or player_id in players:
            raise ValueError(f"{label} player IDs must be unique and non-empty")
        position = str(player.get("position", "")).upper()
        if position not in POSITIONS:
            raise ValueError(f"{label} has an unknown position for {player_id}")
        team_id = str(player.get("team_id", "")).strip()
        if not team_id:
            raise ValueError(f"{label} is missing team_id for {player_id}")
        purchase = _int(player.get("purchase_price_tenths"), f"{label}.{player_id}.purchase_price_tenths", 1)
        current = _int(player.get("current_price_tenths"), f"{label}.{player_id}.current_price_tenths", 1)
        selling = _int(player.get("selling_price_tenths"), f"{label}.{player_id}.selling_price_tenths", 1)
        expected = calculate_selling_price_tenths(purchase, current)
        if selling != expected:
            raise ValueError(f"{label} selling price mismatch for {player_id}: expected {expected}, received {selling}")
        players[player_id] = dict(player, player_id=player_id, position=position, team_id=team_id)
    if Counter(player["position"] for player in players.values()) != Counter(REQUIRED_SQUAD):
        raise ValueError(f"{label} must contain 2 GKP, 5 DEF, 5 MID and 3 FWD")
    return players


def _validate_lineup(action: Mapping, squad_by_id: Mapping[str, dict]) -> dict:
    xi = [str(value) for value in action.get("starting_xi", [])]
    bench = [str(value) for value in action.get("bench_order", [])]
    if len(xi) != 11 or len(bench) != 4 or len(set(xi + bench)) != 15:
        raise ValueError("Action requires 11 starters and four distinct ordered bench players")
    if set(xi + bench) != set(squad_by_id):
        raise ValueError("Action XI and bench must cover the exact Gameweek squad")
    positions = {player_id: player["position"] for player_id, player in squad_by_id.items()}
    if sum(positions[player_id] == "GKP" for player_id in xi) != 1:
        raise ValueError("Starting XI must contain exactly one goalkeeper")
    if any(positions[player_id] == "GKP" for player_id in bench[:3]) or positions[bench[3]] != "GKP":
        raise ValueError("Bench must be three ordered outfield players followed by the reserve goalkeeper")
    counts = Counter(positions[player_id] for player_id in xi)
    if not (3 <= counts["DEF"] <= 5 and 2 <= counts["MID"] <= 5 and 1 <= counts["FWD"] <= 3):
        raise ValueError("Starting XI formation is illegal")
    captain = str(action.get("captain", ""))
    vice = str(action.get("vice_captain", ""))
    if captain not in xi or vice not in xi or captain == vice:
        raise ValueError("Captain and vice-captain must be distinct starters")
    return {"starting_xi": xi, "bench_order": bench, "captain": captain, "vice_captain": vice}


def _validate_chip_inventory(inventory: Mapping) -> dict:
    if not isinstance(inventory, Mapping) or set(inventory) != CHIPS:
        raise ValueError("chip_inventory must contain all four FPL chips")
    result = {}
    for chip, periods in inventory.items():
        if not isinstance(periods, Mapping) or set(periods) != PERIOD_KEYS:
            raise ValueError(f"chip_inventory.{chip} must contain both half-season periods")
        result[chip] = {}
        for period, count in periods.items():
            count = _int(count, f"chip_inventory.{chip}.{period}")
            if count > 1:
                raise ValueError(f"chip_inventory.{chip}.{period} cannot exceed one")
            result[chip][period] = count
    return result


def transition_manager_state(
    state: Mapping,
    action: Mapping,
    next_player_data: Mapping | None = None,
    next_gameweek: int | None = None,
    next_deadline_utc: str | None = None,
    terminal: bool = False,
) -> dict:
    """Apply one deadline's transfers/chip and create the next pre-deadline state.

    The returned gameweek_squad is the squad that actually scores this Gameweek.
    next_state.squad is the permanent squad at the next deadline (restored for FH).
    next_player_data maps player_id to {current_price_tenths, team_id}.
    """
    gameweek = _int(state.get("gameweek"), "state.gameweek", 1)
    current_deadline = _utc(state.get("deadline_utc"), "state.deadline_utc")
    if terminal:
        if next_gameweek is not None or next_deadline_utc is not None:
            raise ValueError("Terminal transitions must not supply a next Gameweek or deadline")
    else:
        next_gameweek = _int(next_gameweek, "next_gameweek", 1)
        if next_gameweek != gameweek + 1:
            raise ValueError("Sequential transition requires the immediately following Gameweek")
        next_deadline = _utc(next_deadline_utc, "next_deadline_utc")
        if next_deadline <= current_deadline:
            raise ValueError("Next deadline must be later than the current deadline")

    bank = _int(state.get("bank_tenths"), "state.bank_tenths")
    free_transfers = _int(state.get("free_transfers"), "state.free_transfers", 1)
    if free_transfers > MAX_FREE_TRANSFERS:
        raise ValueError("Free transfers cannot exceed five")
    original_squad = deepcopy(state.get("squad"))
    original_by_id = _validate_squad(original_squad, "state.squad")
    inventory = _validate_chip_inventory(state.get("chip_inventory"))

    chip = action.get("chip")
    if chip is not None and chip not in CHIPS:
        raise ValueError("Unsupported chip")
    period = "first_half_remaining" if gameweek <= 19 else "second_half_remaining"
    if chip is not None and inventory[chip][period] < 1:
        raise ValueError(f"{chip} is unavailable in Gameweek {gameweek}")
    if chip == "free_hit" and gameweek == 1:
        raise ValueError("Free Hit cannot be played in Gameweek 1")
    if gameweek == 20 and state.get("previous_gameweek_chip") == "free_hit" and chip == "free_hit":
        raise ValueError("The first-half Free Hit in GW19 prevents a second Free Hit in GW20")

    transfers = action.get("transfers")
    if not isinstance(transfers, list):
        raise ValueError("action.transfers must be a list")
    outgoing_ids = [str(row.get("out_player_id", "")) for row in transfers]
    incoming_rows = [row.get("in_player") for row in transfers]
    incoming_ids = [str(row.get("player_id", "")) if isinstance(row, Mapping) else "" for row in incoming_rows]
    if any(not value for value in outgoing_ids + incoming_ids):
        raise ValueError("Every transfer requires an outgoing and incoming player ID")
    if len(set(outgoing_ids)) != len(outgoing_ids) or len(set(incoming_ids)) != len(incoming_ids):
        raise ValueError("Transfer player IDs must not be duplicated")
    if set(outgoing_ids) & set(incoming_ids):
        raise ValueError("A player cannot be transferred out and back in the same action")
    if any(player_id not in original_by_id for player_id in outgoing_ids):
        raise ValueError("A transfer outgoing player is not in the starting squad")
    if any(player_id in original_by_id for player_id in incoming_ids):
        raise ValueError("A transfer incoming player is already in the starting squad")

    gameweek_by_id = deepcopy(original_by_id)
    sale_total = 0
    purchase_total = 0
    normalized_transfers = []
    for transfer, incoming in zip(transfers, incoming_rows):
        outgoing_id = str(transfer["out_player_id"])
        outgoing = gameweek_by_id.pop(outgoing_id)
        incoming_id = str(incoming["player_id"])
        incoming_position = str(incoming.get("position", "")).upper()
        if incoming_position != outgoing["position"]:
            raise ValueError("Transfers must replace a player in the same FPL position")
        incoming_team = str(incoming.get("team_id", "")).strip()
        if not incoming_team:
            raise ValueError(f"Incoming player {incoming_id} is missing team_id")
        incoming_price = _int(incoming.get("current_price_tenths"), f"incoming {incoming_id} current_price_tenths", 1)
        sale_total += outgoing["selling_price_tenths"]
        purchase_total += incoming_price
        gameweek_by_id[incoming_id] = {
            "player_id": incoming_id,
            "position": incoming_position,
            "team_id": incoming_team,
            "purchase_price_tenths": incoming_price,
            "current_price_tenths": incoming_price,
            "selling_price_tenths": incoming_price,
        }
        normalized_transfers.append({
            "out_player_id": outgoing_id,
            "in_player_id": incoming_id,
            "sale_price_tenths": outgoing["selling_price_tenths"],
            "purchase_price_tenths": incoming_price,
        })

    if len(gameweek_by_id) != 15:
        raise ValueError("Transfers must preserve a 15-player squad")
    if Counter(player["position"] for player in gameweek_by_id.values()) != Counter(REQUIRED_SQUAD):
        raise ValueError("Transfers must preserve squad positional composition")

    bank_after = bank + sale_total - purchase_total
    if bank_after < 0:
        raise ValueError("Transfers exceed the available budget")

    if transfers:
        team_counts = Counter(player["team_id"] for player in gameweek_by_id.values())
        if any(count > 3 for count in team_counts.values()):
            raise ValueError("Any transfer action must leave no more than three players per Premier League club")

    gameweek_squad = list(gameweek_by_id.values())
    gameweek_lookup = {player["player_id"]: player for player in gameweek_squad}
    lineup = _validate_lineup(action, gameweek_lookup)

    hit_points = 0 if chip in {"wildcard", "free_hit"} else max(0, len(transfers) - free_transfers) * HIT_PER_TRANSFER
    if chip is not None:
        inventory[chip][period] -= 1

    if chip == "free_hit":
        next_squad_by_id = deepcopy(original_by_id)
        next_bank = bank
        next_free_transfers = free_transfers
    else:
        next_squad_by_id = deepcopy(gameweek_by_id)
        next_bank = bank_after
        if chip == "wildcard":
            next_free_transfers = free_transfers
        else:
            next_free_transfers = min(
                MAX_FREE_TRANSFERS,
                max(1, free_transfers - len(transfers) + 1),
            )

    if terminal:
        return {
            "status": "TERMINAL_GAMEWEEK_ACTION_APPLIED",
            "current_gameweek": gameweek,
            "next_gameweek": None,
            "transfers_made": len(transfers),
            "transfer_hit_points": hit_points,
            "bank_after_transfers_tenths": bank_after,
            "next_bank_tenths": next_bank,
            "next_free_transfers": next_free_transfers,
            "chip_used": chip,
            "gameweek_squad": sorted(gameweek_squad, key=lambda row: row["player_id"]),
            "gameweek_lineup": lineup,
            "next_state": None,
            "scope": "TERMINAL_ACTION_ONLY; NO NEXT STATE",
        }

    if chip == "free_hit":
        prior_lineup = state.get("lineup")
        if not isinstance(prior_lineup, Mapping):
            raise ValueError("Free Hit restoration requires the prior permanent lineup in state")
        next_lineup = _validate_lineup(prior_lineup, original_by_id)
    else:
        next_lineup = lineup

    if not isinstance(next_player_data, Mapping):
        raise ValueError("next_player_data must be a mapping for non-terminal transitions")
    updated_squad = []
    for player_id, player in next_squad_by_id.items():
        market = next_player_data.get(player_id)
        if not isinstance(market, Mapping):
            raise ValueError(f"Missing next-deadline player data for {player_id}")
        next_price = _int(market.get("current_price_tenths"), f"next price for {player_id}", 1)
        next_team = str(market.get("team_id", player["team_id"])).strip()
        if not next_team:
            raise ValueError(f"Missing next-deadline team_id for {player_id}")
        updated = dict(player)
        updated["current_price_tenths"] = next_price
        updated["team_id"] = next_team
        updated["selling_price_tenths"] = calculate_selling_price_tenths(
            updated["purchase_price_tenths"], next_price
        )
        updated_squad.append(updated)
    updated_squad.sort(key=lambda row: row["player_id"])

    history = list(state.get("transfer_history") or [])
    history.append({
        "gameweek": gameweek,
        "chip": chip,
        "transfers": normalized_transfers,
        "hit_points": hit_points,
    })

    next_state = {
        "schema_version": state.get("schema_version", "1.0"),
        "season": state.get("season"),
        "gameweek": next_gameweek,
        "deadline_utc": next_deadline.isoformat().replace("+00:00", "Z"),
        "bank_tenths": next_bank,
        "free_transfers": next_free_transfers,
        "chip_inventory": inventory,
        "previous_gameweek_chip": chip,
        "squad": updated_squad,
        "lineup": next_lineup,
        "transfer_history": history,
    }
    _validate_squad(updated_squad, "next_state.squad")

    return {
        "status": "TRANSITIONED_TO_NEXT_GAMEWEEK",
        "current_gameweek": gameweek,
        "next_gameweek": next_gameweek,
        "transfers_made": len(transfers),
        "transfer_hit_points": hit_points,
        "bank_after_transfers_tenths": bank_after,
        "next_bank_tenths": next_bank,
        "next_free_transfers": next_free_transfers,
        "chip_used": chip,
        "gameweek_squad": sorted(gameweek_squad, key=lambda row: row["player_id"]),
        "gameweek_lineup": lineup,
        "next_state": next_state,
        "scope": "STATE_TRANSITION_ONLY; SCORE THE GAMEWEEK SEPARATELY",
    }
