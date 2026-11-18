#!/usr/bin/env python3
"""Run the squad-independent general-market engine on an official FPL snapshot."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from general_market_engine import recommend_general_market


def run(snapshot):
    result=recommend_general_market(snapshot)
    coverage=snapshot["forecast_quality"]["data_coverage"]
    overall=result["categories"]["overall"]
    value=result["categories"]["value"]
    captaincy=result["categories"]["captaincy"]
    report={
        "status":"PASS_EXPLORATORY_GENERAL_MARKET",
        "system":result["system"],
        "forecast_snapshot_id":result["forecast_snapshot_id"],
        "target_gameweek":coverage.get("target_gameweek"),
        "recommendation_status":result["recommendation_status"],
        "players_ranked":result["coverage"]["filtered_players"],
        "players_with_eo":result["coverage"]["players_with_eo"],
        "differential_status":result["categories"]["differentials"]["status"],
        "covar_used":result["covar_used"],
        "top_overall":[
            {"fpl_element_id":p["fpl_element_id"],"web_name":p.get("web_name",""),
             "expected_points":p["expected_points"],"price":p["price"]}
            for p in overall[:10]
        ],
        "top_value":[
            {"fpl_element_id":p["fpl_element_id"],"web_name":p.get("web_name",""),
             "value_score":p["value_score"],"expected_points":p["expected_points"],"price":p["price"]}
            for p in value[:10]
        ],
        "captaincy_shortlist":[
            {"fpl_element_id":p["fpl_element_id"],"web_name":p.get("web_name",""),
             "expected_points":p["expected_points"]}
            for p in captaincy
        ],
        "limitations":result["limitations"],
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
    (args.out_dir/"fpl_general_market_baseline.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    (args.out_dir/"fpl_general_market_baseline_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
