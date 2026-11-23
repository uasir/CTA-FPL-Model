#!/usr/bin/env python3
"""Five-Gameweek CTA squad HOLD-vs-transfer diagnostic.

Consumes the five weekly player forecast panels from one CTA candidate bundle.
It deliberately does not pretend those panels are independent source snapshots
or require fixture-level rows that the CTA bundle does not contain.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


class CTAMultiGameweekSquadError(ValueError):
    """Raised when CTA five-Gameweek squad inputs are incomplete or illegal."""


POSITIONS = ("GKP", "DEF", "MID", "FWD")


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise CTAMultiGameweekSquadError(f"{field} must be finite numeric")
    if value < 0:
        raise CTAMultiGameweekSquadError(f"{field} cannot be negative")
    return float(value)


def _selling_price(current: float, purchase: float) -> float:
    current_tenths, purchase_tenths = round(current * 10), round(purchase * 10)
    if current_tenths <= purchase_tenths:
        return current_tenths / 10
    return (purchase_tenths + (current_tenths - purchase_tenths) // 2) / 10


def evaluate_cta_five_gameweek_squad(
    gameweek_panels: list[Mapping[str, Any]],
    manager_context: Mapping[str, Any],
    *,
    starting_xi_ids: list[int] | None = None,
    forecast_snapshot_id: str | None = None,
    model_version: str | None = None,
    hit_cost_points: float = 4.0,
    max_alternatives: int = 20,
) -> dict[str, Any]:
    """Compare HOLD with all affordable legal single outfield transfers.

    Manager squad rows require fpl_element_id and purchase_price. Each panel
    requires gameweek and player_forecasts; forecast rows require
    fpl_element_id, position, team_id, price, expected_points, expected_minutes.
    The same XI is held fixed over the horizon, except for a transfer replacing
    the outgoing starter or displacing the weakest same-position starter.
    """
    if not isinstance(gameweek_panels, list) or len(gameweek_panels) != 5:
        raise CTAMultiGameweekSquadError("exactly five ordered Gameweek panels are required")
    weeks = [p.get("gameweek") if isinstance(p, Mapping) else None for p in gameweek_panels]
    if any(isinstance(w, bool) or not isinstance(w, int) for w in weeks) or weeks != list(range(weeks[0], weeks[0] + 5)):
        raise CTAMultiGameweekSquadError("Gameweek panels must cover five consecutive ordered weeks")
    if not isinstance(manager_context, Mapping):
        raise CTAMultiGameweekSquadError("manager_context must be an object")
    squad = manager_context.get("squad_snapshot")
    if not isinstance(squad, list) or len(squad) != 15:
        raise CTAMultiGameweekSquadError("squad_snapshot must contain exactly 15 players")
    bank = _finite(manager_context.get("bank"), "bank")
    free_transfers = manager_context.get("free_transfers")
    if isinstance(free_transfers, bool) or not isinstance(free_transfers, int) or free_transfers < 0:
        raise CTAMultiGameweekSquadError("free_transfers must be a non-negative integer")
    hit = _finite(hit_cost_points, "hit_cost_points")
    if isinstance(max_alternatives, bool) or not isinstance(max_alternatives, int) or not 1 <= max_alternatives <= 100:
        raise CTAMultiGameweekSquadError("max_alternatives must be an integer from 1 to 100")

    owned, purchase = [], {}
    for row in squad:
        if not isinstance(row, Mapping):
            raise CTAMultiGameweekSquadError("squad rows must be objects")
        pid = row.get("fpl_element_id")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1 or pid in purchase:
            raise CTAMultiGameweekSquadError("squad IDs must be unique positive integers")
        owned.append(pid)
        purchase[pid] = _finite(row.get("purchase_price"), f"purchase_price[{pid}]")
    if len(set(owned)) != 15:
        raise CTAMultiGameweekSquadError("squad IDs must be unique")

    by_week: dict[int, dict[int, dict[str, Any]]] = {}
    for panel in gameweek_panels:
        rows = panel.get("player_forecasts")
        if not isinstance(rows, list) or not rows:
            raise CTAMultiGameweekSquadError(f"GW{panel['gameweek']} player_forecasts must be non-empty")
        lookup = {}
        for row in rows:
            if not isinstance(row, Mapping):
                raise CTAMultiGameweekSquadError("forecast rows must be objects")
            pid = row.get("fpl_element_id")
            if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1 or pid in lookup:
                raise CTAMultiGameweekSquadError("forecast player IDs must be unique positive integers per GW")
            if row.get("position") not in POSITIONS:
                raise CTAMultiGameweekSquadError(f"invalid position for player {pid}")
            team = row.get("team_id")
            if isinstance(team, bool) or not isinstance(team, int) or team < 1:
                raise CTAMultiGameweekSquadError(f"invalid team_id for player {pid}")
            lookup[pid] = {
                "position": row["position"], "team_id": team,
                "price": _finite(row.get("price"), f"price[{pid}]"),
                "expected_points": _finite(row.get("expected_points"), f"expected_points[{pid}]"),
                "expected_minutes": _finite(row.get("expected_minutes"), f"expected_minutes[{pid}]"),
            }
        by_week[panel["gameweek"]] = lookup

    first = by_week[weeks[0]]
    missing = sorted(set(owned) - set(first))
    if missing:
        raise CTAMultiGameweekSquadError(f"current squad missing from first panel: {missing}")
    for gw in weeks:
        absent = sorted(set(owned) - set(by_week[gw]))
        if absent:
            raise CTAMultiGameweekSquadError(f"current squad missing from GW{gw}: {absent}")
        for pid in owned:
            if (by_week[gw][pid]["position"], by_week[gw][pid]["team_id"]) != (first[pid]["position"], first[pid]["team_id"]):
                raise CTAMultiGameweekSquadError(f"position/team metadata changed across horizon for player {pid}")

    counts = {pos: sum(first[pid]["position"] == pos for pid in owned) for pos in POSITIONS}
    if counts != {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}:
        raise CTAMultiGameweekSquadError("squad must contain 2 GKP, 5 DEF, 5 MID and 3 FWD")
    if starting_xi_ids is None:
        raise CTAMultiGameweekSquadError("an explicit baseline starting_xi_ids list is required")
    if (not isinstance(starting_xi_ids, list) or len(starting_xi_ids) != 11
            or any(isinstance(x, bool) or not isinstance(x, int) for x in starting_xi_ids)
            or len(set(starting_xi_ids)) != 11 or not set(starting_xi_ids).issubset(set(owned))):
        raise CTAMultiGameweekSquadError("starting_xi_ids must be 11 unique current-squad IDs")
    xi_counts = {pos: sum(first[pid]["position"] == pos for pid in starting_xi_ids) for pos in POSITIONS}
    if (xi_counts["GKP"] != 1 or not 3 <= xi_counts["DEF"] <= 5
            or not 2 <= xi_counts["MID"] <= 5 or not 1 <= xi_counts["FWD"] <= 3):
        raise CTAMultiGameweekSquadError("baseline starting XI formation is illegal")

    # A transfer candidate must exist in every panel. The full CTA pool can
    # legitimately differ by week, so never index a missing future row or
    # silently treat a partial horizon as a five-GW total.
    common_player_ids = set.intersection(*(set(by_week[gw]) for gw in weeks))
    for pid in common_player_ids:
        reference = by_week[weeks[0]][pid]
        for gw in weeks[1:]:
            row = by_week[gw][pid]
            if (row["position"], row["team_id"], row["price"]) != (
                reference["position"], reference["team_id"], reference["price"]
            ):
                raise CTAMultiGameweekSquadError(
                    f"position/team/price metadata changed across horizon for player {pid}"
                )
    totals = {pid: sum(by_week[gw][pid]["expected_points"] for gw in weeks)
              for pid in common_player_ids}
    minutes = {pid: sum(by_week[gw][pid]["expected_minutes"] for gw in weeks)
               for pid in common_player_ids}
    # Global market value is deliberately cross-position: all players are
    # ranked on the same five-GW cumulative xP horizon. Position ranks are
    # supplied alongside it, never used to filter the global ranking.
    global_order = sorted(
        common_player_ids,
        key=lambda pid: (-totals[pid], -minutes[pid], pid),
    )
    global_rank = {pid: index + 1 for index, pid in enumerate(global_order)}
    position_orders = {
        pos: [pid for pid in global_order if first[pid]["position"] == pos]
        for pos in POSITIONS
    }
    position_rank = {
        pid: index + 1
        for pos in POSITIONS
        for index, pid in enumerate(position_orders[pos])
    }
    market_rankings = []
    market_size = len(global_order)
    for pid in global_order:
        row = first[pid]
        market_rankings.append({
            "fpl_element_id": pid,
            "position": row["position"],
            "team_id": row["team_id"],
            "price": round(row["price"], 2),
            "five_gameweek_expected_points": round(totals[pid], 5),
            "five_gameweek_expected_minutes": round(minutes[pid], 2),
            "expected_points_per_million": round(totals[pid] / row["price"], 5) if row["price"] > 0 else None,
            "global_rank": global_rank[pid],
            "global_percentile": round((market_size - global_rank[pid]) / max(market_size - 1, 1), 5),
            "position_rank": position_rank[pid],
            "position_pool_size": len(position_orders[row["position"]]),
        })

    team_counts = {}
    for pid in owned:
        team = first[pid]["team_id"]
        team_counts[team] = team_counts.get(team, 0) + 1
    free_hit_cost = 0.0 if free_transfers > 0 else hit
    candidates = []
    for outgoing in owned:
        old = first[outgoing]
        if old["position"] == "GKP":
            continue
        sale = _selling_price(old["price"], purchase[outgoing])
        budget = bank + sale
        after = dict(team_counts)
        after[old["team_id"]] -= 1
        for incoming in common_player_ids:
            new = first[incoming]
            if incoming in owned:
                continue
            if new["position"] != old["position"] or new["price"] > budget + 1e-9:
                continue
            if after.get(new["team_id"], 0) >= 3:
                continue
            post_xi = list(starting_xi_ids)
            displaced = None
            if outgoing in post_xi:
                post_xi[post_xi.index(outgoing)] = incoming
            else:
                eligible = [pid for pid in post_xi if first[pid]["position"] == new["position"]]
                if not eligible:
                    continue
                displaced = min(eligible, key=lambda pid: (totals[pid], minutes[pid], pid))
                if totals[incoming] <= totals[displaced]:
                    continue
                post_xi[post_xi.index(displaced)] = incoming
            weekly = []
            for gw in weeks:
                hold = sum(by_week[gw][pid]["expected_points"] for pid in starting_xi_ids)
                proposed = sum(by_week[gw][pid]["expected_points"] for pid in post_xi)
                weekly.append({
                    "gameweek": gw,
                    "hold_starting_xi_expected_points": round(hold, 5),
                    "transfer_starting_xi_expected_points": round(proposed, 5),
                    "incremental_expected_points": round(proposed - hold, 5),
                })
            gross = sum(row["incremental_expected_points"] for row in weekly)
            candidates.append({
                "transfer_out_id": outgoing, "transfer_in_id": incoming,
                "selling_price": round(sale, 2), "incoming_price": round(new["price"], 2),
                "bank_after_transfer": round(budget - new["price"], 2),
                "displaced_starting_player_id": displaced,
                "incoming_global_rank": global_rank[incoming],
                "incoming_position_rank": position_rank[incoming],
                "incoming_global_rank": global_rank[incoming],
                "incoming_position_rank": position_rank[incoming],
                "outgoing_global_rank": global_rank[outgoing],
                "outgoing_position_rank": position_rank[outgoing],
                "incoming_five_gameweek_expected_points": round(totals[incoming], 5),
                "outgoing_five_gameweek_expected_points": round(totals[outgoing], 5),
                "incoming_minus_outgoing_player_horizon_xp": round(totals[incoming] - totals[outgoing], 5),
                "post_transfer_starting_xi_ids": post_xi,
                "weekly_comparison": weekly,
                "gross_horizon_expected_points_delta": round(gross, 5),
                "hit_cost_points_applied": free_hit_cost,
                "net_horizon_expected_points_delta": round(gross - free_hit_cost, 5),
                "action": "TRANSFER" if gross - free_hit_cost > 0 else "HOLD",
            })
    candidates.sort(key=lambda r: (-r["net_horizon_expected_points_delta"],
                                  -r["gross_horizon_expected_points_delta"],
                                  r["transfer_out_id"], r["transfer_in_id"]))
    if forecast_snapshot_id is not None and (not isinstance(forecast_snapshot_id, str) or not forecast_snapshot_id.strip()):
        raise CTAMultiGameweekSquadError("forecast_snapshot_id must be a non-empty string when supplied")
    if model_version is not None and (not isinstance(model_version, str) or not model_version.strip()):
        raise CTAMultiGameweekSquadError("model_version must be a non-empty string when supplied")

    return {
        "status": "EXPLORATORY_CTA_FIVE_GAMEWEEK_SQUAD_SWEEP",
        "recommendation_basis": "FIVE_GAMEWEEK_CUMULATIVE_EXPECTED_POINTS",
        "recommended_action": candidates[0]["action"] if candidates else "HOLD",
        "forecast_snapshot_id": forecast_snapshot_id,
        "model_version": model_version,
        "horizon_gameweeks": weeks,
        "manager_state": {"squad_ids": owned, "starting_xi_ids": list(starting_xi_ids),
                          "bank": bank, "free_transfers": free_transfers},
        "hold_starting_xi_expected_points": round(sum(totals[pid] for pid in starting_xi_ids), 5),
        "candidate_count": len(candidates),
        "global_player_value_basis": "CROSS_POSITION_FIVE_GAMEWEEK_CUMULATIVE_EXPECTED_POINTS",
        "global_player_pool_size": market_size,
        "global_player_value_rankings": market_rankings,
        "best_diagnostic": candidates[0] if candidates else None,
        "candidate_evaluations": candidates[:max_alternatives],
        "decision_weight": 0.0,
        "production_eligible": False,
        "covar_used": False,
        "limitations": [
            "One transfer at a time; transfer sequences and future transfer flexibility are not optimized.",
            "Baseline XI is fixed over the horizon; weekly lineups, captaincy and chips remain separate products.",
            "Uses player/Gameweek CTA forecasts from one candidate bundle; weekly panels are not represented as independent source snapshots.",
            "Future price changes and CoVar are excluded; result remains diagnostic-only pending M2 and M4 validation.",
        ],
    }
