#!/usr/bin/env python3
"""Five-plus-Gameweek transfer evaluator over a verified fixture forecast bundle.

This is an exploratory decision diagnostic. It does not replace the current
one-Gameweek production engine, optimize future transfer sequences, or apply
TECM/CoVar to the decision.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Mapping


class MultiGameweekTransferError(ValueError):
    """Raised when a transfer comparison is incomplete or illegal."""


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise MultiGameweekTransferError(f"{field} must be finite and numeric")
    if value < 0:
        raise MultiGameweekTransferError(f"{field} cannot be negative")
    return float(value)


def _ids(values: Any, field: str, length: int) -> list[int]:
    if not isinstance(values, list) or len(values) != length:
        raise MultiGameweekTransferError(f"{field} must contain exactly {length} player IDs")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in values):
        raise MultiGameweekTransferError(f"{field} must contain positive integer player IDs")
    if len(set(values)) != length:
        raise MultiGameweekTransferError(f"{field} must contain unique player IDs")
    return values


def evaluate_multi_gameweek_transfer_bundle(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Compare HOLD and one legal transfer using a provenance-checked bundle."""
    if not isinstance(payload, Mapping):
        raise MultiGameweekTransferError("payload must be an object")
    bundle = payload.get("forecast_bundle")
    if not isinstance(bundle, Mapping):
        raise MultiGameweekTransferError("forecast_bundle is required")
    bundle_id = bundle.get("forecast_bundle_id")
    grain = bundle.get("forecast_grain", "player_fixture")
    snapshot_id = bundle.get("forecast_snapshot_id")
    if not isinstance(bundle_id, str) or not bundle_id.strip() or not isinstance(snapshot_id, str) or not snapshot_id.strip():
        raise MultiGameweekTransferError("forecast bundle and provider snapshot IDs are required")
    if grain == "player_fixture" and snapshot_id != bundle_id:
        raise MultiGameweekTransferError("fixture-level forecast bundle/snapshot ID is inconsistent")
    if grain not in {"player_fixture", "player_gameweek"}:
        raise MultiGameweekTransferError("unsupported forecast grain")
    weeks = bundle.get("horizon_gameweeks")
    if (not isinstance(weeks, list) or len(weeks) < 5
            or any(isinstance(gw, bool) or not isinstance(gw, int) for gw in weeks)
            or weeks != list(range(weeks[0], weeks[0] + len(weeks)))):
        raise MultiGameweekTransferError("forecast bundle must contain at least five consecutive Gameweeks")
    source_ids = bundle.get("source_snapshot_ids")
    expected_snapshot_count = len(weeks) if grain == "player_fixture" else 1
    if (not isinstance(source_ids, list) or len(source_ids) != expected_snapshot_count
            or any(not isinstance(value, str) or not value.strip() for value in source_ids)
            or len(set(source_ids)) != len(source_ids)):
        raise MultiGameweekTransferError("one unique immutable provider snapshot ID is required per Gameweek")
    model_version = bundle.get("model_version")
    if not isinstance(model_version, str) or not model_version.strip():
        raise MultiGameweekTransferError("forecast bundle model_version is required")
    provider_source_id = bundle.get("provider_source_id")
    if not isinstance(provider_source_id, str) or not provider_source_id.strip():
        raise MultiGameweekTransferError("forecast bundle provider_source_id is required")
    provider = bundle.get("provider")
    if not isinstance(provider, Mapping) or any(
        not isinstance(provider.get(key), str) or not provider[key].strip()
        for key in ("name", "product", "variant", "version")
    ):
        raise MultiGameweekTransferError("forecast bundle provider identity is required")
    expected_contract = "1.0.0" if grain == "player_fixture" else "1.0.0-player-gameweek"
    if bundle.get("contract_version") != expected_contract:
        raise MultiGameweekTransferError("forecast bundle must come from the supported canonical contract version")

    squad = _ids(payload.get("squad_ids"), "squad_ids", 15)
    xi = _ids(payload.get("starting_xi_ids"), "starting_xi_ids", 11)
    if not set(xi).issubset(set(squad)):
        raise MultiGameweekTransferError("starting XI must be a subset of the 15-player squad")
    outgoing, incoming = payload.get("transfer_out_id"), payload.get("transfer_in_id")
    if (isinstance(outgoing, bool) or not isinstance(outgoing, int) or outgoing not in squad
            or isinstance(incoming, bool) or not isinstance(incoming, int) or incoming < 1 or incoming in squad):
        raise MultiGameweekTransferError("transfer must remove one owned player and add one unowned player")

    required = set(squad) | {incoming}
    player_rows = bundle.get("player_gameweek_forecasts")
    fixture_rows = bundle.get("fixture_forecasts")
    if not isinstance(player_rows, list):
        raise MultiGameweekTransferError("bundle player/Gameweek forecast rows are required")
    if grain == "player_fixture" and not isinstance(fixture_rows, list):
        raise MultiGameweekTransferError("fixture-level forecast rows are required for player_fixture grain")
    if grain == "player_gameweek" and fixture_rows is not None:
        raise MultiGameweekTransferError("player_gameweek grain must not contain fabricated fixture-level forecasts")

    by_week: dict[int, dict[int, dict[str, Any]]] = defaultdict(dict)
    for row in player_rows:
        if not isinstance(row, Mapping):
            raise MultiGameweekTransferError("player_gameweek_forecasts rows must be objects")
        pid, gw = row.get("fpl_element_id"), row.get("gameweek")
        if pid not in required or gw not in weeks:
            continue
        if pid in by_week[gw]:
            raise MultiGameweekTransferError(f"duplicate player/Gameweek row for {pid}, GW{gw}")
        by_week[gw][pid] = {
            "expected_points": _number(row.get("expected_points"), "expected_points"),
            "expected_minutes": _number(row.get("expected_minutes"), "expected_minutes"),
            "team_id": row.get("team_id"),
            "position": row.get("position"),
        }
        if isinstance(by_week[gw][pid]["team_id"], bool) or not isinstance(by_week[gw][pid]["team_id"], int) or by_week[gw][pid]["team_id"] < 1:
            raise MultiGameweekTransferError(f"player {pid} GW{gw} team_id is invalid")
        if by_week[gw][pid]["position"] not in {"GKP", "DEF", "MID", "FWD"}:
            raise MultiGameweekTransferError(f"player {pid} GW{gw} position is invalid")

    fixture_totals: dict[tuple[int, int], dict[str, float]] = defaultdict(lambda: {"expected_points": 0.0, "expected_minutes": 0.0})
    fixture_keys = set()
    for row in fixture_rows or []:
        if not isinstance(row, Mapping):
            raise MultiGameweekTransferError("fixture_forecasts rows must be objects")
        pid, gw, fixture_id = row.get("fpl_element_id"), row.get("gameweek"), row.get("fixture_id")
        if pid not in required or gw not in weeks:
            continue
        if isinstance(fixture_id, bool) or not isinstance(fixture_id, int) or fixture_id < 1:
            raise MultiGameweekTransferError("fixture_id must be a positive integer")
        key = (pid, gw, fixture_id)
        if key in fixture_keys:
            raise MultiGameweekTransferError(f"duplicate fixture forecast {key}")
        fixture_keys.add(key)
        fixture_totals[(pid, gw)]["expected_points"] += _number(row.get("expected_points"), "fixture expected_points")
        fixture_totals[(pid, gw)]["expected_minutes"] += _number(row.get("expected_minutes"), "fixture expected_minutes")

    for gw in weeks:
        missing = sorted(required - set(by_week.get(gw, {})))
        if missing:
            raise MultiGameweekTransferError(f"missing player forecasts in GW{gw}: {missing}")
        for pid in required:
            aggregate = by_week[gw][pid]
            if grain == "player_fixture":
                fixture = fixture_totals.get((pid, gw), {"expected_points": 0.0, "expected_minutes": 0.0})
                if not math.isclose(aggregate["expected_points"], fixture["expected_points"], abs_tol=1e-5):
                    raise MultiGameweekTransferError(f"fixture xP does not reconcile to player/GW forecast for {pid}, GW{gw}")
                if not math.isclose(aggregate["expected_minutes"], fixture["expected_minutes"], abs_tol=1e-5):
                    raise MultiGameweekTransferError(f"fixture minutes do not reconcile for {pid}, GW{gw}")

    first = by_week[weeks[0]]
    if first[outgoing]["position"] == "GKP":
        raise MultiGameweekTransferError("goalkeeper transfers are excluded")
    if first[outgoing]["position"] != first[incoming]["position"]:
        raise MultiGameweekTransferError("transfer must be position-for-position")
    squad_positions = {position: 0 for position in ("GKP", "DEF", "MID", "FWD")}
    for pid in squad:
        squad_positions[first[pid]["position"]] += 1
    if squad_positions != {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}:
        raise MultiGameweekTransferError("squad must contain 2 GKP, 5 DEF, 5 MID and 3 FWD")
    xi_positions = {position: 0 for position in ("GKP", "DEF", "MID", "FWD")}
    for pid in xi:
        xi_positions[first[pid]["position"]] += 1
    if (xi_positions["GKP"] != 1 or not 3 <= xi_positions["DEF"] <= 5
            or not 2 <= xi_positions["MID"] <= 5 or not 1 <= xi_positions["FWD"] <= 3):
        raise MultiGameweekTransferError("starting XI formation is not legal")

    team_counts: dict[int, int] = defaultdict(int)
    for pid in squad:
        team_counts[first[pid]["team_id"]] += 1
    post_counts = dict(team_counts)
    post_counts[first[outgoing]["team_id"]] -= 1
    post_counts[first[incoming]["team_id"]] = post_counts.get(first[incoming]["team_id"], 0) + 1
    if max(post_counts.values()) > 3:
        raise MultiGameweekTransferError("transfer would exceed the three-player club limit")

    bank = _number(payload.get("bank"), "bank")
    selling_price = _number(payload.get("selling_price"), "selling_price")
    incoming_price = _number(payload.get("incoming_price"), "incoming_price")
    if incoming_price > bank + selling_price + 1e-9:
        raise MultiGameweekTransferError("incoming player is unaffordable at current bank and selling price")
    free_transfers = payload.get("free_transfers")
    if isinstance(free_transfers, bool) or not isinstance(free_transfers, int) or free_transfers < 0:
        raise MultiGameweekTransferError("free_transfers must be a non-negative integer")
    hit_cost = _number(payload.get("hit_cost_points", 4), "hit_cost_points")
    applied_hit = 0.0 if free_transfers > 0 else hit_cost

    transfer_xi = list(xi)
    displaced_id = None
    if outgoing in xi:
        transfer_xi[transfer_xi.index(outgoing)] = incoming
    else:
        eligible = [pid for pid in xi if first[pid]["position"] == first[incoming]["position"]]
        horizon_totals = {
            pid: sum(by_week[gw][pid]["expected_points"] for gw in weeks)
            for pid in eligible + [incoming]
        }
        displaced_id = min(eligible, key=lambda pid: (horizon_totals[pid], pid))
        if horizon_totals[incoming] > horizon_totals[displaced_id]:
            transfer_xi[transfer_xi.index(displaced_id)] = incoming
        else:
            displaced_id = None

    weekly = []
    fixture_detail = []
    for gw in weeks:
        hold = sum(by_week[gw][pid]["expected_points"] for pid in xi)
        proposed = sum(by_week[gw][pid]["expected_points"] for pid in transfer_xi)
        weekly.append({
            "gameweek": gw,
            "hold_starting_xi_expected_points": round(hold, 6),
            "transfer_starting_xi_expected_points": round(proposed, 6),
            "incremental_expected_points": round(proposed - hold, 6),
            "incoming_expected_points": round(by_week[gw][incoming]["expected_points"], 6),
            "outgoing_expected_points": round(by_week[gw][outgoing]["expected_points"], 6),
        })
        for row in fixture_rows or []:
            if row.get("gameweek") == gw and row.get("fpl_element_id") in {outgoing, incoming, displaced_id}:
                fixture_detail.append({
                    "gameweek": gw, "fpl_element_id": row["fpl_element_id"],
                    "fixture_id": row["fixture_id"], "opponent_team_id": row.get("opponent_team_id"),
                    "kickoff_time": row.get("kickoff_time"),
                    "expected_points": row["expected_points"],
                    "expected_minutes": row["expected_minutes"],
                })

    gross = sum(row["incremental_expected_points"] for row in weekly)
    net = gross - applied_hit
    return {
        "provider_source_id": provider_source_id,
        "provider": dict(provider),
        "contract_version": bundle["contract_version"],
        "status": "EXPLORATORY_MULTI_GAMEWEEK_TRANSFER_COMPARISON",
        "forecast_bundle_id": bundle_id,
        "forecast_snapshot_id": snapshot_id,
        "model_version": model_version,
        "source_snapshot_ids": list(source_ids),
        "horizon_gameweeks": list(weeks),
        "transfer": {
            "out_id": outgoing, "in_id": incoming,
            "bank": bank, "selling_price": selling_price, "incoming_price": incoming_price,
            "free_transfers": free_transfers, "hit_cost_points_applied": applied_hit,
            "displaced_starting_player_id": displaced_id,
        },
        "hold_starting_xi_ids": list(xi),
        "transfer_starting_xi_ids": transfer_xi,
        "weekly_comparison": weekly,
        "fixture_level_transfer_player_detail": fixture_detail if grain == "player_fixture" else None,
        "forecast_grain": grain,
        "gross_horizon_expected_points_delta": round(gross, 6),
        "net_horizon_expected_points_delta": round(net, 6),
        "action": "TRANSFER" if net > 0 else "HOLD",
        "decision_weight": 0.0,
        "production_eligible": False,
        "limitations": [
            "Fixed starting-XI comparison; future lineups, captaincy, chips and multi-transfer sequences are not optimized.",
            ("Only the incoming/outgoing/displaced-player fixture rows are expanded; other XI contributions are summarized at player/Gameweek level." if grain == "player_fixture" else "Provider supplies player-Gameweek aggregates only; fixture-level expected points, fixture-specific minutes and double-Gameweek splits are unavailable."),
            "Future price changes and transfer-flexibility option value are not modeled.",
            "TECM/CoVar is not used to alter this expected-points decision.",
            "This evaluator is not wired into the current production recommendation path.",
        ],
    }
