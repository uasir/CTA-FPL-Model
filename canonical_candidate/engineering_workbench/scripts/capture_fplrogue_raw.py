#!/usr/bin/env python3
"""Capture FPLRogue accepted projection release without guessing CSV columns.

The page's release-update and model-training timestamps are retained
separately. Neither is silently treated as the provider's forecast-generation
timestamp; the resulting snapshot is diagnostic-only for strict PIT use.
"""
from __future__ import annotations
import argparse, base64, csv, hashlib, io, json, re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
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
        self.parts = []

    def handle_data(self, data):
        value = " ".join(data.split())
        if value:
            self.parts.append(value)


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch(url):
    request = Request(url, headers={"User-Agent": "CTA-FPL-Model/1.0 (benchmark research)"})
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise CaptureError(f"GET {url} returned HTTP {response.status}")
        return response.read(), response.headers.get("Content-Type", "")


def provider_time(value, field):
    try:
        return datetime.strptime(value.strip(), "%d %b %Y, %H:%M GMT").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise CaptureError(f"FPLRogue {field} timestamp is not in the published format") from exc


def capture_fplrogue_raw(*, season, gameweek, fetch_bytes=fetch, clock=utc_now):
    if isinstance(gameweek, bool) or not isinstance(gameweek, int) or gameweek < 1:
        raise CaptureError("gameweek must be a positive integer")
    page_raw, page_type = fetch_bytes(PAGE_URL)
    page_captured = clock()
    csv_raw, csv_type = fetch_bytes(CSV_URL)
    csv_captured = clock()
    bootstrap_raw, bootstrap_type = fetch_bytes(BOOTSTRAP_URL)
    bootstrap_captured = clock()
    try:
        html = page_raw.decode("utf-8")
        bootstrap = json.loads(bootstrap_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError("FPLRogue page or official FPL bootstrap is invalid") from exc
    if not isinstance(bootstrap, dict) or not isinstance(bootstrap.get("events"), list):
        raise CaptureError("official FPL bootstrap must contain events")
    extractor = TextExtractor()
    extractor.feed(html)
    text = " ".join(extractor.parts)

    def required(pattern, field):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            raise CaptureError(f"FPLRogue page is missing {field}")
        return match.group(1).strip()

    page_gw = int(required(r"Gameweek\s+GW(\d+)", "Gameweek"))
    players = int(required(r"Players\s+(\d+)", "player count"))
    engine = required(r"Projection engine\s+([A-Za-z0-9_.-]+)", "projection engine")
    updated = provider_time(required(
        r"Updated\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4},\s+\d{2}:\d{2}\s+GMT)", "release update time"), "Updated")
    trained = provider_time(required(
        r"Model trained\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4},\s+\d{2}:\d{2}\s+GMT)", "training time"), "Model trained")
    if page_gw != gameweek:
        raise CaptureError(f"FPLRogue page GW{page_gw} does not match requested GW{gameweek}")
    page_dt = datetime.fromisoformat(page_captured.replace("Z", "+00:00"))
    csv_dt = datetime.fromisoformat(csv_captured.replace("Z", "+00:00"))
    bootstrap_dt = datetime.fromisoformat(bootstrap_captured.replace("Z", "+00:00"))
    if updated > page_dt or trained > updated:
        raise CaptureError("FPLRogue timestamps are later than capture or out of order")
    events = [event for event in bootstrap["events"] if event.get("id") == gameweek]
    if len(events) != 1 or not isinstance(events[0].get("deadline_time"), str):
        raise CaptureError("official FPL bootstrap has no unique target deadline")
    deadline = datetime.fromisoformat(events[0]["deadline_time"].replace("Z", "+00:00"))
    if any(value >= deadline for value in (page_dt, csv_dt, bootstrap_dt, updated, trained)):
        raise CaptureError("FPLRogue release or capture is at or after official deadline")
    try:
        reader = csv.reader(io.StringIO(csv_raw.decode("utf-8-sig")))
        headers = next(reader)
        rows = list(reader)
    except (UnicodeDecodeError, StopIteration, csv.Error) as exc:
        raise CaptureError("FPLRogue CSV is empty or invalid") from exc
    if not headers or len(set(headers)) != len(headers):
        raise CaptureError("FPLRogue CSV has empty or duplicate headers")
    if len(rows) != players:
        raise CaptureError(f"FPLRogue CSV row count {len(rows)} does not match page player count {players}")
    if any(len(row) != len(headers) for row in rows):
        raise CaptureError("FPLRogue CSV has inconsistent row widths")
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in (
        ("page", page_raw), ("csv", csv_raw), ("bootstrap", bootstrap_raw))}
    token = page_dt.strftime("%Y%m%dT%H%M%S%fZ")
    return {
        "capture_id": f"fplrogue-gw{gameweek}-{token}",
        "provider": {"name": "FPLRogue", "product": "accepted_projections_release",
                     "variant": "provider_native_xpts", "version": engine, "attribution": "FPLRogue"},
        "season": season, "target_gameweek": gameweek,
        "timing": {
            "provider_release_at_utc": updated.isoformat().replace("+00:00", "Z"),
            "model_trained_at_utc": trained.isoformat().replace("+00:00", "Z"),
            "page_captured_at_utc": page_dt.isoformat().replace("+00:00", "Z"),
            "csv_captured_at_utc": csv_dt.isoformat().replace("+00:00", "Z"),
            "official_bootstrap_captured_at_utc": bootstrap_dt.isoformat().replace("+00:00", "Z"),
            "deadline_utc": deadline.isoformat().replace("+00:00", "Z"),
            "generated_at_utc": None,
            "generation_time_status": "NOT_DISCLOSED_AS_DISTINCT_FORECAST_GENERATION_TIME",
        },
        "source": {
            "page_url": PAGE_URL, "csv_url": CSV_URL,
            "csv_raw_sha256": hashes["csv"], "csv_raw_snapshot_id": f"sha256:{hashes['csv']}",
            "page_raw_sha256": hashes["page"], "bootstrap_raw_sha256": hashes["bootstrap"],
            "content_types": {"page": page_type, "csv": csv_type, "bootstrap": bootstrap_type},
        },
        "schema_inspection": {"csv_headers": headers, "csv_row_count": len(rows),
                              "normalization_status": "PENDING_EXPLICIT_COLUMN_MAPPING"},
        "raw_archives": {
            "page_html_base64": base64.b64encode(page_raw).decode("ascii"),
            "csv_base64": base64.b64encode(csv_raw).decode("ascii"),
            "official_fpl_bootstrap_base64": base64.b64encode(bootstrap_raw).decode("ascii"),
        },
        "coverage": {"page_declared_players": players, "csv_rows": len(rows)},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", required=True)
    parser.add_argument("--gameweek", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = capture_fplrogue_raw(season=args.season, gameweek=args.gameweek)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"capture_id": result["capture_id"], "gameweek": result["target_gameweek"],
                      "csv_rows": result["schema_inspection"]["csv_row_count"],
                      "csv_headers": result["schema_inspection"]["csv_headers"],
                      "generation_time_status": result["timing"]["generation_time_status"],
                      "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

def capture_fplrogue_frozen_archive_raw(
    *, season, gameweek, snapshot_slug, snapshot_page_url, frozen_csv_url,
    fetch_bytes=fetch, clock=utc_now,
):
    """Capture one frozen archive release; distinguish publisher and retrieval times."""
    if isinstance(gameweek, bool) or not isinstance(gameweek, int) or gameweek < 1:
        raise CaptureError("gameweek must be a positive integer")
    if not isinstance(snapshot_slug, str) or not re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}-gw\\d+", snapshot_slug):
        raise CaptureError("snapshot_slug must identify a dated FPLRogue archive release")
    page_raw, page_type = fetch_bytes(snapshot_page_url)
    page_retrieved = clock()
    csv_raw, csv_type = fetch_bytes(frozen_csv_url)
    csv_retrieved = clock()
    bootstrap_raw, bootstrap_type = fetch_bytes(BOOTSTRAP_URL)
    bootstrap_retrieved = clock()
    try:
        extractor = TextExtractor()
        extractor.feed(page_raw.decode("utf-8"))
        text = " ".join(extractor.parts)
        bootstrap = json.loads(bootstrap_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError("FPLRogue archive page or official FPL bootstrap is invalid") from exc
    if not isinstance(bootstrap, dict) or not isinstance(bootstrap.get("events"), list):
        raise CaptureError("official FPL bootstrap must contain events")
    def required(pattern, field):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            raise CaptureError(f"FPLRogue archive page is missing {field}")
        return match.group(1).strip()
    page_gw = int(required(r"Gameweek\\s+GW(\\d+)", "Gameweek"))
    players = int(required(r"Players\\s+(\\d+)", "player count"))
    engine = required(r"Projection engine\\s+([A-Za-z0-9_.-]+)", "projection engine")
    captured = provider_time(required(
        r"Captured\\s+(\\d{1,2}\\s+[A-Za-z]{3}\\s+\\d{4},\\s+\\d{2}:\\d{2}\\s+GMT)",
        "publisher capture time"), "Captured")
    trained = provider_time(required(
        r"Model trained\\s+(\\d{1,2}\\s+[A-Za-z]{3}\\s+\\d{4},\\s+\\d{2}:\\d{2}\\s+GMT)",
        "model training time"), "Model trained")
    if page_gw != gameweek:
        raise CaptureError(f"FPLRogue archive page GW{page_gw} does not match requested GW{gameweek}")
    events = [event for event in bootstrap["events"] if event.get("id") == gameweek]
    if len(events) != 1 or not isinstance(events[0].get("deadline_time"), str):
        raise CaptureError("official FPL bootstrap has no unique target deadline")
    deadline = datetime.fromisoformat(events[0]["deadline_time"].replace("Z", "+00:00"))
    if captured >= deadline:
        raise CaptureError("publisher archive capture is not pre-deadline")
    if trained > captured:
        raise CaptureError("FPLRogue model training time is later than archive capture")
    try:
        for stamp in (page_retrieved, csv_retrieved, bootstrap_retrieved):
            datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        reader = csv.reader(io.StringIO(csv_raw.decode("utf-8-sig")))
        headers = next(reader)
        rows = list(reader)
    except (AttributeError, ValueError, UnicodeDecodeError, StopIteration, csv.Error) as exc:
        raise CaptureError("FPLRogue frozen CSV or retrieval timestamp is invalid") from exc
    if not headers or any(not header.strip() for header in headers) or len(set(headers)) != len(headers):
        raise CaptureError("FPLRogue frozen CSV has empty or duplicate headers")
    if len(rows) != players:
        raise CaptureError(f"FPLRogue frozen CSV row count {len(rows)} does not match page player count {players}")
    if any(len(row) != len(headers) for row in rows):
        raise CaptureError("FPLRogue frozen CSV has inconsistent row widths")
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in
              (("page", page_raw), ("csv", csv_raw), ("bootstrap", bootstrap_raw))}
    return {
        "capture_id": f"fplrogue-{snapshot_slug}-archive-intake",
        "provider": {"name": "FPLRogue", "product": "accepted_projections_release",
                     "variant": "provider_native_xpts", "version": engine, "attribution": "FPLRogue"},
        "season": season, "target_gameweek": gameweek,
        "timing": {
            "publisher_snapshot_captured_at_utc": captured.isoformat().replace("+00:00", "Z"),
            "model_trained_at_utc": trained.isoformat().replace("+00:00", "Z"),
            "page_retrieved_at_utc": page_retrieved,
            "csv_retrieved_at_utc": csv_retrieved,
            "official_bootstrap_retrieved_at_utc": bootstrap_retrieved,
            "deadline_utc": deadline.isoformat().replace("+00:00", "Z"),
            "generated_at_utc": None,
            "generation_time_status": "NOT_DISCLOSED_AS_DISTINCT_FORECAST_GENERATION_TIME",
            "point_in_time_status": "PUBLISHER_ASSERTED_FROZEN_PRE_DEADLINE_ARCHIVE",
        },
        "source": {"page_url": snapshot_page_url, "csv_url": frozen_csv_url,
                   "archive_slug": snapshot_slug, "csv_raw_sha256": hashes["csv"],
                   "csv_raw_snapshot_id": f"sha256:{hashes['csv']}",
                   "page_raw_sha256": hashes["page"], "bootstrap_raw_sha256": hashes["bootstrap"],
                   "content_types": {"page": page_type, "csv": csv_type, "bootstrap": bootstrap_type}},
        "schema_inspection": {"csv_headers": headers, "csv_row_count": len(rows),
                              "normalization_status": "PENDING_EXPLICIT_COLUMN_MAPPING"},
        "raw_archives": {"page_html_base64": base64.b64encode(page_raw).decode("ascii"),
                         "csv_base64": base64.b64encode(csv_raw).decode("ascii"),
                         "official_fpl_bootstrap_base64": base64.b64encode(bootstrap_raw).decode("ascii")},
        "coverage": {"page_declared_players": players, "csv_rows": len(rows)},
    }

