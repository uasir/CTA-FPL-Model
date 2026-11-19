#!/usr/bin/env python3
"""Compare one manager's locked FPL squad exposure with the existing field EO sample.

This consumes the existing EO CSV; it does not estimate or rebuild field EO.
The entry ID is a runtime argument and is never written to output files.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://fantasy.premierleague.com/api"


def fetch_json(url: str, delay: float = 0.15, retries: int = 5, timeout: int = 30):
    headers = {
        "User-Agent": "CTA-FPL-Model/1.0 (personal squad versus field comparison)",
        "Accept": "application/json",
    }
    for attempt in range(retries):
        if delay:
            time.sleep(delay)
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    raise RuntimeError(f"Unexpected HTTP status {response.status}")
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == retries - 1:
                raise
            retry_after = exc.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
            time.sleep(min(wait, 60))
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
            time.sleep(min(2**attempt, 30))
    raise RuntimeError("FPL API request exhausted retries")


def validate_locked_event(bootstrap, gameweek, now=None, lock_grace_seconds=60):
    now = now or datetime.now(timezone.utc)
    events = [
        event for event in bootstrap.get("events", [])
        if int(event.get("id", -1)) == int(gameweek)
    ]
    if len(events) != 1:
        raise ValueError(f"Expected exactly one official FPL event for GW{gameweek}")
    event = events[0]
    deadline_text = event.get("deadline_time")
    if not deadline_text:
        raise ValueError(f"GW{gameweek} has no official deadline_time")
    deadline = datetime.fromisoformat(str(deadline_text).replace("Z", "+00:00"))
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if now.timestamp() < deadline.timestamp() + lock_grace_seconds:
        raise RuntimeError(
            f"GW{gameweek} picks are not eligible for locked comparison until "
            f"{deadline.isoformat()} plus {lock_grace_seconds}s"
        )
    return event


def normalize_personal_picks(payload, gameweek):
    history = payload.get("entry_history") or {}
    returned_event = history.get("event")
    if returned_event is not None and int(returned_event) != int(gameweek):
        raise ValueError(
            f"Entry picks response is for GW{returned_event}, expected GW{gameweek}"
        )
    picks = payload.get("picks") or []
    if len(picks) != 15:
        raise ValueError(f"Expected 15 locked squad picks, received {len(picks)}")
    normalized = []
    seen_ids = set()
    seen_positions = set()
    for pick in picks:
        if not all(key in pick for key in ("element", "position", "is_captain")):
            raise ValueError("A locked pick is missing element, position or is_captain")
        player_id = int(pick["element"])
        position = int(pick["position"])
        if player_id < 1 or position < 1 or position > 15:
            raise ValueError("Locked picks contain an invalid player ID or squad position")
        if player_id in seen_ids or position in seen_positions:
            raise ValueError("Locked picks contain duplicate player IDs or positions")
        seen_ids.add(player_id)
        seen_positions.add(position)
        normalized.append({
            "fpl_element_id": str(player_id),
            "position": position,
            "is_captain": bool(pick.get("is_captain")),
            "is_vice_captain": bool(pick.get("is_vice_captain")),
        })
    if seen_positions != set(range(1, 16)):
        raise ValueError("Locked picks must contain squad positions 1 through 15")
    captains = [row for row in normalized if row["is_captain"]]
    if len(captains) != 1 or captains[0]["position"] > 11:
        raise ValueError("Locked squad must have exactly one captain in the starting XI")
    if sum(row["is_vice_captain"] for row in normalized) != 1:
        raise ValueError("Locked squad must have exactly one vice-captain")
    return normalized, str(payload.get("active_chip") or "").strip().lower()


def _number(row, key, required=True):
    value = row.get(key)
    if value in (None, ""):
        if required:
            raise ValueError(f"Field EO row is missing {key}")
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"Field EO {key} must be a finite non-negative number")
    return number


def compare_squad_to_field(personal_picks, active_chip, field_rows, gameweek, player_metadata=None):
    if not field_rows:
        raise ValueError("Existing field EO input is empty")
    field_by_id = {}
    for row in field_rows:
        if str(row.get("gameweek", "")) != str(gameweek):
            raise ValueError("Field EO input must contain only the requested gameweek")
        player_id = str(row.get("fpl_element_id", "")).strip()
        if not player_id or player_id in field_by_id:
            raise ValueError("Field EO input contains a missing or duplicate FPL element ID")
        field_by_id[player_id] = row

    personal_by_id = {row["fpl_element_id"]: row for row in personal_picks}
    missing_owned = sorted(set(personal_by_id) - set(field_by_id), key=int)
    if missing_owned:
        raise ValueError(
            "Existing field EO sample is missing owned player IDs: " + ", ".join(missing_owned)
        )

    metadata = player_metadata or {}
    all_ids = sorted(set(field_by_id) | set(personal_by_id), key=lambda value: (0, int(value)) if value.isdigit() else (1, value))
    output = []
    for player_id in all_ids:
        field = field_by_id[player_id]
        personal = personal_by_id.get(player_id)
        owned = personal is not None
        position = personal["position"] if personal else None
        captain = bool(personal and personal["is_captain"])
        triple_captain = bool(captain and active_chip == "3xc")
        bench_boost_bench = bool(owned and position > 11 and active_chip == "bboost")
        starting = bool(owned and position <= 11)
        personal_owned = 100.0 if owned else 0.0
        personal_starting = 100.0 if starting else 0.0
        personal_captain = 100.0 if captain else 0.0
        personal_triple = 100.0 if triple_captain else 0.0
        personal_eo = personal_owned + personal_captain + personal_triple
        personal_scoring = (
            personal_starting + (100.0 if bench_boost_bench else 0.0)
            + personal_captain + personal_triple
        )
        field_owned = _number(field, "owned_by_pct")
        field_starting = _number(field, "starting_pct", required=False)
        field_captain = _number(field, "captain_pct", required=False)
        field_eo = _number(field, "effective_ownership_pct")
        field_scoring = _number(field, "scoring_exposure_pct", required=False)
        player = metadata.get(player_id, {})
        output.append({
            "gameweek": int(gameweek),
            "fpl_element_id": player_id,
            "web_name": player.get("web_name", ""),
            "team": player.get("team", ""),
            "position_name": player.get("position", ""),
            "in_personal_squad": owned,
            "personal_squad_position": position,
            "personal_starting_pct": personal_starting,
            "personal_captain_pct": personal_captain,
            "personal_owned_by_pct": personal_owned,
            "personal_effective_ownership_pct": personal_eo,
            "field_owned_by_pct": field_owned,
            "field_starting_pct": field_starting,
            "field_captain_pct": field_captain,
            "field_effective_ownership_pct": field_eo,
            "effective_ownership_delta_pct": round(personal_eo - field_eo, 8),
            "personal_scoring_exposure_pct": personal_scoring,
            "field_scoring_exposure_pct": field_scoring,
            "scoring_exposure_delta_pct": (
                round(personal_scoring - field_scoring, 8) if field_scoring is not None else None
            ),
            "field_sample_managers": int(field.get("sample_managers") or 0),
            "field_sample_weight": _number(field, "sample_weight", required=False),
        })
    output.sort(key=lambda row: (
        -abs(row["effective_ownership_delta_pct"]),
        -row["effective_ownership_delta_pct"],
        int(row["fpl_element_id"]),
    ))
    owned_rows = [row for row in output if row["in_personal_squad"]]
    captain_rows = [row for row in owned_rows if row["personal_captain_pct"] > 0]
    summary = {
        "status": "PASS_PERSONAL_SQUAD_VS_EXISTING_FIELD_EO",
        "gameweek": int(gameweek),
        "personal_squad_players": len(owned_rows),
        "starting_xi_players": sum(row["personal_starting_pct"] > 0 for row in owned_rows),
        "captain_player_id": captain_rows[0]["fpl_element_id"],
        "active_chip": active_chip or None,
        "field_players_compared": len(output),
        "owned_players_above_field_eo": sum(row["effective_ownership_delta_pct"] > 0 for row in owned_rows),
        "owned_players_below_field_eo": sum(row["effective_ownership_delta_pct"] < 0 for row in owned_rows),
        "owned_players_equal_field_eo": sum(row["effective_ownership_delta_pct"] == 0 for row in owned_rows),
        "largest_positive_differentials": [
            {"fpl_element_id": row["fpl_element_id"], "web_name": row["web_name"],
             "personal_eo_pct": row["personal_effective_ownership_pct"],
             "field_eo_pct": row["field_effective_ownership_pct"],
             "delta_pct": row["effective_ownership_delta_pct"]}
            for row in sorted(owned_rows, key=lambda row: -row["effective_ownership_delta_pct"])[:5]
        ],
        "largest_negative_differentials": [
            {"fpl_element_id": row["fpl_element_id"], "web_name": row["web_name"],
             "in_personal_squad": row["in_personal_squad"],
             "personal_eo_pct": row["personal_effective_ownership_pct"],
             "field_eo_pct": row["field_effective_ownership_pct"],
             "delta_pct": row["effective_ownership_delta_pct"]}
            for row in sorted(output, key=lambda row: row["effective_ownership_delta_pct"])[:5]
        ],
        "most_underowned_field_players_not_owned": [
            {"fpl_element_id": row["fpl_element_id"], "web_name": row["web_name"],
             "personal_eo_pct": row["personal_effective_ownership_pct"],
             "field_eo_pct": row["field_effective_ownership_pct"],
             "delta_pct": row["effective_ownership_delta_pct"]}
            for row in sorted(
                [row for row in output if not row["in_personal_squad"] and row["field_effective_ownership_pct"] > 0],
                key=lambda row: row["effective_ownership_delta_pct"],
            )[:5]
        ],
        "interpretation": (
            "Positive effective-ownership delta means this squad has more exposure than the sampled field; "
            "negative means less exposure. This is an exposure comparison, not a points or rank forecast."
        ),
        "co_var": "NOT_COMPUTED_HERE; the existing CoVar portfolio layer remains separate.",
        "field_source": "Existing rank-stratified pre-deadline cohort / post-lock picks EO snapshot",
        "field_scope": "Sample estimate, not a whole-game census",
    }
    return output, summary


def _read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--entry-id", type=int, required=True, help="FPL entry ID; runtime input only")
    parser.add_argument("--gameweek", type=int, required=True)
    parser.add_argument("--field-eo", type=Path, required=True, help="CSV produced by the existing EO capture workflow")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--delay", type=float, default=0.15)
    parser.add_argument("--lock-grace-seconds", type=int, default=60)
    args = parser.parse_args()
    if args.entry_id < 1 or args.gameweek < 1:
        raise ValueError("entry-id and gameweek must be positive integers")

    bootstrap = fetch_json(f"{BASE}/bootstrap-static/", delay=args.delay)
    validate_locked_event(bootstrap, args.gameweek, lock_grace_seconds=args.lock_grace_seconds)
    picks_payload = fetch_json(
        f"{BASE}/entry/{args.entry_id}/event/{args.gameweek}/picks/", delay=args.delay
    )
    personal_picks, active_chip = normalize_personal_picks(picks_payload, args.gameweek)
    field_rows = _read_csv(args.field_eo)
    team_by_id = {str(team["id"]): team.get("name", "") for team in bootstrap.get("teams", [])}
    positions = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
    player_metadata = {}
    for player in bootstrap.get("elements", []):
        player_metadata[str(player["id"])] = {
            "web_name": player.get("web_name", ""),
            "team": team_by_id.get(str(player.get("team")), ""),
            "position": positions.get(player.get("element_type"), ""),
        }
    output, report = compare_squad_to_field(
        personal_picks, active_chip, field_rows, args.gameweek, player_metadata
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with (args.out_dir / "fpl_personal_team_vs_field.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)
    (args.out_dir / "fpl_personal_team_vs_field_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
