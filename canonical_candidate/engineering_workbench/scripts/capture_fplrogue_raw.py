#!/usr/bin/env python3
"""Capture the accepted FPLRogue projection release without guessing CSV fields.

The public page's release and training timestamps are preserved separately.
Because the page's "Updated" label is not independently documented as the
forecast-generation timestamp, this capture is diagnostic-only for strict
provider-generation-time eligibility.
"""
from __future__ import annotations

import argparse
import base64
import csv
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
from typing import Any, Callable
from urllib.request import Request, urlopen

PAGE_URL = "https://www.fplrogue.com/research/projections"
CSV_URL = "https://www.fplrogue.com/research/projections.csv"
BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"


class CaptureError(ValueError):
    pass


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if value:
            self.parts.append(value)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch(url: str) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": "CTA-FPL-Model/1.0 (benchmark research)"})
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise CaptureError(f"GET {url} returned HTTP {response.status}")
        return response.read(), response.headers.get("Content-Type", "")


def parse_provider_time(value: str, field: str) -> datetime:
    try:
        parsed = datetime.strptime(value.strip(), "%d %b %Y, %H:%M GMT")
    except ValueError as exc:
        raise CaptureError(f"FPLRogue {field} has an unsupported timestamp format") from exc
    return parsed.replace(tzinfo=timezone.utc)


def capture_fplrogue_raw(
    *, season: str, gameweek: int,
    fetch_bytes: Callable[[str], tuple[bytes, str]] = fetch,
    clock: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    if isinstance(gameweek, bool) or not isinstance(gameweek, int) or gameweek < 1:
        raise CaptureError("gameweek must be a positive integer")

    page_raw, page_type = fetch_bytes(PAGE_URL)
    page_captured = clock()
    csv_raw, csv_type = fetch_bytes(CSV_URL)
    csv_captured = clock()
    bootstrap_raw, bootstrap_type = fetch_bytes(BOOTSTRAP_URL)
    bootstrap_captured = clock()

    try:
        page_html = page_raw.decode("utf-8")
        bootstrap = json.loads(bootstrap_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError("FPLRogue page or official FPL bootstrap could not be decoded") from exc
    if not isinstance(bootstrap, dict) or not isinstance(bootstrap.get("events"), list):
        raise CaptureError("official FPL bootstrap must contain an events array")

    extractor = TextExtractor()
    extractor.feed(page_html)
    page_text = " ".join(extractor.parts)

    def required(pattern: str, field: str) -> str:
        match = re.search(pattern, page_text, flags=re.IGNORECASE)
        if not match:
            raise CaptureError(f"FPLRogue page is missing {field}")
        return match.group(1).strip()

    page_gw = int(required(r"Gameweek\s+GW(\d+)", "Gameweek"))
    players = int(required(r"Players\s+(\d+)", "player count"))
    engine = required(r"Projection engine\s+([A-Za-z0-9_.-]+)", "projection engine")
    updated_text = required(r"Updated\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4},\s+\d{2}:\d{2}\s+GMT)", "release update time")
    trained_text = required(r"Model trained\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4},\s+\d{2}:\d{2}\s+GMT)", "model training time")
    if page_gw != gameweek:
        raise CaptureError(f"FPLRogue page Gameweek GW{page_gw} does not match requested GW{gameweek}")

    updated = parse_provider_time(updated_text, "Updated")
    trained = parse_provider_time(trained_text, "Model trained")
    page_capture_dt = datetime.fromisoformat(page_captured.replace("Z", "+00:00"))
    csv_capture_dt = datetime.fromisoformat(csv_captured.replace("Z", "+00:00"))
    bootstrap_capture_dt = datetime.fromisoformat(bootstrap_captured.replace("Z", "+00:00"))
    if updated > page_capture_dt or trained > updated:
        raise CaptureError("FPLRogue provider timestamps are later than capture or out of order")

    events = [event for event in bootstrap["events"] if event.get("id") == gameweek]
    if len(events) != 1:
        raise CaptureError("official FPL bootstrap does not contain exactly one target event")
    deadline_raw = events[0].get("deadline_time")
    if not isinstance(deadline_raw, str):
        raise CaptureError("official FPL deadline is missing")
    deadline = datetime.fromisoformat(deadline_raw.replace("Z", "+00:00"))
    if page_capture_dt >= deadline or csv_capture_dt >= deadline or bootstrap_capture_dt >= deadline:
        raise CaptureError("FPLRogue release capture occurred at or after the official deadline")
    if updated >= deadline or trained >= deadline:
        raise CaptureError("FPLRogue provider update/training timestamp is at or after deadline")

    try:
        csv_text = csv_raw.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(csv_text))
        headers = next(reader)
        data_rows = list(reader)
    except (UnicodeDecodeError, StopIteration, csv.Error) as exc:
        raise CaptureError("FPLRogue CSV is empty or invalid") from exc
    if not headers or len(set(headers)) != len(headers):
        raise CaptureError("FPLRogue CSV header is empty or contains duplicate columns")
    if len(data_rows) != players:
        raise CaptureError(f"FPLRogue CSV row count {len(data_rows)} does not match page player count {players}")
    if any(len(row) != len(headers) for row in data_rows):
        raise CaptureError("FPLRogue CSV contains rows with inconsistent column counts")

    hashes = {
        "page": hashlib.sha256(page_raw).hexdigest(),
        "csv": hashlib.sha256(csv_raw).hexdigest(),
        "bootstrap": hashlib.sha256(bootstrap_raw).hexdigest(),
    }
    token = page_capture_dt.strftime("%Y%m%dT%H%M%S%fZ")
    return {
        "capture_id": f"fplrogue-gw{gameweek}-{token}",
        "provider": {
            "name": "FPLRogue",
            "product": "accepted xPts projection release",
            "variant": "xpts_v1 CSV",
            "version": engine,
            "attribution": "FPLRogue",
        },
        "season": season,
        "target_gameweek": gameweek,
        "timing": {
            "provider_release_at_utc": updated.isoformat().replace("+00:00", "Z"),
            "model_trained_at_utc": trained.isoformat().replace("+00:00", "Z"),
            "page_captured_at_utc": page_capture_dt.isoformat().replace("+00:00", "Z"),
            "csv_captured_at_utc": csv_capture_dt.isoformat().replace("+00:00", "Z"),
            "official_bootstrap_captured_at_utc": bootstrap_capture_dt.isoformat().replace("+00:00", "Z"),
            "deadline_utc": deadline.isoformat().replace("+00:00", "Z"),
            "generated_at_utc": None,
            "generation_time_status": "NOT_DISCLOSED_AS_DISTINCT_FORECAST_GENERATION_TIME",
            "point_in_time_status": "PROVIDER_RELEASE_AND_CAPTURE_PRE_DEADLINE",
        },
        "source": {
            "page_url": PAGE_URL,
            "csv_url": CSV_URL,
            "csv_raw_sha256": hashes["csv"],
            "csv_raw_snapshot_id": f"sha256:{hashes['csv']}",
            "page_raw_sha256": hashes["page"],
            "bootstrap_raw_sha256": hashes["bootstrap"],
            "content_types": {"page": page_type, "csv": csv_type, "bootstrap": bootstrap_type},
        },
        "schema_inspection": {
            "csv_headers": headers,
            "csv_row_count": len(data_rows),
            "normalization_status": "PENDING_EXPLICIT_COLUMN_MAPPING",
        },
        "raw_archives": {
            "page_html_base64": base64.b64encode(page_raw).decode("ascii"),
            "csv_base64": base64.b64encode(csv_raw).decode("ascii"),
            "official_fpl_bootstrap_base64": base64.b64encode(bootstrap_raw).decode("ascii"),
        },
        "coverage": {"page_declared_players": players, "csv_rows": len(data_rows)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", required=True)
    parser.add_argument("--gameweek", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = capture_fplrogue_raw(season=args.season, gameweek=args.gameweek)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "capture_id": result["capture_id"],
        "gameweek": result["target_gameweek"],
        "csv_rows": result["schema_inspection"]["csv_row_count"],
        "csv_headers": result["schema_inspection"]["csv_headers"],
        "provider_generation_time_status": result["timing"]["generation_time_status"],
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
