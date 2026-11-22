#!/usr/bin/env python3
"""Audit Vaastav FPL player-match archive coverage against the season fixture list.

This audit verifies fixture-level coverage and internal match metadata. It does
not assume every registered player must have a row for every fixture: the
upstream archive's player-row population is treated as authoritative and its
counts/zero-minute rows are reported, never synthesized.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"{path}: missing or duplicate CSV headers")
        return list(reader)


def truth(value: str) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def audit_archive(
    player_rows: list[dict[str, str]],
    fixtures: list[dict[str, str]],
    teams: list[dict[str, str]],
    season: str,
) -> dict:
    required_fixture = {"id", "event", "finished", "team_h", "team_a", "kickoff_time"}
    required_player = {"fixture", "round", "element", "team", "opponent_team", "was_home", "minutes", "kickoff_time"}
    if not fixtures or not teams:
        raise ValueError("fixtures and teams must contain data")
    for label, rows, required in (
        ("fixtures", fixtures, required_fixture),
        ("merged_gw", player_rows, required_player),
    ):
        if not rows and label == "merged_gw":
            continue
        missing = sorted(required - set(rows[0]))
        if missing:
            raise ValueError(f"{label}: missing required columns {missing}")

    team_names = {}
    for row in teams:
        team_id, name = (row.get("id") or "").strip(), (row.get("name") or "").strip()
        if not team_id or not name or team_id in team_names:
            raise ValueError("teams.csv contains blank or duplicate team IDs/names")
        team_names[team_id] = name

    fixture_by_id = {}
    for row in fixtures:
        fixture_id = (row.get("id") or "").strip()
        if not fixture_id or fixture_id in fixture_by_id:
            raise ValueError(f"fixtures.csv contains blank or duplicate fixture ID {fixture_id!r}")
        fixture_by_id[fixture_id] = row
        for key in ("team_h", "team_a"):
            if (row.get(key) or "").strip() not in team_names:
                raise ValueError(f"fixture {fixture_id}: unknown {key} team ID")
        if (row.get("team_h") or "").strip() == (row.get("team_a") or "").strip():
            raise ValueError(f"fixture {fixture_id}: home and away teams are identical")

    rows_by_fixture = defaultdict(list)
    seen_rows_by_key = {}
    exact_duplicate_rows = 0
    errors = []
    for index, row in enumerate(player_rows, start=2):
        fixture_id = (row.get("fixture") or "").strip()
        element = (row.get("element") or "").strip()
        if fixture_id not in fixture_by_id:
            raise ValueError(f"merged_gw row {index}: fixture {fixture_id!r} absent from fixtures.csv")
        if not element:
            raise ValueError(f"merged_gw row {index}: blank element ID")
        key = (fixture_id, element)
        previous = seen_rows_by_key.get(key)
        if previous is not None:
            if previous == row:
                # Some upstream season archives contain byte-for-byte repeated
                # player rows. They add no information and are safe to collapse.
                exact_duplicate_rows += 1
                continue
            errors.append(
                f"merged_gw row {index}: conflicting duplicate fixture/player key "
                f"{key}; previous={previous}; duplicate={row}"
            )
            rows_by_fixture[fixture_id].append(row)
            continue
        seen_rows_by_key[key] = row
        rows_by_fixture[fixture_id].append(row)

    kickoff_schedule_differences = []
    fixture_summaries = []
    expected_finished = {
        fixture_id for fixture_id, fixture in fixture_by_id.items()
        if truth(fixture.get("finished", ""))
    }
    missing_finished = sorted(expected_finished - set(rows_by_fixture), key=int)

    for fixture_id, rows in rows_by_fixture.items():
        fixture = fixture_by_id[fixture_id]
        home_id, away_id = fixture["team_h"].strip(), fixture["team_a"].strip()
        home_name, away_name = team_names[home_id], team_names[away_id]
        events = {int(float(str(row.get("round", "")).strip())) for row in rows}
        fixture_event = int(float(str(fixture.get("event", "")).strip()))
        if events != {fixture_event}:
            errors.append(f"fixture {fixture_id}: player round values {sorted(events)} disagree with fixture event")
        def normalized_kickoff(value):
            from datetime import datetime, timezone
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        kickoffs = {normalized_kickoff(row.get("kickoff_time", "")) for row in rows}
        scheduled_kickoff = normalized_kickoff(fixture.get("kickoff_time", ""))
        if len(kickoffs) != 1:
            errors.append(
                f"fixture {fixture_id}: player rows contain inconsistent kickoff values {sorted(kickoffs)}"
            )
        elif next(iter(kickoffs)) != scheduled_kickoff:
            # Historical fixture schedules can be revised after the match. The
            # player archive's consistent match timestamp is the historical
            # observation; retain the schedule discrepancy as an audit warning.
            kickoff_schedule_differences.append({
                "fixture_id": fixture_id,
                "player_archive_kickoff_utc": next(iter(kickoffs)),
                "fixture_schedule_kickoff_utc": scheduled_kickoff,
            })

        sides = set()
        for row in rows:
            team_name = (row.get("team") or "").strip()
            opponent_id = (row.get("opponent_team") or "").strip()
            home_flag = truth(row.get("was_home", ""))
            expected_team = home_name if home_flag else away_name
            expected_opponent = away_id if home_flag else home_id
            if team_name != expected_team:
                errors.append(f"fixture {fixture_id}: team/was_home mismatch for {team_name!r}")
            if opponent_id != expected_opponent:
                errors.append(f"fixture {fixture_id}: opponent_team mismatch for {team_name!r}")
            if team_name not in {home_name, away_name}:
                errors.append(f"fixture {fixture_id}: unexpected team {team_name!r}")
            sides.add("home" if home_flag else "away")

        if len(sides) != 2:
            errors.append(f"fixture {fixture_id}: archive has rows for {sorted(sides)}, expected both home and away")

        home_rows = sum(1 for r in rows if truth(r.get("was_home", "")))
        away_rows = len(rows) - home_rows
        zero_minutes = sum(1 for r in rows if (r.get("minutes") or "").strip() == "0")
        fixture_summaries.append({
            "fixture_id": fixture_id,
            "gameweek": str(fixture.get("event", "")).strip(),
            "finished": truth(fixture.get("finished", "")),
            "home_team": home_name,
            "away_team": away_name,
            "archive_player_rows": len(rows),
            "home_player_rows": home_rows,
            "away_player_rows": away_rows,
            "zero_minute_rows": zero_minutes,
        })

    if missing_finished:
        errors.append(f"finished fixtures missing all player rows: {missing_finished}")

    fixture_summaries.sort(key=lambda x: (int(x["gameweek"] or 0), int(x["fixture_id"])))
    return {
        "schema_version": 1,
        "status": "PASS_FIXTURE_ARCHIVE_AUDIT" if not errors else "FAIL_FIXTURE_ARCHIVE_AUDIT",
        "season": season,
        "schedule_fixture_count": len(fixtures),
        "finished_fixture_count": len(expected_finished),
        "fixtures_with_player_rows": len(rows_by_fixture),
        "finished_fixtures_missing_player_rows": missing_finished,
        "player_match_rows": len(player_rows),
        "unique_fixture_player_keys": len(seen_rows_by_key),
        "exact_duplicate_player_rows_collapsed": exact_duplicate_rows,
        "fixture_metadata_errors": errors,
        "fixture_kickoff_schedule_differences": kickoff_schedule_differences,
        "player_row_population_policy": (
            "No all-roster-per-fixture assumption; player rows are not synthesized. "
            "Per-fixture row counts and zero-minute rows are diagnostic only."
        ),
        "fixture_summaries": fixture_summaries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merged-gw", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--teams", type=Path, required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = audit_archive(
        read_csv(args.merged_gw), read_csv(args.fixtures), read_csv(args.teams), args.season
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS_FIXTURE_ARCHIVE_AUDIT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
