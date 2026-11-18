#!/usr/bin/env python3
"""Estimate rank-tier FPL effective ownership from deadline-locked manager picks.

Input CSV has one row per manager-player pick and must be sourced from a
deadline-aligned sample. This script does not fetch managers or infer rank tiers.
"""
from __future__ import annotations
import argparse,csv,json
from collections import defaultdict
from pathlib import Path


def truth(value):
    return str(value).strip().lower() in {"1","true","yes","y"}


def estimate_effective_ownership(rows):
    if not rows:
        raise ValueError("manager-pick input is empty")
    managers=defaultdict(list)
    seen=set()
    gameweeks=set()
    for row in rows:
        entry=str(row.get("entry_id","")).strip()
        element=str(row.get("fpl_element_id","")).strip()
        gw=str(row.get("gameweek","")).strip()
        if not entry or not element or not gw:
            raise ValueError("entry_id, fpl_element_id and gameweek are required")
        gameweeks.add(gw)
        key=(gw,entry,element)
        if key in seen:
            raise ValueError(f"duplicate manager-player pick: {key}")
        seen.add(key)
        try:
            position=int(row["position"])
            weight=float(row.get("sample_weight") or 1)
        except (KeyError,TypeError,ValueError):
            raise ValueError(f"invalid position or sample_weight for {key}")
        if position<1 or position>15 or weight<=0:
            raise ValueError(f"position must be 1..15 and sample_weight positive for {key}")
        managers[(gw,entry)].append((row,position,weight))
    if len(gameweeks)!=1:
        raise ValueError("input must contain exactly one gameweek")
    output=[]
    manager_weights={}
    for (gw,entry),items in managers.items():
        weights={weight for _,_,weight in items}
        if len(weights)!=1:
            raise ValueError(f"sample_weight differs within manager {entry}")
        if len(items)!=15:
            raise ValueError(f"manager {entry} GW{gw} must have exactly 15 player picks; found {len(items)}")
        positions=[position for _,position,_ in items]
        if len(set(positions))!=15:
            raise ValueError(f"manager {entry} GW{gw} has duplicate pick positions")
        manager_weights[(gw,entry)]=next(iter(weights))
    denominator=sum(manager_weights.values())
    if denominator<=0:
        raise ValueError("total sample weight must be positive")
    per_player=defaultdict(lambda:{"owned":0.0,"starting":0.0,"captained":0.0,"triple_captained":0.0,"scoring_exposure":0.0})
    for (gw,entry),items in managers.items():
        weight=manager_weights[(gw,entry)]
        captain_count=0
        for row,position,_ in items:
            chip=str(row.get("active_chip") or "").strip().lower()
            is_captain=truth(row.get("is_captain"))
            is_triple=chip=="3xc" and is_captain
            is_starter=position<=11
            is_bench_boost=chip=="bboost" and not is_starter
            if is_captain and not is_starter:
                raise ValueError(f"captain is not in the starting XI for manager {entry}")
            stats=per_player[str(row["fpl_element_id"])]
            # Standard FPL ownership includes every squad pick (all 15),
            # irrespective of whether the player starts or Bench Boost is active.
            stats["owned"]+=weight
            if is_starter:
                stats["starting"]+=weight
                stats["scoring_exposure"]+=weight
            elif is_bench_boost:
                stats["scoring_exposure"]+=weight
            if is_captain:
                stats["captained"]+=weight
                stats["scoring_exposure"]+=weight
                captain_count+=1
            if is_triple:
                stats["triple_captained"]+=weight
                stats["scoring_exposure"]+=weight
        if captain_count!=1:
            raise ValueError(f"manager {entry} GW{gw} must have exactly one captain")
    for player_id,stats in sorted(per_player.items(),key=lambda item:(0,int(item[0])) if item[0].isdigit() else (1,item[0])):
        effective_exposure=stats["owned"]+stats["captained"]+stats["triple_captained"]
        output.append({
            "gameweek":next(iter(gameweeks)),
            "fpl_element_id":player_id,
            "sample_managers":len(managers),
            "sample_weight":round(denominator,8),
            "owned_by_pct":round(stats["owned"]/denominator*100,8),
            "starting_pct":round(stats["starting"]/denominator*100,8),
            "captain_pct":round(stats["captained"]/denominator*100,8),
            "triple_captain_pct":round(stats["triple_captained"]/denominator*100,8),
            "effective_ownership_pct":round(effective_exposure/denominator*100,8),
            "scoring_exposure_pct":round(stats["scoring_exposure"]/denominator*100,8),
        })
    report={
        "gameweek":next(iter(gameweeks)),
        "sample_managers":len(managers),
        "sample_weight":round(denominator,8),
        "players_with_exposure":len(output),
        "status":"SAMPLE_ESTIMATE_NOT_GLOBAL_CENSUS",
        "formula":"standard EO = 100 * weighted sum(all 15 squad selections + captain extra + Triple Captain extra) / total manager sample weight",
        "lineup_policy":"ownership and standard EO count all 15 squad picks; starting_pct separately counts positions 1-11; scoring_exposure_pct counts starters, Bench Boost bench players, captain extra, and Triple Captain extra",
        "limitations":[
            "Results are representative only of the supplied manager sample and its weighting scheme.",
            "Standard ownership and EO count all 15 squad picks, including bench players; starting_pct and scoring_exposure_pct are separate measures.",
            "Manager ranks and picks must be captured at/after the deadline without using post-gameweek rank to define the cohort.",
            "This estimate is not the official whole-game ownership or a census unless the input contains the complete manager population.",
            "Bench Boost and Triple Captain chip states must reflect the locked gameweek picks.",
        ],
    }
    return output,report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--out-dir",type=Path,required=True)
    args=parser.parse_args()
    with args.input.open(newline="",encoding="utf-8-sig") as handle:
        rows=list(csv.DictReader(handle))
    output,report=estimate_effective_ownership(rows)
    args.out_dir.mkdir(parents=True,exist_ok=True)
    fields=["gameweek","fpl_element_id","sample_managers","sample_weight","owned_by_pct","captain_pct","triple_captain_pct","effective_ownership_pct"]
    with (args.out_dir/"fpl_effective_ownership_sample.csv").open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows(output)
    (args.out_dir/"fpl_effective_ownership_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
