"""Audit point-in-time vintages of FPL-native match history and defensive fields.

For each historical target deadline, select the latest Vaastav merged-GW commit
strictly before the deadline minus five minutes. Compare prior-match FPL-native
source values and keys against the pinned final source. Historical total_points
is treated only as a prior-match input after the strict match-availability filter;
target labels are not used by the audit.
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

FPL_NATIVE_FIELDS = (
    "total_points",
    "minutes",
    "influence",
    "creativity",
    "threat",
    "goals_scored",
    "penalties_missed",
    "assists",
    "goals_conceded",
    "own_goals",
    "saves",
    "penalties_saved",
    "yellow_cards",
    "red_cards",
    "bps",
    "bonus",
)
OPTIONAL_FPL_FIELDS = ("starts",)
DEFENSIVE_FIELDS = (
    "defensive_contribution",
    "clearances_blocks_interceptions",
    "recoveries",
    "tackles",
)
SOURCE_ID_COLUMNS = ("fixture", "element", "kickoff_time", "minutes")
SOURCE_KEY_COLUMNS = ("fixture", "element")
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


FPLCACHE_REPOSITORY = "Randdalf/fplcache"


def _snapshot_index(
    root: Path, commit: str, token: str | None
) -> list[tuple[datetime, Path]]:
    """Index the pinned archive tree without downloading every historical snapshot."""
    root.mkdir(parents=True, exist_ok=True)
    tree_path = root / "tree.json"
    if not tree_path.exists():
        url = (
            f"https://api.github.com/repos/{FPLCACHE_REPOSITORY}/git/trees/"
            f"{commit}?recursive=1"
        )
        payload = _github_json(url, token)
        if payload.get("truncated"):
            raise RuntimeError("Pinned FPL-cache Git tree is truncated")
        temporary = tree_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(tree_path)
    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    if tree.get("truncated"):
        raise RuntimeError("Pinned FPL-cache Git tree is truncated")
    snapshot_root = root / "snapshots"
    rows = []
    for entry in tree.get("tree", []):
        source_path = entry.get("path", "")
        match = SNAPSHOT_PATH.match(source_path)
        if entry.get("type") != "blob" or not match:
            continue
        year, month, day, hour, minute = map(int, match.groups())
        captured = datetime(
            year, month, day, hour, minute, tzinfo=timezone.utc
        )
        rows.append((captured, snapshot_root / source_path))
    return sorted(rows, key=lambda row: row[0])


def _read_snapshot(
    path: Path, snapshot_root: Path | None = None, commit: str | None = None
) -> dict[str, Any]:
    if not path.exists():
        if snapshot_root is None or commit is None:
            raise FileNotFoundError(path)
        source_path = path.relative_to(snapshot_root).as_posix()
        url = (
            f"https://raw.githubusercontent.com/{FPLCACHE_REPOSITORY}/"
            f"{commit}/{source_path}"
        )
        request = urllib.request.Request(
            url, headers={"User-Agent": "CTA-FPL-2PM-source-vintage-audit/1.0"}
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = response.read()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_bytes(payload)
        temporary.replace(path)
    return json.loads(lzma.decompress(path.read_bytes()).decode("utf-8"))


def _season_label(events: list[dict[str, Any]]) -> str:
    deadlines = [_parse_time(event["deadline_time"]) for event in events if event.get("deadline_time")]
    if not deadlines:
        raise ValueError("FPL cache snapshot has no event deadlines")
    first = min(deadlines)
    start = first.year if first.month >= 6 else first.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _season_capture_bounds(season: str) -> tuple[datetime, datetime]:
    try:
        start_year = int(season.split("-")[0])
        end_suffix = season.split("-")[1]
    except (ValueError, IndexError) as exc:
        raise ValueError(f"Invalid season label: {season}") from exc
    if len(end_suffix) != 2 or int(end_suffix) != (start_year + 1) % 100:
        raise ValueError(f"Invalid season label: {season}")
    return (
        datetime(start_year, 6, 1, tzinfo=timezone.utc),
        datetime(start_year + 1, 7, 1, tzinfo=timezone.utc),
    )


def _season_index(
    index: list[tuple[datetime, Path]], season: str
) -> list[tuple[datetime, Path]]:
    start, end = _season_capture_bounds(season)
    return [(captured, path) for captured, path in index if start <= captured < end]


def _probe_payload(
    index: list[tuple[datetime, Path]],
    season: str,
    snapshot_root: Path | None = None,
    commit: str | None = None,
) -> tuple[datetime, Path, dict[str, Any]]:
    candidates = _season_index(index, season)
    for captured, path in reversed(candidates):
        payload = _read_snapshot(path, snapshot_root, commit)
        if _season_label(payload.get("events", [])) == season:
            return captured, path, payload
    raise ValueError(
        f"No archived FPL-cache snapshot for {season} in its season capture window"
    )


def _snapshot_for_deadline(
    index: list[tuple[datetime, Path]],
    season: str,
    gameweek: int,
    initial_deadline: datetime,
    snapshot_root: Path | None = None,
    commit: str | None = None,
) -> dict[str, Any]:
    deadline = initial_deadline
    same_season_index = _season_index(index, season)
    seen: set[datetime] = set()
    for _ in range(4):
        if deadline in seen:
            return {"status": "deadline_did_not_converge", "deadline": deadline}
        seen.add(deadline)
        cutoff = deadline - FIXTURE_SAFETY_BUFFER
        eligible = [(captured, path) for captured, path in same_season_index if captured <= cutoff]
        if not eligible:
            return {"status": "no_pre_deadline_snapshot", "deadline": deadline}
        captured, path = eligible[-1]
        payload = _read_snapshot(path, snapshot_root, commit)
        if _season_label(payload.get("events", [])) != season:
            return {"status": "snapshot_season_mismatch", "deadline": deadline}
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
    audited_fields = list(dict.fromkeys(
        FPL_NATIVE_FIELDS + OPTIONAL_FPL_FIELDS + DEFENSIVE_FIELDS
    ))
    present = [field for field in audited_fields if field in header]
    columns = list(dict.fromkeys(
        [field for field in SOURCE_ID_COLUMNS if field in header] + present
    ))
    frame = pd.read_csv(reader_source, usecols=columns, low_memory=False)
    for field in audited_fields:
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


def _field_counts(frame: pd.DataFrame, fields: tuple[str, ...]) -> dict[str, Any]:
    report = {}
    for field in fields:
        values = pd.to_numeric(frame[field], errors="coerce")
        finite = values[np.isfinite(values)]
        report[field] = {
            "finite": int(len(finite)),
            "missing": int(values.isna().sum()),
            "zero": int(finite.eq(0).sum()),
            "nonzero": int(finite.ne(0).sum()),
        }
    return report


def _field_parity(
    historical: pd.DataFrame,
    final: pd.DataFrame,
    fields: tuple[str, ...],
) -> dict[str, Any]:
    """Compare historical-vintage prior-match values with pinned final source values."""
    joined = historical[list(SOURCE_KEY_COLUMNS) + list(fields)].merge(
        final[list(SOURCE_KEY_COLUMNS) + list(fields)],
        on=list(SOURCE_KEY_COLUMNS),
        how="inner",
        suffixes=("_historical", "_final"),
        validate="one_to_one",
    )
    report = {"common_prior_keys": int(len(joined)), "fields": {}}
    for field in fields:
        left = pd.to_numeric(joined[f"{field}_historical"], errors="coerce")
        right = pd.to_numeric(joined[f"{field}_final"], errors="coerce")
        valid = left.notna() & right.notna()
        equal = np.isclose(left[valid], right[valid], atol=1e-6, rtol=0.0)
        difference = (left[valid] - right[valid]).abs()
        report["fields"][field] = {
            "valid_pairs": int(valid.sum()),
            "exact_match_rows": int(equal.sum()),
            "changed_rows": int((~equal).sum()),
            "exact_match_rate": float(equal.mean()) if len(equal) else None,
            "mean_absolute_difference": float(difference.mean()) if len(difference) else None,
            "p95_absolute_difference": float(difference.quantile(0.95)) if len(difference) else None,
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
            "fpl_native_columns_present": [],
            "fpl_native_columns_missing": list(FPL_NATIVE_FIELDS),
            "optional_fpl_columns_present": [],
            "defensive_columns_present": [],
            "source_status": "no_commit_before_deadline",
            "defensive_status": "no_commit_before_deadline",
            "fpl_native_field_counts_all_prior_rows": {},
            "fpl_native_field_counts_prior_played_rows": {},
            "fpl_native_prior_value_parity": {},
            "defensive_field_counts_all_prior_rows": {},
            "defensive_field_counts_prior_played_rows": {},
            "defensive_prior_value_parity": {},
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
            "fpl_native_columns_incomplete"
            if not set(FPL_NATIVE_FIELDS).issubset(present)
            else "selected_pre_deadline_commit"
        ),
        "fpl_native_columns_present": [field for field in FPL_NATIVE_FIELDS if field in present],
        "fpl_native_columns_missing": sorted(set(FPL_NATIVE_FIELDS) - set(present)),
        "optional_fpl_columns_present": [field for field in OPTIONAL_FPL_FIELDS if field in present],
        "defensive_columns_present": [field for field in DEFENSIVE_FIELDS if field in present],
        "defensive_status": (
            "all_defensive_columns_present"
            if set(DEFENSIVE_FIELDS).issubset(present)
            else "one_or_more_defensive_columns_absent"
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
        "fpl_native_field_counts_all_prior_rows": _field_counts(prior, FPL_NATIVE_FIELDS),
        "fpl_native_field_counts_prior_played_rows": _field_counts(played, FPL_NATIVE_FIELDS),
        "fpl_native_prior_value_parity": _field_parity(prior, final_prior, FPL_NATIVE_FIELDS),
        "defensive_field_counts_all_prior_rows": _field_counts(prior, DEFENSIVE_FIELDS),
        "defensive_field_counts_prior_played_rows": _field_counts(played, DEFENSIVE_FIELDS),
        "defensive_prior_value_parity": _field_parity(prior, final_prior, DEFENSIVE_FIELDS),
    }


def audit_season(
    season: str,
    max_gameweek: int,
    final_source_path: Path,
    fplcache_root: Path,
    fplcache_commit: str,
    token: str | None,
) -> dict[str, Any]:
    index = _snapshot_index(fplcache_root, fplcache_commit, token)
    snapshot_root = fplcache_root / "snapshots"
    probe_at, probe_path, probe_payload = _probe_payload(
        index, season, snapshot_root, fplcache_commit
    )
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
        snapshot = _snapshot_for_deadline(
            index, season, gw, deadlines[gw], snapshot_root, fplcache_commit
        )
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
    parser.add_argument(
        "--season-config", type=Path, required=True,
        help="JSON mapping season to {max_gameweek, source_path}.",
    )
    parser.add_argument("--fplcache-root", type=Path, required=True)
    parser.add_argument("--fplcache-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--detail-output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.season_config.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not config:
        raise ValueError("Season config must be a non-empty JSON object")
    token = os.environ.get("GITHUB_TOKEN")
    reports = {}
    for season, settings in config.items():
        if not isinstance(settings, dict):
            raise ValueError(f"Invalid season config for {season}")
        source_path = Path(settings["source_path"])
        max_gameweek = int(settings["max_gameweek"])
        if max_gameweek < 1 or max_gameweek > 50:
            raise ValueError(f"Invalid max_gameweek for {season}: {max_gameweek}")
        reports[season] = audit_season(
            season, max_gameweek, source_path, args.fplcache_root,
            args.fplcache_commit, token,
        )
    report = {
        "status": "POINT_IN_TIME_SOURCE_VINTAGE_AUDIT_COMPLETE",
        "source_repository": "vaastav/Fantasy-Premier-League",
        "commit_selection_rule": "latest merged_gw.csv commit strictly before official deadline minus five minutes",
        "season_snapshot_scoping": "snapshot index restricted to capture dates from June 1 of the season start year through June 30 of the following year; payload season label verified",
        "match_availability_rule": "fixture kickoff + 24 hours; strict availability < target deadline",
        "fplcache_snapshot_rule": "latest archived bootstrap snapshot from the same season at least five minutes before deadline; no cross-season snapshot fallback",
        "target_labels_used": False,
        "historical_total_points_audited_only_after_match_availability_filter": True,
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
