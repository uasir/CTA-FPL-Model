#!/usr/bin/env python3
"""Capture a provisional rank-stratified field EO estimate before FPL deadline.

Unlike capture_fpl_ranked_manager_picks.py, this deliberately fetches the
sampled managers' current picks before deadline. It is provisional, not locked
EO; no post-deadline picks or outcomes are used.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from capture_fpl_ranked_manager_picks import (
    fetch_json, choose_pages, select_managers, normalize_picks,
    official_player_ids, parse_deadline, BASE,
)
from estimate_fpl_effective_ownership import estimate_effective_ownership


def capture_predeadline(bootstrap, *, rank_limit=10000, sample_size=400,
                        seed=20261117, delay=0.15, workers=2,
                        deadline_window_minutes=35, now_fn=lambda: datetime.now(timezone.utc)):
    import concurrent.futures

    now = now_fn()
    upcoming = []
    for event in bootstrap.get("events", []):
        if event.get("deadline_time"):
            deadline = parse_deadline(event)
            if deadline > now:
                upcoming.append((deadline, event))
    if not upcoming:
        return None, {"status": "SKIPPED_NO_FUTURE_DEADLINE"}
    deadline, event = min(upcoming, key=lambda item: item[0])
    minutes = (deadline - now).total_seconds() / 60
    if not 0 < minutes <= deadline_window_minutes:
        return None, {
            "status": "SKIPPED_OUTSIDE_PREDEADLINE_WINDOW",
            "gameweek": int(event["id"]), "deadline_time_utc": deadline.isoformat(),
            "minutes_until_deadline": round(minutes, 2),
        }
    if rank_limit < 1 or rank_limit % 50 or sample_size < 1 or sample_size > rank_limit:
        raise ValueError("rank_limit must be a positive multiple of 50 and sample_size must be positive")
    pages = choose_pages(rank_limit, sample_size, seed)
    started = now_fn()
    if started >= deadline:
        raise RuntimeError("Capture started at or after deadline")
    page_payloads = {}
    def get_page(page):
        url = f"{BASE}/leagues-classic/314/standings/?page_standings={page}"
        return page, fetch_json(url, delay=delay)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for future in concurrent.futures.as_completed([pool.submit(get_page, p) for p in pages]):
            page, result = future.result()
            page_payloads[page] = result
    managers = select_managers(page_payloads, sample_size, rank_limit, seed)
    cohort_at = now_fn()
    if cohort_at >= deadline:
        raise RuntimeError("Rank cohort capture crossed deadline; refusing mixed-time cohort")
    pick_payloads = {}
    def get_picks(manager):
        url = f"{BASE}/entry/{manager['entry_id']}/event/{event['id']}/picks/"
        return manager["entry_id"], fetch_json(url, delay=delay)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for future in concurrent.futures.as_completed([pool.submit(get_picks, m) for m in managers]):
            entry, result = future.result()
            pick_payloads[entry] = result
    picks_at = now_fn()
    if picks_at >= deadline:
        raise RuntimeError("Picks capture crossed deadline; refusing to label it pre-deadline")
    rows = normalize_picks(managers, pick_payloads, int(event["id"]))
    eo_rows, eo_report = estimate_effective_ownership(
        rows, player_ids=official_player_ids(bootstrap)
    )
    metadata = {
        "status": "CAPTURED_PRE_DEADLINE_CURRENT_PICKS",
        "evidence_role": "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE",
        "picks_lock_verified": False,
        "provisional_picks": True,
        "gameweek": int(event["id"]),
        "deadline_time_utc": deadline.isoformat(),
        "capture_started_at_utc": started.isoformat(),
        "rank_cohort_captured_at_utc": cohort_at.isoformat(),
        "picks_captured_at_utc": picks_at.isoformat(),
        "cohort": "overall global league rank observed before target gameweek deadline",
        "rank_limit": rank_limit,
        "rank_min": min(m["rank_before_deadline"] for m in managers),
        "rank_max": max(m["rank_before_deadline"] for m in managers),
        "rank_strata_count": len(pages),
        "sample_size_captured": len(managers),
        "sample_managers": len(managers),
        "sample_weight": eo_report["sample_weight"],
        "effective_sample_size": eo_report["effective_sample_size"],
        "sample_size_requested": sample_size,
        "manager_pick_rows": len(rows),
        "limitations": [
            "Current picks are provisional and may change before deadline.",
            "This is a rank-stratified sample estimate, not a whole-game census.",
            "No post-deadline picks, final ranks or gameweek outcomes are used.",
        ],
    }
    return eo_rows, metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--rank-limit", type=int, default=10000)
    parser.add_argument("--sample-size", type=int, default=400)
    parser.add_argument("--seed", type=int, default=20261117)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--delay", type=float, default=0.15)
    parser.add_argument("--deadline-window-minutes", type=int, default=35)
    args = parser.parse_args()
    bootstrap = fetch_json(f"{BASE}/bootstrap-static/", delay=args.delay)
    rows, report = capture_predeadline(
        bootstrap, rank_limit=args.rank_limit, sample_size=args.sample_size,
        seed=args.seed, delay=args.delay, workers=args.workers,
        deadline_window_minutes=args.deadline_window_minutes,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if rows is not None:
        csv_path = args.out_dir / "predeadline_field_eo.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        report["csv_sha256"] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
        report["csv_row_count"] = len(rows)
    (args.out_dir / "predeadline_field_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
