#!/usr/bin/env python3
"""Acquire and prepare reproducible FPL/Understat inputs for the CTA five-GW pipeline.

Uses a pinned Vaastav repository snapshot for historical archives, then refreshes
the active season from the official FPL API. Dastan's MIT reconstruction code is
used only for canonical source joins and feature definitions; its points heads
are never invoked. Ambiguous shared Understat identities are excluded from joins.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from feature_availability import unavailable_feature_names

FPL_API = "https://fantasy.premierleague.com/api"
USER_AGENT = {"User-Agent": "CTA-FPL-Model/1.0 (forecast data preparation)"}
POSITIONS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
API_HISTORY_FIELDS = (
    "minutes", "total_points", "goals_scored", "assists", "clean_sheets",
    "goals_conceded", "own_goals", "penalties_saved", "penalties_missed",
    "yellow_cards", "red_cards", "saves", "bonus", "bps", "influence",
    "creativity", "threat", "ict_index", "starts", "expected_goals",
    "expected_assists", "expected_goal_involvements", "expected_goals_conceded",
    "selected", "transfers_balance", "transfers_in", "transfers_out", "value",
    "clearances_blocks_interceptions", "defensive_contribution", "recoveries", "tackles",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_bytes(url: str, retries: int = 5) -> bytes:
    last = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers=USER_AGENT)
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code not in (429, 500, 502, 503, 504):
                raise
            time.sleep(min(30, 2 ** attempt))
    raise RuntimeError(f"Unable to fetch {url}: {last}")


def fetch_json(url: str):
    return json.loads(fetch_bytes(url).decode("utf-8"))


def write_csv_frame(frame: pd.DataFrame, path: Path) -> None:
    """Write portable UTF-8 CSV with a real LF line terminator."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n")


def player_elements(bootstrap: dict) -> list[dict]:
    """Return real FPL players only, excluding manager/club entity element types."""
    return [
        player for player in bootstrap.get("elements", [])
        if int(player.get("element_type", 0)) in POSITIONS
    ]


def season_from_bootstrap(bootstrap: dict) -> str:
    deadlines = [
        datetime.fromisoformat(event["deadline_time"].replace("Z", "+00:00"))
        for event in bootstrap.get("events", [])
        if event.get("deadline_time")
    ]
    if not deadlines:
        raise ValueError("FPL bootstrap contains no event deadlines")
    start = min(deadlines).year if min(deadlines).month >= 6 else min(deadlines).year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def write_current_roster(dastan_root: Path, bootstrap: dict, season: str) -> Path:
    mapping_dir = dastan_root / "data" / "mappings"
    path = mapping_dir / "fpl_players_current.csv"
    teams = {int(row["id"]): str(row["name"]) for row in bootstrap.get("teams", [])}
    rows = []
    for player in player_elements(bootstrap):
        position = POSITIONS[int(player["element_type"])]
        rows.append({
            "season": season,
            "fpl_code": int(player["code"]),
            "element": int(player["id"]),
            "player_name": str(player.get("web_name", "")),
            "position": "GKP" if position == "GK" else position,
            "team_name": teams[int(player["team"])],
        })
    if not rows:
        raise ValueError("Live FPL bootstrap returned an empty roster")
    frame = pd.DataFrame(rows).sort_values("fpl_code", kind="mergesort")
    if frame["fpl_code"].duplicated().any() or frame["element"].duplicated().any():
        raise ValueError("Live FPL roster contains duplicate stable codes or element IDs")
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n")
    return path


def patch_identity_resolution(mappings, sources):
    """Use corrected historical IDs and exclude every shared Understat ID."""
    original_training = mappings.load_training_assignments
    original_operational = mappings.load_operational_players

    def safe_training_assignments():
        assignments = original_training().copy()
        corrected = mappings.load()
        counts = corrected.groupby("understat_id")["fpl_code"].nunique()
        shared = set(counts[counts > 1].index.astype(int))
        safe = corrected[~corrected["understat_id"].astype(int).isin(shared)]
        lookup = safe.set_index("fpl_code")["understat_id"]
        assignments["understat_id"] = assignments["fpl_code"].map(lookup)
        return assignments

    def safe_operational_players():
        players = original_operational().copy()
        mapped = players["understat_player_id"].notna()
        counts = players.loc[mapped].groupby("understat_player_id")["fpl_code"].nunique()
        shared = set(counts[counts > 1].index.astype(int))
        players.loc[players["understat_player_id"].isin(shared), "understat_player_id"] = pd.NA
        return players

    mappings.load_training_assignments = safe_training_assignments
    mappings.load_operational_players = safe_operational_players

    def needed_understat_ids(raw_dir: Path, seasons: list[str]) -> set[int]:
        assignments = mappings.assignments_for_seasons(seasons)
        values = assignments.loc[assignments["season"].isin(seasons), "understat_id"].dropna()
        return set(values.astype(int))

    sources._needed_understat_ids = needed_understat_ids


def refresh_current_core(raw_dir: Path, season: str, bootstrap: dict, fixtures: list[dict],
                         *, workers: int = 10) -> dict:
    """Replace active-season roster/team lookup and refresh player match history."""
    base = raw_dir / "vaastav" / season
    merged_path = base / "merged_gw.csv"
    players_path = base / "players_raw.csv"
    teams_path = base / "teams.csv"
    # The active season may not exist in the pinned historical archive yet.
    # Seed empty source files; the official bootstrap and element-summary API below
    # provide the authoritative current-season roster and completed match rows.
    if not merged_path.is_file():
        merged_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=[
            "name", "position", "team", "element", "fixture", "round", "GW",
            "opponent_team", "kickoff_time", "was_home", *API_HISTORY_FIELDS,
        ]).to_csv(merged_path, index=False, lineterminator="\n")

    live_players = pd.DataFrame([{
        "id": int(p["id"]), "code": int(p["code"]),
        "element_type": int(p["element_type"]), "web_name": str(p.get("web_name", "")),
    } for p in bootstrap.get("elements", [])])
    old_players = pd.read_csv(players_path, low_memory=False) if players_path.exists() else pd.DataFrame()
    combined_players = pd.concat([old_players, live_players], ignore_index=True, sort=False)
    combined_players = combined_players.drop_duplicates("id", keep="last")
    if combined_players["code"].duplicated().any():
        raise ValueError("Active-season players_raw has duplicate stable fpl_code values")
    combined_players.to_csv(players_path, index=False, lineterminator="\n")

    live_teams = pd.DataFrame([{
        "id": int(t["id"]), "name": str(t["name"]),
        "short_name": str(t.get("short_name", "")), "code": int(t.get("code", 0)),
    } for t in bootstrap.get("teams", [])])
    if live_teams["id"].duplicated().any() or live_teams["name"].duplicated().any():
        raise ValueError("Live FPL teams contain duplicate IDs or names")
    live_teams.to_csv(teams_path, index=False, lineterminator="\n")

    fixture_by_id = {int(f["id"]): f for f in fixtures}
    team_by_id = {int(t["id"]): str(t["name"]) for t in bootstrap.get("teams", [])}
    # FPL bootstrap may also contain manager/club entities (element_type 5+).
    # Only the four player positions belong in the player-match archive.
    players = player_elements(bootstrap)
    position_by_element = {
        int(player["id"]): POSITIONS[int(player["element_type"])]
        for player in players
    }
    history_payloads = {}
    failures = []

    def fetch_player(player):
        element = int(player["id"])
        return element, fetch_json(f"{FPL_API}/element-summary/{element}/")

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(fetch_player, player) for player in players]
        for index, future in enumerate(as_completed(futures), 1):
            try:
                element, payload = future.result()
                history_payloads[element] = payload
            except Exception as exc:
                failures.append(str(exc))
            if index % 50 == 0 or index == len(futures):
                print(
                    f"    FPL element-summary history {index:,}/{len(futures):,}; "
                    f"failed={len(failures):,}",
                    flush=True,
                )
    if failures:
        raise RuntimeError(f"FPL element-summary retrieval failed for {len(failures)} players: {failures[:3]}")

    rows = []
    players_with_history = set()
    for player in players:
        element = int(player["id"])
        payload = history_payloads[element]
        for history in payload.get("history", []):
            fixture_id = history.get("fixture")
            if fixture_id is None or int(fixture_id) not in fixture_by_id:
                continue
            fixture = fixture_by_id[int(fixture_id)]
            if not (fixture.get("finished") or fixture.get("finished_provisional")):
                continue
            kickoff = history.get("kickoff_time") or fixture.get("kickoff_time")
            if not kickoff:
                raise ValueError(f"FPL history has no kickoff time for element={element}, fixture={fixture_id}")
            home = history.get("was_home")
            was_home = home is True or str(home).strip().lower() in {"true", "1"}
            own_team_id = int(fixture["team_h"] if was_home else fixture["team_a"])
            opponent_id = int(fixture["team_a"] if was_home else fixture["team_h"])
            row = {
                "name": str(player.get("web_name", "")),
                "position": position_by_element[element],
                "team": team_by_id[own_team_id],
                "element": element,
                "fixture": int(fixture_id),
                "round": int(history.get("round") or fixture.get("event") or 0),
                "GW": int(history.get("round") or fixture.get("event") or 0),
                "opponent_team": opponent_id,
                "kickoff_time": kickoff,
                "was_home": was_home,
                "team_h_score": fixture.get("team_h_score", 0) or 0,
                "team_a_score": fixture.get("team_a_score", 0) or 0,
                "xP": "",
            }
            for field in API_HISTORY_FIELDS:
                row[field] = history.get(field, "")
            rows.append(row)
            players_with_history.add(element)

    if not rows:
        raise RuntimeError("FPL element-summary API returned no completed current-season match rows")
    live_history = pd.DataFrame(rows)
    old = pd.read_csv(merged_path, low_memory=False)
    if not {"element", "fixture"}.issubset(old.columns):
        raise ValueError("Pinned merged_gw.csv is missing element/fixture identity")
    live_keys = set(zip(live_history["element"].astype(int), live_history["fixture"].astype(int)))
    old_keys = list(zip(pd.to_numeric(old["element"], errors="coerce").fillna(-1).astype(int),
                        pd.to_numeric(old["fixture"], errors="coerce").fillna(-1).astype(int)))
    keep_mask = [key not in live_keys for key in old_keys]
    old = old.loc[keep_mask]
    merged = pd.concat([old, live_history], ignore_index=True, sort=False)
    merged["element"] = pd.to_numeric(merged["element"], errors="raise").astype(int)
    merged["fixture"] = pd.to_numeric(merged["fixture"], errors="raise").astype(int)
    if merged.duplicated(["element", "fixture"]).any():
        raise ValueError("Refreshed active-season archive has duplicate element-fixture keys")
    merged.to_csv(merged_path, index=False, lineterminator="\n")

    return {
        "live_roster_players": len(players),
        "players_with_completed_history": len(players_with_history),
        "api_player_fixture_rows": len(live_history),
        "active_archive_player_fixture_rows": len(merged),
        "api_fixture_coverage": len(set(live_history["fixture"].astype(int))),
        "current_players_without_history": sorted(set(int(p["id"]) for p in players) - players_with_history),
        "history_source": "official FPL element-summary API",
    }


def download_fixture_schedules(raw_dir: Path, seasons: list[str], source_commit: str) -> None:
    for season in seasons:
        path = raw_dir / "vaastav" / season / "fixtures.csv"
        if path.exists() and path.stat().st_size:
            continue
        url = f"https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/{source_commit}/data/{season}/fixtures.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(fetch_bytes(url))


def write_live_fixture_schedule(raw_dir: Path, season: str, fixtures: list[dict]) -> Path:
    rows = [{
        "id": int(row["id"]),
        "event": "" if row.get("event") is None else int(row["event"]),
        "finished": bool(row.get("finished")),
        "team_h": int(row["team_h"]),
        "team_a": int(row["team_a"]),
        "kickoff_time": row.get("kickoff_time") or "",
    } for row in fixtures]
    path = raw_dir / "vaastav" / season / "fixtures.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_csv_frame(pd.DataFrame(rows), path)
    return path


def audit_all_fixture_archives(raw_dir: Path, seasons: list[str]) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from audit_vaastav_fixture_archive import audit_archive, read_csv
    reports = {}
    for season in seasons:
        base = raw_dir / "vaastav" / season
        report = audit_archive(
            read_csv(base / "merged_gw.csv"),
            read_csv(base / "fixtures.csv"),
            read_csv(base / "teams.csv"),
            season,
        )
        reports[season] = {
            key: value for key, value in report.items()
            if key != "fixture_summaries"
        }
        if report["status"] != "PASS_FIXTURE_ARCHIVE_AUDIT":
            raise RuntimeError(f"{season} fixture archive audit failed: {report['fixture_metadata_errors'][:5]}")
    return reports


def apply_historical_snapshot_safety_buffer(training_dir: Path, minutes: int = 5) -> dict:
    """Drop archived snapshots captured inside the final safety buffer before deadline."""
    reports = {}
    for stem in ("pre_deadline_ep_next", "pre_deadline_signals"):
        parquet_path = training_dir / f"{stem}.parquet"
        report_path = training_dir / f"{stem}.json"
        frame = pd.read_parquet(parquet_path)
        required = {"snapshot_at", "deadline_time"}
        if not required.issubset(frame.columns):
            raise ValueError(f"{stem}: missing snapshot/deadline provenance columns")
        captured = pd.to_datetime(frame["snapshot_at"], utc=True, errors="coerce")
        deadline = pd.to_datetime(frame["deadline_time"], utc=True, errors="coerce")
        if captured.isna().any() or deadline.isna().any():
            raise ValueError(f"{stem}: invalid snapshot/deadline timestamps")
        eligible = captured.le(deadline - pd.Timedelta(minutes=minutes))
        before = len(frame)
        frame = frame.loc[eligible].copy()
        if frame.empty:
            raise RuntimeError(f"{stem}: no rows survive the {minutes}-minute safety buffer")
        frame.to_parquet(parquet_path, index=False)
        sidecar = (
            json.loads(report_path.read_text(encoding="utf-8"))
            if report_path.is_file() else {
                "source": "imported Dastan release artifact",
                "release_artifact": str(parquet_path.name),
            }
        )
        sidecar["rows_before_cta_safety_buffer"] = before
        sidecar["rows"] = len(frame)
        sidecar["cta_deadline_safety_buffer"] = {
            "minutes": minutes,
            "rows_retained": len(frame),
            "rows_rejected": before - len(frame),
            "rule": "snapshot_at <= deadline_time - safety_buffer",
        }
        report_path.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
        reports[stem] = sidecar["cta_deadline_safety_buffer"]
    return reports


def understat_players_needing_refresh(
    raw_dir: Path, seasons: list[str], player_ids: set[int] | list[int], sources,
) -> set[int]:
    """Select only mapped players with FPL appearances missing from both caches."""
    expected = sources._expected_understat_player_dates(raw_dir, seasons)
    csv_root = raw_dir / "vaastav" / "understat" / "players"
    json_root = raw_dir / "understat" / "players"
    refresh = set()
    for value in player_ids:
        player_id = int(value)
        expected_dates = {
            pd.Timestamp(value).date() for value in expected.get(player_id, set())
            if pd.notna(pd.to_datetime(value, errors="coerce"))
        }
        if not expected_dates:
            continue
        json_path = json_root / f"{player_id}.json"
        if json_path.is_file() and json_path.stat().st_size:
            try:
                payload = json.loads(json_path.read_text(encoding="utf-8"))
                dates = pd.DataFrame(payload).get("date", pd.Series(dtype="object"))
                actual = set(pd.to_datetime(dates, errors="coerce").dt.date.dropna())
                if expected_dates.issubset(actual):
                    continue
            except (ValueError, TypeError, json.JSONDecodeError):
                pass
        csv_path = csv_root / f"{player_id}.csv"
        if csv_path.is_file() and csv_path.stat().st_size:
            try:
                dates = pd.read_csv(csv_path, usecols=["date"])["date"]
                actual = set(pd.to_datetime(dates, errors="coerce").dt.date.dropna())
                if expected_dates.issubset(actual):
                    continue
            except (ValueError, KeyError, pd.errors.ParserError):
                pass
        refresh.add(player_id)
    return refresh


def parallel_understat_fallbacks(
    raw_dir: Path,
    missing_players: list[int],
    missing_team_seasons: list[str],
    *,
    force: bool,
    allow_missing: bool,
    workers: int = 4,
    team_names_by_season: dict[str, set[str]] | None = None,
) -> dict:
    """Acquire complete player/team histories through API.SH's documented JSON API."""
    from understat_apish_provider import ApiShUnderstatClient, reserve_monthly_calls

    api_key = os.environ.get("APISH_KEY")
    if not api_key:
        raise RuntimeError(
            "Understat's own automated endpoint now returns an HTML error page. "
            "Add an API.SH key as GitHub Actions secret APISH_KEY; the API.SH "
            "player endpoint supplies full career match rows and the team endpoint "
            "supplies team match histories."
        )
    budget = int(os.environ.get("APISH_MONTHLY_CREDIT_BUDGET", "900"))
    usage_path = raw_dir / "understat" / "apish_usage.json"
    root = raw_dir / "understat" / "players"
    team_root = raw_dir / "understat" / "teams"
    root.mkdir(parents=True, exist_ok=True)
    team_root.mkdir(parents=True, exist_ok=True)

    # The caller supplies only missing or incomplete player histories. Do not
    # skip a partial cached JSON file: it is exactly what needs refreshing.
    player_ids = sorted(set(int(value) for value in missing_players))
    team_names_by_season = team_names_by_season or {}
    team_requests: dict[str, list[str]] = {}
    for season in missing_team_seasons:
        path = team_root / f"{season}.json"
        existing_team_payload = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.is_file() and path.stat().st_size and not force else {}
        )
        names = sorted(
            set(team_names_by_season.get(season, set())) - set(existing_team_payload)
        )
        if names:
            # API.SH exposes all EPL team histories in one league request.
            # One request per season avoids N repeated calls for N clubs.
            team_requests[season] = names

    if not player_ids and not team_requests:
        return {
            "provider": "API.SH",
            "player_histories_fetched": 0,
            "team_histories_fetched": 0,
            "credits_reserved": 0,
            "status": "CACHE_COMPLETE",
        }

    worker_state = threading.local()
    clients: list[Any] = []
    clients_lock = threading.Lock()

    def get_client():
        client = getattr(worker_state, "client", None)
        if client is None:
            client = ApiShUnderstatClient(api_key=api_key)
            worker_state.client = client
            with clients_lock:
                clients.append(client)
        return client

    def close_clients():
        with clients_lock:
            owned = list(clients)
            clients.clear()
        for client in owned:
            try:
                client.session.close()
            except Exception:
                pass

    calls_reserved = 0
    usage = None

    def reserve(calls: int):
        nonlocal calls_reserved, usage
        if calls <= 0:
            return
        usage = reserve_monthly_calls(usage_path, calls, budget)
        calls_reserved += calls

    def fetch_player(player_id: int) -> tuple[int, list | None, str | None]:
        path = root / f"{player_id}.json"
        if path.is_file() and path.stat().st_size and not force:
            return player_id, None, None
        try:
            history, _credits = get_client().player_history(player_id)
            return player_id, history, None
        except Exception as exc:
            return player_id, None, str(exc)

    def fetch_teams(season: str) -> tuple[str, dict | None, str | None]:
        try:
            histories, _credits = get_client().league_team_histories(season)
            return "team", season, histories, None
        except Exception as exc:
            return "team", season, None, str(exc)

    player_success = 0
    team_success = 0
    failures: list[str] = []
    team_payloads: dict[str, dict] = {}
    for season in team_requests:
        path = team_root / f"{season}.json"
        team_payloads[season] = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.is_file() and path.stat().st_size else {}
        )
    print(
        f"  API.SH import: {len(player_ids):,} player histories and "
        f"{sum(len(names) for names in team_requests.values()):,} team histories across "
        f"{len(team_requests):,} league requests; monthly local credit cap={budget}",
        flush=True,
    )

    # Reserve a small preflight first. Do not reserve the full bulk job until
    # the provider has proved the key and response contract work.
    preflight_ids = player_ids[:3]
    if preflight_ids:
        reserve(len(preflight_ids))
        preflight = [fetch_player(player_id) for player_id in preflight_ids]
        failed = [item for item in preflight if item[2] is not None]
        for player_id, history, error in preflight:
            if history is not None:
                (root / f"{player_id}.json").write_text(
                    json.dumps(history, ensure_ascii=False) + "\n", encoding="utf-8"
                )
                player_success += 1
            else:
                failures.append(f"player:{player_id}:{error}")
        if player_success == 0 and failed:
            close_clients()
            raise RuntimeError(
                "API.SH player-history preflight failed; stopping before bulk acquisition. "
                f"Errors: {failures[:3]}"
            )

    remaining_player_ids = player_ids[len(preflight_ids):]
    remaining_calls = len(remaining_player_ids) + len(team_requests)
    reserve(remaining_calls)
    try:
        tasks = []
        with ThreadPoolExecutor(max_workers=min(max(1, workers), 6)) as pool:
            tasks.extend(
                pool.submit(fetch_player, player_id)
                for player_id in remaining_player_ids
            )
            tasks.extend(
                pool.submit(fetch_teams, season)
                for season in team_requests
            )
            completed = 0
            for future in as_completed(tasks):
                result = future.result()
                completed += 1
                if len(result) == 3:
                    player_id, history, error = result
                    if error is not None:
                        failures.append(f"player:{player_id}:{error}")
                    elif history is not None:
                        (root / f"{player_id}.json").write_text(
                            json.dumps(history, ensure_ascii=False) + "\n", encoding="utf-8"
                        )
                        player_success += 1
                else:
                    _kind, season, histories, error = result
                    if error is not None:
                        failures.append(f"league:{season}:{error}")
                    elif histories is not None:
                        requested_names = set(team_requests.get(season, []))
                        for team_name in requested_names:
                            history = histories.get(team_name)
                            if history is None:
                                failures.append(f"team:{season}:{team_name}:missing from league payload")
                                continue
                            team_payloads.setdefault(season, {})[team_name] = history
                            team_success += 1
                if completed % 25 == 0 or completed == len(tasks):
                    print(
                        f"    API.SH source imports {completed:,}/{len(tasks):,}; "
                        f"players={player_success:,}; teams={team_success:,}; "
                        f"failed={len(failures):,}",
                        flush=True,
                    )
    finally:
        close_clients()

    for season, team_payload in team_payloads.items():
        (team_root / f"{season}.json").write_text(
            json.dumps(team_payload, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    if failures and not allow_missing:
        raise RuntimeError(
            f"API.SH could not resolve {len(failures)} Understat sources: {failures[:10]}"
        )
    return {
        "provider": "API.SH",
        "player_histories_requested": len(player_ids),
        "player_histories_fetched": player_success,
        "team_histories_requested": sum(len(names) for names in team_requests.values()),
        "team_histories_fetched": team_success,
        "credits_reserved": calls_reserved,
        "monthly_usage": usage,
        "status": "PASS" if not failures else "PARTIAL",
        "failures": failures[:10],
    }


def historical_source_seasons(training_seasons: list[str], active_season: str) -> list[str]:
    """Keep the pinned historical archive downloader away from the live season.

    The active season is refreshed from the official FPL API after historical
    source acquisition. Including it in Dastan's initial completeness audit
    makes a partial, mutable season look like an incomplete archive and can
    trigger unnecessary per-player Understat fallback requests.
    """
    historical = list(dict.fromkeys(str(value) for value in training_seasons))
    if active_season in historical:
        raise ValueError(f"Active season {active_season} overlaps historical training seasons")
    if not historical:
        raise ValueError("Dastan training season list is empty")
    return historical



def copy_verified_dastan_release(dastan_root: Path, training_dir: Path) -> dict:
    """Import every published Dastan data-release artifact after hash verification."""
    release_dir = dastan_root / "data"
    manifest_path = release_dir / "release_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise RuntimeError("Dastan release manifest has no artifact inventory")
    copied = {}
    training_dir.mkdir(parents=True, exist_ok=True)
    for relative, expected in sorted(files.items()):
        source = release_dir / relative
        if not source.is_file() or not isinstance(expected, dict):
            raise RuntimeError(f"Dastan release artifact is missing: {relative}")
        actual_hash = sha256(source)
        if actual_hash != expected.get("sha256"):
            raise RuntimeError(
                f"Dastan release hash mismatch for {relative}: "
                f"{actual_hash} != {expected.get('sha256')}"
            )
        destination = training_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied[relative] = {
            "path": str(destination),
            "sha256": sha256(destination),
            "bytes": destination.stat().st_size,
            "rows": expected.get("rows"),
            "columns": expected.get("columns"),
        }
    shutil.copy2(manifest_path, training_dir / "release_manifest.json")
    return {
        "release_manifest_sha256": sha256(manifest_path),
        "release_manifest_path": str(manifest_path),
        "source_commit": "758db9247e8b3a9a870c991064f74d8339d61cd0",
        "artifact_count": len(copied),
        "artifacts": copied,
    }


def copy_verified_dastan_model_contract(dastan_root: Path, output_dir: Path) -> dict:
    """Import all 40 published Dastan model-contract files with hash verification."""
    source_dir = dastan_root / "models"
    manifest_path = source_dir / "artifact_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files")
    if not isinstance(files, dict) or len(files) != 40:
        raise RuntimeError("Dastan model manifest does not contain its complete 40-file contract")
    model_dir = output_dir / "dastan_model"
    model_dir.mkdir(parents=True, exist_ok=True)
    copied = {}
    for relative, expected in sorted(files.items()):
        source = source_dir / relative
        if not source.is_file() or not isinstance(expected, dict):
            raise RuntimeError(f"Dastan model artifact is missing: {relative}")
        actual_hash = sha256(source)
        if actual_hash != expected.get("sha256") or source.stat().st_size != int(expected.get("bytes", -1)):
            raise RuntimeError(f"Dastan model artifact integrity mismatch: {relative}")
        destination = model_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied[relative] = {"sha256": sha256(destination), "bytes": destination.stat().st_size}
    shutil.copy2(manifest_path, model_dir / "artifact_manifest.json")
    return {
        "model_version": manifest.get("public_version"),
        "model_manifest_sha256": sha256(manifest_path),
        "artifact_count": len(copied),
        "model_dir": str(model_dir),
        "artifacts": copied,
    }


def copy_dastan_operational_mappings(dastan_root: Path, output_dir: Path) -> dict:
    """Preserve every current/operational Dastan mapping artifact with hashes."""
    source_dir = dastan_root / "data" / "mappings"
    destination_dir = output_dir / "dastan_mappings"
    destination_dir.mkdir(parents=True, exist_ok=True)
    copied = {}
    for source in sorted(path for path in source_dir.iterdir() if path.is_file()):
        destination = destination_dir / source.name
        shutil.copy2(source, destination)
        copied[source.name] = {
            "sha256": sha256(destination),
            "bytes": destination.stat().st_size,
        }
    if not copied:
        raise RuntimeError("Dastan operational mapping directory is empty")
    return {"artifact_count": len(copied), "directory": str(destination_dir), "artifacts": copied}


def import_dastan_release(dastan_root: Path, training_dir: Path) -> tuple[pd.DataFrame, dict]:
    """Verify and load the published Dastan frame and point-in-time snapshot tables."""
    sys.path.insert(0, str(dastan_root))
    from dastan import data as dastan_data
    from dastan import datasets as dastan_datasets

    dastan_datasets.verify_release()
    imported = copy_verified_dastan_release(dastan_root, training_dir)
    model_contract = copy_verified_dastan_model_contract(dastan_root, training_dir.parent)
    operational_mappings = copy_dastan_operational_mappings(dastan_root, training_dir.parent)
    safety = apply_historical_snapshot_safety_buffer(training_dir, minutes=5)
    for name in ("pre_deadline_ep_next.parquet", "pre_deadline_signals.parquet"):
        imported["artifacts"][name]["post_safety_buffer_sha256"] = sha256(training_dir / name)
        imported["artifacts"][name]["post_safety_buffer_rows"] = safety[
            name.removesuffix(".parquet")
        ]["rows_retained"]
    frame = dastan_data.load(check_rows=True, data_dir=training_dir)
    output = training_dir / "features_with_snapshots.parquet"
    frame.to_parquet(output, index=False)
    report = {
        "status": "PASS_IMPORTED_DASTAN_RELEASE",
        **imported,
        "model_contract": model_contract,
        "operational_mappings": operational_mappings,
        "training_rows": len(frame),
        "training_columns": len(frame.columns),
        "feature_count": len(dastan_data.shipped_features(frame)),
        "snapshot_safety_buffer": safety,
        "training_frame": {
            "path": str(output),
            "sha256": sha256(output),
            "bytes": output.stat().st_size,
        },
        "reconstruction_performed": False,
    }
    (training_dir / "dastan_release_import_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return frame, report


def historical_source_seasons(training_seasons: list[str], active_season: str) -> list[str]:
    """Return the registered historical seasons without the live season."""
    historical = list(dict.fromkeys(str(value) for value in training_seasons))
    if active_season in historical:
        raise ValueError(f"Active season {active_season} overlaps historical training seasons")
    if not historical:
        raise ValueError("Dastan training season list is empty")
    return historical


def build_fpl_team_matches(player_matches: pd.DataFrame, fpl_to_understat) -> pd.DataFrame:
    """Build team-match rows from FPL fixture scores; no Understat dependency."""
    required = {
        "season", "fixture", "team_name", "opponent_team_name", "is_home",
        "kickoff_time", "team_h_score", "team_a_score",
    }
    missing = sorted(required - set(player_matches.columns))
    if missing:
        raise RuntimeError(f"FPL player matches lack team-match inputs: {missing}")
    frame = player_matches[
        [
            "season", "fixture", "team_name", "opponent_team_name", "is_home",
            "kickoff_time", "team_h_score", "team_a_score",
        ]
    ].drop_duplicates(
        ["season", "fixture", "team_name", "opponent_team_name", "is_home"]
    ).copy()
    frame["date"] = pd.to_datetime(frame["kickoff_time"], utc=True, errors="coerce")
    if frame["date"].isna().any():
        raise RuntimeError("FPL team-match inputs contain invalid kickoff times")
    frame["is_home"] = pd.to_numeric(frame["is_home"], errors="coerce").fillna(0).astype(int)
    home_score = pd.to_numeric(frame["team_h_score"], errors="coerce")
    away_score = pd.to_numeric(frame["team_a_score"], errors="coerce")
    if home_score.isna().any() or away_score.isna().any():
        raise RuntimeError("FPL team-match inputs include fixtures without final scores")
    is_home = frame["is_home"].eq(1)
    frame["scored"] = np.where(is_home, home_score, away_score).astype(float)
    frame["missed"] = np.where(is_home, away_score, home_score).astype(float)
    frame["pts"] = np.where(
        frame["scored"] > frame["missed"], 3,
        np.where(frame["scored"] == frame["missed"], 1, 0),
    ).astype(float)
    frame["understat_team"] = frame["team_name"].map(fpl_to_understat)
    frame["opponent"] = frame["opponent_team_name"].map(fpl_to_understat)
    for column in (
        "xG", "xGA", "deep", "deep_allowed", "ppda_att", "ppda_def",
        "ppda_allowed_att", "ppda_allowed_def",
    ):
        frame[column] = 0.0
    if frame.duplicated(["season", "understat_team", "date"]).any():
        raise RuntimeError("FPL team-match table contains duplicate team kickoffs")
    fixture_sides = frame.groupby(["season", "fixture"])["understat_team"].nunique()
    if not fixture_sides.eq(2).all():
        bad = fixture_sides[fixture_sides.ne(2)].head(10).to_dict()
        raise RuntimeError(f"FPL team-match table lacks two sides for fixtures: {bad}")
    return frame[
        [
            "season", "fixture", "date", "understat_team", "opponent", "is_home",
            "scored", "missed", "pts", "xG", "xGA", "deep", "deep_allowed",
            "ppda_att", "ppda_def", "ppda_allowed_att", "ppda_allowed_def",
        ]
    ].sort_values(["season", "date", "understat_team"], kind="mergesort").reset_index(drop=True)


def merge_understat_team_metrics(
    fpl_team_matches: pd.DataFrame,
    understat_team_matches: pd.DataFrame,
    *,
    minimum_coverage: float = 0.95,
) -> tuple[pd.DataFrame, dict]:
    """Attach Understat team metrics to exact FPL fixture/team identities."""
    metrics = [
        "xG", "xGA", "deep", "deep_allowed",
        "ppda_att", "ppda_def", "ppda_allowed_att", "ppda_allowed_def",
    ]
    required_left = {"season", "fixture", "date", "understat_team", "is_home", "opponent"}
    required_right = {"season", "date", "understat_team", "is_home", *metrics}
    missing_left = sorted(required_left - set(fpl_team_matches.columns))
    missing_right = sorted(required_right - set(understat_team_matches.columns))
    if missing_left or missing_right:
        raise ValueError(
            f"Understat team merge inputs incomplete: fpl={missing_left}, understat={missing_right}"
        )
    if understat_team_matches.empty:
        raise RuntimeError("Understat team history is empty; refusing FPL-only silent fallback")

    left = fpl_team_matches.drop(columns=[name for name in metrics if name in fpl_team_matches]).copy()
    right = understat_team_matches.copy()
    left["_match_date"] = pd.to_datetime(left["date"], utc=True, errors="coerce").dt.date
    right["_match_date"] = pd.to_datetime(right["date"], utc=True, errors="coerce").dt.date
    left["is_home"] = pd.to_numeric(left["is_home"], errors="raise").astype(int)
    right["is_home"] = pd.to_numeric(right["is_home"], errors="raise").astype(int)
    keys = ["season", "_match_date", "understat_team", "is_home"]
    if left[keys].isna().any().any() or right[keys].isna().any().any():
        raise ValueError("Understat team merge has incomplete season/date/team/venue keys")
    if left.duplicated(keys).any() or right.duplicated(keys).any():
        raise ValueError("Understat team merge keys are not unique by season/date/team/venue")

    merged = left.merge(
        right[keys + metrics], on=keys, how="left", validate="one_to_one",
    )
    coverage = {metric: float(merged[metric].notna().mean()) for metric in metrics}
    weak = {name: value for name, value in coverage.items() if value < minimum_coverage}
    if weak:
        raise RuntimeError(
            f"Understat team metric coverage below {minimum_coverage:.0%}: {weak}"
        )
    merged = merged.drop(columns=["_match_date"])
    return merged, {
        "status": "PASS_UNDERSTAT_TEAM_METRIC_JOIN",
        "fixture_team_rows": len(merged),
        "understat_source_rows": len(right),
        "minimum_required_coverage": minimum_coverage,
        "metric_coverage": coverage,
        "join_keys": keys,
        "fixture_identity_source": "official FPL fixture ID and reciprocal opponent mapping",
    }


def prepare(dastan_root: Path, raw_dir: Path, output_dir: Path, source_commit: str,
            workers: int = 10) -> dict:
    sys.path.insert(0, str(dastan_root))
    from dastan import data as dastan_data
    from dastan import mappings
    from dastan.rebuild import sources, features as dastan_features

    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir = output_dir / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    training_dir = output_dir / "training"
    print("Importing and verifying Dastan's complete published data/model release", flush=True)
    training_frame, release_import_report = import_dastan_release(dastan_root, training_dir)
    bootstrap = fetch_json(f"{FPL_API}/bootstrap-static/")
    fixtures = fetch_json(f"{FPL_API}/fixtures/")
    bootstrap_captured_at = datetime.now(timezone.utc)
    season = season_from_bootstrap(bootstrap)
    next_events = [int(event["id"]) for event in bootstrap.get("events", []) if event.get("is_next")]
    if len(next_events) != 1:
        raise RuntimeError(f"Expected one next FPL gameweek, got {next_events}")
    first_gw = next_events[0]
    next_event = next(event for event in bootstrap["events"] if int(event["id"]) == first_gw)
    deadline = datetime.fromisoformat(next_event["deadline_time"].replace("Z", "+00:00"))
    if bootstrap_captured_at > deadline - timedelta(minutes=5):
        raise RuntimeError("Current FPL bootstrap snapshot is inside the five-minute deadline safety buffer")
    bootstrap["_cta_snapshot"] = {
        "captured_at_utc": bootstrap_captured_at.isoformat(),
        "gameweek": first_gw,
        "deadline_time": deadline.isoformat(),
        "safety_buffer_minutes": 5,
        "acceptance_rule": "captured_at_utc <= deadline_time - 5 minutes",
    }
    target_gameweeks = list(range(first_gw, first_gw + 5))
    if any(not any(int(event["id"]) == gw for event in bootstrap["events"]) for gw in target_gameweeks):
        raise RuntimeError("FPL season does not have five remaining consecutive gameweeks")
    bootstrap_path = snapshot_dir / "bootstrap-static.json"
    fixtures_path = snapshot_dir / "fixtures.json"
    bootstrap_path.write_text(json.dumps(bootstrap, indent=2) + "\n", encoding="utf-8")
    fixtures_path.write_text(json.dumps(fixtures, indent=2) + "\n", encoding="utf-8")

    roster_path = write_current_roster(dastan_root, bootstrap, season)
    mapping_release_report = mappings.verify_operational_release()
    patch_identity_resolution(mappings, sources)
    # Use pinned Vaastav Understat histories first. If a player or team-season
    # history is incomplete, use API.SH's documented JSON endpoint with a local
    # monthly credit guard; never fall back to scraping the blocked HTML endpoint.
    apish_fallback_reports = []

    def fetch_understat_fallbacks(
        fallback_raw_dir, missing_players, missing_team_seasons, *,
        force, allow_missing,
    ):
        team_names = (
            sources._epl_teams(fallback_raw_dir, missing_team_seasons)
            if missing_team_seasons else {}
        )
        result = parallel_understat_fallbacks(
            fallback_raw_dir, missing_players, missing_team_seasons,
            force=force, allow_missing=allow_missing, workers=workers,
            team_names_by_season=team_names,
        )
        apish_fallback_reports.append(result)
        return result

    sources._fetch_understat_fallbacks = fetch_understat_fallbacks
    operational_clubs = mappings.load_operational_clubs()
    dastan_features.FPL_TO_UNDERSTAT.update({
        str(row["club_name"]): str(row["understat_name"])
        for row in operational_clubs.to_dict("records")
        if row.get("understat_name")
    })
    sources.VAASTAV_COMMIT = source_commit
    sources.VAASTAV_RAW = f"https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/{source_commit}/"
    sources.VAASTAV_TREE = f"https://api.github.com/repos/vaastav/Fantasy-Premier-League/git/trees/{source_commit}?recursive=1"

    historical_seasons = historical_source_seasons(list(dastan_data.SEASONS), season)
    seasons = historical_seasons + [season]
    print(
        f"Downloading pinned raw match inputs needed for future feature generation; "
        f"published Dastan training data will be imported",
        flush=True,
    )
    # Acquire historical and active-season FPL/team inputs, but only fetch
    # Understat histories for current-roster players with actual appearances.
    sources.download_sources(
        raw_dir, historical_seasons, workers=workers, force=False,
        allow_missing_understat=False,
    )
    sources.download_sources(
        raw_dir, [season], workers=workers, force=False,
        allow_missing_understat=False,
    )
    download_fixture_schedules(raw_dir, historical_seasons, source_commit)

    current_api_report = refresh_current_core(raw_dir, season, bootstrap, fixtures, workers=workers)
    write_live_fixture_schedule(raw_dir, season, fixtures)
    fixture_archive_audits = audit_all_fixture_archives(raw_dir, seasons)

    manifest_path = sources.write_download_manifest(raw_dir, seasons)
    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_manifest["feature_source_mode"] = "FPL_UNDERSTAT"
    source_manifest["understat_status"] = "PINNED_VAASTAV_WITH_API_SH_FALLBACK"
    source_manifest["understat_fallback_reports"] = apish_fallback_reports
    source_manifest["active_season_overrides"] = {
        "season": season,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": {
            f"vaastav/{season}/merged_gw.csv": "Hybrid: pinned Vaastav archive plus official FPL element-summary history for current-roster players",
            f"vaastav/{season}/players_raw.csv": "Pinned Vaastav roster extended/refreshed from official FPL bootstrap-static",
            f"vaastav/{season}/teams.csv": "Official FPL bootstrap-static team snapshot",
            f"vaastav/{season}/fixtures.csv": "Official FPL fixtures API snapshot",
        },
        "api_endpoints": [
            f"{FPL_API}/bootstrap-static/",
            f"{FPL_API}/fixtures/",
            f"{FPL_API}/element-summary/{{element_id}}/",
        ],
        "history_rows_from_official_api": current_api_report["api_player_fixture_rows"],
    }
    manifest_path.write_text(json.dumps(source_manifest, indent=2) + "\n", encoding="utf-8")
    source_manifest_copy = output_dir / "source_download_manifest.json"
    shutil.copy2(manifest_path, source_manifest_copy)
    dastan_manifest_path = dastan_root / "models" / "artifact_manifest.json"
    dastan_manifest_copy = output_dir / "dastan_artifact_manifest.json"
    shutil.copy2(dastan_manifest_path, dastan_manifest_copy)

    print("Building canonical current/historical match tables for target feature generation", flush=True)
    player_matches, understat_team_matches, player_lookup = sources.build_canonical_matches(raw_dir, seasons)
    fpl_team_matches = build_fpl_team_matches(player_matches, dastan_features.fpl_to_understat)
    team_matches, understat_team_report = merge_understat_team_metrics(
        fpl_team_matches, understat_team_matches, minimum_coverage=0.95,
    )
    player_understat_columns = ["us_xG", "us_xA", "us_shots", "us_key_passes"]
    player_understat_coverage = {
        name: float(pd.to_numeric(player_matches[name], errors="coerce").notna().mean())
        for name in player_understat_columns
    }
    weak_player_coverage = {name: value for name, value in player_understat_coverage.items() if value < 0.70}
    if weak_player_coverage:
        raise RuntimeError(f"Understat player metric coverage below 70%: {weak_player_coverage}")
    if player_matches.duplicated(["season", "fixture", "fpl_code"]).any():
        raise RuntimeError("Canonical player-match table contains duplicate season-fixture-player keys")
    if team_matches.duplicated(["season", "understat_team", "date"]).any():
        raise RuntimeError("Canonical team-match table contains duplicate season-team-date keys")
    player_matches_path = output_dir / "canonical_player_matches.parquet"
    team_matches_path = output_dir / "canonical_team_matches.parquet"
    lookup_path = output_dir / "canonical_player_lookup.csv"
    player_matches.to_parquet(player_matches_path, index=False)
    team_matches.to_parquet(team_matches_path, index=False)
    player_lookup.to_csv(lookup_path, index=False, lineterminator="\n")

    mapping_file = dastan_root / "data" / "mappings" / "current_fpl_understat_players.csv"
    mapping_df = pd.read_csv(mapping_file)
    mapped = mapping_df[mapping_df["understat_player_id"].notna()].copy()
    id_counts = mapped.groupby("understat_player_id")["fpl_code"].nunique()
    shared_ids = sorted(id_counts[id_counts > 1].index.astype(int).tolist())
    unique_mapped = mapped[~mapped["understat_player_id"].astype(int).isin(shared_ids)]
    safe_mapping = mapping_df.copy()
    safe_mapping.loc[
        safe_mapping["understat_player_id"].notna()
        & safe_mapping["understat_player_id"].astype("Int64").isin(shared_ids),
        "understat_player_id",
    ] = pd.NA
    safe_mapping_path = output_dir / "safe_current_player_mapping.csv"
    write_csv_frame(safe_mapping, safe_mapping_path)
    mapping_report = {
        "roster_players": len(bootstrap.get("elements", [])),
        "mapping_registry_rows": len(mapping_df),
        "mapped_registry_rows": int(mapping_df["understat_player_id"].notna().sum()),
        "unique_understat_player_ids": int(unique_mapped["understat_player_id"].nunique()),
        "shared_understat_ids": shared_ids,
        "live_roster_mapped": int(pd.DataFrame(bootstrap["elements"])[["code"]].merge(
            unique_mapped[["fpl_code", "understat_player_id"]],
            left_on="code", right_on="fpl_code", how="inner"
        )["understat_player_id"].notna().sum()),
        "join_policy": "exact fpl_code; shared Understat IDs excluded; unmapped retained",
    }
    report = {
        "status": "PASS_IMPORTED_DASTAN_RELEASE_AND_CURRENT_SOURCE_PREPARATION",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "season": season,
        "target_gameweeks": target_gameweeks,
        "source_commit": source_commit,
        "historical_seasons": list(dastan_data.SEASONS),
        "source_manifest": str((raw_dir / "downloads.json").resolve()),
        "source_manifest_sha256": sha256(raw_dir / "downloads.json"),
        "current_roster_snapshot": str(roster_path),
        "current_api_history": current_api_report,
        "current_bootstrap_snapshot": bootstrap["_cta_snapshot"],
        "historical_snapshot_safety_buffer": release_import_report["snapshot_safety_buffer"],
        "fixture_archive_audits": fixture_archive_audits,
        "feature_source_mode": "FPL_UNDERSTAT",
        "understat_status": "PASS_PINNED_VAASTAV_WITH_API_SH_FALLBACK",
        "understat_fallback_reports": apish_fallback_reports,
        "understat_player_metric_coverage": player_understat_coverage,
        "understat_team_metric_join": understat_team_report,
        "historical_player_history_source": "Pinned Vaastav FPL match archives plus official FPL API history, joined to Understat player match metrics",
        "team_match_source": "Understat xG/deep/PPDA team histories joined to exact FPL fixture IDs and reciprocal opponents",
        "masked_unavailable_features": unavailable_feature_names(
            json.loads((dastan_root / "models" / "feature_cols.json").read_text(encoding="utf-8"))
        ),
        "canonical_player_match_rows": len(player_matches),
        "canonical_team_match_rows": len(team_matches),
        "historical_training_rows": len(training_frame),
        "dastan_release_import": release_import_report,
        "training_features": len(json.loads((dastan_root / "models" / "feature_cols.json").read_text(encoding="utf-8"))),
        "mapping_release_verification": mapping_release_report,
        "mapping": mapping_report,
        "club_mapping": {
            "total": len(operational_clubs),
            "mapped": int(operational_clubs["understat_team_id"].notna().sum()),
            "unmapped": operational_clubs.loc[
                operational_clubs["understat_team_id"].isna(), "club_name"
            ].astype(str).tolist(),
        },
        "artifacts": {
            "bootstrap": {"path": str(bootstrap_path), "sha256": sha256(bootstrap_path)},
            "fixtures": {"path": str(fixtures_path), "sha256": sha256(fixtures_path)},
            "canonical_player_matches": {"path": str(player_matches_path), "sha256": sha256(player_matches_path)},
            "canonical_team_matches": {"path": str(team_matches_path), "sha256": sha256(team_matches_path)},
            "safe_current_player_mapping": {"path": str(safe_mapping_path), "sha256": sha256(safe_mapping_path)},
            "source_download_manifest": {"path": str(source_manifest_copy), "sha256": sha256(source_manifest_copy)},
            "dastan_artifact_manifest": {"path": str(dastan_manifest_copy), "sha256": sha256(dastan_manifest_copy)},
            "historical_training_frame": release_import_report["training_frame"],
        },
        "important_boundaries": [
            "Dastan's full data release and 40-file model contract are imported; its full xPts model is benchmark-only, while CTA retains its own primary points model.",
            "Historical point-in-time snapshot artifacts are imported from the verified Dastan release and safety-filtered; no historical fplcache reconstruction is performed.",
            "Current next-GW snapshot values come only from the live official bootstrap; later target GWs receive -1 snapshot sentinels.",
            "Raw player/team match histories are reconstructed only to calculate new target-fixture features; the historical training frame and pre-deadline snapshots are imported directly from Dastan.",
            "Understat player/team histories use pinned Vaastav data with API.SH documented JSON fallback, bounded by a monthly credit guard.",
            "Source acquisition and feature generation do not clear CTA M2 validation or production eligibility.",
        ],
    }
    report_path = output_dir / "source_preparation_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    target_path = output_dir / "target_gameweeks.json"
    target_path.write_text(json.dumps({"season": season, "gameweeks": target_gameweeks}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"mapping", "artifacts"}}, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dastan-root", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-commit", default="d7b05b51d137bfefef4b692386d18c610975b9b9")
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()
    prepare(args.dastan_root, args.raw_dir, args.output_dir, args.source_commit, args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
