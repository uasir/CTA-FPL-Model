#!/usr/bin/env python3
"""Capture public official FPL source snapshots for future point-in-time forecasts.

This tool does not reconstruct historical snapshots. It records the bytes and
retrieval time observed now, stores them privately, and labels every capture as
usable only for forecasts generated at or after that retrieval time.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "https://fantasy.premierleague.com/api"
ENDPOINTS = {
    "bootstrap_static": lambda event: f"{BASE_URL}/bootstrap-static/",
    "fixtures": lambda event: f"{BASE_URL}/fixtures/",
    "event_live": lambda event: f"{BASE_URL}/event/{event}/live/",
}


class SourceCaptureError(RuntimeError):
    """A source capture could not be completed safely."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_source_bytes(url: str, *, timeout: float = 30.0) -> bytes:
    if not isinstance(url, str) or not url.startswith(BASE_URL + "/"):
        raise SourceCaptureError("only official Fantasy Premier League API endpoints are allowed")
    request = Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "CTA-FPL-Model-point-in-time-source-capture/1.0",
    })
    try:
        with urlopen(request, timeout=timeout) as response:
            if getattr(response, "status", 200) != 200:
                raise SourceCaptureError("official FPL endpoint did not return HTTP 200")
            payload = response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise SourceCaptureError(f"official FPL source request failed: {type(exc).__name__}") from exc
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceCaptureError("official FPL endpoint did not return valid UTF-8 JSON") from exc
    if not isinstance(parsed, (dict, list)):
        raise SourceCaptureError("official FPL endpoint returned an unexpected JSON root")
    return payload


def capture_public_sources(
    event_id: int,
    output_dir: Path,
    *,
    fetch=fetch_source_bytes,
    clock=_utc_now,
    sleep=time.sleep,
) -> dict[str, Any]:
    if isinstance(event_id, bool) or not isinstance(event_id, int) or event_id < 1:
        raise ValueError("event_id must be a positive integer")
    if not isinstance(output_dir, Path) or not output_dir.is_absolute():
        raise ValueError("output_dir must be an absolute path")
    target = output_dir.resolve()
    repository_root = Path(__file__).resolve().parents[3]
    if target.is_relative_to(repository_root):
        raise ValueError("source archive must be outside the repository working tree")
    if target.exists():
        raise FileExistsError("refusing to overwrite an existing source archive directory")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(mode=stat.S_IRWXU)
    source_rows = []
    archive_rows = []
    try:
        for index, (source_id, url_factory) in enumerate(ENDPOINTS.items()):
            if index:
                sleep(0.25)
            url = url_factory(event_id)
            retrieved_at = clock()
            raw = fetch(url)
            # Parse again at the boundary to ensure the exact archived bytes are JSON.
            try:
                json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SourceCaptureError(f"{source_id}: response is not valid UTF-8 JSON") from exc
            filename = f"{source_id}.json"
            file_path = target / filename
            fd = os.open(file_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            digest = hashlib.sha256(raw).hexdigest()
            source_rows.append({
                "source_id": source_id,
                "source_version": "OFFICIAL_FPL_API_HTTP_CAPTURE",
                "source_url": url,
                "available_at_utc": retrieved_at,
                "retrieved_at_utc": retrieved_at,
                "availability_basis": "OBSERVED_RETRIEVAL_UPPER_BOUND",
                "content_sha256": digest,
                "archive_path": filename,
                "byte_count": len(raw),
            })
            archive_rows.append({
                "artifact_type": "source_snapshot",
                "source_id": source_id,
                "archive_path": filename,
                "sha256": digest,
            })
        manifest = {
            "schema_version": "1.0.0",
            "capture_status": "PUBLIC_SOURCE_BYTES_CAPTURED",
            "source_provider": "OFFICIAL_FANTASY_PREMIER_LEAGUE_API",
            "event_id": event_id,
            "captured_at_utc": _utc_now(),
            "source_snapshots": source_rows,
            "archive_manifest": archive_rows,
            "point_in_time_policy": {
                "historical_reconstruction": False,
                "usable_for_forecast_as_of": "ONLY_AT_OR_AFTER_EACH_RETRIEVED_AT_UTC",
                "availability_semantics": "RETRIEVAL_TIME_USED_AS_CONSERVATIVE_UPPER_BOUND",
                "retrospective_data_claimed_as_historical": False,
                "forecast_or_model_artifact_included": False,
            },
            "limitations": [
                "This is a current HTTP capture, not a reconstructed historical snapshot.",
                "The retrieval timestamp is the earliest defensible local observation time, not proof of provider publication time.",
                "No forecast may claim this source was used before its recorded retrieval time.",
                "The endpoint may expose mutable or retrospective data; capture alone does not establish historical point-in-time integrity.",
            ],
            "manager_data_included": False,
            "decision_weight": 0.0,
            "production_eligible": False,
        }
        manifest_path = target / "capture_manifest.json"
        fd = os.open(manifest_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return {
            "status": manifest["capture_status"],
            "event_id": event_id,
            "archive_directory": str(target),
            "manifest_path": str(manifest_path),
            "source_count": len(source_rows),
            "manager_data_included": False,
            "historical_reconstruction": False,
            "decision_weight": 0.0,
            "production_eligible": False,
        }
    except Exception:
        # Preserve partial evidence for forensic inspection, but never label it complete.
        incomplete = target / "CAPTURE_INCOMPLETE"
        try:
            incomplete.write_text("Capture failed; do not use this directory as a complete archive.\n", encoding="utf-8")
            os.chmod(incomplete, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", type=int, required=True, help="FPL Gameweek/event ID")
    parser.add_argument("--output-dir", type=Path, required=True, help="New absolute private archive directory outside repository")
    args = parser.parse_args()
    result = capture_public_sources(args.event, args.output_dir)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
