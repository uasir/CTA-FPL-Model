#!/usr/bin/env python3
"""Build leakage-safe FPL player-fixture rows from official API history.

Every feature for a gameweek is computed only from strictly earlier gameweeks.
All fixtures in a double gameweek share the same pre-deadline feature state.
"""
from __future__ import annotations
import argparse, csv, json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

AGG_FIELDS=["minutes","total_points","goals_scored","assists","starts","expected_goals","expected_assists","expected_goal_involvements","clean_sheets","bonus","bps","defensive_contribution"]
OUTPUT_FIELDS=[
 "season","fpl_element_id","fpl_player_code","fixture_id","gameweek","kickoff_time","features_as_of_deadline",
 "team_id_at_fixture","opponent_team_id","was_home","team_difficulty_snapshot","opponent_difficulty_snapshot",
 "prior_gameweeks_count","prior_gw_points","prior_gw_minutes","prior3_gw_points_avg",
 "prior3_gw_minutes_avg","prior3_gw_xg_avg","prior3_gw_xa_avg",
 "prior5_gw_points_avg","prior5_gw_minutes_avg","season_to_date_points",
 "season_to_date_minutes","season_to_date_xg","season_to_date_xa","season_to_date_points_per90",
 "target_minutes","target_total_points","target_goals","target_assists","target_expected_goals","target_expected_assists"
]
def num(v):
    try:
        if v is None or str(v).strip()=="": return 0.0
        return float(v)
    except (TypeError,ValueError):
        return 0.0
def read_csv(path):
    with path.open(newline="",encoding="utf-8-sig") as h: return list(csv.DictReader(h))
def mean(values):
    return sum(values)/len(values) if values else ""
def parse_time(value):
    if not value: raise ValueError("Missing timestamp in FPL history/deadline data")
    return datetime.fromisoformat(str(value).replace("Z","+00:00"))

def build_dataset(players,fixtures,history,bootstrap):
    fixture_map={str(x["fixture_id"]):x for x in fixtures}
    deadlines={int(x["id"]):parse_time(x["deadline_time"]) for x in bootstrap.get("events",[]) if x.get("deadline_time")}
    if not deadlines: raise ValueError("No gameweek deadlines found in bootstrap-static")
    grouped=defaultdict(lambda:defaultdict(list))
    for row in history:
        key=(str(row["fpl_element_id"]),str(row["fpl_player_code"] or ""))
        gw=int(row["gameweek"] or 0)
        if gw<=0: raise ValueError(f"Missing/invalid gameweek for player {key}")
        if str(row["fixture_id"]) not in fixture_map:
            raise ValueError(f"Unknown fixture {row['fixture_id']} in player history")
        grouped[key][gw].append(row)
    player_meta={str(p["fpl_element_id"]):p for p in players}
    output=[]
    for (element_id,player_code),gws in grouped.items():
        player_history=[row for rows in gws.values() for row in rows]
        for gw in sorted(gws):
            if gw not in deadlines: raise ValueError(f"Missing deadline for gameweek {gw}")
            cutoff=deadlines[gw]
            current_rows=gws[gw]
            for target in current_rows:
                if parse_time(target.get("kickoff_time"))<cutoff:
                    raise ValueError(f"Target fixture {target['fixture_id']} kicks off before GW{gw} deadline")
            known=[row for row in player_history if parse_time(row.get("kickoff_time"))<cutoff]
            known_by_gw=defaultdict(list)
            for row in known: known_by_gw[int(row["gameweek"])].append(row)
            prior=[]
            for prior_gw in sorted(known_by_gw):
                prior.append({field:sum(num(x.get(field)) for x in known_by_gw[prior_gw]) for field in AGG_FIELDS})
            prior3=prior[-3:];prior5=prior[-5:]
            sum_prior={field:sum(x[field] for x in prior) for field in AGG_FIELDS}
            last=prior[-1] if prior else None
            for row in sorted(current_rows,key=lambda x:(x.get("kickoff_time") or "",str(x.get("fixture_id")))):
                fx=fixture_map[str(row["fixture_id"])]
                was_home=str(row.get("was_home","")).lower() in {"true","1"}
                team_id=int(fx["team_h_id"] if was_home else fx["team_a_id"])
                team_diff=fx.get("team_h_difficulty") if was_home else fx.get("team_a_difficulty")
                opp_diff=fx.get("team_a_difficulty") if was_home else fx.get("team_h_difficulty")
                rowout={
                    "season":row.get("season",""),"fpl_element_id":element_id,"fpl_player_code":player_code,
                    "fixture_id":row["fixture_id"],"gameweek":gw,"kickoff_time":row.get("kickoff_time",""),
                    "features_as_of_deadline":cutoff.isoformat(),
                    "team_id_at_fixture":team_id,"opponent_team_id":row.get("opponent_team_id",""),
                    "was_home":was_home,"team_difficulty_snapshot":team_diff,"opponent_difficulty_snapshot":opp_diff,
                    "prior_gameweeks_count":len(prior),
                    "prior_gw_points":last["total_points"] if last else "",
                    "prior_gw_minutes":last["minutes"] if last else "",
                    "prior3_gw_points_avg":mean([x["total_points"] for x in prior3]),
                    "prior3_gw_minutes_avg":mean([x["minutes"] for x in prior3]),
                    "prior3_gw_xg_avg":mean([x["expected_goals"] for x in prior3]),
                    "prior3_gw_xa_avg":mean([x["expected_assists"] for x in prior3]),
                    "prior5_gw_points_avg":mean([x["total_points"] for x in prior5]),
                    "prior5_gw_minutes_avg":mean([x["minutes"] for x in prior5]),
                    "season_to_date_points":sum_prior["total_points"],
                    "season_to_date_minutes":sum_prior["minutes"],
                    "season_to_date_xg":sum_prior["expected_goals"],
                    "season_to_date_xa":sum_prior["expected_assists"],
                    "season_to_date_points_per90":(sum_prior["total_points"]*90/sum_prior["minutes"]) if sum_prior["minutes"]>0 else "",
                    "target_minutes":row.get("minutes",""),"target_total_points":row.get("total_points",""),
                    "target_goals":row.get("goals_scored",""),"target_assists":row.get("assists",""),
                    "target_expected_goals":row.get("expected_goals",""),"target_expected_assists":row.get("expected_assists","")
                }
                output.append(rowout)
    keys=[(x["fpl_element_id"],x["fixture_id"]) for x in output]
    if len(keys)!=len(set(keys)): raise ValueError("Duplicate player-fixture keys in output")
    report={
        "rows":len(output),"unique_players":len({x["fpl_element_id"] for x in output}),
        "unique_fixtures":len({x["fixture_id"] for x in output}),
        "gameweeks":sorted({x["gameweek"] for x in output}),
        "status":"PASS_STRUCTURAL_ONLY","leakage_policy":"Only player history with actual kickoff_time strictly before the target gameweek deadline_time is used; all fixtures in the same gameweek share one pre-deadline feature snapshot.",
        "point_in_time_status":"NOT_VERIFIED",
        "point_in_time_caveat":"The current official API snapshot may include retrospective revisions to earlier gameweek stats. Strict historical backtests require archived pre-deadline snapshots.",
        "fixture_difficulty_status":"CURRENT_SNAPSHOT_ONLY_NOT_POINT_IN_TIME_VERIFIED",
        "deadline_cutoff_policy":"history kickoff_time < bootstrap-static event deadline_time",
        "player_universe":"only players with a positive season-minute total were fetched for element-summary history"
    }
    return output,report
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--players",type=Path,required=True);p.add_argument("--fixtures",type=Path,required=True)
    p.add_argument("--history",type=Path,required=True);p.add_argument("--bootstrap",type=Path,required=True);p.add_argument("--out-dir",type=Path,required=True)
    a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=True)
    bootstrap=json.loads(a.bootstrap.read_text(encoding="utf-8"))
    rows,report=build_dataset(read_csv(a.players),read_csv(a.fixtures),read_csv(a.history),bootstrap)
    with (a.out_dir/"fpl_lagged_training.csv").open("w",newline="",encoding="utf-8") as h:
        w=csv.DictWriter(h,fieldnames=OUTPUT_FIELDS);w.writeheader();w.writerows(rows)
    (a.out_dir/"fpl_lagged_training_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
