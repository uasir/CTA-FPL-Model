#!/usr/bin/env python3
"""Fetch and normalize the official Fantasy Premier League public API.

The output is season-scoped and intentionally does not fuzzy-join FPL players
onto StatsBomb identities. Cross-provider identity requires a separately
verified alias/ID crosswalk.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, os, time, urllib.error, urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_URL = "https://fantasy.premierleague.com/api"
PLAYER_FIELDS = ["season","fpl_element_id","fpl_player_code","first_name","second_name","web_name","team_id","team_name","position","status","minutes_season","total_points_season","now_cost","selected_by_percent","chance_of_playing_next_round","ep_next","ep_this","form","points_per_game","expected_goals","expected_assists","expected_goal_involvements","expected_goals_conceded","ict_index","influence","creativity","threat","starts","bonus","bps","clean_sheets","goals_scored","assists","saves","penalties_saved","penalties_missed","yellow_cards","red_cards","own_goals","goals_conceded"]
FIXTURE_FIELDS = ["season","fixture_id","gameweek","kickoff_time","team_h_id","team_h_name","team_a_id","team_a_name","finished","finished_provisional","team_h_score","team_a_score","team_h_difficulty","team_a_difficulty"]
MATCH_FIELDS = ["season","fpl_element_id","fpl_player_code","player_name","fixture_id","gameweek","opponent_team_id","opponent_team_name","was_home","kickoff_time","minutes","total_points","goals_scored","assists","clean_sheets","goals_conceded","own_goals","penalties_saved","penalties_missed","yellow_cards","red_cards","saves","bonus","bps","influence","creativity","threat","ict_index","starts","expected_goals","expected_assists","expected_goal_involvements","expected_goals_conceded","selected","transfers_balance","transfers_in","transfers_out","value"]

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
            "chance_of_playing_next_round":p.get("chance_of_playing_next_round"),
            # Official FPL expected-points baseline and current-season form fields
            # are preserved with this snapshot's source timestamp and hash.
            "ep_next":p.get("ep_next"),"ep_this":p.get("ep_this"),
            "form":p.get("form"),"points_per_game":p.get("points_per_game"),
            "expected_goals":p.get("expected_goals"),"expected_assists":p.get("expected_assists"),
            "expected_goal_involvements":p.get("expected_goal_involvements"),
            "expected_goals_conceded":p.get("expected_goals_conceded"),
            "ict_index":p.get("ict_index"),"influence":p.get("influence"),
            "creativity":p.get("creativity"),"threat":p.get("threat"),
            "starts":p.get("starts"),"bonus":p.get("bonus"),"bps":p.get("bps"),
            "clean_sheets":p.get("clean_sheets"),"goals_scored":p.get("goals_scored"),
            "assists":p.get("assists"),"saves":p.get("saves"),
            "penalties_saved":p.get("penalties_saved"),"penalties_missed":p.get("penalties_missed"),
            "yellow_cards":p.get("yellow_cards"),"red_cards":p.get("red_cards"),
            "own_goals":p.get("own_goals"),"goals_conceded":p.get("goals_conceded")
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
        "official_ep_next_coverage_count":sum(p.get("ep_next") not in (None,"") for p in player_rows),
        "official_ep_next_missing_ids":[p["fpl_element_id"] for p in player_rows if p.get("ep_next") in (None,"")],
        "official_ep_this_coverage_count":sum(p.get("ep_this") not in (None,"") for p in player_rows),
        "player_fixture_rows_with_unknown_player":sum(int(r["fpl_element_id"]) not in player_id_set for r in match_rows),
        "status":"PASS" if not summary_missing and not orphan_fixture_rows and not minutes_mismatches and not points_mismatches else "BLOCKED"
    }
    return player_rows,fixture_rows,match_rows,report

def reconcile_snapshot(bootstrap: dict[str, Any], fixtures: list[dict[str, Any]],
                        summaries: dict[int, dict[str, Any]], season: str,
                        max_retries: int = 2, retry_delay: float = 0.25):
    """Refresh inconsistent FPL summary snapshots without weakening reconciliation.

    After the initial per-player summary batch, refresh bootstrap-static and
    fixtures. If aggregate minutes/points disagree, refresh only the affected
    element-summary endpoints, then refresh bootstrap-static/fixtures again.
    Persistent mismatches remain BLOCKED; no points or minutes are adjusted.
    """
    if max_retries < 0:
        raise ValueError("max_retries must be non-negative")
    current_summaries = dict(summaries)
    attempts = []
    current_bootstrap, current_fixtures = bootstrap, fixtures
    player_rows = fixture_rows = match_rows = report = None

    for attempt in range(max_retries + 1):
        refresh_errors = []
        if attempt > 0:
            mismatch_ids = {
                int(item["fpl_element_id"])
                for field in ("minutes_reconciliation_mismatches", "total_points_reconciliation_mismatches")
                for item in (report or {}).get(field, [])
            }
            mismatch_ids.update(
                int(element_id) for element_id in (report or {}).get("summaries_missing_for_players_with_minutes", [])
            )
            if not mismatch_ids:
                break
            if retry_delay:
                time.sleep(retry_delay)
            for element_id in sorted(mismatch_ids):
                try:
                    current_summaries[element_id] = fetch_json(
                        f"{BASE_URL}/element-summary/{element_id}/"
                    )
                except Exception as exc:
                    refresh_errors.append({"fpl_element_id": element_id, "error": str(exc)})
            current_bootstrap = fetch_json(f"{BASE_URL}/bootstrap-static/")
            current_fixtures = fetch_json(f"{BASE_URL}/fixtures/")
            if infer_season(current_bootstrap.get("events", [])) != season:
                raise ValueError("FPL season changed during consistency retry")

        player_rows, fixture_rows, match_rows, report = build_tables(
            current_bootstrap, current_fixtures, current_summaries, season
        )
        attempts.append({
            "attempt": attempt + 1,
            "status": report["status"],
            "minutes_mismatch_count": len(report["minutes_reconciliation_mismatches"]),
            "total_points_mismatch_count": len(report["total_points_reconciliation_mismatches"]),
            "refreshed_summary_errors": refresh_errors,
        })
        if report["status"] == "PASS":
            break

    report["consistency_capture_attempts"] = attempts
    report["consistency_retry_limit"] = max_retries
    report["consistency_retry_policy"] = (
        "Refresh only player summaries whose aggregate minutes/points disagree, "
        "then refresh bootstrap-static and fixtures; persistent mismatches remain BLOCKED."
    )
    report["summary_refresh_errors"] = [
        error for attempt in attempts for error in attempt["refreshed_summary_errors"]
    ]
    if report["summary_refresh_errors"]:
        report["status"] = "BLOCKED"
    return current_bootstrap, current_fixtures, current_summaries, player_rows, fixture_rows, match_rows, report


def write_csv(path:Path, fields:list[str], rows:list[dict[str,Any]]) -> None:
    with path.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields,extrasaction="ignore"); writer.writeheader(); writer.writerows(rows)

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--out-dir",type=Path,required=True)
    parser.add_argument("--workers",type=int,default=2)
    parser.add_argument("--delay",type=float,default=0.15)
    parser.add_argument("--consistency-retries",type=int,default=2)
    args=parser.parse_args()
    if args.workers<1 or args.workers>4: parser.error("--workers must be between 1 and 4")
    if args.consistency_retries<0 or args.consistency_retries>5:
        parser.error("--consistency-retries must be between 0 and 5")
    args.out_dir.mkdir(parents=True,exist_ok=True)
    capture_started_at=datetime.now(timezone.utc)
    bootstrap_url=f"{BASE_URL}/bootstrap-static/"; fixtures_url=f"{BASE_URL}/fixtures/"
    bootstrap=fetch_json(bootstrap_url); fixtures=fetch_json(fixtures_url)
    season=infer_season(bootstrap.get("events",[])); players=bootstrap.get("elements",[])
    summaries={}; errors=[]
    targets=players  # Include the full roster so historical ownership is not limited to players with minutes.
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

    (bootstrap,fixtures,summaries,player_rows,fixture_rows,match_rows,report) = reconcile_snapshot(
        bootstrap, fixtures, summaries, season,
        max_retries=args.consistency_retries,
    )
    report["summary_fetch_errors"]=errors
    report["summary_fetch_count"]=len(summaries)
    report["summary_fetch_expected"]=len(targets)
    report["players_with_history_count"]=sum(bool(x.get("history")) for x in summaries.values())
    if errors:
        report["status"]="BLOCKED"
    (args.out_dir/"bootstrap-static.json").write_text(json.dumps(bootstrap,indent=2),encoding="utf-8")
    (args.out_dir/"fixtures.json").write_text(json.dumps(fixtures,indent=2),encoding="utf-8")
    write_csv(args.out_dir/"fpl_players.csv",PLAYER_FIELDS,player_rows)
    write_csv(args.out_dir/"fpl_fixtures.csv",FIXTURE_FIELDS,fixture_rows)
    write_csv(args.out_dir/"fpl_player_fixture.csv",MATCH_FIELDS,match_rows)
    fetched_at=datetime.now(timezone.utc)
    report["capture_started_at_utc"]=capture_started_at.isoformat()
    report["capture_completed_at_utc"]=fetched_at.isoformat()
    (args.out_dir/"ingestion_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    future_events=[]
    for event in bootstrap.get("events",[]):
        if not event.get("deadline_time"): continue
        deadline=datetime.fromisoformat(str(event["deadline_time"]).replace("Z","+00:00"))
        if deadline>fetched_at: future_events.append((deadline,event))
    next_event=min(future_events,key=lambda x:x[0]) if future_events else None
    hours_to_deadline=(next_event[0]-fetched_at).total_seconds()/3600 if next_event else None
    snapshot_timing=("PRE_DEADLINE_WITHIN_24H" if hours_to_deadline is not None and hours_to_deadline<=24
                     else "PRE_DEADLINE_OVER_24H" if hours_to_deadline is not None else "NO_FUTURE_DEADLINE")
    def digest(obj): return hashlib.sha256(json.dumps(obj,sort_keys=True).encode()).hexdigest()
    bootstrap_hash=digest(bootstrap)
    fixtures_hash=digest(fixtures)
    summaries_hash=digest({str(key):summaries[key] for key in sorted(summaries)})
    source_snapshot_id=hashlib.sha256(
        json.dumps({"bootstrap":bootstrap_hash,"fixtures":fixtures_hash,"element_summaries":summaries_hash},
                   sort_keys=True,separators=(",",":")).encode("utf-8")
    ).hexdigest()
    def file_digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
    metadata={"source":"Official Fantasy Premier League public API","season":season,"fetched_at_utc":fetched_at.isoformat(),
              "snapshot_timing":snapshot_timing,
              "point_in_time_status":"CURRENT_CAPTURE_ONLY_HISTORICAL_VINTAGE_UNVERIFIED",
              "source_snapshot_id":source_snapshot_id,
              "pipeline_git_commit":os.environ.get("GITHUB_SHA"),
              "workflow_run_id":os.environ.get("GITHUB_RUN_ID"),
              "workflow_ref":os.environ.get("GITHUB_WORKFLOW_REF"),
              "ingestion_script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "next_deadline_event_id":next_event[1].get("id") if next_event else None,
              "next_deadline_time_utc":next_event[0].isoformat() if next_event else None,
              "hours_until_next_deadline":round(hours_to_deadline,3) if hours_to_deadline is not None else None,
              "bootstrap_url":bootstrap_url,"fixtures_url":fixtures_url,
              "bootstrap_sha256":bootstrap_hash,"fixtures_sha256":fixtures_hash,
              "element_summaries_sha256":summaries_hash,
              "normalized_players_sha256":file_digest(args.out_dir/"fpl_players.csv"),
              "normalized_fixtures_sha256":file_digest(args.out_dir/"fpl_fixtures.csv"),
              "normalized_player_fixture_sha256":file_digest(args.out_dir/"fpl_player_fixture.csv"),
              "summary_endpoint":f"{BASE_URL}/element-summary/{{element_id}}/",
              "summary_fetch_count":len(summaries),"summary_fetch_errors":len(errors)}
    (args.out_dir/"source_metadata.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    return 0 if report["status"]=="PASS" else 2

if __name__=="__main__": raise SystemExit(main())
