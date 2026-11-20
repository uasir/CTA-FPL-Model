#!/usr/bin/env python3
"""Build a private player-GW fixture reference from the pinned FPL history panel.

The reference is a pinned retrospective Vaastav FPL export, not an official
live API snapshot. Fixture IDs and target points/minutes are reconciled at
player-fixture grain before the expected fixture set is accepted. Public logs
contain aggregate status only; player-level keys stay in runner-local files.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def number(value):
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def season_key(value):
    return str(value or "").replace("/", "-")


def row_key(row):
    gw = number(row.get("gameweek"))
    if gw is None or not gw.is_integer():
        raise ValueError("Invalid gameweek in panel row")
    season = season_key(row.get("season"))
    player = str(row.get("fpl_element_id") or "")
    if not season or not player:
        raise ValueError("Every row needs season and FPL element ID")
    return season, player, int(gw)


def build_expected_fixture_rows(abc_rows, fpl_rows, tolerance=1e-9,
                                abc_source_report=None, fpl_source_report=None):
    abc_source_report = abc_source_report or {}
    fpl_source_report = fpl_source_report or {}
    abc_by_key_fixture = {}
    abc_keys = set()
    abc_season_labels = {}
    for row in abc_rows:
        key = row_key(row)
        fixture = str(row.get("fixture_id") or "")
        if not fixture:
            raise ValueError("ABC row missing fixture ID")
        pair = (key, fixture)
        if pair in abc_by_key_fixture:
            raise ValueError("Duplicate ABC player-fixture row")
        abc_by_key_fixture[pair] = row
        abc_keys.add(key)
        abc_season_labels[key] = str(row.get("season") or "")

    fpl_by_key_fixture = {}
    for row in fpl_rows:
        key = row_key(row)
        if key not in abc_keys:
            continue
        fixture = str(row.get("fixture_id") or "")
        if not fixture:
            raise ValueError("FPL reference row missing fixture ID")
        pair = (key, fixture)
        if pair in fpl_by_key_fixture:
            raise ValueError("Duplicate FPL reference player-fixture row")
        fpl_by_key_fixture[pair] = row

    expected = []
    mismatch_reasons = Counter()
    missing_key_count = 0
    for key in sorted(abc_keys):
        fpl_fixtures = sorted(
            fixture for (candidate, fixture) in fpl_by_key_fixture if candidate == key
        )
        abc_fixtures = sorted(
            fixture for (candidate, fixture) in abc_by_key_fixture if candidate == key
        )
        if not fpl_fixtures:
            missing_key_count += 1
            continue
        for fixture in fpl_fixtures:
            abc = abc_by_key_fixture.get((key, fixture))
            fpl = fpl_by_key_fixture[(key, fixture)]
            if abc is None:
                mismatch_reasons["ABC_FIXTURE_MISSING"] += 1
                continue
            for abc_field, fpl_field in (
                ("target_fpl_total_points", "target_total_points"),
                ("target_fpl_minutes", "target_minutes"),
            ):
                left, right = number(abc.get(abc_field)), number(fpl.get(fpl_field))
                if left is None or right is None or abs(left - right) > tolerance:
                    mismatch_reasons["TARGET_MISMATCH"] += 1
        for fixture in abc_fixtures:
            if fixture not in fpl_fixtures:
                mismatch_reasons["FPL_REFERENCE_FIXTURE_MISSING"] += 1

        for fixture in fpl_fixtures:
            expected.append({
                "season": abc_season_labels[key],
                "fpl_element_id": key[1],
                "gameweek": key[2],
                "fixture_id": fixture,
            })

    fpl_files = fpl_source_report.get("source_files", [])
    report = {
        "status": "PASS" if missing_key_count == 0 and not mismatch_reasons else "FAIL_CLOSED",
        "abc_player_gameweeks": len(abc_keys),
        "reference_player_gameweeks_found": len(abc_keys) - missing_key_count,
        "missing_player_gameweek_key_count": missing_key_count,
        "expected_player_fixture_rows": len(expected),
        "fixture_or_target_mismatch_count": sum(mismatch_reasons.values()),
        "mismatch_reason_counts": dict(sorted(mismatch_reasons.items())),
        "abc_source_hashes": abc_source_report.get("source_hashes", {}),
        "abc_source_attribution": abc_source_report.get("attribution", ""),
        "fpl_reference_source": "PINNED_VAASTAV_FPL_HISTORY_EXPORT",
        "fpl_source_commit": fpl_source_report.get("source_commit"),
        "fpl_panel_sha256": fpl_source_report.get("panel_sha256"),
        "fpl_source_file_hashes": {
            str(item.get("season")): item.get("sha256") for item in fpl_files
        },
        "point_in_time_status": "RETROSPECTIVE_NOT_POINT_IN_TIME_VERIFIED",
    }
    return expected, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--abc-panel", type=Path, required=True)
    parser.add_argument("--fpl-panel", type=Path, required=True)
    parser.add_argument("--abc-source-report", type=Path, required=True)
    parser.add_argument("--fpl-panel-report", type=Path, required=True)
    parser.add_argument("--expected-fixtures-out", type=Path, required=True)
    parser.add_argument("--report-out", type=Path, required=True)
    args = parser.parse_args()
    expected, report = build_expected_fixture_rows(
        read_csv(args.abc_panel),
        read_csv(args.fpl_panel),
        abc_source_report=json.loads(args.abc_source_report.read_text(encoding="utf-8")),
        fpl_source_report=json.loads(args.fpl_panel_report.read_text(encoding="utf-8")),
    )
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if report["status"] != "PASS":
        return 2
    args.expected_fixtures_out.parent.mkdir(parents=True, exist_ok=True)
    with args.expected_fixtures_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "season", "fpl_element_id", "gameweek", "fixture_id"
        ])
        writer.writeheader()
        writer.writerows(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
