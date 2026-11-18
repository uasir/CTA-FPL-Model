#!/usr/bin/env python3
"""Require exact Python/JavaScript parity for the live general-market output."""
from __future__ import annotations
import argparse,json
from pathlib import Path


def first_difference(left,right,path="$"):
    if isinstance(left,bool) or isinstance(right,bool):
        if type(left) is not type(right) or left!=right:
            return {"path":path,"python_value":left,"javascript_value":right}
        return None
    if isinstance(left,(int,float)) and isinstance(right,(int,float)):
        if left!=right:
            return {"path":path,"python_value":left,"javascript_value":right}
        return None
    if type(left) is not type(right):
        return {"path":path,"python_type":type(left).__name__,"javascript_type":type(right).__name__}
    if isinstance(left,dict):
        if set(left)!=set(right):
            return {"path":path,"python_keys":sorted(left),"javascript_keys":sorted(right)}
        for key in sorted(left):
            diff=first_difference(left[key],right[key],f"{path}.{key}")
            if diff: return diff
        return None
    if isinstance(left,list):
        if len(left)!=len(right):
            return {"path":path,"python_length":len(left),"javascript_length":len(right)}
        for index,(a,b) in enumerate(zip(left,right)):
            diff=first_difference(a,b,f"{path}[{index}]")
            if diff: return diff
        return None
    if left!=right:
        return {"path":path,"python_value":left,"javascript_value":right}
    return None


def compare(python_result,javascript_result):
    diff=first_difference(python_result,javascript_result)
    if diff:
        return {"status":"FAIL_PYTHON_JAVASCRIPT_PARITY","first_difference":diff}
    return {
        "status":"PASS_PYTHON_JAVASCRIPT_PARITY",
        "forecast_snapshot_id":python_result["forecast_snapshot_id"],
        "system":"general_market",
        "players_ranked":python_result["coverage"]["filtered_players"],
        "categories":{
            "overall":len(python_result["categories"]["overall"]),
            "value":len(python_result["categories"]["value"]),
            "captaincy":len(python_result["categories"]["captaincy"]),
            "positions":{key:len(value) for key,value in python_result["categories"]["by_position"].items()},
        },
        "covar_used":python_result["covar_used"],
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--python",type=Path,required=True)
    parser.add_argument("--javascript",type=Path,required=True)
    parser.add_argument("--out-dir",type=Path,required=True)
    args=parser.parse_args()
    python_result=json.loads(args.python.read_text(encoding="utf-8"))
    javascript_result=json.loads(args.javascript.read_text(encoding="utf-8"))
    report=compare(python_result,javascript_result)
    args.out_dir.mkdir(parents=True,exist_ok=True)
    (args.out_dir/"fpl_general_market_live_parity_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    if report["status"]!="PASS_PYTHON_JAVASCRIPT_PARITY":
        raise SystemExit(1)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
