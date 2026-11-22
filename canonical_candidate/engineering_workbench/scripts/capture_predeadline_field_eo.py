#!/usr/bin/env python3
"""Capture a rank-stratified snapshot of current FPL picks before deadline.

Unlike the post-lock workflow, this is a decision-time observation of managers'
current picks. It is intentionally labelled provisional: managers can still
change picks before lock, and the sample is not a whole-game census.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from capture_fpl_ranked_manager_picks import (
    BASE, choose_pages, fetch_json, normalize_picks, official_player_ids,
    parse_deadline, select_managers,
)
from estimate_fpl_effective_ownership import estimate_effective_ownership
from m4_covar_field_portfolio_adapter import (
    strip_manager_identifiers_from_manager_picks,
    canonical_artifact_sha256,
)
from m4_covar_field_portfolio_summary import summarize_field_portfolio_sample


def capture_predeadline(
    bootstrap: dict[str, Any],
    *,
    fetch: Callable[..., Any] = fetch_json,
    rank_limit: int = 10000,
    sample_size: int = 400,
    seed: int = 20261117,
    delay: float = 0.15,
    workers: int = 4,
    deadline_window_minutes: int = 35,
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    now = now_fn()
    upcoming = [(parse_deadline(event), event) for event in bootstrap.get("events", [])
                if event.get("deadline_time") and parse_deadline(event) > now]
    if not upcoming:
        return [], {"status": "SKIPPED_NO_FUTURE_DEADLINE"}
    deadline, event = min(upcoming, key=lambda item: item[0])
    minutes = (deadline - now).total_seconds() / 60
    if not 0 < minutes <= deadline_window_minutes:
        return [], {"status": "SKIPPED_OUTSIDE_DEADLINE_WINDOW",
                    "gameweek": event["id"], "deadline_time_utc": deadline.isoformat(),
                    "minutes_until_deadline": round(minutes, 2)}
    if sample_size < 1 or rank_limit < sample_size or rank_limit % 50 or sample_size % (rank_limit // 50):
        raise ValueError("sample_size must allocate equal positive samples to every 50-rank page")

    started_at = now_fn()
    if started_at >= deadline:
        raise RuntimeError("pre-deadline capture started after deadline")
    pages = choose_pages(rank_limit, sample_size, seed)
    page_payloads = {}

    def get_page(page: int):
        return page, fetch(f"{BASE}/leagues-classic/314/standings/?page_standings={page}", delay=delay)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(get_page, page) for page in pages]
        for future in as_completed(futures):
            page, payload = future.result()
            page_payloads[page] = payload
    managers = select_managers(page_payloads, sample_size, rank_limit, seed)
    cohort_at = now_fn()
    if cohort_at >= deadline:
        raise RuntimeError("rank cohort capture crossed deadline; discard snapshot")

    pick_payloads = {}

    def get_picks(manager: dict[str, Any]):
        url = f"{BASE}/entry/{manager['entry_id']}/event/{event['id']}/picks/"
        return manager["entry_id"], fetch(url, delay=delay)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(get_picks, manager) for manager in managers]
        for future in as_completed(futures):
            entry_id, payload = future.result()
            pick_payloads[entry_id] = payload
    picks_at = now_fn()
    if picks_at >= deadline:
        raise RuntimeError("manager-picks capture crossed deadline; discard entire snapshot")
    if len(pick_payloads) != sample_size:
        raise RuntimeError("incomplete manager-picks sample; discard entire snapshot")

    rows = normalize_picks(managers, pick_payloads, event["id"])
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
        "rank_cohort_captured_at_utc": cohort_at.isoformat(),
        "picks_captured_at_utc": picks_at.isoformat(),
        "capture_started_at_utc": started_at.isoformat(),
        "cohort": "overall global league rank observed before target gameweek deadline",
        "rank_limit": rank_limit,
        "rank_min": min(x["rank_before_deadline"] for x in managers),
        "rank_max": max(x["rank_before_deadline"] for x in managers),
        "sample_size_requested": sample_size,
        "sample_size_captured": len(managers),
        "sample_weight_per_manager": float(rank_limit) / sample_size,
        "manager_sample_sha256": hashlib.sha256(
            ",".join(str(x["entry_id"]) for x in sorted(managers, key=lambda x: x["entry_id"])).encode()
        ).hexdigest(),
        "standings_pages_fetched": len(pages),
        "rank_strata_count": len(pages),
        "sampled_managers_per_rank_page": sample_size // len(pages),
        "manager_pick_rows": len(rows),
        "status_caveat": (
            "This is a time-stamped snapshot of sampled managers' current picks before deadline. "
            "Picks may change before lock. It is not final locked EO and not a whole-game census."
        ),
        **eo_report,
    }
    metadata["estimator_status"] = metadata.get("status")
    metadata["status"] = "CAPTURED_PRE_DEADLINE_CURRENT_PICKS"
    # Build an manager-ID-stripped manager-level artifact while raw entry IDs are still
    # in memory. Only sequential sample IDs and rank strata leave this function.
    metadata["manager_id_stripped_portfolios"] = strip_manager_identifiers_from_manager_picks(
        rows,
        gameweek=int(event["id"]),
        deadline_utc=deadline.isoformat(),
        captured_at_utc=picks_at.isoformat(),
        evidence_role="PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE",
        cohort=metadata["cohort"],
        rank_limit=rank_limit,
        player_positions_by_id={
            str(element["id"]): {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}.get(int(element["element_type"]), "")
            for element in bootstrap.get("elements", [])
            if "id" in element and "element_type" in element
        },
    )
    return eo_rows, metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--rank-limit", type=int, default=10000)
    parser.add_argument("--sample-size", type=int, default=400)
    parser.add_argument("--seed", type=int, default=20261117)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--delay", type=float, default=0.15)
    parser.add_argument("--deadline-window-minutes", type=int, default=35)
    parser.add_argument(
        "--manager-portfolio-output",
        type=Path,
        help="Optional PRIVATE local path for manager-ID-stripped portfolios; never upload this file from a public workflow",
    )
    args = parser.parse_args()
    bootstrap = fetch_json(f"{BASE}/bootstrap-static/", delay=args.delay)
    rows, metadata = capture_predeadline(
        bootstrap, rank_limit=args.rank_limit, sample_size=args.sample_size,
        seed=args.seed, delay=args.delay, workers=args.workers,
        deadline_window_minutes=args.deadline_window_minutes,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if rows:
        manager_portfolio_artifact = metadata.pop("manager_id_stripped_portfolios")
        metadata["portfolio_structure_summary"] = summarize_field_portfolio_sample(
            manager_portfolio_artifact
        )
        if args.manager_portfolio_output is not None:
            manager_portfolio_path = args.manager_portfolio_output
            if not manager_portfolio_path.is_absolute():
                raise ValueError("--manager-portfolio-output must be an absolute private local path")
            repo_root = Path(__file__).resolve().parents[3]
            if manager_portfolio_path.resolve().is_relative_to(repo_root):
                raise ValueError("manager portfolio output must be outside the repository working tree")
            if manager_portfolio_path.resolve().is_relative_to(args.out_dir.resolve()):
                raise ValueError("manager portfolio output must be outside the aggregate EO artifact directory")
            manager_portfolio_path.parent.mkdir(parents=True, exist_ok=True)
            manager_portfolio_path.write_text(
                json.dumps(manager_portfolio_artifact, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            metadata["manager_portfolio_artifact"] = {
                "filename": manager_portfolio_path.name,
                "sha256": canonical_artifact_sha256(manager_portfolio_artifact),
                "manager_count": manager_portfolio_artifact["metadata"]["manager_count"],
                "manager_entry_ids_retained": False,
                "storage_policy": "EXPLICIT_LOCAL_PRIVATE_EXPORT",
            }
        else:
            metadata["manager_portfolio_export_status"] = "NOT_EXPORTED_LOCAL_ONLY"
        fields = list(rows[0].keys())
        with (args.out_dir / "fpl_predeadline_effective_ownership.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        metadata["csv_sha256"] = hashlib.sha256(
            (args.out_dir / "fpl_predeadline_effective_ownership.csv").read_bytes()
        ).hexdigest()
    (args.out_dir / "fpl_predeadline_field_report.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
