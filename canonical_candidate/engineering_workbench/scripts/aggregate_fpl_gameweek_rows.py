#!/usr/bin/env python3
"""Aggregate fixture-level lagged rows into FPL player-gameweek targets."""
from __future__ import annotations
import argparse,csv,json
from collections import defaultdict
from pathlib import Path

FEATURE_FIELDS=[
 "season","fpl_element_id","fpl_player_code","gameweek","features_as_of_deadline",
 "prior_gameweeks_count","prior_gw_points","prior_gw_minutes","prior3_gw_points_avg",
 "prior3_gw_minutes_avg","prior3_gw_xg_avg","prior3_gw_xa_avg",
 "prior5_gw_points_avg","prior5_gw_minutes_avg","season_to_date_points",
 "season_to_date_minutes","season_to_date_xg","season_to_date_xa","season_to_date_points_per90","prior_gw_selected_count","prior_gw_selected_pct","prior3_gw_selected_pct_avg","prior5_gw_selected_pct_avg"
]
TARGET_FIELDS=["target_minutes","target_total_points","target_goals","target_assists","target_expected_goals","target_expected_assists"]
OUTPUT_FIELDS=FEATURE_FIELDS+[
 "target_fixtures_count","home_fixtures_count","team_ids","opponent_team_ids",
 "team_difficulty_snapshot_avg","opponent_difficulty_snapshot_avg"
]+TARGET_FIELDS

def number(value):
    try:return float(value) if value not in (None,"") else 0.0
    except (TypeError,ValueError):return 0.0

def aggregate(rows):
    groups=defaultdict(list)
    for row in rows:
        groups[(str(row["fpl_element_id"]),str(row["gameweek"]))].append(row)
    output=[]
    for (player_id,gw),items in sorted(groups.items(),key=lambda x:(x[0][0],int(x[0][1]))):
        first=items[0]
        for field in FEATURE_FIELDS:
            values={str(x.get(field,"")) for x in items}
            if len(values)>1:
                raise ValueError(f"Pre-deadline feature {field} differs within player {player_id} GW{gw}")
        home=sum(str(x.get("was_home","")).lower() in {"true","1"} for x in items)
        teams=sorted({str(x.get("team_id_at_fixture","")) for x in items if x.get("team_id_at_fixture","")})
        opponents=sorted({str(x.get("opponent_team_id","")) for x in items if x.get("opponent_team_id","")})
        out={field:first.get(field,"") for field in FEATURE_FIELDS}
        out.update({
            "target_fixtures_count":len(items),"home_fixtures_count":home,
            "team_ids":";".join(teams),"opponent_team_ids":";".join(opponents),
            "team_difficulty_snapshot_avg":sum(number(x.get("team_difficulty_snapshot")) for x in items)/len(items),
            "opponent_difficulty_snapshot_avg":sum(number(x.get("opponent_difficulty_snapshot")) for x in items)/len(items)
        })
        for field in TARGET_FIELDS:out[field]=sum(number(x.get(field)) for x in items)
        output.append(out)
    keys=[(x["fpl_element_id"],x["gameweek"]) for x in output]
    if len(keys)!=len(set(keys)):raise ValueError("Duplicate player-gameweek keys after aggregation")
    report={
        "rows":len(output),"unique_players":len({x["fpl_element_id"] for x in output}),
        "gameweeks":sorted({int(x["gameweek"]) for x in output}),
        "fixture_rows_aggregated":len(rows),
        "status":"PASS_STRUCTURAL_ONLY",
        "target_grain":"one row per FPL player-gameweek; target points and minutes sum across all fixtures in that gameweek",
        "point_in_time_status":"NOT_VERIFIED",
        "feature_policy":"Pre-deadline features are shared across all fixtures in the same gameweek; postponed prior-GW fixtures after the deadline are excluded."
    }
    return output,report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True);p.add_argument("--out-dir",type=Path,required=True)
    a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=True)
    with a.input.open(newline="",encoding="utf-8-sig") as h:rows=list(csv.DictReader(h))
    output,report=aggregate(rows)
    with (a.out_dir/"fpl_lagged_gameweek.csv").open("w",newline="",encoding="utf-8") as h:
        w=csv.DictWriter(h,fieldnames=OUTPUT_FIELDS);w.writeheader();w.writerows(output)
    (a.out_dir/"fpl_lagged_gameweek_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
