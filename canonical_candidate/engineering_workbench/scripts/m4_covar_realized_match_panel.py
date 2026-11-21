"""Join official realized FPL player-fixture outcomes to fixture score states."""
from __future__ import annotations
import csv
import hashlib
import json
import math
import os
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence


class RealizedMatchPanelError(ValueError):
    """Player-fixture and fixture-state panels cannot be joined safely."""


def build_realized_match_panel(*, player_fixture_rows: Sequence[Mapping[str, Any]],
        fixture_state_rows: Sequence[Mapping[str, Any]], season: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(season, str) or not season.strip():
        raise RealizedMatchPanelError("season is required")
    if not isinstance(player_fixture_rows, Sequence) or isinstance(player_fixture_rows, (str, bytes)) or not player_fixture_rows:
        raise RealizedMatchPanelError("player_fixture_rows must be non-empty")
    if not isinstance(fixture_state_rows, Sequence) or isinstance(fixture_state_rows, (str, bytes)) or not fixture_state_rows:
        raise RealizedMatchPanelError("fixture_state_rows must be non-empty")
    fixtures: dict[int, Mapping[str, Any]] = {}
    for row in fixture_state_rows:
        if not isinstance(row, Mapping) or row.get("season") != season:
            raise RealizedMatchPanelError("fixture state rows must be objects in the requested season")
        fid = row.get("fixture_id")
        if isinstance(fid, bool) or not isinstance(fid, int) or fid < 1 or fid in fixtures:
            raise RealizedMatchPanelError("fixture state IDs must be unique positive integers")
        for field in ("gameweek", "home_team_id", "away_team_id", "home_goals", "away_goals"):
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, int):
                raise RealizedMatchPanelError(f"fixture {fid} {field} must be an integer")
        if row["home_team_id"] == row["away_team_id"]:
            raise RealizedMatchPanelError(f"fixture {fid} has identical home/away teams")
        if row["home_goals"] < 0 or row["away_goals"] < 0:
            raise RealizedMatchPanelError(f"fixture {fid} goals cannot be negative")
        fixtures[fid] = row
    seen: set[tuple[int, int]] = set()
    result: list[dict[str, Any]] = []
    for index, player in enumerate(player_fixture_rows):
        if not isinstance(player, Mapping) or player.get("season") != season:
            raise RealizedMatchPanelError(f"player-fixture row {index} has invalid season/object")
        pid, fid = player.get("fpl_element_id"), player.get("fixture_id")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1 or isinstance(fid, bool) or not isinstance(fid, int) or fid not in fixtures:
            raise RealizedMatchPanelError(f"player-fixture row {index} has invalid player or unknown fixture")
        key = (pid, fid)
        if key in seen:
            raise RealizedMatchPanelError(f"duplicate player-fixture key {key}")
        seen.add(key)
        fixture = fixtures[fid]
        if player.get("gameweek") != fixture["gameweek"]:
            raise RealizedMatchPanelError(f"player {pid} fixture {fid} Gameweek mismatch")
        was_home = player.get("was_home")
        if not isinstance(was_home, bool):
            raise RealizedMatchPanelError(f"player {pid} fixture {fid} was_home must be boolean")
        expected_team = fixture["home_team_id"] if was_home else fixture["away_team_id"]
        expected_opponent = fixture["away_team_id"] if was_home else fixture["home_team_id"]
        if player.get("team_id_at_fixture") != expected_team or player.get("opponent_team_id") != expected_opponent:
            raise RealizedMatchPanelError(f"player {pid} fixture {fid} team/opponent orientation mismatch")
        provisional = player.get("fixture_finished_provisional")
        if provisional is not fixture.get("finished_provisional"):
            raise RealizedMatchPanelError(f"player {pid} fixture {fid} provisional flag mismatch")
        attached = dict(player)
        attached.update({
            "home_goals": fixture["home_goals"],
            "away_goals": fixture["away_goals"],
            "fixture_total_goals": fixture["home_goals"] + fixture["away_goals"],
            "fixture_goal_difference_home": fixture["home_goals"] - fixture["away_goals"],
            "fixture_result": "H" if fixture["home_goals"] > fixture["away_goals"] else "A" if fixture["away_goals"] > fixture["home_goals"] else "D",
        })
        result.append(attached)
    if not result:
        raise RealizedMatchPanelError("no player-fixture rows matched fixture states")
    report = {
        "schema_version": "1.0.0",
        "status": "PASS_STRUCTURAL_MATCHED_PANEL",
        "season": season,
        "player_fixture_row_count": len(result),
        "unique_fixture_count": len({row["fixture_id"] for row in result}),
        "unique_player_count": len({row["fpl_element_id"] for row in result}),
        "gameweeks": sorted({row["gameweek"] for row in result}),
        "provisional_fixture_count": len({row["fixture_id"] for row in result if row["fixture_finished_provisional"]}),
        "fixture_state_join": "EXACT_FIXTURE_ID_SEASON_GAMEWEEK_TEAM_ORIENTATION",
        "finality_status": "INHERITED_FROM_UPSTREAM_AUDIT_NOT_RECHECKED",
        "point_in_time_status": "RETROSPECTIVE_OFFICIAL_API_HISTORY",
        "decision_weight": 0.0,
        "production_eligible": False,
    }
    return result, report


def write_private_match_panel(rows: Sequence[Mapping[str, Any]], report: Mapping[str, Any],
        output_dir: str | Path) -> dict[str, Any]:
    root = Path(output_dir).expanduser().resolve(strict=False)
    if root.exists():
        raise RealizedMatchPanelError("output directory already exists")
    if any((parent / ".git").exists() or (parent / ".git").is_file() for parent in (root, *root.parents)):
        raise RealizedMatchPanelError("private output must be outside a Git repository")
    if not rows:
        raise RealizedMatchPanelError("rows must be non-empty")
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(mode=0o700)
    try:
        fields = list(rows[0].keys())
        csv_path = root / "fpl_realized_player_fixture_match_panel.csv"
        with csv_path.open("x", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        os.chmod(csv_path, 0o600)
        report_out = dict(report)
        raw = csv_path.read_bytes()
        report_out["panel_sha256"] = hashlib.sha256(raw).hexdigest()
        report_out["panel_bytes"] = len(raw)
        report_path = root / "match_panel_report.json"
        report_path.write_text(json.dumps(report_out, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.chmod(report_path, 0o600)
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return report_out
