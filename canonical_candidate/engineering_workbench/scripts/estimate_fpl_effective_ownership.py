#!/usr/bin/env python3
"""Estimate rank-tier FPL effective ownership from deadline-locked manager picks.

Input CSV has one row per manager-player pick and must be sourced from a
deadline-aligned sample. This script does not fetch managers or infer rank tiers.
"""
from __future__ import annotations
import argparse,csv,json,math
from collections import defaultdict
from pathlib import Path

PAGE_SIZE=50


def truth(value):
    return str(value).strip().lower() in {"1","true","yes","y"}


def _weighted_normal_ci(samples, confidence_z=1.96):
    if not samples:
        return None
    weights=[weight for _,weight in samples]
    total=sum(weights)
    total_sq=sum(weight*weight for weight in weights)
    if total<=0 or total_sq<=0:
        return None
    mean=sum(value*weight for value,weight in samples)/total
    n_eff=total*total/total_sq
    if n_eff<=1:
        return None
    variance=sum(weight*(value-mean)**2 for value,weight in samples)/total
    variance*=n_eff/(n_eff-1)
    se=math.sqrt(max(0.0,variance)/n_eff)
    return max(0.0,mean-confidence_z*se),mean+confidence_z*se


def _stratified_normal_ci(samples_by_stratum, metric_index, rank_limit, confidence_z=1.96):
    if rank_limit<=0 or rank_limit%PAGE_SIZE:
        return None
    page_count=rank_limit//PAGE_SIZE
    mean=0.0
    variance=0.0
    for page in range(1,page_count+1):
        samples=samples_by_stratum.get(page,[])
        n=len(samples)
        population=min(PAGE_SIZE,rank_limit-(page-1)*PAGE_SIZE)
        if n<2 or n>population:
            return None
        values=[sample[metric_index] for sample in samples]
        page_mean=sum(values)/n
        page_variance=sum((value-page_mean)**2 for value in values)/(n-1)
        share=population/rank_limit
        mean+=share*page_mean
        variance+=(share**2)*(1-n/population)*page_variance/n
    se=math.sqrt(max(0.0,variance))
    return max(0.0,mean-confidence_z*se),mean+confidence_z*se


def estimate_effective_ownership(rows):
    if not rows:
        raise ValueError("manager-pick input is empty")
    managers=defaultdict(list)
    seen=set()
    gameweeks=set()
    manager_ranks={}
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
            rank_value=row.get("rank_before_deadline")
            rank=int(rank_value) if rank_value not in (None,"") else None
        except (KeyError,TypeError,ValueError):
            raise ValueError(f"invalid position, rank or sample_weight for {key}")
        if position<1 or position>15 or weight<=0 or (rank is not None and rank<1):
            raise ValueError(f"position must be 1..15, rank positive and sample_weight positive for {key}")
        manager_key=(gw,entry)
        managers[manager_key].append((row,position,weight))
        if rank is not None:
            if manager_key in manager_ranks and manager_ranks[manager_key]!=rank:
                raise ValueError(f"rank_before_deadline differs within manager {entry}")
            manager_ranks[manager_key]=rank
    if len(gameweeks)!=1:
        raise ValueError("input must contain exactly one gameweek")
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
    rank_values=[manager_ranks.get(key) for key in managers]
    if any(value is not None for value in rank_values) and any(value is None for value in rank_values):
        raise ValueError("rank_before_deadline must be supplied for every manager or none")
    rank_stratified=all(value is not None for value in rank_values)
    denominator=sum(manager_weights.values())
    if denominator<=0:
        raise ValueError("total sample weight must be positive")
    rank_limit=int(round(denominator)) if rank_stratified else None
    if rank_stratified:
        if abs(denominator-rank_limit)>1e-8 or rank_limit%PAGE_SIZE:
            raise ValueError("rank-stratified sample weight must equal a multiple of the 50-rank page size")
        counts=defaultdict(int)
        for key,rank in manager_ranks.items():
            counts[(rank-1)//PAGE_SIZE+1]+=1
        page_count=rank_limit//PAGE_SIZE
        if set(counts)!=set(range(1,page_count+1)) or len(set(counts.values()))!=1:
            raise ValueError("rank-stratified sample must contain an equal manager count from every rank page")
        weights=set(manager_weights.values())
        if len(weights)!=1:
            raise ValueError("rank-stratified sample requires equal manager weights")
    else:
        page_count=0

    all_players=sorted(
        {str(row["fpl_element_id"]) for items in managers.values() for row,_,_ in items},
        key=lambda value:(0,int(value)) if value.isdigit() else (1,value),
    )
    per_player=defaultdict(lambda:{"owned":0.0,"starting":0.0,"captained":0.0,"triple_captained":0.0,"scoring_exposure":0.0})
    samples_by_player=defaultdict(lambda:defaultdict(list))
    for (gw,entry),items in managers.items():
        weight=manager_weights[(gw,entry)]
        captain_count=0
        local={}
        for row,position,_ in items:
            player_id=str(row["fpl_element_id"])
            chip=str(row.get("active_chip") or "").strip().lower()
            is_captain=truth(row.get("is_captain"))
            is_triple=chip=="3xc" and is_captain
            is_starter=position<=11
            is_bench_boost=chip=="bboost" and not is_starter
            if is_captain and not is_starter:
                raise ValueError(f"captain is not in the starting XI for manager {entry}")
            stats=per_player[player_id]
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
            local[player_id]=[
                1.0,
                float(is_starter),
                float(is_captain),
                float(is_triple),
                float(1+int(is_captain)+int(is_triple)),
                float(int(is_starter or is_bench_boost)+int(is_captain)+int(is_triple)),
            ]
        if captain_count!=1:
            raise ValueError(f"manager {entry} GW{gw} must have exactly one captain")
        rank=manager_ranks.get((gw,entry))
        stratum=(rank-1)//PAGE_SIZE+1 if rank is not None else "all"
        for player_id in all_players:
            values=local.get(player_id,[0.0]*6)
            samples_by_player[player_id][stratum].append(values)

    def interval(player_id,metric_index):
        samples=samples_by_player[player_id]
        if rank_stratified:
            return _stratified_normal_ci(samples,metric_index,rank_limit)
        weighted=[]
        for values in samples.get("all",[]):
            weighted.append((values[metric_index],1.0))
        return _weighted_normal_ci(weighted)

    output=[]
    for player_id in all_players:
        stats=per_player[player_id]
        effective_exposure=stats["owned"]+stats["captained"]+stats["triple_captained"]
        ci_owned=interval(player_id,0)
        ci_starting=interval(player_id,1)
        ci_captain=interval(player_id,2)
        ci_triple=interval(player_id,3)
        ci_eo=interval(player_id,4)
        ci_scoring=interval(player_id,5)
        output.append({
            "gameweek":next(iter(gameweeks)),
            "fpl_element_id":player_id,
            "sample_managers":len(managers),
            "sample_weight":round(denominator,8),
            "owned_by_pct":round(stats["owned"]/denominator*100,8),
            "owned_by_pct_ci95_low":round(ci_owned[0]*100,8) if ci_owned else None,
            "owned_by_pct_ci95_high":round(ci_owned[1]*100,8) if ci_owned else None,
            "starting_pct":round(stats["starting"]/denominator*100,8),
            "starting_pct_ci95_low":round(ci_starting[0]*100,8) if ci_starting else None,
            "starting_pct_ci95_high":round(ci_starting[1]*100,8) if ci_starting else None,
            "captain_pct":round(stats["captained"]/denominator*100,8),
            "captain_pct_ci95_low":round(ci_captain[0]*100,8) if ci_captain else None,
            "captain_pct_ci95_high":round(ci_captain[1]*100,8) if ci_captain else None,
            "triple_captain_pct":round(stats["triple_captained"]/denominator*100,8),
            "triple_captain_pct_ci95_low":round(ci_triple[0]*100,8) if ci_triple else None,
            "triple_captain_pct_ci95_high":round(ci_triple[1]*100,8) if ci_triple else None,
            "effective_ownership_pct":round(effective_exposure/denominator*100,8),
            "effective_ownership_pct_ci95_low":round(ci_eo[0]*100,8) if ci_eo else None,
            "effective_ownership_pct_ci95_high":round(ci_eo[1]*100,8) if ci_eo else None,
            "scoring_exposure_pct":round(stats["scoring_exposure"]/denominator*100,8),
            "scoring_exposure_pct_ci95_low":round(ci_scoring[0]*100,8) if ci_scoring else None,
            "scoring_exposure_pct_ci95_high":round(ci_scoring[1]*100,8) if ci_scoring else None,
        })
    report={
        "gameweek":next(iter(gameweeks)),
        "sample_managers":len(managers),
        "sample_weight":round(denominator,8),
        "effective_sample_size":round(denominator**2/sum(w*w for w in manager_weights.values()),4),
        "rank_stratified":rank_stratified,
        "rank_strata_count":page_count,
        "sampled_managers_per_rank_stratum":len(managers)//page_count if rank_stratified else None,
        "confidence_interval":{
            "level":0.95,
            "method":"rank-page-stratified normal approximation with finite population correction" if rank_stratified else "weighted normal approximation",
            "intervals_available":all(row["effective_ownership_pct_ci95_low"] is not None for row in output),
            "caveat":"Intervals are approximate; within-page sample variance is estimated from the sampled managers and does not model every source of rank-cohort uncertainty.",
        },
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
    fields=list(output[0].keys()) if output else []
    with (args.out_dir/"fpl_effective_ownership_sample.csv").open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows(output)
    (args.out_dir/"fpl_effective_ownership_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
