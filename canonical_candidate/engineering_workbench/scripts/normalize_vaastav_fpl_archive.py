#!/usr/bin/env python3
"""Normalize one Vaastav season archive into canonical FPL player-match rows.

Identity is resolved by joining merged_gw.element to players_raw.id within the
same season, then carrying players_raw.code as the stable cross-season fpl_code.
No name-based identity matching or synthetic fixture rows are permitted.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

POSITION_BY_ELEMENT_TYPE = {"1": "GKP", "2": "DEF", "3": "MID", "4": "FWD"}
MATCH_FIELDS = (
    "xP", "assists", "bonus", "bps", "clean_sheets", "creativity",
    "expected_assists", "expected_goal_involvements", "expected_goals",
    "expected_goals_conceded", "goals_conceded", "goals_scored", "ict_index",
    "influence", "minutes", "own_goals", "penalties_missed", "penalties_saved",
    "red_cards", "saves", "selected", "starts", "threat", "total_points",
    "transfers_balance", "transfers_in", "transfers_out", "value", "yellow_cards",
    "clearances_blocks_interceptions", "defensive_contribution", "recoveries", "tackles",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"{path}: missing CSV header")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"{path}: duplicate CSV column names")
        return list(reader)


def require_columns(rows: list[dict[str, str]], required: set[str], label: str) -> None:
    if not rows:
        raise ValueError(f"{label}: file contains no data rows")
    available = set(rows[0])
    missing = sorted(required - available)
    if missing:
        raise ValueError(f"{label}: missing required columns: {missing}")


def normalize_archive(
    merged: list[dict[str, str]],
    roster: list[dict[str, str]],
    teams: list[dict[str, str]],
    season: str,
) -> tuple[list[dict[str, str]], dict]:
    require_columns(merged, {
        "element", "fixture", "round", "position", "team", "opponent_team",
        "kickoff_time", "was_home", *MATCH_FIELDS,
    }, "merged_gw")
    require_columns(roster, {
        "id", "code", "element_type", "team", "web_name",
    }, "players_raw")
    require_columns(teams, {"id", "name"}, "teams")

    by_element: dict[str, dict[str, str]] = {}
    seen_codes: set[str] = set()
    for line, player in enumerate(roster, start=2):
        element = (player.get("id") or "").strip()
        code = (player.get("code") or "").strip()
        if not element or not code:
            raise ValueError(f"players_raw row {line}: blank id or stable code")
        if element in by_element:
            raise ValueError(f"players_raw row {line}: duplicate element id {element}")
        if code in seen_codes:
            raise ValueError(f"players_raw row {line}: duplicate stable fpl_code {code}")
        if (player.get("element_type") or "").strip() not in POSITION_BY_ELEMENT_TYPE:
            raise ValueError(f"players_raw row {line}: unsupported element_type")
        by_element[element] = player
        seen_codes.add(code)

    team_by_id: dict[str, dict[str, str]] = {}
    team_by_name: dict[str, dict[str, str]] = {}
    for line, team in enumerate(teams, start=2):
        team_id = (team.get("id") or "").strip()
        team_name = (team.get("name") or "").strip()
        if not team_id or not team_name:
            raise ValueError(f"teams row {line}: blank id or name")
        if team_id in team_by_id or team_name in team_by_name:
            raise ValueError(f"teams row {line}: duplicate team id or name")
        team_by_id[team_id] = team
        team_by_name[team_name] = team

    output = []
    seen_keys = set()
    unknown_elements = set()
    unknown_teams = set()
    for line, row in enumerate(merged, start=2):
        element = (row.get("element") or "").strip()
        fixture = (row.get("fixture") or "").strip()
        gameweek = (row.get("round") or "").strip()
        if not element or not fixture or not gameweek:
            raise ValueError(f"merged_gw row {line}: missing element, fixture or round")
        player = by_element.get(element)
        if player is None:
            unknown_elements.add(element)
            continue

        fpl_code = player["code"].strip()
        key = (season, fixture, fpl_code)
        if key in seen_keys:
            raise ValueError(f"merged_gw row {line}: duplicate (season, fixture, fpl_code) {key}")
        seen_keys.add(key)

        position = (row.get("position") or "").strip().upper()
        if position == "GK":
            position = "GKP"
        expected_position = POSITION_BY_ELEMENT_TYPE[player["element_type"].strip()]
        if position != expected_position:
            raise ValueError(
                f"merged_gw row {line}: position {position!r} conflicts with roster {expected_position!r}"
            )

        team_name = (row.get("team") or "").strip()
        team = team_by_name.get(team_name)
        opponent_id = (row.get("opponent_team") or "").strip()
        opponent = team_by_id.get(opponent_id)
        if team is None:
            unknown_teams.add(team_name)
            continue
        if opponent is None:
            unknown_teams.add(f"id:{opponent_id}")
            continue

        kickoff = (row.get("kickoff_time") or "").strip()
        if not kickoff:
            raise ValueError(f"merged_gw row {line}: missing kickoff_time")
        try:
            datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"merged_gw row {line}: invalid kickoff_time {kickoff!r}") from exc

        normalized = {
            "season": season,
            "fixture_id": fixture,
            "gameweek": gameweek,
            "fpl_code": fpl_code,
            "fpl_element_id": element,
            "player_name": (player.get("web_name") or "").strip(),
            "position": position,
            "team_id": (team.get("id") or "").strip(),
            "team_name": team_name,
            "opponent_team_id": opponent_id,
            "opponent_team_name": (opponent.get("name") or "").strip(),
            "kickoff_time": kickoff,
            "was_home": (row.get("was_home") or "").strip(),
        }
        for field in MATCH_FIELDS:
            normalized[field] = (row.get(field) or "").strip()
        output.append(normalized)

    if unknown_elements:
        raise ValueError(f"merged_gw contains element IDs absent from season roster: {sorted(unknown_elements)[:20]}")
    if unknown_teams:
        raise ValueError(f"merged_gw contains teams absent from teams.csv: {sorted(unknown_teams)[:20]}")
    if not output:
        raise ValueError("No canonical player-match rows produced")

    output.sort(key=lambda r: (r["kickoff_time"], int(r["fixture_id"]), int(r["fpl_code"])))
    report = {
        "schema_version": 1,
        "status": "PASS_CANONICAL_FPL_ARCHIVE_NORMALIZATION",
        "season": season,
        "input_merged_rows": len(merged),
        "roster_players": len(roster),
        "teams": len(teams),
        "canonical_player_match_rows": len(output),
        "unique_fpl_codes_in_matches": len({r["fpl_code"] for r in output}),
        "unique_fixtures": len({r["fixture_id"] for r in output}),
        "unique_gameweeks": sorted({r["gameweek"] for r in output}, key=int),
        "grain": ["season", "fixture_id", "fpl_code"],
        "identity_join": "merged_gw.element -> season players_raw.id -> stable players_raw.code",
        "name_matching": "NOT_USED",
        "position_normalization": "GK -> GKP; validated against players_raw.element_type",
        "source_completeness": "No missing fixture/player rows are inferred; archive coverage must be checked separately",
    }
    return output, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merged-gw", type=Path, required=True)
    parser.add_argument("--players-raw", type=Path, required=True)
    parser.add_argument("--teams", type=Path, required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    rows, report = normalize_archive(
        read_csv(args.merged_gw), read_csv(args.players_raw), read_csv(args.teams), args.season
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
