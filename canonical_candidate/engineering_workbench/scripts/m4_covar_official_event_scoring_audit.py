#!/usr/bin/env python3
"""Reconcile the 2026/27 CoVar event scorer with official FPL fixture explain data.

Only public official FPL event-live and bootstrap payloads are read. Raw payloads
remain in memory; the report contains IDs, counts and mismatch diagnostics only.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import stat
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from m4_covar_fpl_api_replay_fetch import (
    BASE_URL,
    OfficialFplFetchError,
    fetch_official_json,
)
from m4_covar_fpl_event_scoring import (
    CovarEventScoringError,
    calculate_fpl_points_2026_27,
)


class OfficialEventScoringAuditError(ValueError):
    """Raised when official event scoring evidence is incomplete or malformed."""


_IDENTIFIER_MAP = {
    "minutes": "minutes",
    "goals_scored": "goals",
    "assists": "assists",
    "saves": "saves",
    "penalties_saved": "penalty_saves",
    "defensive_contribution": "defensive_contribution_count",
    "penalties_missed": "penalty_misses",
    "bonus": "bonus_points",
    "goals_conceded": "goals_conceded_while_on_pitch",
    "yellow_cards": "yellow_cards",
    "red_cards": "red_cards",
    "own_goals": "own_goals",
    "clean_sheets": "clean_sheet",
}


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise OfficialEventScoringAuditError(f"{label} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise OfficialEventScoringAuditError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise OfficialEventScoringAuditError(f"{label} must be finite")
    return number


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise OfficialEventScoringAuditError(f"{label} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise OfficialEventScoringAuditError(f"{label} must be a positive integer") from exc
    if parsed < 1 or str(value).strip() not in (str(parsed), f"{parsed}.0"):
        raise OfficialEventScoringAuditError(f"{label} must be a positive integer")
    return parsed


def _fixture_events(explain_row: Mapping[str, Any], player_id: int) -> tuple[dict[str, Any], float, list[str]]:
    fixture_id = _positive_int(explain_row.get("fixture"), "explain.fixture")
    raw_stats = explain_row.get("stats")
    if not isinstance(raw_stats, list):
        raise OfficialEventScoringAuditError(f"player {player_id} fixture {fixture_id} stats must be a list")

    values: dict[str, float] = {}
    official_points = 0.0
    unknown_positive: list[str] = []
    for item in raw_stats:
        if not isinstance(item, Mapping):
            raise OfficialEventScoringAuditError("fixture explain stat must be an object")
        identifier = item.get("identifier")
        if not isinstance(identifier, str) or not identifier:
            raise OfficialEventScoringAuditError("fixture explain stat requires identifier")
        if identifier in values:
            raise OfficialEventScoringAuditError(
                f"player {player_id} fixture {fixture_id} has duplicate stat identifier {identifier}"
            )
        value = _finite_number(item.get("value", 0), f"{identifier}.value")
        points = _finite_number(item.get("points", 0), f"{identifier}.points")
        values[identifier] = value
        official_points += points
        if identifier not in _IDENTIFIER_MAP and points != 0:
            unknown_positive.append(identifier)

    events: dict[str, Any] = {
        "minutes": values.get("minutes", 0),
        "goals": values.get("goals_scored", 0),
        "assists": values.get("assists", 0),
        "saves": values.get("saves", 0),
        "penalty_saves": values.get("penalties_saved", 0),
        "defensive_contribution_count": values.get("defensive_contribution", 0),
        "penalty_misses": values.get("penalties_missed", 0),
        "bonus_points": values.get("bonus", 0),
        "goals_conceded_while_on_pitch": values.get("goals_conceded", 0),
        "yellow_cards": values.get("yellow_cards", 0),
        "red_cards": values.get("red_cards", 0),
        "own_goals": values.get("own_goals", 0),
        "clean_sheet": values.get("clean_sheets", 0) > 0,
        "goalkeeping_duties": values.get("saves", 0) > 0 or values.get("penalties_saved", 0) > 0,
    }
    return events, official_points, unknown_positive


def audit_official_event_payload(
    live_payload: Mapping[str, Any],
    bootstrap_payload: Mapping[str, Any],
    *,
    event_id: int,
) -> dict[str, Any]:
    if not isinstance(live_payload, Mapping) or not isinstance(bootstrap_payload, Mapping):
        raise OfficialEventScoringAuditError("live and bootstrap payloads must be objects")
    event = _positive_int(event_id, "event_id")
    raw_players = live_payload.get("elements")
    raw_bootstrap_players = bootstrap_payload.get("elements")
    if not isinstance(raw_players, list) or not raw_players:
        raise OfficialEventScoringAuditError("official live payload must contain elements")
    if not isinstance(raw_bootstrap_players, list) or not raw_bootstrap_players:
        raise OfficialEventScoringAuditError("official bootstrap must contain elements")

    positions: dict[int, str] = {}
    for row in raw_bootstrap_players:
        if not isinstance(row, Mapping):
            raise OfficialEventScoringAuditError("bootstrap player row must be an object")
        player_id = _positive_int(row.get("id"), "bootstrap player id")
        element_type = _positive_int(row.get("element_type"), f"player {player_id}.element_type")
        role = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}.get(element_type)
        if role is None or player_id in positions:
            raise OfficialEventScoringAuditError("bootstrap player IDs or positions are invalid")
        positions[player_id] = role

    seen_players: set[int] = set()
    mismatches: list[dict[str, Any]] = []
    unknown_identifiers: dict[str, int] = {}
    player_rows = 0
    fixture_rows = 0
    matched_rows = 0
    official_points_total = 0.0
    calculated_points_total = 0.0
    fixture_ids: set[int] = set()

    for player in raw_players:
        if not isinstance(player, Mapping):
            raise OfficialEventScoringAuditError("live player row must be an object")
        player_id = _positive_int(player.get("id"), "live player id")
        if player_id in seen_players or player_id not in positions:
            raise OfficialEventScoringAuditError("live player IDs must be unique and present in bootstrap")
        seen_players.add(player_id)
        player_rows += 1
        stats = player.get("stats")
        explain = player.get("explain")
        if not isinstance(stats, Mapping) or not isinstance(explain, list):
            raise OfficialEventScoringAuditError(f"player {player_id} requires stats and explain")
        official_gameweek_points = _finite_number(
            stats.get("total_points"), f"player {player_id}.stats.total_points"
        )
        official_explain_total = 0.0
        calculated_gameweek_total = 0.0
        player_fixture_ids: set[int] = set()

        for explain_row in explain:
            if not isinstance(explain_row, Mapping):
                raise OfficialEventScoringAuditError("player explain row must be an object")
            fixture_id = _positive_int(explain_row.get("fixture"), "explain.fixture")
            if fixture_id in player_fixture_ids:
                raise OfficialEventScoringAuditError(
                    f"player {player_id} has duplicate fixture {fixture_id} in explain"
                )
            player_fixture_ids.add(fixture_id)
            fixture_ids.add(fixture_id)
            events, official_fixture_points, unknown = _fixture_events(explain_row, player_id)
            for identifier in unknown:
                unknown_identifiers[identifier] = unknown_identifiers.get(identifier, 0) + 1
            try:
                calculated = calculate_fpl_points_2026_27(positions[player_id], events)
            except CovarEventScoringError as exc:
                raise OfficialEventScoringAuditError(
                    f"player {player_id} fixture {fixture_id} cannot be scored: {exc}"
                ) from exc
            calculated_fixture_points = float(calculated["fpl_points"])
            fixture_rows += 1
            official_explain_total += official_fixture_points
            calculated_gameweek_total += calculated_fixture_points
            if unknown or not math.isclose(
                calculated_fixture_points, official_fixture_points, rel_tol=0, abs_tol=1e-9
            ):
                mismatches.append({
                    "event_id": event,
                    "player_id": player_id,
                    "fixture_id": fixture_id,
                    "position": positions[player_id],
                    "calculated_points": calculated_fixture_points,
                    "official_explain_points": official_fixture_points,
                    "point_difference": calculated_fixture_points - official_fixture_points,
                    "unknown_positive_identifiers": unknown,
                })
            else:
                matched_rows += 1

        if not math.isclose(
            official_explain_total, official_gameweek_points, rel_tol=0, abs_tol=1e-9
        ):
            mismatches.append({
                "event_id": event,
                "player_id": player_id,
                "fixture_id": None,
                "position": positions[player_id],
                "calculated_points": calculated_gameweek_total,
                "official_explain_points": official_explain_total,
                "official_gameweek_points": official_gameweek_points,
                "point_difference": calculated_gameweek_total - official_gameweek_points,
                "unknown_positive_identifiers": [],
                "mismatch_type": "EXPLAIN_TO_GAMEWEEK_TOTAL",
            })
        official_points_total += official_gameweek_points
        calculated_points_total += calculated_gameweek_total

    return {
        "event_id": event,
        "player_rows": player_rows,
        "fixture_rows": fixture_rows,
        "distinct_fixture_ids": sorted(fixture_ids),
        "matched_fixture_rows": matched_rows,
        "mismatch_count": len(mismatches),
        "unknown_positive_identifiers": unknown_identifiers,
        "official_gameweek_points_sum": official_points_total,
        "calculated_gameweek_points_sum": calculated_points_total,
        "gameweek_total_difference": calculated_points_total - official_points_total,
        "mismatches": mismatches,
    }


def audit_completed_gameweeks(
    event_ids: list[int],
    *,
    fetch: Callable[[str], dict[str, Any]] = fetch_official_json,
    sleep: Callable[[float], None] = time.sleep,
    min_gameweeks: int = 1,
) -> dict[str, Any]:
    if not event_ids or any(isinstance(event, bool) or not isinstance(event, int) or event < 1 for event in event_ids):
        raise ValueError("event_ids must be a non-empty list of positive integers")
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("event_ids must be unique")
    bootstrap = fetch(f"{BASE_URL}/bootstrap-static/")
    events = bootstrap.get("events")
    if not isinstance(events, list):
        raise OfficialFplFetchError("bootstrap event status is missing")
    status: dict[int, list[Mapping[str, Any]]] = {}
    for row in events:
        if isinstance(row, Mapping) and isinstance(row.get("id"), int) and not isinstance(row.get("id"), bool):
            status.setdefault(row["id"], []).append(row)

    reports = []
    skipped = []
    failures = []
    for event in event_ids:
        matching = status.get(event, [])
        if len(matching) != 1:
            failures.append({"event_id": event, "reason": "missing_or_duplicate_bootstrap_event"})
            continue
        if matching[0].get("finished") is not True or matching[0].get("data_checked") is not True:
            skipped.append(event)
            continue
        try:
            live = fetch(f"{BASE_URL}/event/{event}/live/")
            reports.append(audit_official_event_payload(live, bootstrap, event_id=event))
        except (OfficialFplFetchError, OfficialEventScoringAuditError) as exc:
            failures.append({"event_id": event, "error_type": type(exc).__name__, "reason": str(exc)[:240]})
        sleep(0.25)

    if len(reports) < min_gameweeks:
        raise OfficialFplFetchError(
            f"only {len(reports)} final-scored Gameweeks audited; minimum required is {min_gameweeks}"
        )
    mismatch_count = sum(row["mismatch_count"] for row in reports)
    return {
        "schema_version": "1.0.0",
        "status": "PASS" if mismatch_count == 0 and not failures else "FAIL",
        "requested_event_ids": event_ids,
        "audited_event_ids": [row["event_id"] for row in reports],
        "skipped_event_ids": skipped,
        "failed_event_ids": [row["event_id"] for row in failures],
        "gameweek_count": len(reports),
        "player_rows": sum(row["player_rows"] for row in reports),
        "fixture_rows": sum(row["fixture_rows"] for row in reports),
        "matched_fixture_rows": sum(row["matched_fixture_rows"] for row in reports),
        "mismatch_count": mismatch_count,
        "unknown_positive_identifiers": {
            key: sum(row["unknown_positive_identifiers"].get(key, 0) for row in reports)
            for key in sorted({key for row in reports for key in row["unknown_positive_identifiers"]})
        },
        "official_gameweek_points_sum": sum(row["official_gameweek_points_sum"] for row in reports),
        "calculated_gameweek_points_sum": sum(row["calculated_gameweek_points_sum"] for row in reports),
        "gameweek_reports": reports,
        "failures": failures,
        "decision_weight": 0.0,
        "production_eligible": False,
    }


def write_private_report(report: Mapping[str, Any], output: Path) -> Path:
    if not output.is_absolute():
        raise ValueError("output must be absolute")
    target = output.resolve()
    repository_root = Path(__file__).resolve().parents[3]
    if target.is_relative_to(repository_root):
        raise ValueError("output must be outside the repository")
    if target.exists():
        raise FileExistsError("refusing to overwrite existing report")
    target.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(target, flags, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", required=True, help="Comma-separated Gameweek IDs")
    parser.add_argument("--output", type=Path, required=True, help="Absolute output path outside repository")
    args = parser.parse_args()
    event_ids = [int(value) for value in args.events.split(",")]
    report = audit_completed_gameweeks(event_ids)
    target = write_private_report(report, args.output)
    print(json.dumps({
        "status": report["status"],
        "gameweek_count": report["gameweek_count"],
        "player_rows": report["player_rows"],
        "fixture_rows": report["fixture_rows"],
        "matched_fixture_rows": report["matched_fixture_rows"],
        "mismatch_count": report["mismatch_count"],
        "skipped_event_ids": report["skipped_event_ids"],
        "failed_event_ids": report["failed_event_ids"],
        "output": str(target),
        "decision_weight": 0.0,
        "production_eligible": False,
    }, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
