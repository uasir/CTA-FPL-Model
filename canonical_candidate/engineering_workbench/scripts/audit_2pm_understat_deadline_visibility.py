"""Reconcile Understat row/value histories to FPL fixtures and target deadlines.

This is a row-level visibility audit, not a feature-frame rebuild. Repository commit
timestamps are conservative repository-lineage evidence, not original Understat
publication timestamps. A source row is counted as deadline-eligible only when its
state is present before the five-minute cutoff and its canonical FPL match is more
than 24 hours before the target deadline.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from decimal import Decimal, InvalidOperation
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_2pm_point_in_time_source_vintages import (  # noqa: E402
    FPLCACHE_REPOSITORY,
    _parse_time,
    _probe_payload,
    _snapshot_for_deadline,
    _snapshot_index,
)

FPL_TO_UNDERSTAT = {
    "Man City": "Manchester City",
    "Man Utd": "Manchester United",
    "Newcastle": "Newcastle United",
    "Nott'm Forest": "Nottingham Forest",
    "Sheffield Utd": "Sheffield United",
    "Spurs": "Tottenham",
    "West Brom": "West Bromwich Albion",
    "Wolves": "Wolverhampton Wanderers",
}
SAFETY_BUFFER = timedelta(minutes=5)
MATCH_AVAILABILITY_HOURS = 24
DEFAULT_SEASONS = ("2020-21", "2021-22", "2022-23", "2023-24", "2024-25")


def _normalize_team(value: Any) -> str:
    raw = html.unescape(str(value or "")).strip()
    return FPL_TO_UNDERSTAT.get(raw, raw)


def _team_from_path(source_path: str) -> str:
    name = Path(source_path).stem.removeprefix("understat_").replace("_", " ")
    return _normalize_team(name)


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _fetch_pinned_csv(
    session: requests.Session,
    repository: str,
    commit: str,
    source_path: str,
    cache_root: Path,
) -> Path:
    local = cache_root / commit / source_path
    if local.is_file() and local.stat().st_size:
        return local
    url = f"https://raw.githubusercontent.com/{repository}/{commit}/{source_path}"
    response = session.get(url, headers={"Accept": "text/csv"}, timeout=90)
    response.raise_for_status()
    if not response.content:
        raise RuntimeError(f"Pinned source file is empty: {source_path}")
    _atomic_write(local, response.content)
    return local


def load_fixture_calendars(
    seasons: list[str],
    vaastav_commit: str,
    cache_root: Path,
) -> dict[str, pd.DataFrame]:
    session = requests.Session()
    calendars: dict[str, pd.DataFrame] = {}
    for season in seasons:
        fixtures_path = _fetch_pinned_csv(
            session, "vaastav/Fantasy-Premier-League", vaastav_commit,
            f"data/{season}/fixtures.csv", cache_root,
        )
        teams_path = _fetch_pinned_csv(
            session, "vaastav/Fantasy-Premier-League", vaastav_commit,
            f"data/{season}/teams.csv", cache_root,
        )
        fixtures = pd.read_csv(fixtures_path)
        teams = pd.read_csv(teams_path)
        required_fixtures = {"id", "event", "kickoff_time", "team_h", "team_a"}
        required_teams = {"id", "name"}
        if required_fixtures - set(fixtures.columns):
            raise ValueError(f"{season} fixtures.csv lacks {sorted(required_fixtures - set(fixtures.columns))}")
        if required_teams - set(teams.columns):
            raise ValueError(f"{season} teams.csv lacks {sorted(required_teams - set(teams.columns))}")
        names = {
            int(row.id): _normalize_team(row.name)
            for row in teams[["id", "name"]].itertuples(index=False)
        }
        fixtures["fixture_id"] = pd.to_numeric(fixtures["id"], errors="raise").astype(int)
        fixtures["event"] = pd.to_numeric(fixtures["event"], errors="coerce")
        fixtures["kickoff_time"] = pd.to_datetime(
            fixtures["kickoff_time"], utc=True, errors="coerce"
        )
        fixtures["home_team"] = fixtures["team_h"].map(
            lambda value: names.get(int(value), "") if pd.notna(value) else ""
        )
        fixtures["away_team"] = fixtures["team_a"].map(
            lambda value: names.get(int(value), "") if pd.notna(value) else ""
        )
        fixtures = fixtures.dropna(subset=["kickoff_time"]).copy()
        fixtures["season"] = season
        calendars[season] = fixtures[
            ["season", "fixture_id", "event", "kickoff_time", "home_team", "away_team"]
        ].reset_index(drop=True)
    return calendars


def load_deadline_calendars(
    seasons: list[str],
    fplcache_root: Path,
    fplcache_commit: str,
) -> dict[str, list[dict[str, Any]]]:
    token = os.environ.get("GITHUB_TOKEN")
    index = _snapshot_index(fplcache_root, fplcache_commit, token)
    snapshot_root = fplcache_root / "snapshots"
    result: dict[str, list[dict[str, Any]]] = {}
    for season in seasons:
        _, _, probe = _probe_payload(
            index, season, snapshot_root, fplcache_commit
        )
        events = [
            event for event in probe.get("events", [])
            if event.get("deadline_time")
        ]
        rows = []
        for event in sorted(events, key=lambda item: int(item["id"])):
            gameweek = int(event["id"])
            probe_deadline = _parse_time(event["deadline_time"])
            selected = _snapshot_for_deadline(
                index, season, gameweek, probe_deadline,
                snapshot_root, fplcache_commit,
            )
            verified = (
                selected.get("status") == "selected"
                and bool(selected.get("is_next"))
                and selected.get("deadline") is not None
            )
            deadline = selected["deadline"] if selected.get("status") == "selected" else probe_deadline
            rows.append({
                "season": season,
                "gameweek": gameweek,
                "deadline": deadline,
                "deadline_status": (
                    "pre_deadline_snapshot_verified" if verified
                    else selected.get("status", "deadline_unresolved")
                ),
                "deadline_verified": verified,
                "snapshot_at": selected.get("captured_at"),
                "snapshot_path": selected.get("path"),
                "probe_deadline": probe_deadline,
            })
        result[season] = rows
    return result


def _fixture_match(
    row: dict[str, Any],
    kind: str,
    source_path: str,
    calendars: dict[str, pd.DataFrame],
) -> tuple[dict[str, Any] | None, str]:
    parsed = pd.to_datetime(row.get("date"), errors="coerce")
    if pd.isna(parsed):
        return None, "invalid_source_date"
    source_date = parsed.date()
    if kind == "team":
        source_season = source_path.split("/")[1]
        candidate_seasons = [source_season] if source_season in calendars else []
    else:
        understat_season = str(row.get("season", "")).strip()
        try:
            start = int(float(understat_season))
            inferred = f"{start}-{str(start + 1)[-2:]}"
        except (ValueError, TypeError):
            inferred = ""
        candidate_seasons = [inferred] if inferred in calendars else list(calendars)
    candidates = []
    for season in candidate_seasons:
        frame = calendars[season]
        date_match = frame["kickoff_time"].dt.date.map(
            lambda value: abs((value - source_date).days) <= 1
        )
        subset = frame.loc[date_match]
        if kind == "player":
            home = _normalize_team(row.get("h_team"))
            away = _normalize_team(row.get("a_team"))
            subset = subset.loc[
                subset["home_team"].eq(home) & subset["away_team"].eq(away)
            ]
        else:
            team = _team_from_path(source_path)
            side = str(row.get("h_a", "")).strip().lower()
            if side == "h":
                subset = subset.loc[subset["home_team"].eq(team)]
            elif side == "a":
                subset = subset.loc[subset["away_team"].eq(team)]
            else:
                return None, "invalid_home_away"
        candidates.extend(subset.to_dict("records"))
    if len(candidates) == 1:
        return candidates[0], "matched"
    if len(candidates) > 1:
        return None, "ambiguous_fixture_match"
    return None, "unmatched_fixture"


def _metric_signature(signature: str | None) -> str | None:
    """Compare metric values numerically, not by CSV string formatting.

    Understat histories sometimes serialize the same numeric value as (for
    example) "0" and "0.0". Keep identity/metadata fields exact, while
    canonicalizing numeric metric cells so formatting-only revisions do not
    appear as deadline-vintage value changes.
    """
    if not signature:
        return None
    try:
        row = json.loads(signature)
    except (TypeError, ValueError):
        return None
    row.pop("date", None)
    for key, value in row.items():
        if key in {"id", "roster_id", "season"} or not isinstance(value, str):
            continue
        try:
            number = Decimal(value.strip())
        except (InvalidOperation, ValueError):
            continue
        if number.is_finite():
            row[key] = format(number.normalize(), "f")
    return json.dumps(row, sort_keys=True, separators=(",", ":"))


def _source_entity(kind: str, source_path: str, row_key: str) -> str:
    if kind == "player":
        player_id = Path(source_path).stem.rsplit("_", 1)[-1]
        return f"player:{player_id}"
    return f"team:{_team_from_path(source_path)}"


def _build_canonical_rows(
    history_report: dict[str, Any],
    calendars: dict[str, pd.DataFrame],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, int]]]:
    grouped: dict[str, dict[str, Any]] = {}
    mapping_stats: dict[str, dict[str, int]] = {}
    for file_result in history_report.get("results", []):
        source_path = file_result["source_path"]
        kind = "player" if file_result["source_kind"] == "pinned_player_csv" else "team"
        stats = mapping_stats.setdefault(source_path, {
            "rows_in_history": 0, "mapped_rows": 0,
            "unmatched_rows": 0, "ambiguous_rows": 0, "invalid_rows": 0,
        })
        for row_key, row_history in file_result.get("row_history", {}).items():
            stats["rows_in_history"] += 1
            base_signature = row_history.get("first_value_signature")
            try:
                base_row = json.loads(base_signature) if base_signature else {}
            except (TypeError, ValueError):
                base_row = {}
            fixture, status = _fixture_match(base_row, kind, source_path, calendars)
            if fixture is None:
                if status == "ambiguous_fixture_match":
                    stats["ambiguous_rows"] += 1
                elif status == "invalid_source_date":
                    stats["invalid_rows"] += 1
                else:
                    stats["unmatched_rows"] += 1
                continue
            stats["mapped_rows"] += 1
            entity = _source_entity(kind, source_path, row_key)
            canonical_id = f"{fixture['season']}|{entity}|{int(fixture['fixture_id'])}"
            item = grouped.setdefault(canonical_id, {
                "season": fixture["season"],
                "entity": entity,
                "source_kind": file_result["source_kind"],
                "source_path": source_path,
                "fixture_id": int(fixture["fixture_id"]),
                "fixture_event": (
                    int(fixture["event"]) if pd.notna(fixture["event"]) else None
                ),
                "kickoff_time": fixture["kickoff_time"].isoformat(),
                "home_team": fixture["home_team"],
                "away_team": fixture["away_team"],
                "source_row_keys": [],
                "events": [],
            })
            item["source_row_keys"].append(row_key)
            for event in row_history.get("state_events", []):
                signature = event.get("value_signature")
                if event.get("status") == "present" and signature:
                    try:
                        event_row = json.loads(signature)
                    except (TypeError, ValueError):
                        event_row = {}
                    event_fixture, event_status = _fixture_match(
                        event_row, kind, source_path, calendars
                    )
                    if event_fixture is None or int(event_fixture["fixture_id"]) != int(fixture["fixture_id"]):
                        stats["invalid_rows"] += 1
                        continue
                item["events"].append({
                    "commit": event.get("commit"),
                    "committed_at": event.get("committed_at"),
                    "status": event.get("status"),
                    "value_signature": signature,
                    "metric_signature": _metric_signature(signature),
                    "source_row_key": row_key,
                })
    for item in grouped.values():
        item["events"].sort(key=lambda event: (
            pd.to_datetime(event["committed_at"], utc=True),
            1 if event["status"] == "present" else 0,
        ))
        present = [event for event in item["events"] if event["status"] == "present"]
        item["final_metric_signature"] = present[-1]["metric_signature"] if present else None
        item["first_seen_at"] = present[0]["committed_at"] if present else None
        item["value_revision_events"] = sum(
            1 for previous, current in zip(present, present[1:])
            if previous["metric_signature"] != current["metric_signature"]
        )
        item["date_or_key_revision_events"] = max(
            0, len(item["source_row_keys"]) - 1
        )
    return grouped, mapping_stats


def _latest_state_before_deadline(
    events: list[dict[str, Any]], deadline: datetime
) -> dict[str, Any] | None:
    cutoff = deadline - SAFETY_BUFFER
    eligible = [
        event for event in events
        if pd.to_datetime(event["committed_at"], utc=True).to_pydatetime() < cutoff
    ]
    return eligible[-1] if eligible else None


def _state_visibility(
    item: dict[str, Any], deadline: datetime, state: dict[str, Any] | None
) -> dict[str, Any]:
    kickoff = pd.to_datetime(item["kickoff_time"], utc=True).to_pydatetime()
    match_available_at = kickoff + timedelta(hours=MATCH_AVAILABILITY_HOURS)
    if state is None:
        return {
            "status": "not_yet_in_repository", "source_commit_at": None,
            "source_commit": None, "source_row_key": None,
            "value_matches_final": None, "source_date": None,
        }
    signature = state["value_signature"]
    source_date = None
    if signature:
        try:
            source_date = json.loads(signature).get("date")
        except (TypeError, ValueError):
            source_date = None
    value_matches_final = (
        state["metric_signature"] == item["final_metric_signature"]
        if state["status"] == "present" and state["metric_signature"] is not None
        and item["final_metric_signature"] is not None else None
    )
    if state["status"] != "present":
        visibility = "source_row_missing"
    elif match_available_at >= deadline:
        visibility = "match_not_yet_available"
    else:
        visibility = "repository_proven_prior_row"
    return {
        "status": visibility,
        "source_commit_at": state["committed_at"],
        "source_commit": state["commit"],
        "source_row_key": state["source_row_key"],
        "value_matches_final": value_matches_final,
        "source_date": source_date,
    }


def _evaluate_deadline(
    item: dict[str, Any],
    deadline_row: dict[str, Any],
) -> dict[str, Any]:
    deadline = deadline_row["deadline"]
    kickoff = pd.to_datetime(item["kickoff_time"], utc=True).to_pydatetime()
    match_available_at = kickoff + timedelta(hours=MATCH_AVAILABILITY_HOURS)
    base = {
        "season": item["season"],
        "gameweek": deadline_row["gameweek"],
        "deadline": deadline.isoformat(),
        "deadline_status": deadline_row["deadline_status"],
        "deadline_verified": deadline_row["deadline_verified"],
        "entity": item["entity"],
        "source_kind": item["source_kind"],
        "source_path": item["source_path"],
        "fixture_id": item["fixture_id"],
        "fixture_event": item["fixture_event"],
        "kickoff_time": item["kickoff_time"],
        "match_available_at": match_available_at.isoformat(),
        "home_team": item["home_team"],
        "away_team": item["away_team"],
        "first_seen_at": item["first_seen_at"],
        "value_revision_events": item["value_revision_events"],
        "source_row_keys": ";".join(sorted(set(item["source_row_keys"]))),
    }
    state = _latest_state_before_deadline(item["events"], deadline)
    details = _state_visibility(item, deadline, state)
    if not deadline_row["deadline_verified"]:
        return base | {
            "visibility_status": "deadline_unverified",
            "source_commit_at": None,
            "source_commit": None,
            "source_row_key": None,
            "value_matches_final": None,
            "source_date": None,
            "provisional_visibility_status": details["status"],
            "provisional_source_commit_at": details["source_commit_at"],
            "provisional_source_commit": details["source_commit"],
            "provisional_source_row_key": details["source_row_key"],
            "provisional_value_matches_final": details["value_matches_final"],
            "provisional_source_date": details["source_date"],
        }
    return base | {
        "visibility_status": details["status"],
        "source_commit_at": details["source_commit_at"],
        "source_commit": details["source_commit"],
        "source_row_key": details["source_row_key"],
        "value_matches_final": details["value_matches_final"],
        "source_date": details["source_date"],
        "provisional_visibility_status": None,
        "provisional_source_commit_at": None,
        "provisional_source_commit": None,
        "provisional_source_row_key": None,
        "provisional_value_matches_final": None,
        "provisional_source_date": None,
    }

def audit_deadline_visibility(
    history_report: dict[str, Any],
    seasons: list[str],
    vaastav_commit: str,
    fplcache_commit: str,
    fixture_cache_root: Path,
    fplcache_root: Path,
) -> dict[str, Any]:
    calendars = load_fixture_calendars(seasons, vaastav_commit, fixture_cache_root)
    deadlines = load_deadline_calendars(seasons, fplcache_root, fplcache_commit)
    canonical_rows, mapping_stats = _build_canonical_rows(history_report, calendars)
    detail = []
    for item in canonical_rows.values():
        for deadline_row in deadlines.get(item["season"], []):
            detail.append(_evaluate_deadline(item, deadline_row))
    status_counts: dict[str, int] = defaultdict(int)
    for row in detail:
        status_counts[row["visibility_status"]] += 1
    correction_rows = []
    for file_result in history_report.get("results", []):
        source_path = file_result["source_path"]
        kind = "player" if file_result["source_kind"] == "pinned_player_csv" else "team"
        histories = file_result.get("row_history", {})
        for candidate in file_result.get("possible_date_corrections", []):
            mapped = []
            for key_name in ("old_row_key", "new_row_key"):
                row_history = histories.get(candidate[key_name], {})
                signature = row_history.get("first_value_signature")
                try:
                    source_row = json.loads(signature) if signature else {}
                except (TypeError, ValueError):
                    source_row = {}
                fixture, status = _fixture_match(source_row, kind, source_path, calendars)
                mapped.append((fixture, status))
            same_fixture = (
                mapped[0][0] is not None and mapped[1][0] is not None
                and int(mapped[0][0]["fixture_id"]) == int(mapped[1][0]["fixture_id"])
            )
            fixture = mapped[0][0] if same_fixture else None
            correction_rows.append({
                "source_path": source_path,
                **candidate,
                "fixture_mapping_status": (
                    "same_canonical_fixture" if same_fixture
                    else f"{mapped[0][1]}|{mapped[1][1]}"
                ),
                "fixture_id": int(fixture["fixture_id"]) if fixture is not None else None,
                "fixture_event": (
                    int(fixture["event"]) if fixture is not None and pd.notna(fixture["event"]) else None
                ),
                "fixture_kickoff_time": (
                    fixture["kickoff_time"].isoformat() if fixture is not None else None
                ),
            })
    return {
        "schema_version": 1,
        "audit_type": "understat_row_visibility_at_fpl_deadlines",
        "repository_lineage_only": True,
        "original_understat_publication_proven": False,
        "vaastav_commit": vaastav_commit,
        "fplcache_repository": FPLCACHE_REPOSITORY,
        "fplcache_commit": fplcache_commit,
        "safety_buffer_minutes": int(SAFETY_BUFFER.total_seconds() / 60),
        "match_availability_hours": MATCH_AVAILABILITY_HOURS,
        "source_files_audited": history_report.get("files_audited"),
        "canonical_fixture_rows": len(canonical_rows),
        "mapping_stats_by_source_file": mapping_stats,
        "deadline_status_counts": dict(status_counts),
        "date_correction_reconciliations": correction_rows,
        "detail_rows": len(detail),
        "admission_decision": "NO_FEATURES_ADMITTED",
        "training_authorized": False,
    }, detail


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-report", type=Path, required=True)
    parser.add_argument("--seasons", default=",".join(DEFAULT_SEASONS))
    parser.add_argument("--vaastav-commit", required=True)
    parser.add_argument("--fplcache-commit", required=True)
    parser.add_argument("--fixture-cache-root", type=Path, required=True)
    parser.add_argument("--fplcache-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--detail-output", type=Path, required=True)
    args = parser.parse_args()
    history_report = json.loads(args.history_report.read_text(encoding="utf-8"))
    report, detail = audit_deadline_visibility(
        history_report,
        [value for value in args.seasons.split(",") if value],
        args.vaastav_commit,
        args.fplcache_commit,
        args.fixture_cache_root,
        args.fplcache_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    pd.DataFrame(detail).to_csv(args.detail_output, index=False)
    print(json.dumps({
        "canonical_fixture_rows": report["canonical_fixture_rows"],
        "detail_rows": report["detail_rows"],
        "deadline_status_counts": report["deadline_status_counts"],
        "date_correction_reconciliations": report["date_correction_reconciliations"],
        "admission_decision": report["admission_decision"],
    }, indent=2, default=str), flush=True)


if __name__ == "__main__":
    main()
