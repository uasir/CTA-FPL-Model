#!/usr/bin/env python3
"""Fetch and audit the openly licensed Onside FPL graded-predictions ledger.

This is a source-inspection step only. It does not train CTA, merge forecasts,
or treat the provider's published accuracy claims as independently verified.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

URL = "https://onsidearena.com/data/graded-predictions.csv"
ATTRIBUTION = "Onside Arena (2026), Fantasy Premier League — graded predictions, 2026/27; CC BY 4.0; https://onsidearena.com/data"


def parse_time(value: str):
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed
    except ValueError:
        return None


def choose_column(headers, exact=(), contains=()):
    lower = {h.lower().strip(): h for h in headers}
    for name in exact:
        if name in lower:
            return lower[name]
    for h in headers:
        value = h.lower().strip()
        if all(token in value for token in contains):
            return h
    return None


def profile(rows, headers):
    result = {}
    for header in headers:
        values = [(row.get(header) or "").strip() for row in rows]
        nonempty = [v for v in values if v]
        numeric = 0
        for value in nonempty:
            try:
                float(value)
                numeric += 1
            except ValueError:
                pass
        result[header] = {
            "nonempty": len(nonempty),
            "empty": len(values) - len(nonempty),
            "unique_nonempty": len(set(nonempty)),
            "numeric_parseable": numeric,
            "examples": nonempty[:3],
        }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=URL)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    request = urllib.request.Request(
        args.url,
        headers={"User-Agent": "CTA-FPL-Model benchmark source audit/1.0"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        raw = response.read()
        final_url = response.geturl()
        content_type = response.headers.get("Content-Type")

    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    rows = list(reader)
    if not headers:
        raise ValueError("Downloaded CSV has no header row")

    captured = choose_column(headers, exact=("captured_at",), contains=("captured", "at"))
    deadline = choose_column(headers, exact=("deadline_utc", "deadline_time"), contains=("deadline",))
    player = choose_column(
        headers,
        exact=("element", "player_code", "player_id", "playerid", "fpl_player_id"),
    )
    gameweek = choose_column(headers, exact=("gameweek", "gw", "event", "event_id"))
    actual = choose_column(
        headers,
        exact=("actual_points", "points_actual", "actual", "total_points"),
        contains=("actual", "point"),
    )
    onside = choose_column(
        headers,
        exact=("onside_xp", "onside_predicted_points", "onside_prediction"),
        contains=("onside",),
    )
    ep_next = choose_column(headers, exact=("ep_next", "fpl_ep_next"), contains=("ep", "next"))

    timing = {"checked": 0, "valid": 0, "invalid_or_missing": 0, "invalid_examples": []}
    if captured and deadline:
        for index, row in enumerate(rows, start=2):
            c = parse_time(row.get(captured, ""))
            d = parse_time(row.get(deadline, ""))
            timing["checked"] += 1
            if c is not None and d is not None and c < d:
                timing["valid"] += 1
            else:
                timing["invalid_or_missing"] += 1
                if len(timing["invalid_examples"]) < 10:
                    timing["invalid_examples"].append({
                        "csv_line": index,
                        "captured_at": row.get(captured),
                        "deadline": row.get(deadline),
                    })
    else:
        timing["status"] = "NOT_CHECKABLE_MISSING_TIMESTAMP_COLUMNS"

    duplicate_key_count = None
    duplicate_key_examples = []
    if player and gameweek:
        counts = Counter((row.get(player, "").strip(), row.get(gameweek, "").strip()) for row in rows)
        duplicate_keys = [(key, count) for key, count in counts.items() if not all(key) or count > 1]
        duplicate_key_count = sum(count - 1 for key, count in duplicate_keys if all(key))
        duplicate_key_examples = [
            {"player": key[0], "gameweek": key[1], "count": count}
            for key, count in duplicate_keys[:10]
        ]

    required_discovery = {
        "captured_at": captured,
        "deadline": deadline,
        "player_key_candidate": player,
        "gameweek_key_candidate": gameweek,
        "actual_points_candidate": actual,
        "onside_forecast_candidate": onside,
        "official_ep_next_candidate": ep_next,
    }
    timing_pass = bool(captured and deadline and timing["checked"] == len(rows)
                       and timing["invalid_or_missing"] == 0)
    key_pass = bool(player and gameweek and duplicate_key_count == 0)
    schema_pass = len(headers) == 14 and all(
        required_discovery[k] for k in (
            "captured_at", "deadline", "player_key_candidate",
            "gameweek_key_candidate", "actual_points_candidate",
            "onside_forecast_candidate", "official_ep_next_candidate",
        )
    )
    audit = {
        "status": "PASS_SOURCE_SCHEMA_AND_TIMING" if schema_pass and timing_pass and key_pass else "REVIEW_REQUIRED",
        "source_url": args.url,
        "final_url": final_url,
        "content_type": content_type,
        "retrieved_at_utc": datetime.now().astimezone().isoformat(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "license_and_attribution": ATTRIBUTION,
        "row_count": len(rows),
        "column_count": len(headers),
        "headers": headers,
        "candidate_columns": required_discovery,
        "timestamp_order": timing,
        "player_gameweek_key": {
            "available": bool(player and gameweek),
            "duplicate_rows_beyond_first": duplicate_key_count,
            "duplicate_or_incomplete_key_examples": duplicate_key_examples,
        },
        "column_profiles": profile(rows, headers),
        "preview_rows": rows[:3],
        "guardrails": [
            "This audit does not verify the provider's claimed historical accuracy.",
            "Do not train on or blend provider predictions into CTA forecasts.",
            "Join only through a verified official FPL player key and gameweek.",
            "Score Onside and official ep_next on identical eligible rows.",
            "Keep provider forecasts as a separate benchmark arm.",
        ],
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "graded_predictions.csv").write_bytes(raw)
    (args.out_dir / "onside_source_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps({
        "status": audit["status"],
        "rows": len(rows),
        "columns": headers,
        "candidate_columns": required_discovery,
        "timestamp_order": timing,
        "player_gameweek_key": audit["player_gameweek_key"],
        "sha256": audit["sha256"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
