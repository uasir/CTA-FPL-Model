#!/usr/bin/env python3
"""Capture and reconcile a completed public FPL manager Gameweek."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from evaluate_external_benchmark_decisions import _score_plan
from reconcile_official_fpl_manager_result import reconcile_official_manager_result


class CaptureReconciliationError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch(url: str) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": "CTA-FPL-Model/1.0 (official result reconciliation)"})
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise CaptureReconciliationError(f"GET {url} returned HTTP {response.status}")
        raw = response.read()
    return raw, utc_now()


def parse_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CaptureReconciliationError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise CaptureReconciliationError(f"{label} must be a JSON object")
    return payload


def capture_and_reconcile(manager_team_id: int, gameweek: int) -> dict[str, Any]:
    if manager_team_id < 1 or gameweek < 1:
        raise CaptureReconciliationError("manager_team_id and gameweek must be positive integers")

    base_url = "https://fantasy.premierleague.com/api"
    sources = []
    payloads = {}
    for source_type, url in (
        ("bootstrap_static", f"{base_url}/bootstrap-static/"),
        ("manager_picks", f"{base_url}/entry/{manager_team_id}/event/{gameweek}/picks/"),
        ("event_live", f"{base_url}/event/{gameweek}/live/"),
    ):
        raw, captured_at = fetch(url)
        payloads[source_type] = parse_object(raw, source_type)
        sources.append({
            "source_type": source_type,
            "source_url": url,
            "raw_snapshot_id": f"fpl-{source_type}-manager-{manager_team_id}-gw{gameweek}-{captured_at}",
            "captured_at_utc": captured_at,
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_payload_base64": base64.b64encode(raw).decode("ascii"),
        })

    bootstrap = payloads["bootstrap_static"]
    events = bootstrap.get("events")
    if not isinstance(events, list):
        raise CaptureReconciliationError("bootstrap is missing its events list")
    event_rows = [row for row in events if isinstance(row, dict) and row.get("id") == gameweek]
    if len(event_rows) != 1 or event_rows[0].get("finished") is not True or event_rows[0].get("data_checked") is not True:
        raise CaptureReconciliationError("target Gameweek is not marked finished and data_checked by official FPL")

    picks = payloads["manager_picks"]
    history = picks.get("entry_history")
    if not isinstance(history, dict) or history.get("event") != gameweek:
        raise CaptureReconciliationError("official manager picks do not match the requested Gameweek")
    if picks.get("active_chip") not in (None, ""):
        raise CaptureReconciliationError("chip gameweeks are outside the initial reconciliation contract")

    pick_rows = picks.get("picks")
    if not isinstance(pick_rows, list) or len(pick_rows) != 15:
        raise CaptureReconciliationError("official manager picks must contain exactly 15 players")
    ordered = sorted(pick_rows, key=lambda row: row.get("position", 0) if isinstance(row, dict) else 0)
    if [row.get("position") for row in ordered] != list(range(1, 16)):
        raise CaptureReconciliationError("official manager picks positions must be exactly 1..15")
    starting_xi = [row["element"] for row in ordered[:11]]
    reserve_gk = ordered[11]["element"]
    bench_order = [row["element"] for row in ordered[12:15]]
    captain_rows = [row["element"] for row in pick_rows if row.get("is_captain") is True]
    vice_rows = [row["element"] for row in pick_rows if row.get("is_vice_captain") is True]
    if len(captain_rows) != 1 or len(vice_rows) != 1:
        raise CaptureReconciliationError("official manager picks must contain exactly one captain and vice-captain")

    element_types = bootstrap.get("element_types")
    elements = bootstrap.get("elements")
    if not isinstance(element_types, list) or not isinstance(elements, list):
        raise CaptureReconciliationError("official bootstrap is missing element_types or elements")
    position_names = {
        row.get("id"): row.get("singular_name_short")
        for row in element_types if isinstance(row, dict)
    }
    position_map = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
    team_by_id = {}
    position_by_id = {}
    for row in elements:
        if isinstance(row, dict) and isinstance(row.get("id"), int):
            team_by_id[row["id"]] = row.get("team")
            element_type = row.get("element_type")
            short_name = position_names.get(element_type)
            position_by_id[row["id"]] = position_map.get(element_type, short_name)
    squad_ids = [row["element"] for row in ordered]
    if len(set(squad_ids)) != 15 or any(pid not in position_by_id or pid not in team_by_id for pid in squad_ids):
        raise CaptureReconciliationError("official bootstrap metadata does not cover the manager's 15 unique players")

    roster = {
        pid: {"position": position_by_id[pid], "team_id": team_by_id[pid]}
        for pid in squad_ids
    }
    live_elements = payloads["event_live"].get("elements")
    if not isinstance(live_elements, list):
        raise CaptureReconciliationError("official event-live response is missing elements")
    live_by_id = {}
    for row in live_elements:
        if isinstance(row, dict) and isinstance(row.get("id"), int) and isinstance(row.get("stats"), dict):
            live_by_id[row["id"]] = row["stats"]
    if any(pid not in live_by_id for pid in squad_ids):
        raise CaptureReconciliationError("official event-live data does not cover the manager's 15 players")

    realised = {}
    for pid in squad_ids:
        stats = live_by_id[pid]
        for field in ("total_points", "minutes", "yellow_cards", "red_cards"):
            if not isinstance(stats.get(field), int) or isinstance(stats.get(field), bool):
                raise CaptureReconciliationError(f"official event-live {field} missing or invalid for player {pid}")
        realised[pid] = {
            "total_points": stats["total_points"],
            "minutes": stats["minutes"],
            "yellow_cards": stats["yellow_cards"],
            "red_cards": stats["red_cards"],
        }

    plan = {
        "starting_xi": starting_xi,
        "bench_order": bench_order,
        "reserve_goalkeeper_id": reserve_gk,
        "captain_id": captain_rows[0],
        "vice_captain_id": vice_rows[0],
    }
    local_score = _score_plan(plan, roster, realised)
    reconciliation = reconcile_official_manager_result(
        local_score, picks, payloads["event_live"],
        manager_team_id=manager_team_id,
        target_gameweek=gameweek,
        expected_starting_xi=starting_xi,
        expected_bench_order=bench_order,
        expected_reserve_goalkeeper_id=reserve_gk,
        expected_captain_id=captain_rows[0],
        expected_vice_captain_id=vice_rows[0],
    )
    return {
        "capture_contract_version": "0.1.0",
        "manager_team_id": manager_team_id,
        "target_gameweek": gameweek,
        "event_finalized": True,
        "source_archives": sources,
        "local_score": local_score,
        "official_entry_history": history,
        "reconciliation": reconciliation,
        "historical_evidence_admitted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manager-team-id", type=int, required=True)
    parser.add_argument("--gameweek", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = capture_and_reconcile(args.manager_team_id, args.gameweek)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["reconciliation"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
