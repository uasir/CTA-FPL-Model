#!/usr/bin/env python3
"""Build a transparent one-gameweek forecast snapshot from official FPL fields.

This is an exploratory baseline adapter, not a CTA-trained predictive model.
It preserves official ep_next as the points baseline and uses the latest
completed gameweek's minutes as an explicitly labelled minutes proxy.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math
from collections import Counter,defaultdict
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


def build_snapshot(players,gameweek_rows,fixtures,source_metadata,eo_rows=None,eo_report=None,cta_rows=None,cta_report=None):
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
        fixture_gameweek=finite_number(fixture.get("gameweek") or fixture.get("event"))
        if fixture_gameweek!=int(target_gw):
            continue
        for field in ("team_h_id","team_a_id","team_h","team_a"):
            if field in ("team_h","team_a") and (fixture.get("team_h_id") or fixture.get("team_a_id")):
                continue
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

    cta_by_player={}
    cta_status_counts=Counter()
    cta_verified_players=set()
    cta_prior_players=set()
    if cta_rows is not None or cta_report is not None:
        if cta_rows is None or cta_report is None:
            raise ValueError("CTA CSV and CTA report must be supplied together")
        if cta_report.get("status")!="PASS_LAGGED_VERIFIED_FEATURES_BUILT":
            raise ValueError("CTA sidecar is not a passed verified upcoming-feature build")
        if int(target_gw) not in {int(value) for value in cta_report.get("target_gameweeks",[])}:
            raise ValueError("CTA sidecar gameweek does not match forecast target")
        if cta_report.get("decision_use_status")!="RESEARCH_ONLY_NOT_IN_BASELINE":
            raise ValueError("CTA sidecar must remain explicitly research-only")
        if cta_report.get("prediction_training_eligible") is not False or cta_report.get("production_eligible") is not False:
            raise ValueError("Unvalidated CTA features cannot be marked training- or production-eligible")
        cta_snapshot=parse_time(cta_report.get("source_snapshot_as_of"))
        if cta_snapshot>deadline:
            raise ValueError("CTA source snapshot was captured after the target FPL deadline")
        for row in cta_rows:
            if int(row.get("gameweek",-1))!=int(target_gw):
                raise ValueError("CTA feature row gameweek does not match forecast target")
            row_deadline=parse_time(row.get("features_as_of_deadline"))
            if row_deadline!=deadline:
                raise ValueError("CTA feature deadline does not match official FPL target deadline")
            player_id=str(row.get("fpl_element_id") or "").strip()
            if not player_id:
                raise ValueError("CTA feature row is missing fpl_element_id")
            cta_by_player.setdefault(player_id,[]).append(row)
            cta_status_counts[str(row.get("identity_status") or "UNKNOWN")]+=1
            if str(row.get("identity_verified") or "").lower() in {"true","1"}:
                cta_verified_players.add(player_id)
            if finite_number(row.get("cta_prior_matches_count")) and finite_number(row.get("cta_prior_matches_count"))>0:
                cta_prior_players.add(player_id)

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
        if cta_report is not None:
            player_cta_rows=sorted(cta_by_player.get(player_id,[]),key=lambda row:str(row.get("fixture_id") or ""))
            fixture_features=[]
            player_identity_verified=player_id in cta_verified_players
            player_has_prior=player_id in cta_prior_players
            if not player_identity_verified:
                coverage_status="NO_VERIFIED_IDENTITY"
                identity_status="NO_VERIFIED_IDENTITY"
            elif player_has_prior:
                coverage_status="HAS_PRIOR_VERIFIED_HISTORY"
                identity_status="VERIFIED_IDENTITY_AND_PRIOR_CTA_HISTORY"
            else:
                coverage_status="VERIFIED_IDENTITY_NO_PRIOR_HISTORY"
                identity_status="VERIFIED_IDENTITY_NO_PRIOR_HISTORY"
            for cta_row in player_cta_rows:
                feature_values={}
                for feature in (
                    "minutes_played","goals","assists","own_goals","shots","shots_on_target",
                    "key_passes","attempts","attempts_inside_box","attempts_outside_box",
                    "big_chances","offsides","fouls_suffered","fouls_committed",
                    "tracked_shots","tracked_shots_with_xg","tracked_xg_sum"
                ):
                    for window in ("prior3_matches","prior5_matches","season_to_date"):
                        suffix="_sum" if window=="season_to_date" else "_avg"
                        key=f"cta_{window}_{feature}{suffix}"
                        feature_values[key]=finite_number(cta_row.get(key))
                fixture_features.append({
                    "fixture_id":str(cta_row.get("fixture_id") or ""),
                    "prior_matches_count":int(finite_number(cta_row.get("cta_prior_matches_count")) or 0),
                    "prior3_matches_count":int(finite_number(cta_row.get("cta_prior3_matches_count")) or 0),
                    "prior5_matches_count":int(finite_number(cta_row.get("cta_prior5_matches_count")) or 0),
                    "snapshot_available_as_of_deadline":str(cta_row.get("cta_snapshot_available_as_of_deadline") or "").lower() in {"true","1"},
                    "identity_verified":str(cta_row.get("identity_verified") or "").lower() in {"true","1"},
                    "features":feature_values,
                })
            record["cta"]={
                "source":"11footy player-match feature sidecar",
                "identity_verified":player_identity_verified,
                "identity_status":identity_status,
                "coverage_status":coverage_status,
                "source_snapshot_as_of":cta_report.get("source_snapshot_as_of"),
                "target_gameweek":int(target_gw),
                "fixtures":fixture_features,
                "composite":None,
                "decision_use_status":"RESEARCH_ONLY_NOT_IN_BASELINE",
                "prediction_training_eligible":False,
                "production_eligible":False,
                "attribution":cta_report.get("attribution","11footy; CC BY-NC 4.0; non-commercial use only."),
            }
        forecasts.append(record)

    if not forecasts:
        raise ValueError("No usable player forecasts were built")
    total=len(players)
    hours_before_deadline=(deadline-fetched).total_seconds()/3600
    freshness_status="FRESH_WITHIN_24H" if hours_before_deadline<=24 else "STALE_OVER_24H"
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
            "hours_before_deadline":round(hours_before_deadline,3),
            "freshness_status":freshness_status,
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
            "cta_sidecar_integrated":cta_report is not None,
            "cta_source":"11footy" if cta_report is not None else "unavailable",
            "cta_source_snapshot_as_of":cta_report.get("source_snapshot_as_of") if cta_report else None,
            "cta_target_player_fixture_rows":len(cta_rows) if cta_rows is not None else 0,
            "cta_players_with_verified_identity":len(cta_verified_players),
            "cta_players_with_prior_history":len(cta_prior_players),
            "cta_identity_status_counts":dict(sorted(cta_status_counts.items())),
            "cta_features_used_in_expected_points":False,
            "cta_composite":None,
            "cta_decision_use_status":cta_report.get("decision_use_status") if cta_report else "unavailable",
        },
        "limitations":[
            "expected_points is the official FPL ep_next baseline, not a CTA-trained prediction.",
            "expected_minutes is a proxy: latest completed-gameweek minutes per fixture scaled by the target gameweek fixture count; it is not a trained minutes forecast.",
            "Players without gameweek history receive a zero-minute fallback; players with no target-gameweek fixture also receive zero expected minutes.",
            "Historical lagged training rows remain point-in-time-unverified because older source vintages are not durably archived.",
            "The current EO field, when present, is a weighted top-10k sample and not whole-game effective ownership.",
            "Player variance and CoVar are not supplied to this baseline snapshot.",
            "This snapshot covers one upcoming gameweek only.",
            "Snapshots older than 24 hours before the deadline are explicitly marked stale and should not be treated as current recommendations."
        ] + ([
            "11footy CTA features are attached as a research-only sidecar and do not change official ep_next expected points or ranking scores.",
            "Players without a verified 11footy identity or prior history retain explicit missing-coverage statuses; missing CTA metrics are not treated as zero.",
            "11footy source data is CC BY-NC 4.0 and restricted to non-commercial use."
        ] if cta_report is not None else []),
    }
    model_version=(
        "cta-fpl-official-epnext-fixture-scaled-minutes-proxy-v0.1.2-cta-sidecar"
        if cta_report is not None
        else "cta-fpl-official-epnext-fixture-scaled-minutes-proxy-v0.1.1"
    )
    identity_payload={
        "model_version":model_version,
        "forecast_horizon_gameweeks":1,
        "player_forecasts":forecasts,
        "forecast_quality":quality,
    }
    snapshot_id=hashlib.sha256(json.dumps(identity_payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return {
        "forecast_snapshot_id":snapshot_id,
        "model_version":model_version,
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
        "cta_sidecar_integrated":cta_report is not None,
        "cta_players_with_verified_identity":len(cta_verified_players),
        "cta_players_with_prior_history":len(cta_prior_players),
        "cta_target_player_fixture_rows":len(cta_rows) if cta_rows is not None else 0,
        "cta_composite":None,
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
    parser.add_argument("--cta-csv",type=Path)
    parser.add_argument("--cta-report",type=Path)
    parser.add_argument("--out-dir",type=Path,required=True)
    args=parser.parse_args()
    if bool(args.eo_csv)!=bool(args.eo_report):
        parser.error("--eo-csv and --eo-report must be supplied together")
    if bool(args.cta_csv)!=bool(args.cta_report):
        parser.error("--cta-csv and --cta-report must be supplied together")
    source_metadata=json.loads(args.source_metadata.read_text(encoding="utf-8"))
    eo_rows=read_csv(args.eo_csv) if args.eo_csv else None
    eo_report=json.loads(args.eo_report.read_text(encoding="utf-8")) if args.eo_report else None
    cta_rows=read_csv(args.cta_csv) if args.cta_csv else None
    cta_report=json.loads(args.cta_report.read_text(encoding="utf-8")) if args.cta_report else None
    snapshot,report=build_snapshot(
        read_csv(args.players),read_csv(args.gameweek_rows),read_csv(args.fixtures),
        source_metadata,eo_rows,eo_report,cta_rows,cta_report
    )
    args.out_dir.mkdir(parents=True,exist_ok=True)
    (args.out_dir/"fpl_baseline_forecast_snapshot.json").write_text(json.dumps(snapshot,indent=2),encoding="utf-8")
    (args.out_dir/"fpl_baseline_forecast_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
