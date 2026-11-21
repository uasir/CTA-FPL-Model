#!/usr/bin/env python3
"""Fetch one official completed-GW FPL replay into a private local JSON file.

This is deliberately a local CLI, not a workflow. The manager entry ID is
prompted interactively, never written to output, and never printed. The
resulting anonymized replay file must remain outside the repository.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import stat
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from m4_covar_fpl_api_replay_adapter import normalize_official_fpl_replay


BASE_URL = "https://fantasy.premierleague.com/api"


class OfficialFplFetchError(RuntimeError):
    """Raised when an official API request fails or returns invalid JSON."""


def fetch_official_json(url: str, *, timeout: float = 20.0) -> dict[str, Any]:
    if not url.startswith(BASE_URL + "/"):
        raise OfficialFplFetchError("only official Fantasy Premier League API endpoints are allowed")
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "CTA-FPL-Model-private-replay-validation/1.0",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OfficialFplFetchError(f"official FPL API request failed: {type(exc).__name__}") from exc
    if not isinstance(payload, dict):
        raise OfficialFplFetchError("official FPL API response must be a JSON object")
    return payload


def acquire_replay(
    entry_id: int,
    event_id: int,
    *,
    fetch=fetch_official_json,
    sleep=time.sleep,
) -> dict[str, Any]:
    if isinstance(entry_id, bool) or int(entry_id) < 1:
        raise ValueError("entry_id must be a positive integer")
    if isinstance(event_id, bool) or int(event_id) < 1:
        raise ValueError("event_id must be a positive integer")
    entry = int(entry_id)
    event = int(event_id)
    # The picks endpoint is manager-specific. Do not log its URL or payload.
    picks = fetch(f"{BASE_URL}/entry/{entry}/event/{event}/picks/")
    sleep(0.25)
    live = fetch(f"{BASE_URL}/event/{event}/live/")
    sleep(0.25)
    bootstrap = fetch(f"{BASE_URL}/bootstrap-static/")
    case = normalize_official_fpl_replay(
        picks, live, bootstrap, event_id=event
    )
    return {"schema_version": "1.0.0", "replays": [case]}


def write_private_replay(document: dict[str, Any], output: Path) -> Path:
    if not output.is_absolute():
        raise ValueError("--output must be an absolute path")
    target = output.resolve()
    repository_root = Path(__file__).resolve().parents[3]
    if target.is_relative_to(repository_root):
        raise ValueError("--output must be outside the repository working tree")
    if target.exists():
        raise FileExistsError("refusing to overwrite an existing replay file")
    target.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(target, flags, stat.S_IRUSR | stat.S_IWUSR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except Exception:
        try:
            target.unlink()
        except OSError:
            pass
        raise
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", type=int, required=True, help="Completed FPL Gameweek number")
    parser.add_argument("--output", type=Path, required=True, help="Absolute private output path outside the repository")
    args = parser.parse_args()
    raw_entry = getpass.getpass("FPL manager entry ID (input hidden; not retained): ").strip()
    if not re.fullmatch(r"[1-9][0-9]*", raw_entry):
        raise ValueError("manager entry ID must be a positive integer")
    document = acquire_replay(int(raw_entry), args.event)
    target = write_private_replay(document, args.output)
    print(json.dumps({
        "status": "PRIVATE_REPLAY_SAVED",
        "event": args.event,
        "output": str(target),
        "manager_identity_in_output": False,
        "production_eligible": False,
        "decision_weight": 0.0,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
