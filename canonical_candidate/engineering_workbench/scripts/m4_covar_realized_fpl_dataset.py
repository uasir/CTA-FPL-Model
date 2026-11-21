#!/usr/bin/env python3
"""Build a season-scoped realized FPL player-fixture and player-GW outcome panel.

Consumes the existing official FPL ingestion outputs. It never fills missing
player-fixture rows with zero and never claims retrospective API history is
point-in-time. The output is research-only and should be archived privately.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import stat
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

PLAYER_FIELDS = ("season", "fpl_element_id")
FIXTURE_FIELDS = ("season", "fixture_id", "gameweek", "kickoff_time",
                  "team_h_id", "team_a_id", "finished", "finished_provisional")
OUTCOME_FIELDS = (
    "minutes", "total_points", "goals_scored", "assists", "clean_sheets",
    "goals_conceded", "own_goals", "penalties_saved", "penalties_missed",
    "yellow_cards", "red_cards", "saves", "bonus", "bps",
)
REQUIRED_NUMERIC = ("minutes", "total_points")
AGGREGATE_FIELDS = (
    "minutes", "total_points", "goals_scored", "assists", "clean_sheets",
    "goals_conceded", "own_goals", "penalties_saved", "penalties_missed",
    "yellow_cards", "red_cards", "saves", "bonus", "bps",
)
FIXTURE_OUTPUT_FIELDS = (
    "season", "gameweek", "fixture_id", "kickoff_time", "fpl_element_id",
    "team_id_at_fixture", "opponent_team_id", "was_home", *OUTCOME_FIELDS,
    "played",
)
GAMEWEEK_OUTPUT_FIELDS = (
    "season", "gameweek", "fpl_element_id", "fixtures_count",
    "team_ids", "opponent_team_ids", *AGGREGATE_FIELDS, "played_any_fixture",
)


class RealizedFplDatasetError(ValueError):
    """Input data cannot form a trustworthy realized-outcome panel."""


def _read_csv(path: Path) -> tuple[list[dict[str, str]], bytes]:
    if not path.is_file():
        raise RealizedFplDatasetError(f"required input file missing: {path.name}")
    raw = path.read_bytes()
    try:
        rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise RealizedFplDatasetError(f"cannot parse {path.name}: {exc}") from exc
    if not rows:
        raise RealizedFplDatasetError(f"{path.name} contains no data rows")
    return rows, raw


def _integer(value: Any, field: str, *, nullable: bool = False) -> int | None:
    if value in (None, "") and nullable:
        return None
    if isinstance(value, bool):
        raise RealizedFplDatasetError(f"{field} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise RealizedFplDatasetError(f"{field} must be an integer") from exc
    if str(value).strip() not in (str(number), f"{number}.0"):
        raise RealizedFplDatasetError(f"{field} must be an integer")
    return number


def _truth(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    raise RealizedFplDatasetError(f"{field} must be an explicit boolean")


def _season_check(rows: Iterable[dict[str, str]], season: str, label: str) -> None:
    mismatches = sorted({str(row.get("season", "")) for row in rows if row.get("season") != season})
    if mismatches:
        raise RealizedFplDatasetError(f"{label} contains season mismatch: {mismatches[:5]}")


def build_realized_panel(
    players: list[dict[str, str]],
    fixtures: list[dict[str, str]],
    player_fixture: list[dict[str, str]],
    *,
    season: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(season, str) or not season.strip():
        raise RealizedFplDatasetError("season must be a non-empty season label")
    for rows, label in ((players, "players"), (fixtures, "fixtures"),
                        (player_fixture, "player_fixture")):
        _season_check(rows, season, label)

    player_ids = [_integer(row.get("fpl_element_id"), "fpl_element_id") for row in players]
    if len(player_ids) != len(set(player_ids)):
        raise RealizedFplDatasetError("duplicate season-scoped FPL player IDs")
    player_set = set(player_ids)

    fixture_by_id: dict[int, dict[str, Any]] = {}
    for row in fixtures:
        fid = _integer(row.get("fixture_id"), "fixture_id")
        if fid in fixture_by_id:
            raise RealizedFplDatasetError(f"duplicate season-scoped fixture ID {fid}")
        gw = _integer(row.get("gameweek"), "fixture.gameweek", nullable=True)
        if gw is None:
            continue
        finished = _truth(row.get("finished"), f"fixture {fid}.finished")
        if not finished:
            continue
        home = _integer(row.get("team_h_id"), f"fixture {fid}.team_h_id")
        away = _integer(row.get("team_a_id"), f"fixture {fid}.team_a_id")
        if home == away:
            raise RealizedFplDatasetError(f"fixture {fid} has identical home/away team IDs")
        fixture_by_id[fid] = {
            "gameweek": gw, "kickoff_time": row.get("kickoff_time", ""),
            "team_h_id": home, "team_a_id": away,
        }
    if not fixture_by_id:
        raise RealizedFplDatasetError("no finished, gameweek-assigned fixtures available")

    seen: set[tuple[int, int]] = set()
    fixture_rows: list[dict[str, Any]] = []
    gw_groups: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    ignored_unfinished = 0
    for index, source in enumerate(player_fixture):
        pid = _integer(source.get("fpl_element_id"), f"player_fixture[{index}].fpl_element_id")
        fid = _integer(source.get("fixture_id"), f"player_fixture[{index}].fixture_id")
        if pid not in player_set:
            raise RealizedFplDatasetError(f"player_fixture row references unknown season player {pid}")
        if fid not in fixture_by_id:
            # Unfinished or unassigned fixture rows are not realized targets.
            ignored_unfinished += 1
            continue
        key = (pid, fid)
        if key in seen:
            raise RealizedFplDatasetError(f"duplicate season-scoped player-fixture key {key}")
        seen.add(key)
        fixture = fixture_by_id[fid]
        source_gw = _integer(source.get("gameweek"), f"player_fixture[{index}].gameweek", nullable=True)
        if source_gw != fixture["gameweek"]:
            raise RealizedFplDatasetError(f"player {pid} fixture {fid} Gameweek disagrees with official fixture feed")
        minutes = _integer(source.get("minutes"), f"player_fixture[{index}].minutes")
        if minutes < 0 or minutes > 120:
            raise RealizedFplDatasetError(f"player {pid} fixture {fid} minutes outside [0,120]")
        outcome: dict[str, Any] = {}
        for field in OUTCOME_FIELDS:
            value = source.get(field)
            if value in (None, "") and field not in REQUIRED_NUMERIC:
                outcome[field] = None
            else:
                parsed = _integer(value, f"player_fixture[{index}].{field}")
                if field != "total_points" and parsed < 0:
                    raise RealizedFplDatasetError(f"{field} cannot be negative")
                outcome[field] = parsed
        was_home = _truth(source.get("was_home"), f"player_fixture[{index}].was_home")
        team_id = fixture["team_h_id"] if was_home else fixture["team_a_id"]
        opponent_id = fixture["team_a_id"] if was_home else fixture["team_h_id"]
        record = {
            "season": season, "gameweek": fixture["gameweek"], "fixture_id": fid,
            "kickoff_time": fixture["kickoff_time"], "fpl_element_id": pid,
            "team_id_at_fixture": team_id, "opponent_team_id": opponent_id,
            "was_home": was_home, **outcome, "played": minutes > 0,
        }
        fixture_rows.append(record)
        gw_groups[(pid, fixture["gameweek"])].append(record)

    if not fixture_rows:
        raise RealizedFplDatasetError("no player-fixture rows matched finished official fixtures")

    gameweek_rows = []
    for (pid, gw), items in sorted(gw_groups.items(), key=lambda item: (item[0][1], item[0][0])):
        row: dict[str, Any] = {
            "season": season, "gameweek": gw, "fpl_element_id": pid,
            "fixtures_count": len(items),
            "team_ids": ";".join(map(str, sorted({x["team_id_at_fixture"] for x in items}))),
            "opponent_team_ids": ";".join(map(str, sorted({x["opponent_team_id"] for x in items}))),
        }
        for field in AGGREGATE_FIELDS:
            values = [item[field] for item in items]
            row[field] = None if any(value is None for value in values) else sum(values)
        row["played_any_fixture"] = any(item["played"] for item in items)
        gameweek_rows.append(row)

    report = {
        "schema_version": "1.0.0",
        "season": season,
        "status": "PASS_STRUCTURAL_ONLY",
        "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_OFFICIAL_API_HISTORY",
        "fixture_rows": len(fixture_rows),
        "player_gameweek_rows": len(gameweek_rows),
        "unique_players_with_observed_rows": len({row["fpl_element_id"] for row in fixture_rows}),
        "finished_gameweeks": sorted({row["gameweek"] for row in fixture_rows}),
        "finished_fixtures": len(fixture_by_id),
        "ignored_unfinished_or_unassigned_player_fixture_rows": ignored_unfinished,
        "duplicate_player_fixture_keys": 0,
        "missing_player_fixture_rows_zero_filled": 0,
        "gameweek_aggregation": "sum official fixture outcomes; preserve DGW/TGW as multiple fixtures",
        "player_identity": "season-scoped FPL element ID; fixture identity is season-scoped fixture ID",
        "limitations": [
            "Rows absent from element-summary history are missing, not assumed zero.",
            "Current API history is retrospective and does not establish original deadline-time source vintage.",
            "Structural validation does not establish licensing, historical completeness or predictive validity.",
        ],
    }
    return fixture_rows, gameweek_rows, report


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_archive(input_dir: Path, output_dir: Path, *, repository_root: Path | None = None) -> dict[str, Any]:
    if not input_dir.is_dir():
        raise RealizedFplDatasetError("input_dir must be an existing directory")
    if not output_dir.is_absolute():
        raise RealizedFplDatasetError("output_dir must be absolute")
    target = output_dir.resolve()
    if repository_root is not None and target.is_relative_to(repository_root.resolve()):
        raise RealizedFplDatasetError("realized-outcome archive must be outside repository")
    if target.exists():
        raise FileExistsError("refusing to overwrite existing realized-outcome archive")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(mode=stat.S_IRWXU)

    try:
        names = ("fpl_players.csv", "fpl_fixtures.csv", "fpl_player_fixture.csv",
                 "ingestion_report.json", "source_metadata.json")
        inputs = {}
        raw_hashes = {}
        for name in names[:3]:
            rows, raw = _read_csv(input_dir / name)
            inputs[name] = rows
            raw_hashes[name] = hashlib.sha256(raw).hexdigest()
        for name in names[3:]:
            path = input_dir / name
            if not path.is_file():
                raise RealizedFplDatasetError(f"required input file missing: {name}")
            raw = path.read_bytes()
            raw_hashes[name] = hashlib.sha256(raw).hexdigest()
            try:
                inputs[name] = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RealizedFplDatasetError(f"cannot parse {name}") from exc

        report_in = inputs["ingestion_report.json"]
        if report_in.get("status") != "PASS":
            raise RealizedFplDatasetError("official FPL ingestion report must have status PASS")
        if report_in.get("summary_fetch_errors"):
            raise RealizedFplDatasetError("official FPL ingestion contains summary fetch errors")
        season = str(report_in.get("season", "")).strip()
        if not season:
            raise RealizedFplDatasetError("ingestion report must declare season")
        fixture_rows, gameweek_rows, report = build_realized_panel(
            inputs["fpl_players.csv"], inputs["fpl_fixtures.csv"],
            inputs["fpl_player_fixture.csv"], season=season,
        )
        _write_csv(target / "fpl_realized_player_fixture.csv", FIXTURE_OUTPUT_FIELDS, fixture_rows)
        _write_csv(target / "fpl_realized_player_gameweek.csv", GAMEWEEK_OUTPUT_FIELDS, gameweek_rows)
        report["input_artifact_sha256"] = raw_hashes
        report["source_metadata"] = inputs["source_metadata.json"]
        report["archive_artifacts"] = {
            name: hashlib.sha256((target / name).read_bytes()).hexdigest()
            for name in ("fpl_realized_player_fixture.csv", "fpl_realized_player_gameweek.csv")
        }
        (target / "dataset_manifest.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.chmod(target / "dataset_manifest.json", stat.S_IRUSR | stat.S_IWUSR)
        for name in ("fpl_realized_player_fixture.csv", "fpl_realized_player_gameweek.csv"):
            os.chmod(target / name, stat.S_IRUSR | stat.S_IWUSR)
        return {
            "status": report["status"], "season": season,
            "fixture_rows": report["fixture_rows"],
            "player_gameweek_rows": report["player_gameweek_rows"],
            "archive_directory": str(target), "point_in_time_status": report["point_in_time_status"],
        }
    except Exception:
        marker = target / "ARCHIVE_INCOMPLETE"
        marker.write_text("Build failed; do not use this archive.\n", encoding="utf-8")
        os.chmod(marker, stat.S_IRUSR | stat.S_IWUSR)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = build_archive(args.input_dir, args.output_dir)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
