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
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

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
    if not merged_path.is_file():
        raise FileNotFoundError(merged_path)

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


def normalize_all_fpl_archives(raw_dir: Path, output_dir: Path, seasons: list[str]) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from normalize_vaastav_fpl_archive import normalize_archive, read_csv
    normalized_dir = output_dir / "normalized_fpl"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    reports = {}
    for season in seasons:
        base = raw_dir / "vaastav" / season
        rows, report = normalize_archive(
            read_csv(base / "merged_gw.csv"),
            read_csv(base / "players_raw.csv"),
            read_csv(base / "teams.csv"),
            season,
        )
        path = normalized_dir / f"{season}_player_matches.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        reports[season] = {
            "status": report["status"],
            "input_rows": report["input_merged_rows"],
            "canonical_player_rows": report["canonical_player_match_rows"],
            "excluded_non_player_rows": report["excluded_non_player_rows"],
            "unique_fixtures": report["unique_fixtures"],
            "unique_gameweeks": report["unique_gameweeks"],
            "normalized_path": str(path),
            "normalized_sha256": sha256(path),
        }
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
        sidecar = json.loads(report_path.read_text(encoding="utf-8"))
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


def parallel_understat_fallbacks(
    raw_dir: Path,
    missing_players: list[int],
    missing_team_seasons: list[str],
    *,
    force: bool,
    allow_missing: bool,
    workers: int = 4,
) -> None:
    """Fetch missing Understat histories concurrently with isolated client sessions.

    The upstream pinned downloader fetches missing player histories serially. For
    a large historical roster this can dominate the entire forecast build. Each
    task owns its client/session; concurrency is deliberately capped to reduce
    provider pressure, retries are bounded, and every unresolved ID is reported.
    """
    if not missing_players and not missing_team_seasons:
        return
    try:
        from understatapi import UnderstatClient
    except ImportError as exc:
        raise RuntimeError("Understat fallbacks are required; install requirements-data.txt") from exc

    root = raw_dir / "understat" / "players"
    root.mkdir(parents=True, exist_ok=True)
    player_ids = sorted(set(int(value) for value in missing_players))
    failures: list[str] = []

    def make_bounded_client():
        client = UnderstatClient()
        session = getattr(client, "session", None)
        if session is not None:
            original_request = session.request

            def request_with_timeout(method, url, **kwargs):
                if kwargs.get("timeout") is None:
                    kwargs["timeout"] = (10, 45)
                return original_request(method, url, **kwargs)

            # understatapi 0.7.1 does not set a requests timeout itself.
            # Bound connect/read time so one stalled response cannot pin a worker.
            session.request = request_with_timeout
        return client

    def fetch_player(player_id: int) -> tuple[int, list | None, str | None]:
        path = root / f"{player_id}.json"
        if path.exists() and path.stat().st_size and not force:
            return player_id, None, None
        last_error = None
        for attempt in range(3):
            try:
                with make_bounded_client() as client:
                    payload = client.player(player=str(player_id)).get_match_data()
                if not isinstance(payload, list):
                    raise ValueError(f"unexpected player payload type: {type(payload).__name__}")
                return player_id, payload, None
            except Exception as exc:
                last_error = str(exc)
                time.sleep(2 ** attempt)
        return player_id, None, last_error or "unknown error"

    print(
        f"  fetching {len(player_ids):,} missing Understat player histories "
        f"with {min(max(1, workers), 4)} workers",
        flush=True,
    )
    # Probe a few real mapped IDs before scheduling hundreds of requests. This
    # turns a provider-wide block, parser regression, or endpoint failure into a
    # short actionable error instead of an hour of identical retries.
    preflight = []
    for player_id in player_ids[:3]:
        result = fetch_player(player_id)
        preflight.append(result)
    successful_preflight = [item for item in preflight if item[1] is not None]
    failed_preflight = [item for item in preflight if item[2] is not None]
    for player_id, payload, error in successful_preflight:
        (root / f"{player_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    if not successful_preflight and failed_preflight:
        details = "; ".join(
            f"{player_id}: {error}" for player_id, _, error in failed_preflight
        )
        raise RuntimeError(
            "Understat fallback preflight failed for the first three mapped player IDs; "
            f"stopping before bulk acquisition. Errors: {details}"
        )

    completed = len(preflight)
    failures.extend(
        f"player:{player_id}:{error}" for player_id, _, error in failed_preflight
    )
    with ThreadPoolExecutor(max_workers=min(max(1, workers), 4)) as pool:
        futures = {
            pool.submit(fetch_player, player_id): player_id
            for player_id in player_ids[3:]
        }
        for future in as_completed(futures):
            player_id, payload, error = future.result()
            completed += 1
            if error is not None:
                failures.append(f"player:{player_id}:{error}")
                if len(failures) <= 10:
                    print(
                        f"    Understat fallback error {len(failures)}: "
                        f"player={player_id}; {error}",
                        flush=True,
                    )
            elif payload is not None:
                (root / f"{player_id}.json").write_text(
                    json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8"
                )
            if completed % 25 == 0 or completed == len(player_ids):
                print(
                    f"    Understat player fallbacks {completed:,}/{len(player_ids):,}; "
                    f"failed={len(failures):,}",
                    flush=True,
                )

    team_root = raw_dir / "understat" / "teams"
    team_root.mkdir(parents=True, exist_ok=True)
    for season in missing_team_seasons:
        path = team_root / f"{season}.json"
        if path.exists() and path.stat().st_size and not force:
            continue
        payload = None
        last_error = None
        for attempt in range(3):
            try:
                with make_bounded_client() as client:
                    payload = client.league(league="EPL").get_team_data(
                        season=season.split("-")[0]
                    )
                if not payload:
                    raise ValueError("empty team payload")
                break
            except Exception as exc:
                last_error = str(exc)
                time.sleep(2 ** attempt)
        if payload:
            path.write_text(
                json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        else:
            failures.append(f"teams:{season}:{last_error or 'unknown error'}")

    if failures and not allow_missing:
        raise RuntimeError(
            f"Understat could not resolve {len(failures)} sources: {failures[:10]}"
        )
    if failures:
        print(f"  WARNING: {len(failures)} Understat fallbacks remain missing", flush=True)


def download_and_merge_pinned_understat_player_histories(
    raw_dir: Path,
    seasons: list[str],
    sources,
    *,
    workers: int = 10,
) -> dict:
    """Merge Vaastav's separate per-season Understat player CSVs by stable ID.

    The pinned Dastan downloader selects only the latest CSV per player. That
    discards earlier seasons and causes avoidable live Understat API fallbacks.
    Assemble every available pinned season before requesting missing histories.
    """
    wanted_ids = sources._needed_understat_ids(raw_dir, seasons)
    season_set = set(seasons)
    pattern = re.compile(r"^data/(20\d\d-\d\d)/understat/.+_(\d+)\.csv$")
    selected: dict[int, list[tuple[str, str]]] = {}
    for source_path in sources._tree(raw_dir, force=False):
        match = pattern.match(source_path)
        if not match:
            continue
        season, raw_player_id = match.groups()
        player_id = int(raw_player_id)
        if season in season_set and player_id in wanted_ids:
            selected.setdefault(player_id, []).append((season, source_path))

    staging = raw_dir / "vaastav" / "understat" / "player_seasons"
    jobs = []
    destinations: dict[int, list[Path]] = {}
    for player_id, entries in sorted(selected.items()):
        for season, source_path in sorted(entries):
            destination = staging / season / Path(source_path).name
            destinations.setdefault(player_id, []).append(destination)
            jobs.append((sources.VAASTAV_RAW + source_path, destination))
    if jobs:
        sources._download_many(jobs, workers=workers, force=False)

    output_root = raw_dir / "vaastav" / "understat" / "players"
    output_root.mkdir(parents=True, exist_ok=True)
    merged_players = merged_rows = 0
    for player_id, paths in sorted(destinations.items()):
        frames = [pd.read_csv(path, low_memory=False) for path in paths]
        frames = [frame for frame in frames if not frame.empty]
        if not frames:
            continue
        combined = pd.concat(frames, ignore_index=True, sort=False)
        if "id" in combined.columns:
            combined = combined.drop_duplicates("id", keep="last")
        else:
            keys = [column for column in ("date", "h_team", "a_team") if column in combined]
            if not keys:
                raise ValueError(f"Understat player {player_id} has no stable match key")
            combined = combined.drop_duplicates(keys, keep="last")
        if "date" in combined.columns:
            combined = combined.sort_values("date", kind="mergesort")
        combined.to_csv(output_root / f"{player_id}.csv", index=False, lineterminator="\\n")
        merged_players += 1
        merged_rows += len(combined)

    report = {
        "pinned_player_ids_selected": len(selected),
        "pinned_player_ids_merged": merged_players,
        "pinned_season_files_downloaded": len(jobs),
        "pinned_player_match_rows": merged_rows,
        "season_scope": sorted(season_set),
        "policy": "merge all pinned per-season player histories before live fallback",
    }
    print(
        "  merged pinned Understat histories: "
        f"{merged_players:,} players, {len(jobs):,} season files, "
        f"{merged_rows:,} match rows",
        flush=True,
    )
    return report


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


def prepare(dastan_root: Path, raw_dir: Path, output_dir: Path, source_commit: str,
            workers: int = 10) -> dict:
    sys.path.insert(0, str(dastan_root))
    from dastan import data as dastan_data
    from dastan import mappings
    from dastan.rebuild import sources, features as dastan_features
    from dastan.rebuild.features import build_feature_frame
    from dastan.rebuild.fplcache import build_predeadline_artifacts

    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir = output_dir / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
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
    # Defer player API fallback until all season-specific pinned histories
    # have been assembled. The upstream downloader selects only each player's
    # latest season file, which otherwise causes needless per-player API calls.
    def defer_player_fallbacks(raw_dir, missing_players, missing_team_seasons, *,
                               force, allow_missing):
        return parallel_understat_fallbacks(
            raw_dir, [], missing_team_seasons,
            force=force, allow_missing=allow_missing, workers=min(workers, 4),
        )

    sources._fetch_understat_fallbacks = defer_player_fallbacks
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
    # Keep the deliberate two-phase strategy: Dastan's first pass downloads
    # pinned historical files and only fills missing team seasons. Player API
    # fallbacks are deferred until all season-specific pinned player histories
    # have been merged, avoiding unnecessary per-player API requests.
    sources._fetch_understat_fallbacks = defer_player_fallbacks
    print(
        f"Downloading pinned Dastan historical inputs for {historical_seasons}; "
        f"live season {season} will be refreshed separately",
        flush=True,
    )
    sources.download_sources(
        raw_dir, historical_seasons, workers=workers, force=False,
        allow_missing_understat=False,
    )
    pinned_understat_report = download_and_merge_pinned_understat_player_histories(
        raw_dir, seasons, sources, workers=workers,
    )
    download_fixture_schedules(raw_dir, seasons, source_commit)

    current_api_report = refresh_current_core(raw_dir, season, bootstrap, fixtures, workers=workers)
    write_live_fixture_schedule(raw_dir, season, fixtures)
    fixture_archive_audits = audit_all_fixture_archives(raw_dir, seasons)
    normalization_reports = normalize_all_fpl_archives(raw_dir, output_dir, seasons)
    team_paths = {
        value: list((raw_dir / "vaastav" / "understat" / "teams" / value).glob("*.csv"))
        for value in seasons
    }
    wanted_ids = sources._needed_understat_ids(raw_dir, seasons)
    # Historical seasons are supplied by the pinned, merged archives. Their
    # residual Understat gaps are retained as missing values and handled by
    # Dastan's documented feature-builder NaN -> 0 policy; do not issue hundreds
    # of duplicate live API requests to backfill old seasons. Only current-season
    # appearances need a live Understat refresh.
    incomplete_players = sources._incomplete_pinned_players(raw_dir, [season], wanted_ids)
    missing_team_seasons = sources._incomplete_team_seasons(raw_dir, [season], team_paths)
    sources._fetch_understat_fallbacks(
        raw_dir, sorted(incomplete_players), missing_team_seasons,
        force=False, allow_missing=False,
    )
    manifest_path = sources.write_download_manifest(raw_dir, seasons)
    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
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

    print("Building canonical player/team match tables", flush=True)
    player_matches, team_matches, player_lookup = sources.build_canonical_matches(raw_dir, seasons)
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

    print("Building historical CTA points-model training frame", flush=True)
    historical_players = player_matches[player_matches["season"].isin(dastan_data.SEASONS)].copy()
    historical_teams = team_matches[team_matches["season"].isin(dastan_data.SEASONS)].copy()
    training_dir = output_dir / "training"
    training_dir.mkdir(parents=True, exist_ok=True)
    historical_frame = build_feature_frame(historical_players, historical_teams)
    historical_frame.to_parquet(training_dir / "features.parquet", index=False)
    build_predeadline_artifacts(raw_dir, training_dir, list(dastan_data.SEASONS))
    historical_snapshot_buffer_report = apply_historical_snapshot_safety_buffer(training_dir, minutes=5)
    training_frame = dastan_data.load(check_rows=False, data_dir=training_dir)
    training_frame.to_parquet(training_dir / "features_with_snapshots.parquet", index=False)

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
        "status": "PASS_SOURCE_AND_CANONICAL_PREPARATION",
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
        "historical_snapshot_safety_buffer": historical_snapshot_buffer_report,
        "fixture_archive_audits": fixture_archive_audits,
        "normalization_reports": normalization_reports,
        "pinned_understat_player_history_merge": pinned_understat_report,
        "canonical_player_match_rows": len(player_matches),
        "canonical_team_match_rows": len(team_matches),
        "historical_training_rows": len(training_frame),
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
            "historical_training_frame": {"path": str(training_dir / "features_with_snapshots.parquet"), "sha256": sha256(training_dir / "features_with_snapshots.parquet")},
        },
        "important_boundaries": [
            "Dastan expected-points heads are not loaded or used.",
            "Historical point-in-time snapshot artifacts are rebuilt from the pinned fplcache commit.",
            "Current next-GW snapshot values come only from the live official bootstrap; later target GWs receive -1 snapshot sentinels.",
            "The active-season match archive is refreshed from official FPL element-summary history.",
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
