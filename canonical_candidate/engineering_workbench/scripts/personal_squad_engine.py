#!/usr/bin/env python3
"""Manager-specific one-transfer FPL optimiser over a shared forecast snapshot (v0.1.1).

The initial version is intentionally conservative: it optimises a single
transfer and a legal starting XI, while explicitly excluding unvalidated
CoVar, multiweek risk and chip simulation.
"""
from __future__ import annotations
import math
from recommendation_contracts import validate_personal_squad_request, RecommendationContractError

POSITIONS=("GKP","DEF","MID","FWD")


def _player_order(player):
    return (-player["expected_points"],-player["expected_minutes"],player["fpl_element_id"])


def _minutes_order(player):
    return (-player["expected_minutes"],-player["expected_points"],player["fpl_element_id"])


def _formation_counts(value):
    if not isinstance(value,str):
        raise RecommendationContractError("formation must be a string such as 4-3-3")
    parts=value.split("-")
    if len(parts)!=3 or any(not part.isdigit() for part in parts):
        raise RecommendationContractError("formation must be DEF-MID-FWD, such as 4-3-3")
    defenders,midfielders,forwards=map(int,parts)
    if not (3<=defenders<=5 and 2<=midfielders<=5 and 1<=forwards<=3 and defenders+midfielders+forwards==10):
        raise RecommendationContractError("formation must be a legal FPL outfield formation")
    return defenders,midfielders,forwards


def _select_for_formation(owned,by_id,formation,starting_goalkeeper_id=None):
    defenders,midfielders,forwards=formation
    counts={"GKP":1,"DEF":defenders,"MID":midfielders,"FWD":forwards}
    selected=[]
    for position in POSITIONS:
        candidates=sorted([by_id[player["fpl_element_id"]] for player in owned
                           if by_id[player["fpl_element_id"]]["position"]==position
                           and (position != "GKP" or starting_goalkeeper_id is None
                                or player["fpl_element_id"] == starting_goalkeeper_id)],key=_player_order)
        if len(candidates)<counts[position]:
            raise RecommendationContractError(f"Not enough {position} players for requested formation")
        selected.extend(candidates[:counts[position]])
    return selected


def _best_starting_xi(owned,by_id,formation_value=None,starting_xi_value=None,starting_goalkeeper_id=None):
    requested=_formation_counts(formation_value) if formation_value is not None else None
    if starting_xi_value is not None:
        if not isinstance(starting_xi_value,list) or len(starting_xi_value)!=11:
            raise RecommendationContractError("starting_xi must contain exactly 11 FPL element IDs")
        if any(isinstance(value,bool) or not isinstance(value,int) or value<1 for value in starting_xi_value):
            raise RecommendationContractError("starting_xi must contain positive integer FPL element IDs")
        ids=list(starting_xi_value)
        if len(set(ids))!=11 or any(value not in {p["fpl_element_id"] for p in owned} for value in ids):
            raise RecommendationContractError("starting_xi must contain 11 unique players from the current squad")
        selected=[by_id[value] for value in ids]
        counts=tuple(sum(p["position"]==position for p in selected) for position in ("DEF","MID","FWD"))
        _formation_counts("-".join(map(str,counts)))
        if requested is not None and counts!=requested:
            raise RecommendationContractError("starting_xi does not match requested formation")
        formation=counts
        if starting_goalkeeper_id is not None and not any(
            p["position"] == "GKP" and p["fpl_element_id"] == starting_goalkeeper_id for p in selected
        ):
            raise RecommendationContractError("starting XI must retain the designated starting goalkeeper")
    elif requested is not None:
        formation=requested
        selected=_select_for_formation(owned,by_id,formation,starting_goalkeeper_id)
    else:
        best=None
        for defenders in range(3,6):
            for midfielders in range(2,6):
                forwards=10-defenders-midfielders
                if not 1<=forwards<=3: continue
                candidate=(defenders,midfielders,forwards)
                xi=_select_for_formation(owned,by_id,candidate,starting_goalkeeper_id)
                score=sum(p["expected_points"] for p in xi)
                if best is None or score>best[0]+1e-12:
                    best=(score,candidate,xi)
        if best is None:
            raise RecommendationContractError("No legal starting XI could be constructed")
        _,formation,selected=best
    ordered=[]
    for position in POSITIONS:
        ordered.extend(sorted([p for p in selected if p["position"]==position],key=_player_order))
    return ordered,formation


def _selling_price(current_price,purchase_price):
    current_tenths=int(round(float(current_price)*10))
    purchase_tenths=int(round(float(purchase_price)*10))
    if current_tenths<=purchase_tenths:
        return current_tenths/10.0
    return (purchase_tenths+(current_tenths-purchase_tenths)//2)/10.0


def _transfer_candidates(request,forecasts):
    squad=request["squad_snapshot"]
    owned_ids={int(p["fpl_element_id"]) for p in squad}
    forecast_by_id={int(p["fpl_element_id"]):p for p in forecasts}
    team_counts={}
    for player_id in owned_ids:
        team=forecast_by_id[player_id]["team_id"]
        team_counts[team]=team_counts.get(team,0)+1
    preferences=request.get("personal_preferences", {})
    if preferences is None:
        preferences={}
    if not isinstance(preferences,dict):
        raise RecommendationContractError("personal_preferences must be an object")
    hit_cost=preferences.get("hit_cost_points",4.0)
    min_gain=preferences.get("min_transfer_gain_points",0.0)
    max_alternatives=preferences.get("max_transfer_alternatives",5)
    for name,value in (("hit_cost_points",hit_cost),("min_transfer_gain_points",min_gain)):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(float(value)) or value<0:
            raise RecommendationContractError(f"personal_preferences.{name} must be a non-negative finite number")
    if isinstance(max_alternatives,bool) or not isinstance(max_alternatives,int) or not 1<=max_alternatives<=20:
        raise RecommendationContractError("personal_preferences.max_transfer_alternatives must be an integer from 1 to 20")
    applied_hit_cost=0.0 if request["free_transfers"]>0 else float(hit_cost)
    baseline_plan = request.get("_baseline_squad_plan")
    baseline_xi = set(baseline_plan["starting_xi"]) if baseline_plan else set()
    baseline_by_position = {}
    if baseline_plan:
        for player_id in baseline_plan["starting_xi"]:
            player = forecast_by_id[player_id]
            baseline_by_position.setdefault(player["position"], []).append(player)
        for position in baseline_by_position:
            baseline_by_position[position].sort(key=_player_order)
    candidates=[]
    for outgoing in squad:
        out_id=int(outgoing["fpl_element_id"])
        out_forecast=forecast_by_id[out_id]
        # The goalkeeper is a fixed starter/reserve pair, never a rotation slot.
        if out_forecast["position"] == "GKP":
            continue
        if "purchase_price" in outgoing:
            sell_price = _selling_price(out_forecast["price"], outgoing["purchase_price"])
        else:
            sell_price = min(float(out_forecast["price"]), float(outgoing["selling_price_floor"]))
        team_after=dict(team_counts)
        team_after[out_forecast["team_id"]]-=1
        available=request["bank"]+sell_price
        for incoming in forecasts:
            in_id=int(incoming["fpl_element_id"])
            if in_id in owned_ids or incoming["position"]!=out_forecast["position"]:
                continue
            if team_after.get(incoming["team_id"],0)>=3:
                continue
            if incoming["price"]>available+1e-9:
                continue
            delta=incoming["expected_points"]-out_forecast["expected_points"]
            if baseline_plan:
                if out_id in baseline_xi:
                    xi_delta = delta
                else:
                    starters = baseline_by_position.get(out_forecast["position"], [])
                    if not starters:
                        continue
                    # Bench replacements count only when they can displace a starter.
                    xi_delta = incoming["expected_points"] - starters[-1]["expected_points"]
            else:
                xi_delta = delta
            net=xi_delta-applied_hit_cost
            candidates.append({
                "transfer_out_id":out_id,"transfer_in_id":in_id,
                "expected_points_delta":delta,
                "starting_xi_expected_points_delta":xi_delta,
                "hit_cost_points":applied_hit_cost,
                "net_expected_points_gain":net,
                "selling_price":round(sell_price,2),
                "incoming_price":round(incoming["price"],2),
                "bank_after_transfer":round(available-incoming["price"],2),
            })
    candidates.sort(key=lambda x:(-x["net_expected_points_gain"],-x["starting_xi_expected_points_delta"],x["transfer_out_id"],x["transfer_in_id"]))
    top=candidates[:max_alternatives]
    best=top[0] if top else None
    action="TRANSFER" if best and best["net_expected_points_gain"]>min_gain else "HOLD"
    return {
        "action":action,
        "best_candidate":best,
        "alternatives":top,
        "hit_cost_points_applied":round(applied_hit_cost,8),
        "minimum_gain_threshold":float(min_gain),
        "free_transfers_available":request["free_transfers"],
        "candidate_count":len(candidates),
        "selling_price_basis": (
            "EXACT_PURCHASE_PRICE" if all("purchase_price" in row for row in squad)
            else "CONSERVATIVE_CURRENT_PRICE_FLOOR"
        ),
        "scope":"one-transfer lookahead only",
    }


def _build_squad_plan(owned, by_id, formation_value=None, starting_xi_value=None, bench_value=None, starting_goalkeeper_id=None):
    starting, formation = _best_starting_xi(owned, by_id, formation_value, starting_xi_value, starting_goalkeeper_id)
    starting_ids = {p["fpl_element_id"] for p in starting}
    remaining = [p for p in owned if p["fpl_element_id"] not in starting_ids]
    reserve_gk = [p for p in remaining if p["position"] == "GKP"]
    outfield_bench = [p for p in remaining if p["position"] != "GKP"]
    if len(reserve_gk) != 1 or len(outfield_bench) != 3:
        raise RecommendationContractError("Squad must leave one reserve goalkeeper and three outfield bench players")
    if bench_value is not None:
        if (not isinstance(bench_value, list) or len(bench_value) != 3
                or any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in bench_value)):
            raise RecommendationContractError("bench_order must contain exactly three positive integer outfield player IDs")
        bench_ids = list(bench_value)
        available = {p["fpl_element_id"] for p in outfield_bench}
        if len(set(bench_ids)) != 3 or set(bench_ids) != available:
            raise RecommendationContractError("bench_order must contain all three outfield substitutes exactly once")
        bench_order = bench_ids
    else:
        bench_order = [p["fpl_element_id"] for p in sorted(outfield_bench, key=_minutes_order)]
    captaincy = sorted(starting, key=_player_order)
    captain, vice = captaincy[0], captaincy[1]
    expected_points = sum(p["expected_points"] for p in starting) + captain["expected_points"]
    return {
        "formation": "-".join(map(str, formation)),
        "starting_xi": [p["fpl_element_id"] for p in starting],
        "captain": captain["fpl_element_id"],
        "vice_captain": vice["fpl_element_id"],
        "reserve_goalkeeper": reserve_gk[0]["fpl_element_id"],
        "bench_order": bench_order,
        "expected_starting_points": expected_points,
    }


def recommend_personal_squad(payload):
    request = validate_personal_squad_request(payload)
    forecasts = request["player_forecasts"]
    forecast_by_id = {int(p["fpl_element_id"]): p for p in forecasts}
    squad = request["squad_snapshot"]
    owned_ids = {int(p["fpl_element_id"]) for p in squad}
    owned = [forecast_by_id[player_id] for player_id in owned_ids]
    preferences = request.get("personal_preferences", {})
    if preferences is None:
        preferences = {}
    if not isinstance(preferences, dict):
        raise RecommendationContractError("personal_preferences must be an object")
    formation_value = request.get("formation") if request.get("formation") is not None else preferences.get("formation")
    starting_value = request.get("starting_xi") if request.get("starting_xi") is not None else preferences.get("starting_xi")
    bench_value = request.get("bench_order") if request.get("bench_order") is not None else preferences.get("bench_order")

    current_squad_plan = _build_squad_plan(owned, forecast_by_id, formation_value, starting_value, bench_value)
    transfer = _transfer_candidates({**request, "_baseline_squad_plan": current_squad_plan}, forecasts)
    recommended_squad_plan = current_squad_plan
    squad_plan_state = "CURRENT_SQUAD_HOLD"
    if transfer["action"] == "TRANSFER" and transfer["best_candidate"] is not None:
        candidate = transfer["best_candidate"]
        incoming_id, outgoing_id = int(candidate["transfer_in_id"]), int(candidate["transfer_out_id"])
        post_transfer_owned = [player for player in owned if int(player["fpl_element_id"]) != outgoing_id]
        post_transfer_owned.append(forecast_by_id[incoming_id])
        # Fixed XI/bench inputs may include the outgoing player; re-optimise after the move.
        starting_goalkeeper_id = next(
            player_id for player_id in current_squad_plan["starting_xi"]
            if forecast_by_id[player_id]["position"] == "GKP"
        )
        recommended_squad_plan = _build_squad_plan(
            post_transfer_owned, forecast_by_id, formation_value,
            starting_goalkeeper_id=starting_goalkeeper_id,
        )
        squad_plan_state = "POST_TRANSFER"

    quality = request["forecast_quality"]
    limitations = [
        "This is an exploratory one-gameweek squad optimiser, not a validated multiweek planner.",
        "CoVar and player variance are excluded because the available covariance estimate is not validated.",
        "The supplied risk profile is recorded but not applied until calibrated player-level variance is available.",
        "Only one transfer is evaluated; multi-transfer sequences, future price changes and transfer flexibility are not modelled.",
        "Chip effects are not simulated in this version.",
        "When exact purchase prices are unavailable, transfer affordability uses current price as a conservative lower bound; this may omit affordable options but will not overstate sale proceeds.",
        "Transfers are evaluated by their effect on the starting XI; a bench-to-bench upgrade is not sufficient reason to transfer.",
        "Goalkeeper transfers are excluded: the starting goalkeeper is not treated as a rotation position.",
        "The bench is treated as budget emergency cover, not a routine rotation pool; bench order remains relevant only for automatic substitutions.",
        "The starting XI is selected by expected points under the requested legal formation; bench order is a minutes/points proxy.",
        "When a transfer is recommended, squad_plan is re-optimised for the post-transfer 15-player squad; current_squad_plan preserves the baseline.",
    ]
    return {
        "system": "personal_squad",
        "forecast_snapshot_id": request["forecast_snapshot_id"],
        "model_version": request["model_version"],
        "forecast_horizon_gameweeks": request["forecast_horizon_gameweeks"],
        "forecast_quality": quality,
        "recommendation_status": "VALIDATED" if (
            quality["validation_status"] == "VALIDATED"
            and quality["point_in_time_status"] == "VERIFIED"
            and quality["data_coverage"].get("freshness_status") == "FRESH_WITHIN_24H"
        ) else "EXPLORATORY_ONLY",
        "manager_context": {
            "bank": request["bank"],
            "free_transfers": request["free_transfers"],
            "personal_risk_profile": request["personal_risk_profile"],
            "manager_rank": request.get("manager_rank"),
            "rank_target": request.get("rank_target"),
        },
        "transfer_recommendation": transfer,
        "current_squad_plan": current_squad_plan,
        "squad_plan": recommended_squad_plan,
        "squad_plan_state": squad_plan_state,
        "portfolio_risk": {
            "covar_used": False,
            "risk_profile_applied": False,
            "status": "NOT_VALIDATED",
            "note": "No CoVar or unvalidated variance estimate affects this decision.",
        },
        "limitations": limitations,
    }
