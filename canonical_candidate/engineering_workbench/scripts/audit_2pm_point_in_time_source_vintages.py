"""Audit point-in-time source vintages for the defensive 2PM experiment.

For each historical target deadline, this selects the latest Vaastav merged-GW
commit strictly before the deadline and the latest archived FPL bootstrap snapshot
before the five-minute safety buffer. It reads no target_points or total_points.
"""
from __future__ import annotations

import argparse
import io
import json
import lzma
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFENSIVE_FIELDS = (
    "defensive_contribution",
    "clearances_blocks_interceptions",
    "recoveries",
    "tackles",
)
SOURCE_ID_COLUMNS = ("fixture", "element", "kickoff_time", "minutes")
FIXTURE_SAFETY_BUFFER = timedelta(minutes=5)
SNAPSHOT_PATH = re.compile(r"^cache/(\d{4})/(\d{1,2})/(\d{1,2})/(\d{2})(\d{2})\.json\.xz$")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _github_json(url: str, token: str | None) -> Any:
    headers = {"User-Agent": "CTA-FPL-2PM-source-vintage-audit/1.0",
               "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_commit_history(season: str, token: str | None) -> list[dict[str, Any]]:
    path = f"data/{season}/gws/merged_gw.csv"
    url = (
        "https://api.github.com/repos/vaastav/Fantasy-Premier-League/commits"
        f"?path={path}&per_page=100"
    )
    payload = _github_json(url, token)
    commits = []
    for item in payload:
        commit = item["commit"]
        commits.append({
            "sha": item["sha"],
            "committed_at": _parse_time(commit["committer"]["date"]),
            "message": str(commit["message"]).splitlines()[0],
            "url": item["html_url"],
        })
    return commits


def select_commit(commits: list[dict[str, Any]], deadline: datetime) -> dict[str, Any] | None:
    cutoff = deadline - FIXTURE_SAFETY_BUFFER
    eligible = [item for item in commits if item["committed_at"] < cutoff]
    return max(eligible, key=lambda item: item["committed_at"]) if eligible else None


def _snapshot_index(root: Path) -> list[tuple[datetime, Path]]:
    rows = []
    for path in (root / "cache").glob("*/*/*/*.json.xz"):
        match = SNAPSHOT_PATH.match(path.relative_to(root).as_posix())
        if not match:
            continue
        year, month, day, hour, minute = map(int, match.groups())
        rows.append((datetime(year, month, day, hour, minute, tzinfo=timezone.utc), path))
    return sorted(rows, key=lambda row: row[0])


def _read_snapshot(path: Path) -> dict[str, Any]:
    return json.loads(lzma.decompress(path.read_bytes()).decode("utf-8"))


def _season_label(events: list[dict[str, Any]]) -> str:
    deadlines = [_parse_time(event["deadline_time"]) for event in events if event.get("deadline_time")]
    if not deadlines:
        raise ValueError("FPL cache snapshot has no event deadlines")
    first = min(deadlines)
    start = first.year if first.month >= 6 else first.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _probe_payload(
    index: list[tuple[datetime, Path]], season: str
) -> tuple[datetime, Path, dict[str, Any]]:
    if season == "2025-26":
        probe_date = date(2026, 1, 15)
        same_day = [(captured, path) for captured, path in index if captured.date() == probe_date]
        if not same_day:
            raise ValueError("No FPL cache snapshot on the 2025/26 season probe date 2026-01-15")
        captured, path = same_day[0]
    elif season == "2026-27":
        if not index:
            raise ValueError("FPL cache snapshot archive is empty")
        captured, path = index[-1]
    else:
        raise ValueError(f"Unsupported season for this experiment: {season}")
    payload = _read_snapshot(path)
    if _season_label(payload.get("events", [])) != season:
        raise ValueError(f"FPL cache probe did not resolve {season}")
    return captured, path, payload


def _snapshot_for_deadline(
    index: list[tuple[datetime, Path]],
    gameweek: int,
    initial_deadline: datetime,
) -> dict[str, Any]:
    deadline = initial_deadline
    seen: set[datetime] = set()
    for _ in range(4):
        if deadline in seen:
            return {"status": "deadline_did_not_converge", "deadline": deadline}
        seen.add(deadline)
        cutoff = deadline - FIXTURE_SAFETY_BUFFER
        eligible = [(captured, path) for captured, path in index if captured <= cutoff]
        if not eligible:
            return {"status": "no_pre_deadline_snapshot", "deadline": deadline}
        captured, path = eligible[-1]
        payload = _read_snapshot(path)
        event = next(
            (item for item in payload.get("events", []) if int(item.get("id", -1)) == gameweek),
            None,
        )
        if event is None or not event.get("deadline_time"):
            return {
                "status": "gameweek_absent_from_snapshot",
                "deadline": deadline,
                "captured_at": captured,
                "path": path.relative_to(path.parents[4]).as_posix() if len(path.parents) > 4 else path.name,
            }
        stated_deadline = _parse_time(event["deadline_time"])
        if stated_deadline != deadline:
            deadline = stated_deadline
            continue
        age_hours = (deadline - captured).total_seconds() / 3600.0
        is_next = bool(event.get("is_next"))
        return {
            "status": "selected",
            "deadline": deadline,
            "captured_at": captured,
            "path": path.as_posix(),
            "age_hours": age_hours,
            "is_next": is_next,
            "ep_next_usable_30h": is_next and 0 <= age_hours <= 30,
            "signals_usable_12h": is_next and 0 <= age_hours <= 12,
        }
    return {"status": "deadline_did_not_converge", "deadline": deadline}


def _read_source_frame(payload: bytes | Path) -> tuple[pd.DataFrame, list[str]]:
    if isinstance(payload, Path):
        header = pd.read_csv(payload, nrows=0).columns.tolist()
        reader_source: Any = payload
    else:
        header = pd.read_csv(io.BytesIO(payload), nrows=0).columns.tolist()
        reader_source = io.BytesIO(payload)
    present = [field for field in DEFENSIVE_FIELDS if field in header]
    columns = [field for field in SOURCE_ID_COLUMNS if field in header] + present
    frame = pd.read_csv(reader_source, usecols=columns, low_memory=False)
    for field in DEFENSIVE_FIELDS:
        if field not in frame:
            frame[field] = np.nan
    for required in SOURCE_ID_COLUMNS:
        if required not in frame:
            raise ValueError(f"Source version lacks required field {required}")
    frame["fixture"] = frame["fixture"].astype(str)
    frame["element"] = pd.to_numeric(frame["element"], errors="raise").astype(int)
    frame["minutes"] = pd.to_numeric(frame["minutes"], errors="coerce")
    frame["kickoff_time"] = pd.to_datetime(frame["kickoff_time"], utc=True, errors="coerce")
    if frame["kickoff_time"].isna().any():
        raise ValueError("Source version contains invalid kickoff_time")
    frame["match_available_at"] = frame["kickoff_time"] + pd.Timedelta(hours=24)
    return frame, present


def _field_counts(frame: pd.DataFrame) -> dict[str, Any]:
    report = {}
    for field in DEFENSIVE_FIELDS:
        values = pd.to_numeric(frame[field], errors="coerce")
        finite = values[np.isfinite(values)]
        report[field] = {
            "finite": int(len(finite)),
            "missing": int(values.isna().sum()),
            "zero": int(finite.eq(0).sum()),
            "nonzero": int(finite.ne(0).sum()),
        }
    return report


def _audit_one_deadline(
    *,
    season: str,
    gameweek: int,
    deadline: datetime,
    commits: list[dict[str, Any]],
    final_source: pd.DataFrame,
    final_columns: list[str],
    raw_cache: dict[str, tuple[pd.DataFrame, list[str]]],
    token: str | None,
) -> dict[str, Any]:
    selected = select_commit(commits, deadline)
    final_prior = final_source.loc[final_source["match_available_at"].lt(pd.Timestamp(deadline))].copy()
    if selected is None:
        return {
            "season": season, "gameweek": gameweek, "deadline": deadline.isoformat(),
            "source_status": "no_commit_before_deadline",
            "final_prior_rows": int(len(final_prior)),
            "final_prior_played_rows": int(final_prior["minutes"].gt(0).sum()),
            "missing_final_prior_keys": int(len(final_prior)),
            "source_coverage_of_final_prior_keys": 0.0 if len(final_prior) else None,
            "defensive_columns_present": [],
            "field_counts_all_prior_rows": {},
            "field_counts_prior_played_rows": {},
        }

    sha = selected["sha"]
    if sha not in raw_cache:
        url = (
            "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/"
            f"{sha}/data/{season}/gws/merged_gw.csv"
        )
        request = urllib.request.Request(url, headers={"User-Agent": "CTA-FPL-2PM-source-vintage-audit/1.0"})
        with urllib.request.urlopen(request, timeout=120) as response:
            raw_cache[sha] = _read_source_frame(response.read())
    historical, present = raw_cache[sha]
    prior = historical.loc[historical["match_available_at"].lt(pd.Timestamp(deadline))].copy()
    played = prior.loc[prior["minutes"].gt(0)].copy()

    final_keys = set(zip(final_prior["fixture"], final_prior["element"]))
    source_keys = set(zip(prior["fixture"], prior["element"]))
    common = final_keys & source_keys
    latest_match = prior["match_available_at"].max() if len(prior) else pd.NaT
    latest_final_match = final_prior["match_available_at"].max() if len(final_prior) else pd.NaT
    age_hours = (deadline - selected["committed_at"]).total_seconds() / 3600.0
    return {
        "season": season,
        "gameweek": gameweek,
        "deadline": deadline.isoformat(),
        "source_status": (
            "defensive_columns_absent"
            if not set(DEFENSIVE_FIELDS).issubset(present)
            else "selected_pre_deadline_commit"
        ),
        "source_commit": sha,
        "source_commit_url": selected["url"],
        "source_commit_at": selected["committed_at"].isoformat(),
        "source_commit_age_hours": round(age_hours, 3),
        "source_commit_message": selected["message"],
        "defensive_columns_present": present,
        "source_prior_rows": int(len(prior)),
        "source_prior_played_rows": int(len(played)),
        "final_prior_rows": int(len(final_prior)),
        "final_prior_played_rows": int(final_prior["minutes"].gt(0).sum()),
        "missing_final_prior_keys": int(len(final_keys - source_keys)),
        "extra_source_prior_keys": int(len(source_keys - final_keys)),
        "source_coverage_of_final_prior_keys": (
            round(len(common) / len(final_keys), 6) if final_keys else None
        ),
        "latest_source_match_available_at": (
            latest_match.isoformat() if pd.notna(latest_match) else None
        ),
        "latest_final_match_available_at": (
            latest_final_match.isoformat() if pd.notna(latest_final_match) else None
        ),
        "source_match_lag_hours": (
            round((deadline - latest_match).total_seconds() / 3600.0, 3)
            if pd.notna(latest_match) else None
        ),
        "field_counts_all_prior_rows": _field_counts(prior),
        "field_counts_prior_played_rows": _field_counts(played),
    }


def audit_season(
    season: str,
    max_gameweek: int,
    final_source_path: Path,
    fplcache_root: Path,
    fplcache_commit: str,
    token: str | None,
) -> dict[str, Any]:
    index = _snapshot_index(fplcache_root)
    probe_at, probe_path, probe_payload = _probe_payload(index, season)
    deadlines = {
        int(event["id"]): _parse_time(event["deadline_time"])
        for event in probe_payload.get("events", [])
        if event.get("deadline_time")
    }
    commits = fetch_commit_history(season, token)
    final_source, final_columns = _read_source_frame(final_source_path)
    raw_cache: dict[str, tuple[pd.DataFrame, list[str]]] = {}
    gameweeks = {}
    for gw in range(1, max_gameweek + 1):
        if gw not in deadlines:
            gameweeks[str(gw)] = {"status": "deadline_missing_from_fplcache"}
            continue
        snapshot = _snapshot_for_deadline(index, gw, deadlines[gw])
        if snapshot["status"] != "selected":
            gameweeks[str(gw)] = {
                "snapshot": snapshot,
                "source": _audit_one_deadline(
                    season=season, gameweek=gw, deadline=deadlines[gw],
                    commits=commits, final_source=final_source,
                    final_columns=final_columns, raw_cache=raw_cache, token=token,
                ),
            }
            continue
        source = _audit_one_deadline(
            season=season, gameweek=gw, deadline=snapshot["deadline"],
            commits=commits, final_source=final_source,
            final_columns=final_columns, raw_cache=raw_cache, token=token,
        )
        gameweeks[str(gw)] = {"snapshot": snapshot, "source": source}

    return {
        "season": season,
        "max_gameweek_audited": max_gameweek,
        "fplcache_commit": fplcache_commit,
        "fplcache_probe_at": probe_at.isoformat(),
        "fplcache_probe_path": probe_path.as_posix(),
        "fplcache_latest_snapshot_at": index[-1][0].isoformat() if index else None,
        "source_commit_history_count": len(commits),
        "gameweeks": gameweeks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-2025-26", type=Path, required=True)
    parser.add_argument("--source-2026-27", type=Path, required=True)
    parser.add_argument("--fplcache-2025-26", type=Path, required=True)
    parser.add_argument("--fplcache-2026-27", type=Path, required=True)
    parser.add_argument("--fplcache-2025-26-commit", required=True)
    parser.add_argument("--fplcache-2026-27-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--detail-output", type=Path, required=True)
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    reports = {
        "2025-26": audit_season(
            "2025-26", 38, args.source_2025_26, args.fplcache_2025_26,
            args.fplcache_2025_26_commit, token,
        ),
        "2026-27": audit_season(
            "2026-27", 10, args.source_2026_27, args.fplcache_2026_27,
            args.fplcache_2026_27_commit, token,
        ),
    }
    report = {
        "status": "POINT_IN_TIME_SOURCE_VINTAGE_AUDIT_COMPLETE",
        "source_repository": "vaastav/Fantasy-Premier-League",
        "commit_selection_rule": "latest merged_gw.csv commit strictly before official deadline minus five minutes",
        "match_availability_rule": "fixture kickoff + 24 hours; strict availability < target deadline",
        "fplcache_snapshot_rule": "latest archived bootstrap snapshot at least five minutes before deadline",
        "labels_read": False,
        "target_points_loaded": False,
        "total_points_loaded": False,
        "seasons": reports,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.detail_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value))
        + "\n", encoding="utf-8"
    )
    rows = []
    for season, season_report in reports.items():
        for gw, values in season_report["gameweeks"].items():
            snapshot = values.get("snapshot", {})
            source = values.get("source", {})
            rows.append({
                "season": season,
                "gameweek": int(gw),
                "deadline": source.get("deadline", snapshot.get("deadline")),
                "snapshot_status": snapshot.get("status", values.get("status")),
                "snapshot_captured_at": snapshot.get("captured_at"),
                "snapshot_age_hours": snapshot.get("age_hours"),
                "snapshot_is_next": snapshot.get("is_next"),
                "ep_next_usable_30h": snapshot.get("ep_next_usable_30h"),
                "signals_usable_12h": snapshot.get("signals_usable_12h"),
                "source_status": source.get("source_status"),
                "source_commit": source.get("source_commit"),
                "source_commit_at": source.get("source_commit_at"),
                "source_commit_age_hours": source.get("source_commit_age_hours"),
                "source_prior_played_rows": source.get("source_prior_played_rows"),
                "final_prior_played_rows": source.get("final_prior_played_rows"),
                "missing_final_prior_keys": source.get("missing_final_prior_keys"),
                "source_coverage_of_final_prior_keys": source.get("source_coverage_of_final_prior_keys"),
                "latest_source_match_available_at": source.get("latest_source_match_available_at"),
                "source_match_lag_hours": source.get("source_match_lag_hours"),
            })
    pd.DataFrame(rows).to_csv(args.detail_output, index=False)
    print(json.dumps(
        report, indent=2,
        default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value),
    ))


if __name__ == "__main__":
    main()
