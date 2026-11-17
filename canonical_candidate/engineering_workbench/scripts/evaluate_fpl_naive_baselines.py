#!/usr/bin/env python3
"""Evaluate simple rolling-history FPL points baselines; no model is trained."""
from __future__ import annotations
import argparse,csv,json,math
from collections import defaultdict
from pathlib import Path

BASELINES={
 "last_gameweek":("prior_gw_points",1),
 "last3_gameweeks":("prior3_gw_points_avg",3),
 "last5_gameweeks":("prior5_gw_points_avg",5)
}
def number(v):
    try:return float(v) if v not in (None,"") else None
    except (TypeError,ValueError):return None
def ranks(values):
    order=sorted(range(len(values)),key=lambda i:values[i])
    result=[0.0]*len(values);i=0
    while i<len(order):
        j=i+1
        while j<len(order) and values[order[j]]==values[order[i]]:j+=1
        avg=((i+1)+j)/2
        for k in range(i,j):result[order[k]]=avg
        i=j
    return result
def correlation(a,b):
    if len(a)<2:return None
    ma=sum(a)/len(a);mb=sum(b)/len(b)
    da=[x-ma for x in a];db=[x-mb for x in b]
    den=math.sqrt(sum(x*x for x in da)*sum(y*y for y in db))
    return sum(x*y for x,y in zip(da,db))/den if den else None
def metrics(rows,pred_field,min_history,target_field="target_total_points"):
    selected=[]
    for row in rows:
        if int(row.get("prior_gameweeks_count") or 0)<min_history:continue
        y=number(row.get(target_field));p=number(row.get(pred_field))
        if y is not None and p is not None:selected.append((int(row["gameweek"]),p,y))
    if not selected:return {"n":0,"mae":None,"rmse":None,"mean_error":None,"spearman_by_gameweek":{},"top_decile_overlap_by_gameweek":{}}
    errors=[p-y for _,p,y in selected]
    by_gw=defaultdict(list)
    for gw,p,y in selected:by_gw[gw].append((p,y))
    spearman={};top_overlap={}
    for gw,values in sorted(by_gw.items()):
        if len(values)<5:continue
        ps=[x[0] for x in values];ys=[x[1] for x in values]
        spearman[str(gw)]=correlation(ranks(ps),ranks(ys))
        k=max(1,math.ceil(len(values)*0.1))
        pred_top=set(sorted(range(len(values)),key=lambda i:ps[i],reverse=True)[:k])
        actual_top=set(sorted(range(len(values)),key=lambda i:ys[i],reverse=True)[:k])
        top_overlap[str(gw)]=len(pred_top&actual_top)/k
    return {
      "n":len(selected),"mae":sum(abs(e) for e in errors)/len(errors),
      "rmse":math.sqrt(sum(e*e for e in errors)/len(errors)),
      "mean_error":sum(errors)/len(errors),
      "spearman_by_gameweek":spearman,
      "top_decile_overlap_by_gameweek":top_overlap
    }
def evaluate(rows,season=""):
    results={name:metrics(rows,field,min_history) for name,(field,min_history) in BASELINES.items()}
    minute_baselines={
      "last_gameweek":metrics(rows,"prior_gw_minutes",1,"target_minutes"),
      "last3_gameweeks":metrics(rows,"prior3_gw_minutes_avg",3,"target_minutes"),
      "last5_gameweeks":metrics(rows,"prior5_gw_minutes_avg",5,"target_minutes")
    }
    report={
      "season":season,"rows":len(rows),"baselines":results,"minutes_baselines":minute_baselines,
      "status":"EXPLORATORY_ONLY","model_trained":False,
      "point_in_time_status":"NOT_VERIFIED",
      "limitations":[
        "Single current season and only currently completed gameweeks.",
        "Current official API snapshot may contain retrospective revisions to prior gameweek statistics.",
        "Only players with positive season minutes were requested for element-summary history.",
        "Rolling averages are naive reference baselines, not an optimized predictive model."
      ]
    }
    return report
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True);p.add_argument("--out-dir",type=Path,required=True)
    a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=True)
    with a.input.open(newline="",encoding="utf-8-sig") as h:rows=list(csv.DictReader(h))
    season=rows[0].get("season","") if rows else ""
    report=evaluate(rows,season)
    (a.out_dir/"fpl_naive_baseline_evaluation.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    lines=["# Exploratory FPL rolling-history baselines","",f"**Status:** {report['status']}","",f"Season: {season}",""]
    for name,result in report["baselines"].items():
        lines += [f"## {name}",f"- Rows: {result['n']}",f"- MAE: {result['mae']}",f"- RMSE: {result['rmse']}",f"- Mean error: {result['mean_error']}",""]
    lines += ["## Limitations",""]+["- "+x for x in report["limitations"]]
    (a.out_dir/"fpl_naive_baseline_evaluation.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
