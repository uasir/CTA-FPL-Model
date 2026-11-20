#!/usr/bin/env python3
"""Build an independent player-GW fixture reference from the pinned FPL panel.

The reference panel is the independently sourced, pinned Vaastav FPL history
export. It is not represented as an official live API snapshot. For every ABC
player-GW key, this script enumerates the full player-fixture set and verifies
fixture-level points/minutes against the ABC panel before emitting expected IDs.
Any missing key, fixture, or target mismatch fails closed.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
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


def row_key(row, season_field="season", player_field="fpl_element_id"):
    gw = number(row.get("gameweek"))
    if gw is None or not gw.is_integer():
        raise ValueError(f"Invalid gameweek in row: {row}")
    season = season_key(row.get(season_field))
    player = str(row.get(player_field) or "")
    if not season or not player:
        raise ValueError("Every row needs season and FPL element ID")
    return season, player, int(gw)


def build_expected_fixture_rows(abc_rows, fpl_rows, tolerance=1e-9):
    abc_by_key_fixture = {}
    abc_keys = set()
    abc_season_labels = {}
    for row in abc_rows:
        key = row_key(row)
        fixture = str(row.get("fixture_id") or "")
        if not fixture:
            raise ValueError(f"ABC row missing fixture ID for {key}")
        pair = (key, fixture)
        if pair in abc_by_key_fixture:
            raise ValueError(f"Duplicate ABC player-fixture row: {pair}")
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
            raise ValueError(f"FPL reference row missing fixture ID for {key}")
        pair = (key, fixture)
        if pair in fpl_by_key_fixture:
            raise ValueError(f"Duplicate FPL reference player-fixture row: {pair}")
        fpl_by_key_fixture[pair] = row

    expected = []
    mismatches = []
    missing_keys = []
    for key in sorted(abc_keys):
        fpl_fixtures = sorted(
            fixture for (candidate, fixture) in fpl_by_key_fixture if candidate == key
        )
        abc_fixtures = sorted(
            fixture for (candidate, fixture) in abc_by_key_fixture if candidate == key
        )
        if not fpl_fixtures:
            missing_keys.append(key)
            continue
        for fixture in fpl_fixtures:
            abc = abc_by_key_fixture.get((key, fixture))
            fpl = fpl_by_key_fixture[(key, fixture)]
            if abc is None:
                mismatches.append({"key": key, "fixture_id": fixture, "reason": "ABC_FIXTURE_MISSING"})
                continue
            for abc_field, fpl_field in (
                ("target_fpl_total_points", "target_total_points"),
                ("target_fpl_minutes", "target_minutes"),
            ):
                left, right = number(abc.get(abc_field)), number(fpl.get(fpl_field))
                if left is None or right is None or abs(left - right) > tolerance:
                    mismatches.append({
                        "key": key, "fixture_id": fixture, "reason": "TARGET_MISMATCH",
                        "abc_field": abc_field, "fpl_field": fpl_field,
                        "abc_value": left, "fpl_value": right,
                    })
        for fixture in abc_fixtures:
            if fixture not in fpl_fixtures:
                mismatches.append({"key": key, "fixture_id": fixture, "reason": "FPL_REFERENCE_FIXTURE_MISSING"})

        for fixture in fpl_fixtures:
            expected.append({
                "season": abc_season_labels[key],
                "fpl_element_id": key[1],
                "gameweek": key[2],
                "fixture_id": fixture,
            })

    report = {
        "status": "PASS" if not missing_keys and not mismatches else "FAIL_CLOSED",
        "abc_player_gameweeks": len(abc_keys),
        "reference_player_gameweeks_found": len(abc_keys) - len(missing_keys),
        "expected_player_fixture_rows": len(expected),
        "missing_player_gameweek_keys": missing_keys,
        "fixture_or_target_mismatches": mismatches,
        "reference_source": "PINNED_VAASTAV_FPL_HISTORY_EXPORT",
        "point_in_time_status": "RETROSPECTIVE_NOT_POINT_IN_TIME_VERIFIED",
    }
    if report["status"] != "PASS":
        raise ValueError(json.dumps(report, indent=2))
    return expected, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--abc-panel", type=Path, required=True)
    parser.add_argument("--fpl-panel", type=Path, required=True)
    parser.add_argument("--expected-fixtures-out", type=Path, required=True)
    parser.add_argument("--report-out", type=Path, required=True)
    args = parser.parse_args()
    expected, report = build_expected_fixture_rows(
        read_csv(args.abc_panel), read_csv(args.fpl_panel)
    )
    args.expected_fixtures_out.parent.mkdir(parents=True, exist_ok=True)
    with args.expected_fixtures_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "season", "fpl_element_id", "gameweek", "fixture_id"
        ])
        writer.writeheader()
        writer.writerows(expected)
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
