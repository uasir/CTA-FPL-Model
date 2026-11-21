#!/usr/bin/env python3
"""Build a finality-aware official FPL fixture scoreline panel for CoVar research.

This is realized data preparation, not a scoreline predictor. It preserves
fixture-level home/away outcomes needed by the M3-anchored joint scenario model.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import stat
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

FIXTURE_FIELDS = (
    "season", "gameweek", "fixture_id", "kickoff_time", "home_team_id",
    "away_team_id", "home_goals", "away_goals", "total_goals",
    "goal_difference_home", "result", "finished_provisional",
)
GAMEWEEK_FIELDS = (
    "season", "gameweek", "fixture_count", "home_goals", "away_goals",
    "total_goals", "home_wins", "draws", "away_wins",
)

class RealizedFixtureStateError(ValueError):
    """Official fixture inputs cannot form a valid realized scoreline panel."""

def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _time(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RealizedFixtureStateError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RealizedFixtureStateError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RealizedFixtureStateError(f"{field} must include a timezone")
    return parsed.isoformat()

def _int(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise RealizedFixtureStateError(f"{field} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise RealizedFixtureStateError(f"{field} must be an integer") from exc
    if str(value) not in (str(result), f"{result}.0") or result < minimum:
        raise RealizedFixtureStateError(f"{field} must be an integer >= {minimum}")
    return result

def _bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if str(value).strip().lower() in {"true", "1"}: return True
    if str(value).strip().lower() in {"false", "0"}: return False
    raise RealizedFixtureStateError(f"{field} must be an explicit boolean")

def build_realized_fixture_states(fixtures: Sequence[Mapping[str, Any]], *, season: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(season, str) or not season.strip():
        raise RealizedFixtureStateError("season is required")
    if not isinstance(fixtures, Sequence) or isinstance(fixtures, (str, bytes)) or not fixtures:
        raise RealizedFixtureStateError("fixtures must be a non-empty list")
    seen: set[int] = set()
    rows: list[dict[str, Any]] = []
    for index, fixture in enumerate(fixtures):
        if not isinstance(fixture, Mapping):
            raise RealizedFixtureStateError(f"fixture[{index}] must be an object")
        fid = _int(fixture.get("id"), f"fixture[{index}].id", minimum=1)
        if fid in seen:
            raise RealizedFixtureStateError(f"duplicate fixture ID {fid}")
        seen.add(fid)
        event = fixture.get("event")
        if event is None:
            continue
        gw = _int(event, f"fixture {fid}.event", minimum=1)
        if not _bool(fixture.get("finished"), f"fixture {fid}.finished"):
            continue
        home = _int(fixture.get("team_h"), f"fixture {fid}.team_h", minimum=1)
        away = _int(fixture.get("team_a"), f"fixture {fid}.team_a", minimum=1)
        if home == away:
            raise RealizedFixtureStateError(f"fixture {fid} has identical home and away teams")
        home_goals = _int(fixture.get("team_h_score"), f"fixture {fid}.team_h_score")
        away_goals = _int(fixture.get("team_a_score"), f"fixture {fid}.team_a_score")
        kickoff = _time(fixture.get("kickoff_time"), f"fixture {fid}.kickoff_time")
        provisional = _bool(fixture.get("finished_provisional"), f"fixture {fid}.finished_provisional")
        result = "H" if home_goals > away_goals else "A" if away_goals > home_goals else "D"
        rows.append({
            "season": season, "gameweek": gw, "fixture_id": fid,
            "kickoff_time": kickoff, "home_team_id": home, "away_team_id": away,
            "home_goals": home_goals, "away_goals": away_goals,
            "total_goals": home_goals + away_goals,
            "goal_difference_home": home_goals - away_goals,
            "result": result, "finished_provisional": provisional,
        })
    if not rows:
        raise RealizedFixtureStateError("no finished Gameweek-assigned fixtures found")
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["gameweek"], []).append(row)
    summaries = []
    for gw, items in sorted(grouped.items()):
        summaries.append({
            "season": season, "gameweek": gw, "fixture_count": len(items),
            "home_goals": sum(x["home_goals"] for x in items),
            "away_goals": sum(x["away_goals"] for x in items),
            "total_goals": sum(x["total_goals"] for x in items),
            "home_wins": sum(x["result"] == "H" for x in items),
            "draws": sum(x["result"] == "D" for x in items),
            "away_wins": sum(x["result"] == "A" for x in items),
        })
    report = {
        "schema_version": "1.0.0",
        "season": season,
        "status": "PASS_STRUCTURAL_ONLY",
        "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_OFFICIAL_API_HISTORY",
        "fixture_state_count": len(rows),
        "gameweek_count": len(summaries),
        "gameweeks": sorted(grouped),
        "finished_provisional_count": sum(bool(x["finished_provisional"]) for x in rows),
        "finality_status": "REQUIRES_OFFICIAL_EVENT_LIVE_RECONCILIATION" if any(x["finished_provisional"] for x in rows) else "OFFICIAL_FIXTURE_FEED_FINISHED",
        "decision_weight": 0.0,
        "production_eligible": False,
    }
    return rows, summaries, report

def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.chmod(path, 0o600)

def build_from_ingestion_directory(input_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    source = Path(input_dir).expanduser().resolve(strict=True)
    if not source.is_dir():
        raise RealizedFixtureStateError("input_dir must be a directory")
    fixture_path = source / "fixtures.json"
    report_path = source / "ingestion_report.json"
    metadata_path = source / "source_metadata.json"
    for path in (fixture_path, report_path, metadata_path):
        if not path.is_file() or path.is_symlink():
            raise RealizedFixtureStateError(f"required regular source file missing: {path.name}")
    raw_fixtures = fixture_path.read_bytes()
    raw_report = report_path.read_bytes()
    raw_metadata = metadata_path.read_bytes()
    try:
        fixtures = json.loads(raw_fixtures.decode("utf-8"))
        ingestion_report = json.loads(raw_report.decode("utf-8"))
        metadata = json.loads(raw_metadata.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RealizedFixtureStateError("official ingestion inputs must be valid UTF-8 JSON") from exc
    if ingestion_report.get("status") != "PASS":
        raise RealizedFixtureStateError("official FPL ingestion report must have PASS status")
    season = ingestion_report.get("season")
    if not isinstance(season, str) or metadata.get("season") != season:
        raise RealizedFixtureStateError("season mismatch between ingestion report and source metadata")
    expected_digest = hashlib.sha256(json.dumps(fixtures, sort_keys=True).encode()).hexdigest()
    if metadata.get("fixtures_sha256") != expected_digest:
        raise RealizedFixtureStateError("fixtures.json content does not match official source metadata hash")
    rows, summaries, report = build_realized_fixture_states(fixtures, season=season)
    root = Path(output_dir).expanduser().resolve(strict=False)
    if root.exists():
        raise RealizedFixtureStateError("output directory already exists")
    if any((parent / ".git").exists() or (parent / ".git").is_file() for parent in (root, *root.parents)):
        raise RealizedFixtureStateError("private output must be outside a Git repository")
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(mode=0o700)
    try:
        _write_csv(root / "fpl_realized_fixture_states.csv", FIXTURE_FIELDS, rows)
        _write_csv(root / "fpl_realized_gameweek_match_summary.csv", GAMEWEEK_FIELDS, summaries)
        report.update({
            "input_fixtures_sha256": _sha(raw_fixtures),
            "input_ingestion_report_sha256": _sha(raw_report),
            "input_source_metadata_sha256": _sha(raw_metadata),
            "canonical_fixtures_object_sha256": expected_digest,
            "fixture_state_output_sha256": _sha((root / "fpl_realized_fixture_states.csv").read_bytes()),
            "gameweek_summary_output_sha256": _sha((root / "fpl_realized_gameweek_match_summary.csv").read_bytes()),
        })
        report_path_out = root / "fixture_state_report.json"
        report_path_out.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.chmod(report_path_out, 0o600)
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return report

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build official FPL realized fixture scoreline panel.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(build_from_ingestion_directory(args.input_dir, args.output_dir), sort_keys=True, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
