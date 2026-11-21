#!/usr/bin/env python3
"""Batch-reconcile a private realized FPL panel against captured official event-live sources.

Expected layout:
  dataset_dir/fpl_realized_player_gameweek.csv
  capture_root/event_<GW>/capture_manifest.json
  capture_root/event_<GW>/event_live.json
  capture_root/event_<GW>/fixtures.json

Each event archive must come from m4_covar_point_in_time_source_capture.py.
The tool is retrospective final-scoring validation only, never point-in-time
forecast reconstruction. Output is private and remains research-only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

from m4_covar_realized_fpl_finality_audit import (
    RealizedFplFinalityAuditError,
    audit_player_gameweek_finality,
)


class FinalityBatchError(ValueError):
    """The batch inputs cannot support a safe finality audit."""


def _load_json(path: Path, *, expected_sha256: str | None = None) -> tuple[Any, bytes]:
    raw = path.read_bytes()
    if expected_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise FinalityBatchError(f"{path.name} source hash mismatch")
    try:
        return json.loads(raw.decode("utf-8")), raw
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FinalityBatchError(f"{path.name} is not valid UTF-8 JSON") from exc


def _private_output(path: Path) -> Path:
    if not path.is_absolute():
        raise FinalityBatchError("output_dir must be absolute")
    target = path.resolve()
    repo_root = Path(__file__).resolve().parents[3]
    if target.is_relative_to(repo_root):
        raise FinalityBatchError("finality audit output must be outside repository")
    if target.exists():
        raise FileExistsError("refusing to overwrite an existing finality audit output")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(mode=stat.S_IRWXU)
    return target


def run_finality_batch(dataset_csv: Path, capture_root: Path, output_dir: Path) -> dict[str, Any]:
    if not dataset_csv.is_file() or not capture_root.is_dir():
        raise FinalityBatchError("dataset CSV and capture root must exist")
    with dataset_csv.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise FinalityBatchError("realized player-Gameweek dataset is empty")
    seasons = {row.get("season") for row in rows}
    if len(seasons) != 1 or not next(iter(seasons)):
        raise FinalityBatchError("dataset must contain exactly one explicit season")
    season = next(iter(seasons))
    events = sorted({int(row["gameweek"]) for row in rows})
    target = _private_output(output_dir)
    reports = []
    try:
        for event in events:
            event_rows = [row for row in rows if int(row["gameweek"]) == event]
            archive = (capture_root / f"event_{event}").resolve()
            if not archive.is_dir() or not archive.is_relative_to(capture_root.resolve()):
                raise FinalityBatchError(f"missing or unsafe event_{event} capture directory")
            if (archive / "CAPTURE_INCOMPLETE").exists():
                raise FinalityBatchError(f"event_{event} source capture is marked incomplete")
            manifest, _ = _load_json(archive / "capture_manifest.json")
            if manifest.get("capture_status") != "PUBLIC_SOURCE_BYTES_CAPTURED":
                raise FinalityBatchError(f"event_{event} capture manifest is not complete")
            if manifest.get("event_id") != event:
                raise FinalityBatchError(f"event_{event} capture manifest has wrong event ID")
            source_rows = manifest.get("source_snapshots")
            if not isinstance(source_rows, list):
                raise FinalityBatchError(f"event_{event} capture manifest has no source_snapshots")
            by_id = {item.get("source_id"): item for item in source_rows if isinstance(item, dict)}
            if len(by_id) != len(source_rows) or not {"event_live", "fixtures"}.issubset(by_id):
                raise FinalityBatchError(f"event_{event} capture manifest has duplicate or missing sources")
            fixture_source = by_id["fixtures"]
            if fixture_source.get("source_url") != "https://fantasy.premierleague.com/api/fixtures/":
                raise FinalityBatchError(f"event_{event} fixtures source URL is not official")
            fixture_path = (archive / fixture_source.get("archive_path", "")).resolve()
            if not fixture_path.is_relative_to(archive) or not fixture_path.is_file():
                raise FinalityBatchError(f"event_{event} fixture source path is unsafe or missing")
            fixtures, fixture_raw = _load_json(
                fixture_path, expected_sha256=fixture_source.get("content_sha256")
            )
            event_fixtures = [f for f in fixtures if isinstance(f, dict) and f.get("event") == event]
            if not event_fixtures or any(f.get("finished") is not True for f in event_fixtures):
                raise FinalityBatchError(f"event_{event} contains fixtures that are not fully finished")
            provisional_fixture_count = sum(
                f.get("finished_provisional") is True for f in event_fixtures
            )
            live_source = by_id["event_live"]
            expected_url = f"https://fantasy.premierleague.com/api/event/{event}/live/"
            if live_source.get("source_url") != expected_url:
                raise FinalityBatchError(f"event_{event} event-live source URL mismatch")
            live_path = (archive / live_source.get("archive_path", "")).resolve()
            if not live_path.is_relative_to(archive) or not live_path.is_file():
                raise FinalityBatchError(f"event_{event} event-live source path is unsafe or missing")
            live_payload, live_raw = _load_json(
                live_path, expected_sha256=live_source.get("content_sha256")
            )
            digest = hashlib.sha256(live_raw).hexdigest()
            report = audit_player_gameweek_finality(
                event_rows, live_payload, season=season, event_id=event,
                source_provenance={
                    "source_url": live_source["source_url"],
                    "captured_at_utc": live_source["retrieved_at_utc"],
                    "raw_sha256": digest,
                },
                raw_source_bytes=live_raw,
            )
            report["fixture_count"] = len(event_fixtures)
            report["fixtures_marked_finished_provisional_at_capture"] = provisional_fixture_count
            report["fixture_finality_interpretation"] = (
                "OFFICIAL_EVENT_LIVE_RECONCILIATION_REQUIRED_AND_PERFORMED"
                if provisional_fixture_count
                else "FIXTURE_FEED_MARKED_NONPROVISIONAL"
            )
            reports.append(report)
        result = {
            "schema_version": "1.0.0",
            "status": "PASS_ALL_EVENTS" if all(x["finality_reconciled"] for x in reports) else "FAIL_MISMATCH",
            "season": season,
            "events_checked": events,
            "event_count": len(events),
            "all_event_finality_reconciled": all(x["finality_reconciled"] for x in reports),
            "reports": reports,
            "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_FINAL_SCORING_AUDIT",
            "decision_weight": 0.0,
            "production_eligible": False,
        }
        output = target / "finality_batch_report.json"
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(output, stat.S_IRUSR | stat.S_IWUSR)
        return result
    except Exception:
        marker = target / "AUDIT_INCOMPLETE"
        marker.write_text("Audit failed or incomplete; do not use as a complete batch.\n", encoding="utf-8")
        os.chmod(marker, stat.S_IRUSR | stat.S_IWUSR)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-csv", type=Path, required=True)
    parser.add_argument("--capture-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run_finality_batch(args.dataset_csv, args.capture_root, args.output_dir)
    print(json.dumps({k: v for k, v in result.items() if k != "reports"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
