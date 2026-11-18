#!/usr/bin/env python3
"""Build a transparent one-gameweek forecast snapshot from official FPL fields.

This is an exploratory baseline adapter, not a CTA-trained predictive model.
It preserves official ep_next as the points baseline and uses the latest
completed gameweek's minutes as an explicitly labelled minutes proxy.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math
from datetime import datetime,timezone
from pathlib import Path


POSITION_MAP={
    "Goalkeeper":"GKP","Defender":"DEF","Midfielder":"MID","Forward":"FWD",
    "GKP":"GKP","DEF":"DEF","MID":"MID","FWD":"FWD",
}


def read_csv(path):
    with path.open(newline="",encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def parse_time(value):
    return datetime.fromisoformat(str(value).replace("Z","+00:00"))


def finite_number(value):
    if value in (None,""):
        return None
    try:
        number=float(value)
    except (TypeError,ValueError):
        return None
    return number if math.isfinite(number) else None


def build_snapshot(players,gameweek_rows,fixtures,source_metadata,eo_rows=None,eo_report=None):
    target_gw=source_metadata.get("next_deadline_event_id")
    deadline_raw=source_metadata.get("next_deadline_time_utc")
    fetched_raw=source_metadata.get("fetched_at_utc")
    if target_gw is None or not deadline_raw or not fetched_raw:
        raise ValueError("source metadata must identify the next deadline and fetch timestamp")
    deadline=parse_time(deadline_raw)
    fetched=parse_time(fetched_raw)
    if fetched>=deadline:
        raise ValueError("FPL source snapshot was not captured before the target deadline")
    if not source_metadata.get("bootstrap_sha256") or not source_metadata.get("fixtures_sha256"):
        raise ValueError("source metadata must include bootstrap and fixtures SHA-256 hashes")

    fixture_counts={}
    for fixture in fixtures:
        if finite_number(fixture.get("event"))!=int(target_gw):
            continue
        for field in ("team_h","team_a"):
            team=finite_number(fixture.get(field))
            if team is not None and team>0:
                team_id=int(team)
                fixture_counts[team_id]=fixture_counts.get(team_id,0)+1
    if not fixture_counts:
        raise ValueError("No upcoming fixtures found for the target gameweek")

    latest_by_player={}
    for row in gameweek_rows:
        player_id=str(row.get("fpl_element_id") or "").strip()
        gw=finite_number(row.get("gameweek"))
        if not player_id or gw is None:
            continue
        current=latest_by_player.get(player_id)
        if current is None or int(gw)>int(current["_gw"]):
            latest_by_player[player_id]={**row,"_gw":int(gw)}

    eo_by_player={}
    if eo_rows is not None or eo_report is not None:
        if eo_rows is None or eo_report is None:
            raise ValueError("EO CSV and EO report must be supplied together")
        if eo_report.get("status")!="CAPTURED_POST_DEADLINE_PICKS" or eo_report.get("picks_lock_verified") is not True:
            raise ValueError("EO input is not verified as post-deadline locked picks")
        if int(eo_report.get("gameweek",-1))!=int(target_gw):
            raise ValueError("EO snapshot gameweek does not match the forecast target gameweek")
        required_eo_metadata=("cohort","rank_cohort_captured_at_utc","deadline_time_utc","picks_captured_at_utc","sample_managers")
        missing_eo_metadata=[field for field in required_eo_metadata if eo_report.get(field) in (None,"")]
        if missing_eo_metadata:
            raise ValueError("EO snapshot is missing cohort/lock provenance: "+", ".join(missing_eo_metadata))
        eo_deadline=parse_time(eo_report["deadline_time_utc"])
        rank_captured=parse_time(eo_report["rank_cohort_captured_at_utc"])
        picks_captured=parse_time(eo_report["picks_captured_at_utc"])
        if eo_deadline!=deadline or rank_captured>=eo_deadline or picks_captured<=eo_deadline:
            raise ValueError("EO rank cohort must be pre-deadline and picks must be post-deadline for the same deadline")
        if isinstance(eo_report.get("sample_managers"),bool) or int(eo_report["sample_managers"])<1:
            raise ValueError("EO sample_managers must be a positive integer")
        for row in eo_rows:
            if int(row.get("gameweek",-1))!=int(target_gw):
                raise ValueError("EO row gameweek does not match forecast target")
            player_id=str(row.get("fpl_element_id") or "")
            value=finite_number(row.get("effective_ownership_pct"))
            if player_id and value is not None and value>=0:
                eo_by_player[player_id]=value

    forecasts=[]
    missing_ep_next=[]
    invalid_players=[]
    no_minutes_history=[]
    minutes_sources={}
    for player in players:
        player_id=str(player.get("fpl_element_id") or "")
        ep_next=finite_number(player.get("ep_next"))
        price_cost=finite_number(player.get("now_cost"))
        team_id=finite_number(player.get("team_id"))
        position=POSITION_MAP.get(str(player.get("position") or ""))
        if ep_next is None:
            missing_ep_next.append(player_id)
            continue
        if price_cost is None or price_cost<=0 or team_id is None or team_id<1 or position is None:
            invalid_players.append(player_id)
            continue
        history=latest_by_player.get(player_id)
        next_fixtures=fixture_counts.get(int(team_id),0)
        last_minutes=finite_number(history.get("target_minutes")) if history else None
        prior_fixture_count=finite_number(history.get("target_fixtures_count")) if history else None
        if history is None or last_minutes is None:
            minutes=0.0
            minutes_source="no_history_zero_fallback"
            no_minutes_history.append(player_id)
        elif next_fixtures==0:
            minutes=0.0
            minutes_source="no_upcoming_fixture"
        elif prior_fixture_count is not None and prior_fixture_count>0:
            minutes=(last_minutes/prior_fixture_count)*next_fixtures
            minutes_source="latest_completed_gameweek_per_fixture_scaled_to_target_fixture_count"
        else:
            minutes=last_minutes*next_fixtures
            minutes_source="latest_completed_gameweek_unscaled_fixture_fallback"
        if minutes<0:
            invalid_players.append(player_id)
            continue
        record={
            "fpl_element_id":int(player_id),
            "web_name":str(player.get("web_name") or ""),
            "team_name":str(player.get("team_name") or ""),
            "expected_points":ep_next,
            "expected_minutes":minutes,
            "minutes_proxy_source":minutes_source,
            "next_fixtures_count":next_fixtures,
            "price":price_cost/10.0,
            "position":position,
            "team_id":int(team_id),
        }
        availability=finite_number(player.get("chance_of_playing_next_round"))
        if availability is not None:
            if not 0<=availability<=100:
                invalid_players.append(player_id)
                continue
            record["availability_probability"]=availability/100.0
        if player_id in eo_by_player:
            record["effective_ownership_pct"]=eo_by_player[player_id]
        forecasts.append(record)

    if not forecasts:
        raise ValueError("No usable player forecasts were built")
    total=len(players)
    ep_coverage=len(forecasts)
    minutes_proxy_coverage=ep_coverage-len(no_minutes_history)
    eo_coverage=sum("effective_ownership_pct" in row for row in forecasts)
    forecasts.sort(key=lambda row:row["fpl_element_id"])
    quality={
        "validation_status":"EXPLORATORY_ONLY",
        "point_in_time_status":"VERIFIED",
        "data_coverage":{
            "target_gameweek":int(target_gw),
            "source_fetched_at_utc":fetched.isoformat(),
            "target_deadline_utc":deadline.isoformat(),
            "bootstrap_sha256":source_metadata["bootstrap_sha256"],
            "fixtures_sha256":source_metadata["fixtures_sha256"],
            "hours_before_deadline":round((deadline-fetched).total_seconds()/3600,3),
            "roster_players":total,
            "target_gameweek_fixtures":sum(fixture_counts.values())//2,
            "teams_with_target_fixtures":len(fixture_counts),
            "forecast_players":ep_coverage,
            "ep_next_coverage_pct":round(ep_coverage/total*100,3) if total else 0,
            "minutes_proxy_players":minutes_proxy_coverage,
            "minutes_proxy_missing_history_players":len(no_minutes_history),
            "eo_players":eo_coverage,
            "eo_sample_managers":eo_report.get("sample_managers") if eo_report else 0,
            "eo_cohort":eo_report.get("cohort") if eo_report else "unavailable",
            "eo_rank_cohort_captured_at_utc":eo_report.get("rank_cohort_captured_at_utc") if eo_report else None,
            "eo_deadline_time_utc":eo_report.get("deadline_time_utc") if eo_report else None,
            "eo_picks_captured_at_utc":eo_report.get("picks_captured_at_utc") if eo_report else None,
            "eo_picks_lock_verified":bool(eo_report and eo_report.get("picks_lock_verified") is True),
            "eo_source":"CTA official FPL ranked manager picks" if eo_report else "unavailable",
            "invalid_players_excluded":len(invalid_players),
        },
        "limitations":[
            "expected_points is the official FPL ep_next baseline, not a CTA-trained prediction.",
            "expected_minutes is a proxy: latest completed-gameweek minutes per fixture scaled by the target gameweek fixture count; it is not a trained minutes forecast.",
            "Players without gameweek history receive a zero-minute fallback; players with no target-gameweek fixture also receive zero expected minutes.",
            "Historical lagged training rows remain point-in-time-unverified because older source vintages are not durably archived.",
            "The current EO field, when present, is a weighted top-10k sample and not whole-game effective ownership.",
            "Player variance and CoVar are not supplied to this baseline snapshot.",
            "This snapshot covers one upcoming gameweek only.",
        ],
    }
    identity_payload={
        "model_version":"cta-fpl-official-epnext-fixture-scaled-minutes-proxy-v0.1.1",
        "forecast_horizon_gameweeks":1,
        "player_forecasts":forecasts,
        "forecast_quality":quality,
    }
    snapshot_id=hashlib.sha256(json.dumps(identity_payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return {
        "forecast_snapshot_id":snapshot_id,
        "model_version":"cta-fpl-official-epnext-fixture-scaled-minutes-proxy-v0.1.1",
        "forecast_horizon_gameweeks":1,
        "forecast_quality":quality,
        "player_forecasts":forecasts,
    },{
        "status":"PASS_EXPLORATORY_BASELINE",
        "target_gameweek":int(target_gw),
        "forecast_snapshot_id":snapshot_id,
        "players_in_source":total,
        "forecast_players":ep_coverage,
        "missing_ep_next_ids":missing_ep_next,
        "invalid_player_ids":invalid_players,
        "no_minutes_history_ids":no_minutes_history,
        "eo_coverage_players":eo_coverage,
        "limitations":quality["limitations"],
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--players",type=Path,required=True)
    parser.add_argument("--gameweek-rows",type=Path,required=True)
    parser.add_argument("--fixtures",type=Path,required=True)
    parser.add_argument("--source-metadata",type=Path,required=True)
    parser.add_argument("--eo-csv",type=Path)
    parser.add_argument("--eo-report",type=Path)
    parser.add_argument("--out-dir",type=Path,required=True)
    args=parser.parse_args()
    if bool(args.eo_csv)!=bool(args.eo_report):
        parser.error("--eo-csv and --eo-report must be supplied together")
    source_metadata=json.loads(args.source_metadata.read_text(encoding="utf-8"))
    eo_rows=read_csv(args.eo_csv) if args.eo_csv else None
    eo_report=json.loads(args.eo_report.read_text(encoding="utf-8")) if args.eo_report else None
    snapshot,report=build_snapshot(
        read_csv(args.players),read_csv(args.gameweek_rows),read_csv(args.fixtures),source_metadata,eo_rows,eo_report
    )
    args.out_dir.mkdir(parents=True,exist_ok=True)
    (args.out_dir/"fpl_baseline_forecast_snapshot.json").write_text(json.dumps(snapshot,indent=2),encoding="utf-8")
    (args.out_dir/"fpl_baseline_forecast_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
