#!/usr/bin/env python3
"""Capture a stratified pre-deadline sample of public FPL manager picks.

The cohort is defined from global-league ranks observed before the target
deadline. This avoids using post-gameweek rank to define the sample.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,random,time,urllib.error,urllib.parse,urllib.request
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from estimate_fpl_effective_ownership import estimate_effective_ownership

BASE="https://fantasy.premierleague.com/api"
PAGE_SIZE=50


def fetch_json(url,delay=0.15,retries=5,timeout=30):
    headers={"User-Agent":"CTA-FPL-Model/1.0 (research data ingestion)","Accept":"application/json"}
    for attempt in range(retries):
        if delay: time.sleep(delay)
        request=urllib.request.Request(url,headers=headers)
        try:
            with urllib.request.urlopen(request,timeout=timeout) as response:
                if response.status!=200:
                    raise RuntimeError(f"Unexpected HTTP status {response.status} for {url}")
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code not in {429,500,502,503,504} or attempt==retries-1:
                raise
            retry_after=exc.headers.get("Retry-After")
            wait=float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
            time.sleep(min(wait,60))
        except (urllib.error.URLError,TimeoutError):
            if attempt==retries-1: raise
            time.sleep(min(2**attempt,30))


def choose_pages(rank_limit,sample_size,seed):
    pages=math.ceil(rank_limit/PAGE_SIZE)
    strata=math.ceil(rank_limit/sample_size)
    rng=random.Random(seed)
    chosen=[]
    for i in range(sample_size):
        first_rank=i*strata
        last_rank=min(rank_limit,(i+1)*strata)
        first_page=first_rank//PAGE_SIZE+1
        last_page=math.ceil(last_rank/PAGE_SIZE)
        if first_page>pages: break
        chosen.append(rng.randint(first_page,min(last_page,pages)))
    return chosen


def select_managers(page_payloads,sample_size,rank_limit,seed):
    rng=random.Random(seed)
    managers=[]
    for page,payload in sorted(page_payloads.items()):
        results=payload.get("standings",{}).get("results",[])
        if not results: continue
        eligible=[x for x in results if int(x.get("rank") or 0)>0 and int(x["rank"])<=rank_limit]
        if not eligible: continue
        selected=rng.choice(eligible)
        managers.append({
            "entry_id":int(selected["entry"]),
            "rank_before_deadline":int(selected["rank"]),
            "sample_weight":float(rank_limit)/sample_size,
            "page_standings":page,
        })
    ids=[x["entry_id"] for x in managers]
    if len(ids)!=len(set(ids)):
        raise ValueError("Duplicate manager IDs in rank sample")
    if len(managers)!=sample_size:
        raise ValueError(f"Expected {sample_size} sampled managers; found {len(managers)}")
    return managers


def normalize_picks(managers,pick_payloads,gameweek):
    rows=[]
    for manager in managers:
        entry=manager["entry_id"]
        payload=pick_payloads[entry]
        entry_history=payload.get("entry_history") or {}
        returned_event=entry_history.get("event")
        if returned_event is not None and int(returned_event)!=int(gameweek):
            raise ValueError(f"Manager {entry} picks response is for GW{returned_event}, expected GW{gameweek}")
        picks=payload.get("picks") or []
        if len(picks)!=15:
            raise ValueError(f"Manager {entry} GW{gameweek} returned {len(picks)} picks, expected 15")
        for pick in picks:
            rows.append({
                "gameweek":int(gameweek),
                "entry_id":entry,
                "rank_before_deadline":manager["rank_before_deadline"],
                "sample_weight":manager["sample_weight"],
                "fpl_element_id":int(pick["element"]),
                "position":int(pick["position"]),
                "is_captain":bool(pick.get("is_captain")),
                "is_vice_captain":bool(pick.get("is_vice_captain")),
                "active_chip":payload.get("active_chip") or "",
            })
    return rows


def capture(bootstrap,fetch=fetch_json,rank_limit=10000,sample_size=100,seed=20261117,
            delay=0.15,workers=2,deadline_window_minutes=70,force=False):
    now=datetime.now(timezone.utc)
    upcoming=[]
    for event in bootstrap.get("events",[]):
        if not event.get("deadline_time"): continue
        deadline=datetime.fromisoformat(str(event["deadline_time"]).replace("Z","+00:00"))
        if deadline>now: upcoming.append((deadline,event))
    if not upcoming:
        return [],{"status":"SKIPPED_NO_FUTURE_DEADLINE"}
    deadline,event=min(upcoming,key=lambda x:x[0])
    minutes=(deadline-now).total_seconds()/60
    if not force and not (0<minutes<=deadline_window_minutes):
        return [],{"status":"SKIPPED_OUTSIDE_DEADLINE_WINDOW","gameweek":event["id"],
                   "deadline_time_utc":deadline.isoformat(),"minutes_until_deadline":round(minutes,2)}
    if sample_size<1 or rank_limit<sample_size or sample_size>math.ceil(rank_limit/PAGE_SIZE):
        raise ValueError("sample_size must be positive and no larger than the number of rank pages")
    pages=choose_pages(rank_limit,sample_size,seed)
    page_payloads={}
    def get_page(page):
        url=f"{BASE}/leagues-classic/314/standings/?page_standings={page}"
        return page,fetch(url,delay=delay)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(get_page,p) for p in pages]
        for future in as_completed(futures):
            page,payload=future.result();page_payloads[page]=payload
    managers=select_managers(page_payloads,sample_size,rank_limit,seed)
    pick_payloads={}
    def get_picks(manager):
        url=f"{BASE}/entry/{manager['entry_id']}/event/{event['id']}/picks/"
        return manager["entry_id"],fetch(url,delay=delay)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(get_picks,m) for m in managers]
        for future in as_completed(futures):
            entry,payload=future.result();pick_payloads[entry]=payload
    rows=normalize_picks(managers,pick_payloads,event["id"])
    metadata={
        "status":"CAPTURED_PRE_DEADLINE_MANAGER_SAMPLE",
        "gameweek":int(event["id"]),
        "deadline_time_utc":deadline.isoformat(),
        "captured_at_utc":now.isoformat(),
        "minutes_until_deadline":round(minutes,2),
        "cohort":"overall global league rank before target gameweek deadline",
        "rank_limit":rank_limit,
        "sample_size_requested":sample_size,
        "sample_size_captured":len(managers),
        "sample_weight_per_manager":float(rank_limit)/sample_size,
        "rank_min":min(x["rank_before_deadline"] for x in managers),
        "rank_max":max(x["rank_before_deadline"] for x in managers),
        "manager_sample_sha256":hashlib.sha256(",".join(str(x["entry_id"]) for x in sorted(managers,key=lambda x:x["entry_id"])).encode()).hexdigest(),
        "standings_pages_fetched":len(pages),
        "manager_pick_rows":len(rows),
        "status_caveat":"This is a stratified sample, not a census; manager picks may still change until the deadline if the capture is not at the final lock."
    }
    return rows,metadata


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out-dir",type=Path,required=True)
    parser.add_argument("--rank-limit",type=int,default=10000)
    parser.add_argument("--sample-size",type=int,default=100)
    parser.add_argument("--seed",type=int,default=20261117)
    parser.add_argument("--workers",type=int,default=2)
    parser.add_argument("--delay",type=float,default=0.15)
    parser.add_argument("--deadline-window-minutes",type=int,default=70)
    parser.add_argument("--force",action="store_true")
    args=parser.parse_args()
    bootstrap=fetch_json(f"{BASE}/bootstrap-static/",delay=args.delay)
    rows,metadata=capture(bootstrap,rank_limit=args.rank_limit,sample_size=args.sample_size,
        seed=args.seed,delay=args.delay,workers=args.workers,
        deadline_window_minutes=args.deadline_window_minutes,force=args.force)
    args.out_dir.mkdir(parents=True,exist_ok=True)
    if rows:
        eo_rows,eo_report=estimate_effective_ownership(rows)
        metadata.update(eo_report)
        fields=list(eo_rows[0].keys())
        with (args.out_dir/"fpl_effective_ownership_sample.csv").open("w",newline="",encoding="utf-8") as handle:
            writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows(eo_rows)
    (args.out_dir/"fpl_ranked_manager_sample_report.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    print(json.dumps(metadata,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
