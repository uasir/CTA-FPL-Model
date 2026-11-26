"""Build isolated point-in-time 286-feature target candidates for the defensive experiment.

Each target Gameweek uses the latest Vaastav repository commit available before its
official deadline and the matching archived FPL pre-deadline snapshot. Historical
seasons are included for player/team history. Target labels are never loaded here.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from build_2pm_active_target_queries import (
    KEY,
    MARKET_FIELDS,
    attach_snapshot_features,
    build_fixture_player_rows,
    build_future_fixture_schedule_rows,
)
from build_2pm_predeadline_market_snapshot import build_market_artifact
from rebuild_2pm_dastan_286_candidate import (
    attach_match_availability_bounds,
    attach_official_deadlines,
    load_dastan_package,
    sha256,
    validate_reconstruction_coverage,
)
from rebuild_2pm_fixture_context import (
    rebuild_deadline_team_context,
    rebuild_fixture_context,
    rebuild_player_history_features,
)

VAASTAV_REPO = "vaastav/Fantasy-Premier-League"
FPLCACHE_REPO = "Randdalf/fplcache"

MERGED_GW_SCHEMA_NORMALIZATION_LOG: list[dict[str, Any]] = []
CSV_PARSER_INSTALLED = False
POSITION_VALUES = {"GK", "GKP", "DEF", "MID", "FWD"}


def read_merged_gw_with_schema_normalization(path: Path) -> pd.DataFrame:
    """Normalize Vaastav's mixed merged/per-GW CSV schema without imputing values."""
    rows: list[list[str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            base_header = next(reader)
        except StopIteration:
            raise ValueError(f"Empty merged_gw.csv: {path}")
        if len(base_header) != len(set(base_header)):
            raise ValueError(f"Duplicate merged_gw.csv headers: {path}")
        for line_number, row in enumerate(reader, start=2):
            if row:
                rows.append(row)

    widths = sorted({len(row) for row in rows})
    base_width = len(base_header)
    mng_columns = [
        "mng_clean_sheets", "mng_draw", "mng_goals_scored", "mng_loss",
        "mng_underdog_draw", "mng_underdog_win", "mng_win",
    ]
    has_mng_header = all(column in base_header for column in mng_columns)
    minutes_index = base_header.index("minutes") if "minutes" in base_header else -1

    # Vaastav's merged file can concatenate weekly exports with a later schema:
    # seven manager-result columns were inserted immediately after minutes in
    # per-GW exports, while the merged file retained its original first header.
    mixed_manager_schema = (
        not has_mng_header and minutes_index >= 0
        and widths in ([base_width, base_width + len(mng_columns)], [base_width + len(mng_columns)])
    )
    if mixed_manager_schema:
        normalized_header = (
            base_header[:minutes_index + 1]
            + mng_columns
            + base_header[minutes_index + 1:]
        )
        normalized_rows = []
        for row in rows:
            if len(row) == base_width:
                normalized_rows.append(
                    row[:minutes_index + 1]
                    + [""] * len(mng_columns)
                    + row[minutes_index + 1:]
                )
            elif len(row) == base_width + len(mng_columns):
                normalized_rows.append(row)
            else:
                raise ValueError(f"Unexpected merged_gw row width at {path}: {len(row)}")
        MERGED_GW_SCHEMA_NORMALIZATION_LOG.append({
            "path": path.as_posix(),
            "schema_normalization": "unioned seven manager-result columns inserted after minutes",
            "base_header_fields": base_width,
            "normalized_header_fields": len(normalized_header),
            "rows_with_manager_columns": sum(len(row) == base_width + len(mng_columns) for row in rows),
            "rows_without_manager_columns_preserved_as_missing": sum(len(row) == base_width for row in rows),
            "missing_values_policy": "blank/NaN; no zero fill",
        })
    else:
        if widths and widths != [base_width]:
            raise ValueError(
                f"Unrecognized merged_gw schema widths at {path}: "
                f"header={base_width}, row_widths={widths}"
            )
        normalized_header = base_header
        normalized_rows = rows

    frame = pd.DataFrame(normalized_rows, columns=normalized_header)
    text_columns = {"name", "position", "team", "kickoff_time", "modified", "was_home"}
    for column in frame.columns:
        if column not in text_columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for boolean_column in ("was_home", "modified"):
        if boolean_column in frame:
            frame[boolean_column] = (
                frame[boolean_column].astype(str).str.strip().str.lower()
                .map({"true": True, "false": False, "1": True, "0": False})
            )
    return frame


def install_merged_gw_csv_parser() -> None:
    """Use the strict parser for Vaastav merged_gw.csv reads in this process."""
    global CSV_PARSER_INSTALLED
    if CSV_PARSER_INSTALLED:
        return
    original_read_csv = pd.read_csv

    def patched_read_csv(filepath_or_buffer, *args, **kwargs):
        source_path = (
            filepath_or_buffer
            if isinstance(filepath_or_buffer, (str, Path))
            else getattr(filepath_or_buffer, "name", filepath_or_buffer)
        )
        if "merged_gw.csv" in str(source_path):
            frame = read_merged_gw_with_schema_normalization(Path(source_path))
            usecols = kwargs.get("usecols")
            if usecols is not None:
                if callable(usecols):
                    selected = [column for column in frame.columns if usecols(column)]
                else:
                    selected = list(usecols)
                frame = frame[selected]
            nrows = kwargs.get("nrows")
            if nrows is not None:
                frame = frame.head(int(nrows))
            return frame
        return original_read_csv(filepath_or_buffer, *args, **kwargs)

    pd.read_csv = patched_read_csv
HISTORY_SEASONS = {
    "2025-26": ["2024-25", "2025-26"],
    "2026-27": ["2025-26", "2026-27"],
}


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _configure_source_pins(sources, fplcache, vaastav_commit: str, fplcache_commit: str) -> None:
    sources.VAASTAV_COMMIT = vaastav_commit
    sources.VAASTAV_RAW = (
        f"https://raw.githubusercontent.com/{VAASTAV_REPO}/{vaastav_commit}/"
    )
    sources.VAASTAV_TREE = (
        f"https://api.github.com/repos/{VAASTAV_REPO}/git/trees/{vaastav_commit}?recursive=1"
    )
    fplcache.FPLCACHE_COMMIT = fplcache_commit
    fplcache.TREE_URL = (
        f"https://api.github.com/repos/{FPLCACHE_REPO}/git/trees/{fplcache_commit}?recursive=1"
    )
    fplcache.RAW_URL = (
        f"https://raw.githubusercontent.com/{FPLCACHE_REPO}/{fplcache_commit}/"
    )


def _patch_deadlines(fplcache, vintage_report: dict[str, Any]) -> None:
    original = fplcache.season_deadlines
    overrides: dict[str, dict[int, datetime]] = {}
    for season, season_report in vintage_report["seasons"].items():
        overrides[season] = {}
        for gw, value in season_report["gameweeks"].items():
            snapshot = value.get("snapshot", {})
            deadline = snapshot.get("deadline")
            if deadline:
                overrides[season][int(gw)] = _parse_datetime(deadline)

    def season_deadlines(raw_dir, index, season):
        if str(season) in overrides and overrides[str(season)]:
            return overrides[str(season)]
        return original(raw_dir, index, season)

    fplcache.season_deadlines = season_deadlines


def _ensure_shared_fplcache(raw_dir: Path, shared_cache: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    shared_cache.mkdir(parents=True, exist_ok=True)
    link = raw_dir / "fplcache"
    if link.exists() or link.is_symlink():
        if link.is_symlink() and link.resolve() == shared_cache.resolve():
            return
        raise RuntimeError(f"Unexpected existing fplcache cache path: {link}")
    link.symlink_to(shared_cache.resolve(), target_is_directory=True)


def _source_status(source_commit: str, fplcache_commit: str, snapshot_path: str) -> str:
    return (
        f"POINT_IN_TIME_VAASTAV_{source_commit}"
        f"|FPLCACHE_{fplcache_commit}"
        f"|SNAPSHOT_{Path(snapshot_path).name}"
    )


def build_point_in_time_target_candidate(
    *,
    dastan_root: Path,
    raw_dir: Path,
    output_dir: Path,
    shared_fplcache: Path,
    vintage_report: dict[str, Any],
    season: str,
    gameweek: int,
    workers: int = 12,
    prepare_sources_only: bool = False,
) -> dict[str, Any]:
    MERGED_GW_SCHEMA_NORMALIZATION_LOG.clear()
    season_report = vintage_report["seasons"][season]
    gw_report = season_report["gameweeks"][str(gameweek)]
    source_report = gw_report.get("source", {})
    snapshot_report = gw_report.get("snapshot", {})
    source_commit = source_report.get("source_commit")
    if not source_commit:
        raise ValueError(f"No pre-deadline Vaastav source commit for {season} GW{gameweek}")
    if snapshot_report.get("status") != "selected":
        raise ValueError(f"No accepted pre-deadline FPL snapshot for {season} GW{gameweek}")
    if not snapshot_report.get("is_next"):
        raise ValueError(f"Selected FPL snapshot does not mark {season} GW{gameweek} as is_next")

    deadline = _parse_datetime(snapshot_report["deadline"])
    captured_at = _parse_datetime(snapshot_report["captured_at"])
    snapshot_age_hours = (deadline - captured_at).total_seconds() / 3600.0
    if snapshot_age_hours < (5 / 60) or snapshot_age_hours > 30:
        raise ValueError(f"FPL snapshot age outside 5m–30h window: {snapshot_age_hours:.2f}h")

    history_seasons = HISTORY_SEASONS[season]
    if history_seasons[-1] != season:
        raise RuntimeError("History season configuration must end with the target season")

    data, mappings, features, fplcache, sources = load_dastan_package(dastan_root)
    fplcache_commit = season_report["fplcache_commit"]
    _configure_source_pins(sources, fplcache, source_commit, fplcache_commit)
    _patch_deadlines(fplcache, vintage_report)
    install_merged_gw_csv_parser()
    _ensure_shared_fplcache(raw_dir, shared_fplcache)

    registry = json.loads((data.DATA / "season_registry.json").read_text())
    if season in set(map(str, registry["completed_seasons"])):
        # Historical target query is intentional on this isolated research branch.
        pass
    else:
        mappings.assert_operational_clubs_ready(season)

    raw_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    all_seasons = history_seasons

    print(
        f"Downloading {all_seasons} from Vaastav commit {source_commit}",
        flush=True,
    )
    sources.download_sources(raw_dir, all_seasons, workers=workers, force=False)

    # Resolve and persist the exact pre-deadline FPL snapshot before expensive
    # feature reconstruction. This makes both Vaastav/Understat and FPL-cache
    # downloads checkpointable as a separate workflow stage.
    index = fplcache.load_index(raw_dir)
    selected_snapshot = fplcache.pick_snapshot(index, deadline)
    if selected_snapshot is None:
        raise RuntimeError("No FPL cache snapshot exists before the target deadline")
    selected_at, snapshot_path = selected_snapshot
    if selected_at != captured_at:
        raise RuntimeError(
            "FPL snapshot selection differs from the audited vintage: "
            f"expected {captured_at.isoformat()}, got {selected_at.isoformat()}"
        )
    payload = fplcache.fetch_snapshot(raw_dir, snapshot_path)
    if not fplcache._accepted_event(payload, int(gameweek), deadline):
        raise RuntimeError("Selected FPL snapshot fails the target is_next/deadline check")

    if prepare_sources_only:
        preparation = {
            "status": "POINT_IN_TIME_SOURCE_PREPARATION_COMPLETE",
            "season": season,
            "gameweek": int(gameweek),
            "history_seasons": all_seasons,
            "vaastav_source_commit": source_commit,
            "fplcache_commit": fplcache_commit,
            "target_snapshot_at": captured_at.isoformat(),
            "target_snapshot_path": snapshot_path,
            "download_manifest": str(raw_dir / "downloads.json"),
            "candidate_reconstruction_started": False,
            "labels_loaded": False,
            "target_points_loaded": False,
        }
        (output_dir / "source_preparation_report.json").write_text(
            json.dumps(preparation, indent=2) + "\\n", encoding="utf-8"
        )
        return preparation

    player_matches, team_matches, _ = sources.build_canonical_matches(raw_dir, all_seasons)

    print("Building pre-deadline FPL artifacts", flush=True)
    fplcache.build_predeadline_artifacts(raw_dir, output_dir, all_seasons)
    ep_safety = __import__(
        "rebuild_2pm_dastan_286_candidate", fromlist=["enforce_snapshot_safety_buffer"]
    ).enforce_snapshot_safety_buffer(
        output_dir / "pre_deadline_ep_next.parquet", minutes=5
    )
    signal_safety = __import__(
        "rebuild_2pm_dastan_286_candidate", fromlist=["enforce_snapshot_safety_buffer"]
    ).enforce_snapshot_safety_buffer(
        output_dir / "pre_deadline_signals.parquet", minutes=5
    )
    market_path, market_report = build_market_artifact(
        raw_dir, output_dir, all_seasons, fplcache, safety_buffer_minutes=5
    )
    if market_path.name != "pre_deadline_market.parquet":
        raise RuntimeError("Unexpected market artifact path")

    print("Rebuilding point-in-time historical feature frame", flush=True)
    history = features.build_feature_frame(player_matches, team_matches)
    history = attach_official_deadlines(history, raw_dir, fplcache, all_seasons)
    history = attach_match_availability_bounds(history, raw_dir, sources, all_seasons)
    history["feature_cutoff_time"] = history["deadline_time"]
    vintage_status = _source_status(source_commit, fplcache_commit, snapshot_path)
    history["source_vintage_status"] = vintage_status
    history, history_snapshot_report = attach_snapshot_features(history, output_dir)

    fixture_path = raw_dir / "vaastav" / season / "fixtures.csv"
    teams_path = raw_dir / "vaastav" / season / "teams.csv"
    if not fixture_path.exists() or not teams_path.exists():
        raise FileNotFoundError("Selected pre-deadline source commit lacks fixtures.csv or teams.csv")
    fixtures = pd.read_csv(fixture_path)
    teams = pd.read_csv(teams_path)
    assignments = mappings.assignments_for_seasons(all_seasons)

    # The target schedule and roster are both frozen at the target deadline.
    # Setting now to deadline-5m is valid because this source commit predates
    # the deadline; the fixture helper still rejects a finished/started fixture.
    query_now = pd.Timestamp(deadline - pd.Timedelta(minutes=5))
    target_fixture_rows = build_fixture_player_rows(
        fixtures,
        payload.get("elements", []),
        teams,
        assignments,
        season=season,
        gameweek=int(gameweek),
        deadline=pd.Timestamp(deadline),
        now=query_now,
        features_module=features,
    )

    query_parts = []
    for fixture_id, fixture_players in target_fixture_rows.groupby("fixture", sort=True):
        print(f"Building {season} GW{gameweek} fixture query {fixture_id}", flush=True)
        combined = pd.concat([player_matches, fixture_players], ignore_index=True, sort=False)
        feature_frame = features.build_feature_frame(combined, team_matches)
        query = feature_frame[
            feature_frame["fixture"].astype(int).eq(int(fixture_id))
            & feature_frame["gameweek"].astype(int).eq(int(gameweek))
        ].copy()
        query = attach_official_deadlines(query, raw_dir, fplcache, all_seasons)
        query = attach_match_availability_bounds(query, raw_dir, sources, all_seasons)
        query["feature_cutoff_time"] = query["deadline_time"]
        query["source_vintage_status"] = vintage_status
        query["target_points"] = np.nan
        query, _ = attach_snapshot_features(query, output_dir)
        query_parts.append(query)

    queries = pd.concat(query_parts, ignore_index=True)
    if queries.duplicated(["season", "gameweek", "fixture", "fpl_code"]).any():
        raise RuntimeError("Point-in-time target queries contain duplicate player-fixture keys")
    queries["row_role"] = "TARGET_QUERY"
    history["row_role"] = "HISTORICAL_FIXTURE"

    ordered_features = data.shipped_features(history)
    if len(ordered_features) != 286:
        raise RuntimeError(f"Expected 286 model features, got {len(ordered_features)}")

    source_player_matches = pd.concat(
        [player_matches, target_fixture_rows], ignore_index=True, sort=False
    )
    source_player_matches = attach_match_availability_bounds(
        source_player_matches, raw_dir, sources, all_seasons
    )
    schedule_rows = build_future_fixture_schedule_rows(
        fixtures, teams, season=season, now=query_now
    )
    if not schedule_rows.empty:
        source_player_matches = pd.concat(
            [source_player_matches, schedule_rows], ignore_index=True, sort=False
        )

    combined = pd.concat([history, queries], ignore_index=True, sort=False)
    for key_frame in (combined, source_player_matches):
        key_frame["season"] = key_frame["season"].astype(str)
        key_frame["fixture"] = key_frame["fixture"].astype(str)
        key_frame["fpl_code"] = pd.to_numeric(
            key_frame["fpl_code"], errors="coerce"
        ).astype("Int64")

    combined, player_history_report = rebuild_player_history_features(
        combined, source_player_matches, features
    )
    combined, team_context_report = rebuild_deadline_team_context(
        combined, team_matches, features
    )
    combined, fixture_context_report = rebuild_fixture_context(
        combined, source_player_matches
    )
    reconstruction_coverage = validate_reconstruction_coverage(
        ordered_features,
        player_history_report,
        team_context_report,
        fixture_context_report,
        combined,
    )

    metadata = [
        "season", "gameweek", "fixture", "fpl_code", "position", "team_name",
        "opponent_team_name", "kickoff_time", "deadline_time", "feature_cutoff_time",
        "match_available_at", "completion_time_quality", "source_vintage_status",
        "minutes", "target_points", "ep_next_snapshot_at", "signals_snapshot_at",
        "market_snapshot_at", "row_role",
    ]
    absent = [column for column in metadata + ordered_features if column not in combined]
    if absent:
        raise RuntimeError(f"Point-in-time candidate missing required columns: {absent[:20]}")
    candidate = combined[metadata + ordered_features].copy()
    candidate["fixture_id"] = candidate["fixture"].astype(str)
    candidate["admission_status"] = "NOT_ADMITTED"
    candidate["feature_order_sha256"] = hashlib.sha256(
        "\n".join(ordered_features).encode()
    ).hexdigest()

    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = output_dir / f"point_in_time_{season}_gw{gameweek}_candidate.parquet"
    history_path = output_dir / "historical_context.parquet"
    target_path = output_dir / "target_queries.parquet"
    player_matches_path = output_dir / "player_matches_with_availability.parquet"
    team_matches_path = output_dir / "team_matches.parquet"
    candidate.to_parquet(candidate_path, index=False)
    candidate[candidate["row_role"].eq("HISTORICAL_FIXTURE")].to_parquet(
        history_path, index=False
    )
    candidate[candidate["row_role"].eq("TARGET_QUERY")].to_parquet(
        target_path, index=False
    )
    source_player_matches.to_parquet(player_matches_path, index=False)
    team_matches.to_parquet(team_matches_path, index=False)
    sources.write_download_manifest(raw_dir, all_seasons)

    report = {
        "status": "POINT_IN_TIME_TARGET_CANDIDATE_BUILT",
        "admission_status": "NOT_ADMITTED",
        "training_authorized": False,
        "season": season,
        "gameweek": int(gameweek),
        "history_seasons": all_seasons,
        "deadline_time": deadline.isoformat(),
        "vaastav_source_commit": source_commit,
        "fplcache_commit": fplcache_commit,
        "target_snapshot_at": captured_at.isoformat(),
        "target_snapshot_age_hours": round(snapshot_age_hours, 4),
        "target_snapshot_path": snapshot_path,
        "source_vintage_status": vintage_status,
        "merged_gw_csv_schema_normalization": {
            "count": len(MERGED_GW_SCHEMA_NORMALIZATION_LOG),
            "rows": MERGED_GW_SCHEMA_NORMALIZATION_LOG[-50:],
            "policy": "only repaired unquoted leading name fragments when a unique position token and required identity/time fields validate; no rows dropped or silently discarded",
        },
        "historical_player_fixture_rows": int(len(history)),
        "target_query_player_fixture_rows": int(len(queries)),
        "target_fixture_count": int(queries["fixture"].nunique()),
        "feature_count": len(ordered_features),
        "feature_order_sha256": candidate["feature_order_sha256"].iat[0],
        "reconstruction_coverage": reconstruction_coverage,
        "player_history_reconstruction": player_history_report,
        "deadline_team_context_reconstruction": team_context_report,
        "fixture_context_reconstruction": fixture_context_report,
        "future_fixture_schedule_rows": int(len(schedule_rows)),
        "snapshot_coverage": {
            "history": history_snapshot_report,
            "target": {
                "ep_next_rows": int(queries["ep_next_snapshot_at"].notna().sum()),
                "signals_rows": int(queries["signals_snapshot_at"].notna().sum()),
                "market_rows": int(queries["market_snapshot_at"].notna().sum()),
            },
        },
        "snapshot_safety_buffer": {
            "ep_next": ep_safety,
            "signals": signal_safety,
            "market": market_report.get("safety_buffer"),
        },
        "identity_mapping_coverage": {
            "target_players": int(queries["fpl_code"].nunique()),
            "understat_mapped_players": int(
                queries.loc[queries["understat_id"].notna(), "fpl_code"].nunique()
            ),
        },
        "artifacts": {
            "candidate": candidate_path.name,
            "history": history_path.name,
            "target_queries": target_path.name,
            "player_matches": player_matches_path.name,
            "team_matches": team_matches_path.name,
        },
        "labels_loaded": False,
        "target_points_loaded": False,
        "limitations": [
            "This candidate is built from the latest Vaastav repository commit before the target deadline, not the final season snapshot.",
            "No realized target-match statistics or target labels are loaded.",
            "Source-row coverage and value parity still require sample-level admission checks.",
            "This script does not train or evaluate the 2PM model.",
        ],
    }
    (output_dir / "point_in_time_candidate_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dastan-root", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--shared-fplcache-root", type=Path, required=True)
    parser.add_argument("--vintage-report", type=Path, required=True)
    parser.add_argument("--target", action="append", required=True, help="Target in SEASON:GW form")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument(
        "--prepare-sources-only", action="store_true",
        help="Download and validate pinned raw inputs, then exit before candidate reconstruction",
    )
    args = parser.parse_args()

    vintage_report = json.loads(args.vintage_report.read_text(encoding="utf-8"))
    reports = []
    for target in args.target:
        season, gw_text = target.split(":", 1)
        gameweek = int(gw_text)
        season_report = vintage_report["seasons"][season]
        gw_report = season_report["gameweeks"][str(gameweek)]
        source_commit = gw_report.get("source", {}).get("source_commit")
        if not source_commit:
            print(f"Skipping {season} GW{gameweek}: no pre-deadline source commit")
            continue
        fplcache_commit = season_report["fplcache_commit"]
        raw_dir = args.raw_root / season / f"gw{gameweek}" / source_commit
        output_dir = args.output_root / season / f"gw{gameweek}"
        shared_cache = args.shared_fplcache_root / fplcache_commit
        report = build_point_in_time_target_candidate(
            dastan_root=args.dastan_root,
            raw_dir=raw_dir,
            output_dir=output_dir,
            shared_fplcache=shared_cache,
            vintage_report=vintage_report,
            season=season,
            gameweek=gameweek,
            workers=args.workers,
            prepare_sources_only=args.prepare_sources_only,
        )
        reports.append(report)

    manifest = {
        "status": (
            "POINT_IN_TIME_SOURCE_PREPARATION_BATCH_COMPLETE"
            if args.prepare_sources_only
            else "POINT_IN_TIME_TARGET_CANDIDATE_BATCH_COMPLETE"
        ),
        "training_authorized": False,
        "targets_requested": args.target,
        "targets_built": [
            f"{item['season']}:{item['gameweek']}" for item in reports
        ],
        "reports": reports,
    }
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "point_in_time_target_candidate_batch.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
