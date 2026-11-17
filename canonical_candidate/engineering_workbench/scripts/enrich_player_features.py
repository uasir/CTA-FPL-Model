#!/usr/bin/env python3
"""Enrich StatsBomb player rows using only a verified season/competition ID crosswalk."""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path

OUTPUT_ID_FIELDS=["fpl_element_id","fpl_player_code","fpl_player_name","fpl_team_id_snapshot","fpl_team_name_snapshot","fpl_position"]
def read_csv(path):
    with path.open(newline="",encoding="utf-8-sig") as h:return list(csv.DictReader(h))
def enrich(player_rows,crosswalk_rows,fpl_players,season,competition_id):
    season=str(season);competition_id=str(competition_id)
    fpl_by_id={}
    errors=[]
    for row in fpl_players:
        if str(row.get("season"))!=season:continue
        key=str(row.get("fpl_element_id") or "")
        if not key:continue
        if key in fpl_by_id:errors.append({"error":"duplicate_fpl_element_id","fpl_element_id":key})
        fpl_by_id[key]=row
    mappings={}
    relevant=[r for r in crosswalk_rows if str(r.get("season"))==season and str(r.get("competition_id"))==competition_id and str(r.get("verification_status","verified")).lower()=="verified"]
    for row in relevant:
        sbid=str(row.get("statsbomb_player_id") or "")
        if not sbid:
            errors.append({"error":"verified_mapping_missing_statsbomb_id"});continue
        prior=mappings.get(sbid)
        if prior and str(prior.get("fpl_element_id"))!=str(row.get("fpl_element_id")):
            errors.append({"error":"conflicting_verified_mapping","statsbomb_player_id":sbid})
        else:mappings[sbid]=row
    output=[];mapped=0
    for source in player_rows:
        sbid=str(source.get("statsbomb_player_id") or "")
        if not sbid:
            errors.append({"error":"player_feature_missing_statsbomb_id","statsbomb_player_name":source.get("statsbomb_player_name","")})
            continue
        row=dict(source)
        for field in OUTPUT_ID_FIELDS:row[field]=""
        mapping=mappings.get(sbid)
        if mapping is None:
            row["fpl_join_status"]="UNMAPPED"
        else:
            element_id=str(mapping.get("fpl_element_id") or "")
            fpl=fpl_by_id.get(element_id)
            if fpl is None:
                errors.append({"error":"crosswalk_fpl_element_missing_from_season_snapshot","statsbomb_player_id":sbid,"fpl_element_id":element_id})
                row["fpl_join_status"]="INVALID_CROSSWALK"
            elif str(fpl.get("fpl_player_code") or "")!=str(mapping.get("fpl_player_code") or ""):
                errors.append({"error":"fpl_player_code_mismatch","statsbomb_player_id":sbid,"fpl_element_id":element_id})
                row["fpl_join_status"]="INVALID_CROSSWALK"
            else:
                row.update({
                    "fpl_element_id":element_id,
                    "fpl_player_code":str(fpl.get("fpl_player_code") or ""),
                    "fpl_player_name":str(fpl.get("web_name") or mapping.get("fpl_player_name") or ""),
                    "fpl_team_id_snapshot":str(fpl.get("team_id") or ""),
                    "fpl_team_name_snapshot":str(fpl.get("team_name") or ""),
                    "fpl_position":str(fpl.get("position") or ""),
                    "fpl_join_status":"VERIFIED"
                })
                mapped+=1
        output.append(row)
    if errors:status="BLOCKED"
    elif not crosswalk_rows:status="EMPTY_NOT_READY"
    elif not relevant:status="NO_MATCHING_CROSSWALK"
    elif mapped==0:status="NO_PLAYER_ROWS_MAPPED"
    elif mapped<len(player_rows):status="PARTIAL_NOT_READY"
    else:status="PASS"
    report={
        "season":season,"competition_id":competition_id,"statsbomb_player_rows":len(player_rows),
        "verified_crosswalk_rows_for_scope":len(relevant),"mapped_rows":mapped,
        "unmapped_rows":len(player_rows)-mapped,"mapping_coverage":round(mapped/len(player_rows),6) if player_rows else 0,
        "errors":errors,"status":status,"join_ready":status=="PASS",
        "per90_policy":"FPL season minutes are metadata only; never use them as the denominator for a one-match or differently scoped StatsBomb sample."
    }
    return output,report
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--player-features",type=Path,required=True);p.add_argument("--crosswalk",type=Path,required=True)
    p.add_argument("--fpl-players",type=Path,required=True);p.add_argument("--season",required=True)
    p.add_argument("--competition-id",required=True);p.add_argument("--out-dir",type=Path,required=True)
    a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=True)
    rows,report=enrich(read_csv(a.player_features),read_csv(a.crosswalk),read_csv(a.fpl_players),a.season,a.competition_id)
    fields=list(dict.fromkeys([k for row in rows for k in row]+["fpl_join_status"]))
    with (a.out_dir/"player_features_fpl_enriched.csv").open("w",newline="",encoding="utf-8") as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)
    (a.out_dir/"fpl_identity_enrichment_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2));return 2 if report["status"]=="BLOCKED" else 0
if __name__=="__main__":raise SystemExit(main())
