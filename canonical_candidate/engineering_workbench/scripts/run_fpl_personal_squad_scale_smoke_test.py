#!/usr/bin/env python3
"""Scale-smoke-test the personal optimiser against a live forecast pool.

The squad is synthetic and is never presented as a real manager recommendation.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
from personal_squad_engine import recommend_personal_squad


COMPOSITION={"GKP":2,"DEF":5,"MID":5,"FWD":3}


def build_synthetic_request(snapshot):
    players=snapshot["player_forecasts"]
    team_counts={}
    squad=[]
    total_cost=0.0
    for position,required in COMPOSITION.items():
        candidates=sorted(
            [p for p in players if p["position"]==position],
            key=lambda p:(p["price"],-p["expected_points"],p["fpl_element_id"]),
        )
        selected=0
        for player in candidates:
            team=player["team_id"]
            if team_counts.get(team,0)>=3:
                continue
            if total_cost+player["price"]>100.0:
                continue
            squad.append({
                "fpl_element_id":player["fpl_element_id"],
                "purchase_price":player["price"],
            })
            total_cost+=player["price"]
            team_counts[team]=team_counts.get(team,0)+1
            selected+=1
            if selected==required:
                break
        if selected!=required:
            raise ValueError(f"Could not construct synthetic {position} quota")
    if len(squad)!=15 or max(team_counts.values())>3:
        raise ValueError("Synthetic squad violates FPL roster or team limits")
    return {
        "system":"personal_squad",
        "forecast_snapshot_id":snapshot["forecast_snapshot_id"],
        "model_version":snapshot["model_version"],
        "forecast_horizon_gameweeks":snapshot["forecast_horizon_gameweeks"],
        "forecast_quality":snapshot["forecast_quality"],
        "player_forecasts":players,
        "squad_snapshot":squad,
        "bank":round(100.0-total_cost,2),
        "free_transfers":1,
        "personal_risk_profile":"SYNTHETIC_SCALE_TEST",
        "personal_preferences":{"hit_cost_points":0,"max_transfer_alternatives":5},
        "formation":"4-3-3",
    }


def run(snapshot):
    request=build_synthetic_request(snapshot)
    result=recommend_personal_squad(request)
    team_counts={}
    for row in request["squad_snapshot"]:
        player=next(p for p in snapshot["player_forecasts"] if p["fpl_element_id"]==row["fpl_element_id"])
        team_counts[player["team_id"]]=team_counts.get(player["team_id"],0)+1
    report={
        "status":"PASS_SYNTHETIC_PERSONAL_SQUAD_SCALE_SMOKE_TEST",
        "scope":"synthetic squad only; not a real manager recommendation",
        "forecast_snapshot_id":snapshot["forecast_snapshot_id"],
        "forecast_players":len(snapshot["player_forecasts"]),
        "synthetic_squad_players":len(request["squad_snapshot"]),
        "synthetic_squad_cost":round(100.0-request["bank"],2),
        "synthetic_bank":request["bank"],
        "maximum_players_per_team":max(team_counts.values()),
        "formation":result["squad_plan"]["formation"],
        "starting_xi_count":len(result["squad_plan"]["starting_xi"]),
        "captain":result["squad_plan"]["captain"],
        "vice_captain":result["squad_plan"]["vice_captain"],
        "transfer_candidate_count":result["transfer_recommendation"]["candidate_count"],
        "transfer_action":result["transfer_recommendation"]["action"],
        "risk_profile_applied":result["portfolio_risk"]["risk_profile_applied"],
        "covar_used":result["portfolio_risk"]["covar_used"],
        "recommendation_status":result["recommendation_status"],
    }
    return result,report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--snapshot",type=Path,required=True)
    parser.add_argument("--out-dir",type=Path,required=True)
    args=parser.parse_args()
    snapshot=json.loads(args.snapshot.read_text(encoding="utf-8"))
    result,report=run(snapshot)
    args.out_dir.mkdir(parents=True,exist_ok=True)
    (args.out_dir/"fpl_personal_squad_scale_smoke_test.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    (args.out_dir/"fpl_personal_squad_scale_smoke_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
