#!/usr/bin/env python3
"""Attach leakage-safe official FPL form features to upcoming ABC player-fixture rows."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

BASELINE_FIELDS = (
    "fpl_total_points_prior_3_avg",
    "fpl_total_points_prior_5_avg",
    "fpl_minutes_prior_3_avg",
    "fpl_minutes_prior_5_avg",
)


def number(value):
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def parse_time(value, field):
    if not value:
        raise ValueError(f"Missing {field}")
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def complete_sum(values):
    parsed = [number(value) for value in values]
    return sum(parsed) if parsed and all(value is not None for value in parsed) else None


def complete_mean(values):
    parsed = [number(value) for value in values]
    return sum(parsed) / len(parsed) if parsed and all(value is not None for value in parsed) else None


def baseline_by_player(history_rows, target_gameweek, deadline):
    grouped = defaultdict(lambda: defaultdict(lambda: {"points": [], "minutes": []}))
    for row in history_rows:
        player = str(row.get("fpl_element_id") or "").strip()
        gw = number(row.get("gameweek"))
        kickoff = parse_time(row.get("kickoff_time"), "historical FPL kickoff_time")
        if not player or gw is None or int(gw) >= target_gameweek or kickoff >= deadline:
            continue
        bucket = grouped[player][int(gw)]
        bucket["points"].append(row.get("target_total_points"))
        bucket["minutes"].append(row.get("target_minutes"))

    result = {}
    for player, gameweeks in grouped.items():
        ordered = []
        for gw in sorted(gameweeks):
            item = gameweeks[gw]
            points = complete_sum(item["points"])
            minutes = complete_sum(item["minutes"])
            if points is not None and minutes is not None:
                ordered.append((gw, points, minutes))
        recent3, recent5 = ordered[-3:], ordered[-5:]
        result[player] = {
            "fpl_total_points_prior_3_avg": complete_mean([x[1] for x in recent3]),
            "fpl_total_points_prior_5_avg": complete_mean([x[1] for x in recent5]),
            "fpl_minutes_prior_3_avg": complete_mean([x[2] for x in recent3]),
            "fpl_minutes_prior_5_avg": complete_mean([x[2] for x in recent5]),
            "prior_gameweeks_available": len(ordered),
        }
    return result


def merge(abc_rows, history_rows, source_metadata):
    target_gw = int(source_metadata["next_deadline_event_id"])
    deadline = parse_time(source_metadata["next_deadline_time_utc"], "next_deadline_time_utc")
    fetched = parse_time(source_metadata["fetched_at_utc"], "fetched_at_utc")
    if fetched >= deadline:
        raise ValueError("Official FPL snapshot was fetched at/after the target deadline")
    if not abc_rows:
        raise ValueError("Upcoming ABC panel is empty")

    baseline = baseline_by_player(history_rows, target_gw, deadline)
    output = []
    seen = set()
    missing = 0
    for source in abc_rows:
        row = dict(source)
        player = str(row.get("fpl_element_id") or "").strip()
        fixture = str(row.get("fixture_id") or "").strip()
        gw = int(float(row.get("gameweek")))
        if not player or not fixture:
            raise ValueError("Upcoming ABC rows require FPL player and fixture identities")
        if gw != target_gw:
            raise ValueError(f"ABC target GW{gw} does not match official next deadline GW{target_gw}")
        if parse_time(row.get("features_as_of_deadline"), "ABC features_as_of_deadline") != deadline:
            raise ValueError("ABC feature deadline does not match official FPL deadline")
        if parse_time(row.get("kickoff_time"), "ABC kickoff_time") <= deadline:
            raise ValueError("Upcoming ABC target fixture must kick off after the official deadline")
        key = (player, fixture)
        if key in seen:
            raise ValueError(f"Duplicate upcoming ABC player-fixture key: {key}")
        seen.add(key)

        features = baseline.get(player, {})
        available = 0
        for field in BASELINE_FIELDS:
            value = features.get(field)
            row[field] = "" if value is None else value
            available += int(value is not None)
        row["fpl_prior_gameweeks_available"] = features.get("prior_gameweeks_available", 0)
        row["fpl_baseline_features_available"] = available
        missing += int(available < len(BASELINE_FIELDS))
        output.append(row)

    report = {
        "status": "PASS_CURRENT_ABC_INFERENCE_PANEL" if output else "NO_ROWS",
        "target_gameweek": target_gw,
        "target_deadline_utc": deadline.isoformat(),
        "fpl_source_fetched_at_utc": fetched.isoformat(),
        "rows": len(output),
        "unique_players": len({row["fpl_element_id"] for row in output}),
        "baseline_complete_rows": len(output) - missing,
        "baseline_incomplete_rows": missing,
        "baseline_feature_names": list(BASELINE_FIELDS),
        "baseline_feature_coverage": {
            field: sum(number(row.get(field)) is not None for row in output)
            for field in BASELINE_FIELDS
        },
        "point_in_time_status": "CURRENT_SNAPSHOT_FETCHED_PRE_DEADLINE; HISTORICAL API REVISIONS NOT VERIFIED",
        "decision_use_status": "RESEARCH_ONLY_NOT_FOR_PRODUCTION",
        "source_hashes": {
            "upcoming_abc_panel_sha256": None,
            "fpl_lagged_training_sha256": None,
        },
    }
    return output, report


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["fpl_element_id", "fixture_id", "gameweek"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--abc-panel", type=Path, required=True)
    parser.add_argument("--fpl-lagged-training", type=Path, required=True)
    parser.add_argument("--source-metadata", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    rows, report = merge(
        read_csv(args.abc_panel),
        read_csv(args.fpl_lagged_training),
        json.loads(args.source_metadata.read_text(encoding="utf-8")),
    )
    report["source_hashes"] = {
        "upcoming_abc_panel_sha256": sha256(args.abc_panel),
        "fpl_lagged_training_sha256": sha256(args.fpl_lagged_training),
        "fpl_source_metadata_sha256": sha256(args.source_metadata),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "cta_abc_current_inference_panel.csv", rows)
    (args.out_dir / "cta_abc_current_inference_panel_report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
