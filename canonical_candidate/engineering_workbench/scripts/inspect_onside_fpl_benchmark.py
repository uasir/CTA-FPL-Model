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
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

URL = "https://onsidearena.com/data/graded-predictions.csv"
FPL_API = "https://fantasy.premierleague.com/api"
ATTRIBUTION = "Onside Arena (2026), Fantasy Premier League — graded predictions, 2026/27; CC BY 4.0; https://onsidearena.com/data"


def fetch_bytes(url: str) -> tuple[bytes, str | None]:
    request = urllib.request.Request(
        url, headers={"User-Agent": "CTA-FPL-Model benchmark source audit/1.0"}
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read(), response.headers.get("Content-Type")


def fetch_json(url: str):
    raw, _ = fetch_bytes(url)
    return json.loads(raw.decode("utf-8"))


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
        if contains and all(token in value for token in contains):
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


def as_int(value):
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=URL)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    raw, content_type = fetch_bytes(args.url)
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

    candidate_columns = {
        "captured_at": captured,
        "deadline": deadline,
        "player_key_candidate": player,
        "gameweek_key_candidate": gameweek,
        "actual_points_candidate": actual,
        "onside_forecast_candidate": onside,
        "official_ep_next_candidate": ep_next,
    }

    # Verify the provider's player_id namespace against the live official FPL
    # bootstrap. Names are metadata only and are never used as join keys.
    identity = {
        "status": "NOT_CHECKED",
        "official_bootstrap_players": 0,
        "dataset_unique_player_ids": 0,
        "matched_official_element_ids": 0,
        "matched_official_player_codes": 0,
        "unmatched_player_id_examples": [],
    }
    official_elements = set()
    official_codes = set()
    if player:
        bootstrap = fetch_json(f"{FPL_API}/bootstrap-static/")
        official_players = bootstrap.get("elements", [])
        official_elements = {int(p["id"]) for p in official_players if p.get("id") is not None}
        official_codes = {int(p["code"]) for p in official_players if p.get("code") is not None}
        dataset_ids = {as_int(row.get(player)) for row in rows}
        dataset_ids.discard(None)
        element_matches = dataset_ids & official_elements
        code_matches = dataset_ids & official_codes
        unmatched = sorted(dataset_ids - official_elements)
        identity = {
            "status": "ELEMENT_ID_MATCH" if dataset_ids and len(element_matches) == len(dataset_ids)
                      else "PLAYER_CODE_MATCH" if dataset_ids and len(code_matches) == len(dataset_ids)
                      else "PARTIAL_OR_UNRESOLVED",
            "official_bootstrap_players": len(official_players),
            "dataset_unique_player_ids": len(dataset_ids),
            "matched_official_element_ids": len(element_matches),
            "matched_official_player_codes": len(code_matches),
            "unmatched_player_id_examples": unmatched[:20],
        }

    # Independently reconcile realized player-gameweek points against the
    # official FPL event-live endpoint. This does not validate forecast skill.
    points_check = {
        "status": "NOT_CHECKED",
        "rows_checked": 0,
        "matches": 0,
        "mismatches": 0,
        "missing_official_rows": 0,
        "mismatch_examples": [],
        "missing_examples": [],
    }
    if player and gameweek and actual and identity["status"] == "ELEMENT_ID_MATCH":
        by_gw = {}
        for row in rows:
            gw = as_int(row.get(gameweek))
            pid = as_int(row.get(player))
            if gw is not None and pid is not None:
                by_gw.setdefault(gw, []).append((pid, as_int(row.get(actual))))
        for gw, gw_rows in sorted(by_gw.items()):
            live = fetch_json(f"{FPL_API}/event/{gw}/live/")
            official_points = {
                int(item["id"]): as_int(item.get("stats", {}).get("total_points"))
                for item in live.get("elements", [])
            }
            for pid, expected in gw_rows:
                observed = official_points.get(pid)
                points_check["rows_checked"] += 1
                if observed is None or expected is None:
                    points_check["missing_official_rows"] += 1
                    if len(points_check["missing_examples"]) < 10:
                        points_check["missing_examples"].append({
                            "player_id": pid, "gameweek": gw, "dataset_actual_points": expected
                        })
                elif observed == expected:
                    points_check["matches"] += 1
                else:
                    points_check["mismatches"] += 1
                    if len(points_check["mismatch_examples"]) < 10:
                        points_check["mismatch_examples"].append({
                            "player_id": pid, "gameweek": gw,
                            "dataset_actual_points": expected,
                            "official_fpl_total_points": observed,
                        })
        points_check["status"] = (
            "PASS" if points_check["rows_checked"] == len(rows)
            and points_check["mismatches"] == 0
            and points_check["missing_official_rows"] == 0
            else "MISMATCH_OR_INCOMPLETE"
        )

    timing_pass = bool(captured and deadline and timing["checked"] == len(rows)
                       and timing["invalid_or_missing"] == 0)
    key_pass = bool(player and gameweek and duplicate_key_count == 0)
    schema_pass = len(headers) == 14 and all(candidate_columns.values())
    identity_pass = identity["status"] == "ELEMENT_ID_MATCH"
    points_pass = points_check["status"] == "PASS"
    overall_pass = schema_pass and timing_pass and key_pass and identity_pass and points_pass

    audit = {
        "status": "PASS_SOURCE_SCHEMA_TIMING_AND_OFFICIAL_FPL_RECONCILIATION"
                 if overall_pass else "REVIEW_REQUIRED",
        "source_url": args.url,
        "final_url": args.url,
        "content_type": content_type,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "license_and_attribution": ATTRIBUTION,
        "row_count": len(rows),
        "column_count": len(headers),
        "headers": headers,
        "candidate_columns": candidate_columns,
        "timestamp_order": timing,
        "player_gameweek_key": {
            "available": bool(player and gameweek),
            "duplicate_rows_beyond_first": duplicate_key_count,
            "duplicate_or_incomplete_key_examples": duplicate_key_examples,
        },
        "official_fpl_identity_reconciliation": identity,
        "official_fpl_actual_points_reconciliation": points_check,
        "column_profiles": profile(rows, headers),
        "preview_rows": rows[:3],
        "guardrails": [
            "This audit does not verify the provider's claimed forecast accuracy.",
            "Do not train on or blend provider predictions into CTA forecasts.",
            "Join only through a verified official FPL element ID and gameweek.",
            "Score Onside and official ep_next on identical eligible rows.",
            "Keep provider forecasts as a separate benchmark arm.",
            "Do not treat this FPL-only benchmark as event-derived CTA validation.",
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
        "candidate_columns": candidate_columns,
        "timestamp_order": timing,
        "player_gameweek_key": audit["player_gameweek_key"],
        "official_fpl_identity_reconciliation": identity,
        "official_fpl_actual_points_reconciliation": points_check,
        "sha256": audit["sha256"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
