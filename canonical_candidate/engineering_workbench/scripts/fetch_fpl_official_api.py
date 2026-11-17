#!/usr/bin/env python3
"""Fetch and normalize the official Fantasy Premier League public API.

The output is season-scoped and intentionally does not fuzzy-join FPL players
onto StatsBomb identities. Cross-provider identity requires a separately
verified alias/ID crosswalk.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, time, urllib.error, urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_URL = "https://fantasy.premierleague.com/api"
PLAYER_FIELDS = ["season","fpl_element_id","fpl_player_code","first_name","second_name","web_name","team_id","team_name","position","status","minutes_season","total_points_season","now_cost","selected_by_percent","chance_of_playing_next_round"]
FIXTURE_FIELDS = ["season","fixture_id","gameweek","kickoff_time","team_h_id","team_h_name","team_a_id","team_a_name","finished","finished_provisional","team_h_score","team_a_score","team_h_difficulty","team_a_difficulty"]
MATCH_FIELDS = ["season","fpl_element_id","fpl_player_code","player_name","fixture_id","gameweek","opponent_team_id","opponent_team_name","was_home","kickoff_time","minutes","total_points","goals_scored","assists","clean_sheets","goals_conceded","own_goals","penalties_saved","penalties_missed","yellow_cards","red_cards","saves","bonus","bps","influence","creativity","threat","ict_index","starts","expected_goals","expected_assists","expected_goal_involvements","expected_goals_conceded"]

def fetch_json(url: str, retries: int = 5, timeout: int = 30) -> Any:
    headers = {"User-Agent":"CTA-FPL-Model/1.0 (research data ingestion)","Accept":"application/json"}
    for attempt in range(retries):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    raise RuntimeError(f"Unexpected HTTP status {response.status} for {url}")
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code not in {429,500,502,503,504} or attempt == retries-1:
                raise
            retry_after = exc.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
            time.sleep(min(delay,60))
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries-1: raise
            time.sleep(min(2 ** attempt,30))
    raise RuntimeError(f"Failed to fetch {url}")

def infer_season(events: list[dict[str,Any]]) -> str:
    deadlines = [datetime.fromisoformat(str(e["deadline_time"]).replace("Z","+00:00")) for e in events if e.get("deadline_time")]
    if not deadlines: raise ValueError("Cannot infer season: bootstrap-static has no dated gameweeks")
    first = min(deadlines)
    start_year = first.year if first.month >= 7 else first.year-1
    return f"{start_year}-{str(start_year+1)[-2:]}"

def build_tables(bootstrap: dict[str,Any], fixtures: list[dict[str,Any]], summaries: dict[int,dict[str,Any]], season: str):
    teams = {int(x["id"]):x for x in bootstrap.get("teams",[])}
    positions = {int(x["id"]):x.get("singular_name",x.get("singular_name_short","")) for x in bootstrap.get("element_types",[])}
    players = bootstrap.get("elements",[])
    player_ids = [int(p["id"]) for p in players]
    if len(player_ids) != len(set(player_ids)): raise ValueError("Duplicate FPL element IDs in bootstrap-static")
    fixture_ids = [int(f["id"]) for f in fixtures]
    if len(fixture_ids) != len(set(fixture_ids)): raise ValueError("Duplicate fixture IDs in FPL fixtures feed")
    player_rows, fixture_rows, match_rows = [], [], []
    player_id_set, fixture_id_set = set(player_ids), set(fixture_ids)
    summary_missing, orphan_fixture_rows = [], []
    for p in players:
        team_id = int(p["team"]) if p.get("team") is not None else None
        element_type = int(p["element_type"]) if p.get("element_type") is not None else None
        player_rows.append({
            "season":season,"fpl_element_id":int(p["id"]),"fpl_player_code":p.get("code"),
            "first_name":p.get("first_name",""),"second_name":p.get("second_name",""),"web_name":p.get("web_name",""),
            "team_id":team_id,"team_name":teams.get(team_id,{}).get("name",""),
            "position":positions.get(element_type,""),"status":p.get("status",""),
            "minutes_season":int(p.get("minutes") or 0),"total_points_season":int(p.get("total_points") or 0),
            "now_cost":p.get("now_cost"),"selected_by_percent":p.get("selected_by_percent"),
            "chance_of_playing_next_round":p.get("chance_of_playing_next_round")
        })
    for f in fixtures:
        home_id = int(f["team_h"]) if f.get("team_h") is not None else None
        away_id = int(f["team_a"]) if f.get("team_a") is not None else None
        fixture_rows.append({
            "season":season,"fixture_id":int(f["id"]),"gameweek":f.get("event"),"kickoff_time":f.get("kickoff_time"),
            "team_h_id":home_id,"team_h_name":teams.get(home_id,{}).get("name",""),
            "team_a_id":away_id,"team_a_name":teams.get(away_id,{}).get("name",""),
            "finished":f.get("finished"),"finished_provisional":f.get("finished_provisional"),
            "team_h_score":f.get("team_h_score"),"team_a_score":f.get("team_a_score"),
            "team_h_difficulty":f.get("team_h_difficulty"),"team_a_difficulty":f.get("team_a_difficulty")
        })
    history_minutes = Counter()
    history_points = Counter()
    for p in players:
        element_id = int(p["id"]); summary = summaries.get(element_id)
        if summary is None:
            if int(p.get("minutes") or 0)>0: summary_missing.append(element_id)
            continue
        for h in summary.get("history",[]):
            fixture_id = int(h["fixture"])
            if fixture_id not in fixture_id_set: orphan_fixture_rows.append({"element_id":element_id,"fixture_id":fixture_id})
            opponent_id = int(h["opponent_team"]) if h.get("opponent_team") is not None else None
            row = {
                "season":season,"fpl_element_id":element_id,"fpl_player_code":p.get("code"),
                "player_name":p.get("web_name",""),"fixture_id":fixture_id,"gameweek":h.get("round"),
                "opponent_team_id":opponent_id,"opponent_team_name":teams.get(opponent_id,{}).get("name",""),
                "was_home":bool(h.get("was_home")),"kickoff_time":h.get("kickoff_time")
            }
            for field in MATCH_FIELDS[10:]: row[field] = h.get(field)
            match_rows.append(row)
            history_minutes[element_id] += int(h.get("minutes") or 0)
            history_points[element_id] += int(h.get("total_points") or 0)

    minutes_mismatches = []
    points_mismatches = []
    for p in players:
        element_id = int(p["id"])
        expected_minutes = int(p.get("minutes") or 0)
        actual_minutes = history_minutes[element_id]
        if expected_minutes != actual_minutes:
            minutes_mismatches.append({
                "fpl_element_id": element_id,
                "player_name": p.get("web_name", ""),
                "bootstrap_minutes": expected_minutes,
                "history_minutes": actual_minutes,
                "delta": expected_minutes - actual_minutes,
            })
        expected_points = int(p.get("total_points") or 0)
        actual_points = history_points[element_id]
        if expected_points != actual_points:
            points_mismatches.append({
                "fpl_element_id": element_id,
                "player_name": p.get("web_name", ""),
                "bootstrap_total_points": expected_points,
                "history_total_points": actual_points,
                "delta": expected_points - actual_points,
            })
    report = {
        "season":season,"players":len(player_rows),"fixtures":len(fixture_rows),"player_fixture_rows":len(match_rows),
        "players_with_positive_minutes":sum(int(p["minutes_season"])>0 for p in player_rows),
        "summaries_missing_for_players_with_minutes":summary_missing,"orphan_fixture_rows":orphan_fixture_rows,
        "minutes_reconciliation_mismatches":minutes_mismatches,
        "total_points_reconciliation_mismatches":points_mismatches,
        "unique_player_ids":len(player_id_set),"unique_fixture_ids":len(fixture_id_set),
        "player_fixture_rows_with_unknown_player":sum(int(r["fpl_element_id"]) not in player_id_set for r in match_rows),
        "status":"PASS" if not summary_missing and not orphan_fixture_rows and not minutes_mismatches and not points_mismatches else "BLOCKED"
    }
    return player_rows,fixture_rows,match_rows,report

def write_csv(path:Path, fields:list[str], rows:list[dict[str,Any]]) -> None:
    with path.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields,extrasaction="ignore"); writer.writeheader(); writer.writerows(rows)

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--out-dir",type=Path,required=True)
    parser.add_argument("--workers",type=int,default=2)
    parser.add_argument("--delay",type=float,default=0.15)
    args=parser.parse_args()
    if args.workers<1 or args.workers>4: parser.error("--workers must be between 1 and 4")
    args.out_dir.mkdir(parents=True,exist_ok=True)
    bootstrap_url=f"{BASE_URL}/bootstrap-static/"; fixtures_url=f"{BASE_URL}/fixtures/"
    bootstrap=fetch_json(bootstrap_url); fixtures=fetch_json(fixtures_url)
    season=infer_season(bootstrap.get("events",[])); players=bootstrap.get("elements",[])
    summaries={}; errors=[]
    targets=[p for p in players if int(p.get("minutes") or 0)>0]
    def get_summary(player):
        element_id=int(player["id"]); time.sleep(args.delay)
        return element_id,fetch_json(f"{BASE_URL}/element-summary/{element_id}/")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(get_summary,p):int(p["id"]) for p in targets}
        for future in as_completed(futures):
            element_id=futures[future]
            try:
                key,value=future.result(); summaries[key]=value
            except Exception as exc:
                errors.append({"fpl_element_id":element_id,"error":str(exc)})
    player_rows,fixture_rows,match_rows,report=build_tables(bootstrap,fixtures,summaries,season)
    report["summary_fetch_errors"]=errors; report["summary_fetch_count"]=len(summaries); report["summary_fetch_expected"]=len(targets)
    if errors: report["status"]="BLOCKED"
    (args.out_dir/"bootstrap-static.json").write_text(json.dumps(bootstrap,indent=2),encoding="utf-8")
    (args.out_dir/"fixtures.json").write_text(json.dumps(fixtures,indent=2),encoding="utf-8")
    write_csv(args.out_dir/"fpl_players.csv",PLAYER_FIELDS,player_rows)
    write_csv(args.out_dir/"fpl_fixtures.csv",FIXTURE_FIELDS,fixture_rows)
    write_csv(args.out_dir/"fpl_player_fixture.csv",MATCH_FIELDS,match_rows)
    (args.out_dir/"ingestion_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    def digest(obj): return hashlib.sha256(json.dumps(obj,sort_keys=True).encode()).hexdigest()
    metadata={"source":"Official Fantasy Premier League public API","season":season,"bootstrap_url":bootstrap_url,"fixtures_url":fixtures_url,
              "bootstrap_sha256":digest(bootstrap),"fixtures_sha256":digest(fixtures),
              "summary_endpoint":f"{BASE_URL}/element-summary/{{element_id}}/","summary_fetch_count":len(summaries),"summary_fetch_errors":len(errors)}
    (args.out_dir/"source_metadata.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    return 0 if report["status"]=="PASS" else 2

if __name__=="__main__": raise SystemExit(main())
