#!/usr/bin/env python3
"""Squad-independent FPL market rankings over a shared forecast snapshot.

This first engine intentionally uses only EV, price and (when available)
sampled EO. It does not consume squad context or exploratory CoVar.
"""
from __future__ import annotations
import math
from recommendation_contracts import validate_general_market_request, RecommendationContractError

POSITIONS=("GKP","DEF","MID","FWD")


def _number(filters,field,default=None):
    value=filters.get(field,default)
    if value is None:
        return None
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(float(value)):
        raise RecommendationContractError(f"filters.{field} must be a finite number")
    return float(value)


def _validate_filters(filters):
    if not isinstance(filters,dict):
        raise RecommendationContractError("filters must be an object")
    position=filters.get("position")
    if position is not None and position not in POSITIONS:
        raise RecommendationContractError("filters.position is invalid")
    team_id=filters.get("team_id")
    if team_id is not None and (isinstance(team_id,bool) or not isinstance(team_id,int) or team_id<1):
        raise RecommendationContractError("filters.team_id must be a positive integer")
    limit=filters.get("limit",10)
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=50:
        raise RecommendationContractError("filters.limit must be an integer from 1 to 50")
    minimum=_number(filters,"min_price")
    maximum=_number(filters,"max_price")
    min_points=_number(filters,"min_expected_points")
    eo_threshold=_number(filters,"differential_eo_max_pct")
    if minimum is not None and minimum<=0:
        raise RecommendationContractError("filters.min_price must be positive")
    if maximum is not None and maximum<=0:
        raise RecommendationContractError("filters.max_price must be positive")
    if minimum is not None and maximum is not None and minimum>maximum:
        raise RecommendationContractError("filters.min_price cannot exceed max_price")
    if eo_threshold is not None and eo_threshold<0:
        raise RecommendationContractError("filters.differential_eo_max_pct cannot be negative")
    return position,team_id,limit,minimum,maximum,min_points,eo_threshold


def recommend_general_market(payload):
    request=validate_general_market_request(payload)
    position,team_id,limit,min_price,max_price,min_points,eo_threshold=_validate_filters(request.get("filters",{}))
    players=request["player_forecasts"]
    filtered=[]
    for source in players:
        if position is not None and source["position"]!=position: continue
        if team_id is not None and source["team_id"]!=team_id: continue
        if min_price is not None and source["price"]<min_price: continue
        if max_price is not None and source["price"]>max_price: continue
        if min_points is not None and source["expected_points"]<min_points: continue
        player=dict(source)
        player["value_score"]=player["expected_points"]/player["price"]
        filtered.append(player)

    order=lambda p:(-p["expected_points"],-p["expected_minutes"],p["fpl_element_id"])
    value_order=lambda p:(-p["value_score"],-p["expected_points"],p["fpl_element_id"])
    overall=sorted(filtered,key=order)[:limit]
    by_position={key:sorted([p for p in filtered if p["position"]==key],key=order)[:limit] for key in POSITIONS}
    value=sorted(filtered,key=value_order)[:limit]
    captaincy=sorted(filtered,key=order)[:min(5,limit)]

    eo_players=[p for p in filtered if "effective_ownership_pct" in p]
    if eo_threshold is None:
        differential={"status":"EO_THRESHOLD_NOT_SET","players":[],"threshold_pct":None}
    elif not eo_players:
        differential={"status":"EO_UNAVAILABLE","players":[],"threshold_pct":eo_threshold}
    else:
        differential={"status":"SAMPLED_EO_AVAILABLE","players":sorted(
            [p for p in eo_players if p["effective_ownership_pct"]<=eo_threshold],key=order
        )[:limit],"threshold_pct":eo_threshold}

    quality=request["forecast_quality"]
    return {
        "system":"general_market",
        "forecast_snapshot_id":request["forecast_snapshot_id"],
        "model_version":request["model_version"],
        "forecast_horizon_gameweeks":request["forecast_horizon_gameweeks"],
        "forecast_quality":quality,
        "recommendation_status":"EXPLORATORY_ONLY" if quality["validation_status"]!="VALIDATED" else "VALIDATED",
        "ranking_basis":"expected_points (EV), expected_points / price (value), and sampled EO only when explicitly supplied",
        "covar_used":False,
        "coverage":{
            "input_players":len(players),"filtered_players":len(filtered),
            "players_with_eo":len(eo_players),
            "point_in_time_status":quality["point_in_time_status"],
        },
        "categories":{
            "overall":overall,
            "by_position":by_position,
            "value":value,
            "captaincy":captaincy,
            "differentials":differential,
        },
        "limitations":[
            "This is a deterministic ranking layer, not a trained CTA points model.",
            "The engine does not use personal squad, bank, transfers, chips, formation or manager rank.",
            "CoVar is deliberately excluded until covariance is stable and validated out of sample.",
            "EO rankings are unavailable unless a locked, cohort-labelled EO field is supplied.",
        ],
    }
