#!/usr/bin/env python3
"""Acquire anonymized official FPL replay cases for multiple completed Gameweeks.

The manager entry ID is supplied through an environment variable and is never
written to output or printed. Only normalized, anonymized replay cases are
saved. Intended for the branch-scoped GitHub Actions research workflow.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from m4_covar_fpl_api_replay_adapter import (
    CovarFplApiReplayAdapterError,
    normalize_official_fpl_replay,
)
from m4_covar_fpl_api_replay_fetch import (
    BASE_URL,
    OfficialFplFetchError,
    fetch_official_json,
    require_completed_event,
    write_private_replay,
)


def acquire_replay_batch(
    entry_id: int,
    event_ids: list[int],
    *,
    fetch: Callable[[str], dict[str, Any]] = fetch_official_json,
    sleep=lambda _seconds: None,
    min_successful: int = 1,
) -> dict[str, Any]:
    """Fetch and normalize multiple completed events, recording safe failures."""
    if isinstance(entry_id, bool) or int(entry_id) < 1:
        raise ValueError("entry_id must be a positive integer")
    if not event_ids or any(
        isinstance(event, bool) or not isinstance(event, int) or event < 1
        for event in event_ids
    ):
        raise ValueError("event_ids must be a non-empty list of positive integers")
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("event_ids must not contain duplicates")
    if isinstance(min_successful, bool) or min_successful < 1:
        raise ValueError("min_successful must be a positive integer")

    bootstrap = fetch(f"{BASE_URL}/bootstrap-static/")
    replays: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    skipped_unfinished: list[int] = []
    official_events = bootstrap.get("events")
    if not isinstance(official_events, list):
        raise OfficialFplFetchError("bootstrap payload does not contain official event status")
    event_status: dict[int, list[dict[str, Any]]] = {}
    for row in official_events:
        if isinstance(row, dict) and isinstance(row.get("id"), int) and not isinstance(row.get("id"), bool):
            event_status.setdefault(row["id"], []).append(row)

    for event in event_ids:
        try:
            matching = event_status.get(event, [])
            if len(matching) != 1:
                raise OfficialFplFetchError("requested Gameweek is missing or duplicated in bootstrap event status")
            if matching[0].get("finished") is not True:
                skipped_unfinished.append(event)
                continue
            require_completed_event(bootstrap, event)
            picks = fetch(f"{BASE_URL}/entry/{int(entry_id)}/event/{event}/picks/")
            sleep(0.25)
            live = fetch(f"{BASE_URL}/event/{event}/live/")
            sleep(0.25)
            replays.append(
                normalize_official_fpl_replay(
                    picks, live, bootstrap, event_id=event
                )
            )
        except (OfficialFplFetchError, CovarFplApiReplayAdapterError, ValueError) as exc:
            failures.append({
                "event_id": event,
                "status": "CAPTURE_FAILED",
                "error_type": type(exc).__name__,
                "reason": str(exc)[:240],
            })

    if len(replays) < min_successful:
        raise OfficialFplFetchError(
            f"only {len(replays)} completed Gameweeks captured; minimum required is {min_successful}"
        )

    return {
        "schema_version": "1.1.0",
        "capture_report": {
            "status": "PASS" if not failures else "PARTIAL",
            "requested_event_ids": event_ids,
            "captured_event_ids": [row["event_id"] for row in replays],
            "skipped_unfinished_event_ids": skipped_unfinished,
            "failed_event_ids": [row["event_id"] for row in failures],
            "captured_count": len(replays),
            "skipped_count": len(skipped_unfinished),
            "failed_count": len(failures),
            "manager_identity_in_output": False,
            "manager_entry_id_in_output": False,
            "raw_manager_payloads_in_output": False,
            "production_eligible": False,
            "decision_weight": 0.0,
            "failures": failures,
        },
        "replays": replays,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", required=True, help="Comma-separated completed Gameweek IDs")
    parser.add_argument("--output", type=Path, required=True, help="Private absolute output path outside repository")
    parser.add_argument("--min-successful", type=int, default=5)
    args = parser.parse_args()

    raw_entry = os.environ.get("FPL_MANAGER_ENTRY_ID", "")
    if not re.fullmatch(r"[1-9][0-9]*", raw_entry):
        raise ValueError("FPL_MANAGER_ENTRY_ID must be supplied as a positive integer environment variable")
    try:
        events = [int(value) for value in args.events.split(",")]
    except ValueError as exc:
        raise ValueError("--events must be comma-separated positive integers") from exc

    document = acquire_replay_batch(
        int(raw_entry), events, min_successful=args.min_successful,
        fetch=fetch_official_json,
        sleep=__import__("time").sleep,
    )
    target = write_private_replay(document, args.output)
    print(json.dumps({
        "status": document["capture_report"]["status"],
        "captured_count": document["capture_report"]["captured_count"],
        "failed_count": document["capture_report"]["failed_count"],
        "skipped_count": document["capture_report"]["skipped_count"],
        "captured_event_ids": document["capture_report"]["captured_event_ids"],
        "skipped_unfinished_event_ids": document["capture_report"]["skipped_unfinished_event_ids"],
        "manager_identity_in_output": False,
        "manager_entry_id_in_output": False,
        "raw_manager_payloads_in_output": False,
        "output": str(target),
        "production_eligible": False,
        "decision_weight": 0.0,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
