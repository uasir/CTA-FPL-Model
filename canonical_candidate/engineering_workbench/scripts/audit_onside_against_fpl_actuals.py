#!/usr/bin/env python3
"""Cross-audit Onside actual_points against official FPL player-fixture history.

FPL fixture rows are summed to player-gameweek totals before comparison.
Missing keys are reported as missing, never silently converted to zero.
This is a source-consistency audit only; it does not feed CoVar or forecasts.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SOURCE_URL = "https://onsidearena.com/data/graded-predictions.csv"


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def fetch_source(url=SOURCE_URL):
    request=urllib.request.Request(
        url,headers={"User-Agent":"CTA-FPL-Model Onside CC-BY-4.0 actual-points cross-audit/1.0"}
    )
    with urllib.request.urlopen(request,timeout=90) as response:
        raw=response.read()
    rows=list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    return rows,hashlib.sha256(raw).hexdigest()


def audit(fpl_rows,onside_rows,*,season="2026-27",source_sha256=None):
    fpl={}
    fixture_counts=defaultdict(int)
    seen_fpl_fixture_keys=set()
    for row in fpl_rows:
        row_season=str(row.get("season") or "")
        if row_season and row_season!=season:
            continue
        try:
            player_id=str(int(row["fpl_element_id"]))
            fixture_id=str(int(row["fixture_id"]))
            gw=int(row["gameweek"])
            points=float(row["target_total_points"])
            if not math.isfinite(points):
                raise ValueError("FPL target_total_points must be finite")
        except (KeyError,TypeError,ValueError):
            raise ValueError("FPL training rows require numeric fpl_element_id, gameweek and target_total_points")
        fixture_key=(player_id,fixture_id)
        if fixture_key in seen_fpl_fixture_keys:
            raise ValueError(f"Duplicate official FPL player-fixture key: {fixture_key}")
        seen_fpl_fixture_keys.add(fixture_key)
        key=(player_id,gw)
        fpl[key]=fpl.get(key,0.0)+points
        fixture_counts[key]+=1

    onside={}
    names={}
    for row in onside_rows:
        try:
            player_id=str(int(row["player_id"]))
            gw=int(row["gw"])
            points=float(row["actual_points"])
        except (KeyError,TypeError,ValueError):
            continue
        if not math.isfinite(points):
            raise ValueError("Onside actual_points must be finite when present")
        if row.get("actual_points") in (None,""):
            continue
        key=(player_id,gw)
        if key in onside:
            raise ValueError(f"Duplicate Onside player-gameweek key: {key}")
        onside[key]=points
        names[key]=str(row.get("player_name") or "")

    fpl_keys=set(fpl)
    onside_keys=set(onside)
    matched=sorted(fpl_keys&onside_keys,key=lambda k:(int(k[1]),int(k[0])))
    mismatches=[]
    abs_diffs=[]
    per_gw=defaultdict(lambda:{"matched":0,"exact":0,"mismatched":0,"absolute_error_sum":0.0})
    for key in matched:
        diff=fpl[key]-onside[key]
        gw=key[1]
        abs_diff=abs(diff)
        abs_diffs.append(abs_diff)
        stats=per_gw[gw]
        stats["matched"]+=1
        stats["absolute_error_sum"]+=abs_diff
        if abs_diff<=1e-9:
            stats["exact"]+=1
        else:
            stats["mismatched"]+=1
            mismatches.append({
                "fpl_element_id":key[0],"gameweek":gw,"player_name":names.get(key,""),
                "fpl_points":fpl[key],"onside_actual_points":onside[key],"difference":diff,
                "fpl_fixture_rows":fixture_counts[key],
            })
    mismatches.sort(key=lambda x:(-abs(x["difference"]),x["gameweek"],int(x["fpl_element_id"])))
    gameweeks=sorted({gw for _,gw in fpl_keys|onside_keys})
    per_gameweek=[]
    for gw in gameweeks:
        stats=per_gw[gw]
        per_gameweek.append({
            "gameweek":gw,
            "matched_player_rows":stats["matched"],
            "exact_matches":stats["exact"],
            "mismatches":stats["mismatched"],
            "mean_absolute_difference":round(stats["absolute_error_sum"]/stats["matched"],8) if stats["matched"] else None,
            "fpl_rows_without_onside":sum(1 for _,g in fpl_keys-onside_keys if g==gw),
            "onside_rows_without_fpl":sum(1 for _,g in onside_keys-fpl_keys if g==gw),
        })
    exact=sum(1 for diff in abs_diffs if diff<=1e-9)
    report={
        "season":season,
        "status":"PASS_EXACT_MATCH" if matched and exact==len(matched) else ("REVIEW_MISMATCHES" if matched else "NO_OVERLAP"),
        "source":"Onside Arena actual_points vs official FPL player-fixture total_points",
        "source_license_and_attribution":"Provider-stated CC BY 4.0; attribution to Onside Arena and https://onsidearena.com/data is required.",
        "source_sha256":source_sha256,
        "retrieved_at_utc":datetime.now(timezone.utc).isoformat(),
        "fpl_player_gameweek_rows":len(fpl),
        "onside_player_gameweek_rows":len(onside),
        "matched_player_gameweek_rows":len(matched),
        "exact_matches":exact,
        "mismatches":len(mismatches),
        "exact_match_rate":round(exact/len(matched),8) if matched else None,
        "mean_absolute_difference":round(sum(abs_diffs)/len(abs_diffs),8) if abs_diffs else None,
        "max_absolute_difference":round(max(abs_diffs),8) if abs_diffs else None,
        "fpl_rows_without_onside":len(fpl_keys-onside_keys),
        "onside_rows_without_fpl":len(onside_keys-fpl_keys),
        "unique_fpl_players":len({pid for pid,_ in fpl_keys}),
        "unique_onside_players":len({pid for pid,_ in onside_keys}),
        "unique_matched_players":len({pid for pid,_ in matched}),
        "fpl_gameweeks":sorted({gw for _,gw in fpl_keys}),
        "onside_gameweeks":sorted({gw for _,gw in onside_keys}),
        "gameweeks":per_gameweek,
        "mismatch_examples":mismatches[:50],
        "methodology":{
            "fpl_aggregation":"Sum official FPL player-fixture total_points by (fpl_element_id, gameweek); double gameweeks are aggregated.",
            "join_key":"(numeric FPL element ID, gameweek)",
            "missingness":"Missing player-gameweek keys are counted separately and never filled with zero.",
            "exactness":"Exact integer FPL points equality, tolerance 1e-9.",
            "usage":"Source-consistency audit only; no forecast, EO, covariance or recommendation inputs are changed.",
        },
    }
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--fpl-training",type=Path,required=True)
    parser.add_argument("--onside-csv",type=Path)
    parser.add_argument("--out-dir",type=Path,required=True)
    parser.add_argument("--season",default="2026-27")
    args=parser.parse_args()
    if args.onside_csv:
        onside_rows=read_csv(args.onside_csv)
        raw=args.onside_csv.read_bytes()
        digest=hashlib.sha256(raw).hexdigest()
    else:
        onside_rows,digest=fetch_source()
    report=audit(read_csv(args.fpl_training),onside_rows,season=args.season,source_sha256=digest)
    args.out_dir.mkdir(parents=True,exist_ok=True)
    (args.out_dir/"onside_fpl_actuals_cross_audit.json").write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!="mismatch_examples"},indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
