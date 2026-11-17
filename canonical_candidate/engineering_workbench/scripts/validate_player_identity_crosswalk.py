#!/usr/bin/env python3
"""Validate an explicitly evidenced, season-scoped StatsBomb↔FPL identity crosswalk. Names are never fuzzy-matched."""
from __future__ import annotations
import argparse, csv, json
from collections import Counter, defaultdict
from pathlib import Path
FIELDS=["season","competition_id","competition_name","statsbomb_player_id","statsbomb_player_name","fpl_element_id","fpl_player_code","fpl_player_name","statsbomb_team_name","fpl_team_name","verification_status","match_method","evidence_source","evidence_url","verified_by","verified_at"]
ALLOWED_STATUS={"verified","pending","ambiguous","rejected"}
ALLOWED_METHODS={"manual_source_verified","official_alias","club_roster_crosscheck","provider_id_crosswalk"}
REQUIRED_VERIFIED=["season","competition_id","statsbomb_player_id","statsbomb_player_name","fpl_element_id","fpl_player_code","fpl_player_name","statsbomb_team_name","fpl_team_name","match_method","evidence_source","evidence_url","verified_by","verified_at"]
def validate_rows(rows):
    errors,accepted,statuses=[],[],Counter()
    for line,row in enumerate(rows,start=2):
        status=(row.get("verification_status") or "").strip().lower()
        statuses[status or "blank"]+=1
        if status not in ALLOWED_STATUS:
            errors.append({"line":line,"error":"invalid_verification_status","value":status}); continue
        if status!="verified": continue
        missing=[f for f in REQUIRED_VERIFIED if not (row.get(f) or "").strip()]
        if missing:
            errors.append({"line":line,"error":"missing_verified_fields","fields":missing}); continue
        method=(row.get("match_method") or "").strip()
        if method not in ALLOWED_METHODS:
            errors.append({"line":line,"error":"unapproved_match_method","value":method}); continue
        if not (row.get("evidence_url") or "").strip().startswith(("https://","http://")):
            errors.append({"line":line,"error":"evidence_url_must_be_http"}); continue
        accepted.append({f:(row.get(f) or "").strip() for f in FIELDS})
    sb_keys=defaultdict(list); fpl_keys=defaultdict(list)
    for row in accepted:
        sb_keys[(row["season"],row["statsbomb_player_id"])].append(row)
        fpl_keys[(row["season"],row["fpl_element_id"])].append(row)
    for key,values in sb_keys.items():
        if len({v["fpl_element_id"] for v in values})>1:
            errors.append({"error":"statsbomb_identity_maps_to_multiple_fpl_elements","key":key})
    for key,values in fpl_keys.items():
        if len({v["statsbomb_player_id"] for v in values})>1:
            errors.append({"error":"fpl_element_maps_to_multiple_statsbomb_identities","key":key})
    if errors:
        status="BLOCKED"
    elif not accepted and not rows:
        status="EMPTY_NOT_READY"
    elif not accepted:
        status="NO_VERIFIED_MAPPINGS"
    else:
        status="PASS"
    report={"input_rows":len(rows),"verified_rows_accepted":len(accepted) if not errors else 0,
            "non_verified_rows_excluded":sum(n for s,n in statuses.items() if s in {"pending","ambiguous","rejected"}),
            "status_counts":dict(statuses),"errors":errors,"status":status,"join_ready":status=="PASS",
            "join_policy":"Only fully evidenced verified rows; no fuzzy name matching"}
    return (accepted if not errors else []),report
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",type=Path,required=True); parser.add_argument("--out-dir",type=Path,required=True)
    args=parser.parse_args(); args.out_dir.mkdir(parents=True,exist_ok=True)
    with args.input.open(newline="",encoding="utf-8-sig") as h: rows=list(csv.DictReader(h))
    accepted,report=validate_rows(rows)
    with (args.out_dir/"verified_player_identity_crosswalk.csv").open("w",newline="",encoding="utf-8") as h:
        writer=csv.DictWriter(h,fieldnames=FIELDS); writer.writeheader(); writer.writerows(accepted)
    (args.out_dir/"crosswalk_validation.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2)); return 2 if report["status"]=="BLOCKED" else 0
if __name__=="__main__": raise SystemExit(main())
