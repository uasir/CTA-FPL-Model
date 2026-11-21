#!/usr/bin/env python3
"""Capture one FPL Lucho public CSV release without guessing its columns.

The CSV is the site's served odds-anchored xP variant. The page's build time
and raw-model calculation time are retained separately; neither is silently
promoted to the served CSV's forecast-generation timestamp. Output should be
kept in private, access-controlled storage and must not be committed.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

PAGE_URL = "https://fpllucho.pythonanywhere.com/forecast"
CSV_URL = "https://fpllucho.pythonanywhere.com/export/predictions.csv"
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


def fetch_bytes(url: str) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": "CTA-FPL-Model/1.0 (forecast benchmark research)"})
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise CaptureError(f"GET {url} returned HTTP {response.status}")
        return response.read(), response.headers.get("Content-Type", "")


def parse_page_time(value: str, formats: tuple[str, ...], field: str) -> datetime:
    for fmt in formats:
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    raise CaptureError(f"FPL Lucho {field} timestamp is not in a documented page format")


def capture_fpl_lucho_raw(
    *,
    season: str,
    gameweek: int,
    fetch: Callable[[str], tuple[bytes, str]] = fetch_bytes,
    clock: Callable[[], str] = utc_now,
) -> dict:
    if isinstance(gameweek, bool) or not isinstance(gameweek, int) or gameweek < 1:
        raise CaptureError("gameweek must be a positive integer")

    page_raw, page_type = fetch(PAGE_URL)
    page_captured = clock()
    csv_raw, csv_type = fetch(CSV_URL)
    csv_captured = clock()
    bootstrap_raw, bootstrap_type = fetch(BOOTSTRAP_URL)
    bootstrap_captured = clock()

    try:
        page_html = page_raw.decode("utf-8")
        bootstrap = json.loads(bootstrap_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError("FPL Lucho page or official FPL bootstrap is invalid") from exc
    if not isinstance(bootstrap, dict) or not isinstance(bootstrap.get("events"), list):
        raise CaptureError("official FPL bootstrap must contain an events array")

    extractor = TextExtractor()
    extractor.feed(page_html)
    page_text = " ".join(extractor.parts)

    built_match = re.search(
        r"Built:\\s*(\\d{1,2}-[A-Za-z]{3}-\\d{4}\\s+\\d{2}:\\d{2})\\s+UTC\\s*[·•]\\s*next GW:\\s*(\\d+)",
        page_text,
        flags=re.IGNORECASE,
    )
    if not built_match:
        raise CaptureError("FPL Lucho page is missing its Built / next GW metadata")
    built_at = parse_page_time(built_match.group(1), ("%d-%b-%Y %H:%M",), "page build")
    page_gw = int(built_match.group(2))
    if page_gw != gameweek:
        raise CaptureError(f"FPL Lucho page GW{page_gw} does not match requested GW{gameweek}")

    model_match = re.search(
        r"xP model last calculated:\\s*([A-Za-z]{3}\\s+\\d{1,2}\\s+[A-Za-z]{3}\\s+\\d{4},\\s+\\d{2}:\\d{2})\\s+UTC",
        page_text,
        flags=re.IGNORECASE,
    )
    if not model_match:
        raise CaptureError("FPL Lucho page is missing xP model calculation time")
    raw_model_calculated_at = parse_page_time(
        model_match.group(1), ("%a %d %b %Y, %H:%M",), "raw-model calculation"
    )

    try:
        reader = csv.reader(io.StringIO(csv_raw.decode("utf-8-sig")))
        headers = next(reader)
        rows = list(reader)
    except (UnicodeDecodeError, StopIteration, csv.Error) as exc:
        raise CaptureError("FPL Lucho CSV is empty or invalid") from exc
    if not headers or any(not header.strip() for header in headers) or len(set(headers)) != len(headers):
        raise CaptureError("FPL Lucho CSV has empty or duplicate headers")
    if any(len(row) != len(headers) for row in rows):
        raise CaptureError("FPL Lucho CSV contains rows with inconsistent column counts")
    if not rows:
        raise CaptureError("FPL Lucho CSV contains no forecast rows")

    def as_utc(value: str, field: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise CaptureError(f"{field} must be an ISO-8601 timestamp") from exc
        if parsed.tzinfo is None:
            raise CaptureError(f"{field} must include a timezone")
        return parsed.astimezone(timezone.utc)

    page_capture_dt = as_utc(page_captured, "page capture time")
    csv_capture_dt = as_utc(csv_captured, "CSV capture time")
    bootstrap_capture_dt = as_utc(bootstrap_captured, "official metadata capture time")
    events = [event for event in bootstrap["events"] if event.get("id") == gameweek]
    if len(events) != 1 or not isinstance(events[0].get("deadline_time"), str):
        raise CaptureError("official FPL bootstrap has no unique target Gameweek deadline")
    deadline = as_utc(events[0]["deadline_time"], "official FPL deadline")
    if any(value >= deadline for value in (
        built_at, raw_model_calculated_at, page_capture_dt, csv_capture_dt, bootstrap_capture_dt
    )):
        raise CaptureError("FPL Lucho release or capture is at or after the official deadline")
    if raw_model_calculated_at > built_at:
        raise CaptureError("raw-model calculation timestamp is later than page build timestamp")

    hashes = {
        "page": hashlib.sha256(page_raw).hexdigest(),
        "csv": hashlib.sha256(csv_raw).hexdigest(),
        "bootstrap": hashlib.sha256(bootstrap_raw).hexdigest(),
    }
    token = csv_capture_dt.strftime("%Y%m%dT%H%M%S%fZ")
    return {
        "capture_id": f"fpl-lucho-gw{gameweek}-{token}",
        "provider": {
            "name": "FPL Lucho",
            "product": "all-player four-Gameweek forecast CSV",
            "variant": "served odds-anchored xP",
            "variant_semantics": "site-served forecast; not raw model xP and not separately reported Odds xP",
            "attribution": "FPL Lucho",
        },
        "season": season,
        "target_gameweek": gameweek,
        "timing": {
            "page_built_at_utc": built_at.isoformat().replace("+00:00", "Z"),
            "raw_model_last_calculated_at_utc": raw_model_calculated_at.isoformat().replace("+00:00", "Z"),
            "page_captured_at_utc": page_capture_dt.isoformat().replace("+00:00", "Z"),
            "csv_captured_at_utc": csv_capture_dt.isoformat().replace("+00:00", "Z"),
            "official_bootstrap_captured_at_utc": bootstrap_capture_dt.isoformat().replace("+00:00", "Z"),
            "deadline_utc": deadline.isoformat().replace("+00:00", "Z"),
            "generated_at_utc": None,
            "generation_time_status": "SERVED_CSV_GENERATION_TIME_NOT_SEPARATELY_DISCLOSED",
        },
        "source": {
            "page_url": PAGE_URL,
            "csv_url": CSV_URL,
            "content_types": {"page": page_type, "csv": csv_type, "bootstrap": bootstrap_type},
            "sha256": hashes,
            "csv_raw_snapshot_id": f"sha256:{hashes['csv']}",
        },
        "schema_inspection": {
            "csv_headers": headers,
            "csv_row_count": len(rows),
            "normalization_status": "PENDING_EXPLICIT_COLUMN_MAPPING",
        },
        "raw_archives": {
            "page_html_base64": base64.b64encode(page_raw).decode("ascii"),
            "csv_base64": base64.b64encode(csv_raw).decode("ascii"),
            "official_fpl_bootstrap_base64": base64.b64encode(bootstrap_raw).decode("ascii"),
        },
        "coverage": {"csv_rows": len(rows), "forecast_window_gameweeks": 4},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", required=True)
    parser.add_argument("--gameweek", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = capture_fpl_lucho_raw(season=args.season, gameweek=args.gameweek)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
    print(json.dumps({
        "capture_id": result["capture_id"],
        "gameweek": result["target_gameweek"],
        "csv_rows": result["schema_inspection"]["csv_row_count"],
        "csv_headers": result["schema_inspection"]["csv_headers"],
        "generation_time_status": result["timing"]["generation_time_status"],
        "csv_sha256": result["source"]["sha256"]["csv"],
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
