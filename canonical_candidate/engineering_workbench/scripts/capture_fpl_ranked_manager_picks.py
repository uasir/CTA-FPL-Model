#!/usr/bin/env python3
"""Capture a stratified pre-deadline manager cohort and their post-lock picks.

The rank cohort is sampled before the deadline. The script then waits until
after the deadline before requesting picks, so last-minute captain, transfer,
and chip changes are included in the EO snapshot.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,random,time,urllib.error,urllib.request
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
    # Use every 50-rank page as a stratum. The sample size must allocate an
    # equal integer number of managers to every page for equal expansion weights.
    if rank_limit < 1 or rank_limit % PAGE_SIZE:
        raise ValueError(f"rank_limit must be a positive multiple of page size {PAGE_SIZE}")
    pages=rank_limit//PAGE_SIZE
    if sample_size < pages or sample_size % pages:
        raise ValueError(f"sample_size must be a positive multiple of {pages} rank pages")
    per_page=sample_size//pages
    if per_page>PAGE_SIZE:
        raise ValueError("sample_size cannot exceed the rank population")
    return list(range(1,pages+1))


def select_managers(page_payloads,sample_size,rank_limit,seed):
    rng=random.Random(seed)
    page_count=rank_limit//PAGE_SIZE
    per_page=sample_size//page_count
    if set(page_payloads)!=set(range(1,page_count+1)):
        raise ValueError("Every rank page must be captured before manager sampling")
    managers=[]
    for page,payload in sorted(page_payloads.items()):
        results=payload.get("standings",{}).get("results",[])
        eligible=[
            x for x in results
            if int(x.get("rank") or 0)>0 and int(x.get("entry") or 0)>0
        ]
        expected_population=min(PAGE_SIZE,rank_limit-(page-1)*PAGE_SIZE)
        entry_ids=[int(x["entry"]) for x in eligible]
        if len(eligible)!=expected_population or len(set(entry_ids))!=expected_population:
            raise ValueError(
                f"Rank page {page} is incomplete: expected {expected_population} unique managers, found {len(eligible)}"
            )
        if len(eligible)<per_page:
            raise ValueError(f"Rank page {page} has {len(eligible)} eligible managers; need {per_page}")
        for selected in rng.sample(eligible,per_page):
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
        rows_for_manager=[]
        for pick in picks:
            if not all(key in pick for key in ("element","position","is_captain")):
                raise ValueError(f"Manager {entry} pick is missing required fields")
            rows_for_manager.append({
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
        rows.extend(rows_for_manager)
    return rows


def parse_deadline(event):
    return datetime.fromisoformat(str(event["deadline_time"]).replace("Z","+00:00"))


def official_player_ids(bootstrap):
    """Return the complete player universe from an official bootstrap snapshot."""
    elements=bootstrap.get("elements")
    if not isinstance(elements,list) or not elements:
        raise ValueError("official bootstrap must contain a non-empty elements list")
    player_ids=[]
    for element in elements:
        if not isinstance(element,dict) or element.get("id") is None:
            raise ValueError("official bootstrap contains an element without an id")
        player_ids.append(int(element["id"]))
    if len(player_ids)!=len(set(player_ids)):
        raise ValueError("official bootstrap contains duplicate player ids")
    return player_ids


def capture(bootstrap,fetch=fetch_json,rank_limit=10000,sample_size=400,seed=20261117,
            delay=0.15,workers=2,deadline_window_minutes=7,lock_grace_seconds=60,
            force=False,now_fn=lambda:datetime.now(timezone.utc),sleep_fn=time.sleep):
    # Retain the old keyword for callers, but never let force bypass deadline
    # timing: final EO must only use picks fetched after the lock grace period.
    now=now_fn()
    upcoming=[]
    for event in bootstrap.get("events",[]):
        if not event.get("deadline_time"): continue
        deadline=parse_deadline(event)
        if deadline>now: upcoming.append((deadline,event))
    if not upcoming:
        return [],{"status":"SKIPPED_NO_FUTURE_DEADLINE"}
    deadline,event=min(upcoming,key=lambda x:x[0])
    minutes=(deadline-now).total_seconds()/60
    if not (0<minutes<=deadline_window_minutes):
        return [],{"status":"SKIPPED_OUTSIDE_DEADLINE_WINDOW","gameweek":event["id"],
                   "deadline_time_utc":deadline.isoformat(),"minutes_until_deadline":round(minutes,2)}
    if sample_size<1 or rank_limit<sample_size or rank_limit%PAGE_SIZE or sample_size%(rank_limit//PAGE_SIZE):
        raise ValueError("sample_size must allocate an equal positive number of managers to every 50-rank page")

    # Stage 1: freeze the rank-defined cohort before the deadline.
    rank_capture_started_at=now_fn()
    if rank_capture_started_at>=deadline:
        raise RuntimeError("Rank cohort capture started after the deadline; refusing a post-lock cohort")
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
    cohort_captured_at=now_fn()
    if cohort_captured_at>=deadline:
        raise RuntimeError("Rank cohort fetch crossed the deadline; refusing to mix pre- and post-deadline standings")

    # Stage 2: wait for the deadline to pass, plus a short API-lock grace period.
    lock_time=deadline.timestamp()+lock_grace_seconds
    wait_seconds=max(0,lock_time-now_fn().timestamp())
    if wait_seconds:
        sleep_fn(wait_seconds)
    picks_captured_at=now_fn()
    if picks_captured_at.timestamp()<lock_time:
        raise RuntimeError("Clock has not passed the deadline lock grace period; refusing provisional picks")

    # Confirm against a fresh official bootstrap response that the target deadline passed.
    locked_bootstrap=fetch(f"{BASE}/bootstrap-static/",delay=delay)
    matching=[x for x in locked_bootstrap.get("events",[]) if int(x.get("id",-1))==int(event["id"])]
    if not matching or parse_deadline(matching[0]).timestamp()>picks_captured_at.timestamp()-lock_grace_seconds:
        raise RuntimeError("Official FPL event deadline is not confirmed passed; refusing to label picks as locked")

    # Stage 3: request the sampled managers' picks only after lock.
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
        "status":"CAPTURED_POST_DEADLINE_PICKS",
        "picks_lock_verified":True,
        "gameweek":int(event["id"]),
        "deadline_time_utc":deadline.isoformat(),
        "rank_cohort_captured_at_utc":cohort_captured_at.isoformat(),
        "picks_captured_at_utc":picks_captured_at.isoformat(),
        "minutes_until_deadline_at_cohort_capture":round((deadline-cohort_captured_at).total_seconds()/60,2),
        "seconds_after_deadline_at_picks_capture":round((picks_captured_at-deadline).total_seconds(),2),
        "lock_grace_seconds":lock_grace_seconds,
        "cohort":"overall global league rank observed before target gameweek deadline",
        "rank_limit":rank_limit,
        "sample_size_requested":sample_size,
        "sample_size_captured":len(managers),
        "sample_weight_per_manager":float(rank_limit)/sample_size,
        "rank_min":min(x["rank_before_deadline"] for x in managers),
        "rank_max":max(x["rank_before_deadline"] for x in managers),
        "manager_sample_sha256":hashlib.sha256(",".join(str(x["entry_id"]) for x in sorted(managers,key=lambda x:x["entry_id"])).encode()).hexdigest(),
        "standings_pages_fetched":len(pages),
        "rank_strata_count":len(pages),
        "sampled_managers_per_rank_page":sample_size//len(pages),
        "manager_pick_rows":len(rows),
        "status_caveat":"The manager cohort is stratified by pre-deadline rank; picks are fetched only after the deadline and lock grace period. This is a weighted sample, not a whole-game census."
    }
    return rows,metadata


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out-dir",type=Path,required=True)
    parser.add_argument("--rank-limit",type=int,default=10000)
    parser.add_argument("--sample-size",type=int,default=400)
    parser.add_argument("--seed",type=int,default=20261117)
    parser.add_argument("--workers",type=int,default=2)
    parser.add_argument("--delay",type=float,default=0.15)
    parser.add_argument("--deadline-window-minutes",type=int,default=7)
    parser.add_argument("--lock-grace-seconds",type=int,default=60)
    args=parser.parse_args()
    bootstrap=fetch_json(f"{BASE}/bootstrap-static/",delay=args.delay)
    rows,metadata=capture(bootstrap,rank_limit=args.rank_limit,sample_size=args.sample_size,
        seed=args.seed,delay=args.delay,workers=args.workers,
        deadline_window_minutes=args.deadline_window_minutes,
        lock_grace_seconds=args.lock_grace_seconds)
    args.out_dir.mkdir(parents=True,exist_ok=True)
    if rows:
        eo_rows,eo_report=estimate_effective_ownership(
            rows, player_ids=official_player_ids(bootstrap),
        )
        metadata.update(eo_report)
        metadata["status"]="CAPTURED_POST_DEADLINE_PICKS"
        metadata["picks_lock_verified"]=True
        fields=list(eo_rows[0].keys())
        with (args.out_dir/"fpl_effective_ownership_sample.csv").open("w",newline="",encoding="utf-8") as handle:
            writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows(eo_rows)
    (args.out_dir/"fpl_ranked_manager_sample_report.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    print(json.dumps(metadata,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
