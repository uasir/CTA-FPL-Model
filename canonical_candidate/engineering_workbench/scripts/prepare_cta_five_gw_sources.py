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
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
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
    for player in bootstrap.get("elements", []):
        position = POSITIONS.get(int(player.get("element_type", 0)))
        if not position:
            continue
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
        for future in as_completed(futures):
            try:
                element, payload = future.result()
                history_payloads[element] = payload
            except Exception as exc:
                failures.append(str(exc))
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
    pd.DataFrame(rows).to_csv(path, index=False, lineterminator="\\n")
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
    season = season_from_bootstrap(bootstrap)
    next_events = [int(event["id"]) for event in bootstrap.get("events", []) if event.get("is_next")]
    if len(next_events) != 1:
        raise RuntimeError(f"Expected one next FPL gameweek, got {next_events}")
    first_gw = next_events[0]
    target_gameweeks = list(range(first_gw, first_gw + 5))
    if any(not any(int(event["id"]) == gw for event in bootstrap["events"]) for gw in target_gameweeks):
        raise RuntimeError("FPL season does not have five remaining consecutive gameweeks")
    bootstrap_path = snapshot_dir / "bootstrap-static.json"
    fixtures_path = snapshot_dir / "fixtures.json"
    bootstrap_path.write_text(json.dumps(bootstrap, indent=2) + "\n", encoding="utf-8")
    fixtures_path.write_text(json.dumps(fixtures, indent=2) + "\n", encoding="utf-8")

    roster_path = write_current_roster(dastan_root, bootstrap, season)
    patch_identity_resolution(mappings, sources)
    operational_clubs = mappings.load_operational_clubs()
    dastan_features.FPL_TO_UNDERSTAT.update({
        str(row["club_name"]): str(row["understat_name"])
        for row in operational_clubs.to_dict("records")
        if row.get("understat_name")
    })
    sources.VAASTAV_COMMIT = source_commit
    sources.VAASTAV_RAW = f"https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/{source_commit}/"
    sources.VAASTAV_TREE = f"https://api.github.com/repos/vaastav/Fantasy-Premier-League/git/trees/{source_commit}?recursive=1"

    seasons = list(dastan_data.SEASONS) + [season]
    if season in dastan_data.SEASONS:
        raise RuntimeError(f"Live FPL season {season} overlaps Dastan's completed training seasons")
    print(f"Downloading pinned source inputs for {seasons}", flush=True)
    sources.download_sources(raw_dir, seasons, workers=workers, force=False, allow_missing_understat=False)
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
    incomplete_players = sources._incomplete_pinned_players(raw_dir, seasons, wanted_ids)
    missing_team_seasons = sources._incomplete_team_seasons(raw_dir, seasons, team_paths)
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
    safe_mapping.to_csv(safe_mapping_path, index=False, lineterminator="\\n")
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
        "fixture_archive_audits": fixture_archive_audits,
        "normalization_reports": normalization_reports,
        "canonical_player_match_rows": len(player_matches),
        "canonical_team_match_rows": len(team_matches),
        "historical_training_rows": len(training_frame),
        "training_features": len(json.loads((dastan_root / "models" / "feature_cols.json").read_text(encoding="utf-8"))),
        "mapping": mapping_report,
        "artifacts": {
            "bootstrap": {"path": str(bootstrap_path), "sha256": sha256(bootstrap_path)},
            "fixtures": {"path": str(fixtures_path), "sha256": sha256(fixtures_path)},
            "canonical_player_matches": {"path": str(player_matches_path), "sha256": sha256(player_matches_path)},
            "canonical_team_matches": {"path": str(team_matches_path), "sha256": sha256(team_matches_path)},
            "safe_current_player_mapping": {"path": str(safe_mapping_path), "sha256": sha256(safe_mapping_path)},
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
