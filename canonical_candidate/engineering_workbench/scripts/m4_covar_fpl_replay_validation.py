#!/usr/bin/env python3
"""Private local replay validator for M4's synthetic full-Gameweek lineup resolver.

The input contains a normalized lineup, final Gameweek player outcomes and the
official final FPL picks multipliers. Keep real manager-level replay files
outside the repository and never upload them to CI or commit them.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from m4_covar_lineup_resolver import resolve_fpl_lineup


class CovarFplReplayError(ValueError):
    """Raised when a replay case is incomplete or malformed."""


_FORBIDDEN_MANAGER_KEYS = {
    "entry_id", "manager_id", "manager_name", "manager_entry_id",
    "exact_rank", "overall_rank", "rank",
}


def _assert_private_input_is_anonymized(value: Any, path: str = "replay") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in _FORBIDDEN_MANAGER_KEYS:
                raise CovarFplReplayError(
                    f"replay input contains restricted manager identifier field: {path}.{key}"
                )
            _assert_private_input_is_anonymized(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _assert_private_input_is_anonymized(nested, f"{path}[{index}]")


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise CovarFplReplayError(f"{label} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CovarFplReplayError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise CovarFplReplayError(f"{label} must be finite")
    return number


def played_from_official_element_stats(stats: Mapping[str, Any]) -> bool:
    """Derive Gameweek played status from official minutes and card statistics."""
    minutes = _finite(stats.get("minutes"), "minutes")
    yellow = _finite(stats.get("yellow_cards"), "yellow_cards")
    red = _finite(stats.get("red_cards"), "red_cards")
    if minutes < 0 or yellow < 0 or red < 0:
        raise CovarFplReplayError("minutes and card counts cannot be negative")
    return minutes > 0 or yellow > 0 or red > 0


def _expected_pick_multipliers(resolution: Mapping[str, Any], player_ids: Sequence[str]) -> dict[str, int]:
    scoring = set(map(str, resolution["scoring_player_ids"]))
    multipliers = {str(pid): (1 if str(pid) in scoring else 0) for pid in player_ids}
    active_captain = resolution["active_captain_id"]
    if active_captain is not None:
        multipliers[str(active_captain)] = int(resolution["captain_multiplier"])
    return multipliers


def validate_official_replay_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Compare resolver output with official final FPL pick multipliers."""
    if not isinstance(case, Mapping):
        raise CovarFplReplayError("replay case must be an object")
    _assert_private_input_is_anonymized(case)
    lineup = case.get("lineup")
    outcomes = case.get("player_outcomes")
    official = case.get("official_final")
    if not isinstance(lineup, Mapping) or not isinstance(outcomes, Mapping) or not isinstance(official, Mapping):
        raise CovarFplReplayError("lineup, player_outcomes and official_final are required")

    player_ids = [str(pid) for pid in lineup.get("player_ids", [])]
    if len(player_ids) != 15 or len(set(player_ids)) != 15:
        raise CovarFplReplayError("lineup must contain exactly 15 unique players")
    if set(map(str, outcomes)) != set(player_ids):
        raise CovarFplReplayError("player_outcomes must cover exactly all 15 squad players")

    minutes = {}
    played = {}
    points = {}
    for pid in player_ids:
        row = outcomes[pid]
        if not isinstance(row, Mapping):
            raise CovarFplReplayError(f"player outcome for {pid} must be an object")
        minutes[pid] = row.get("minutes")
        played[pid] = row.get("played")
        points[pid] = row.get("fpl_points")
        if not isinstance(played[pid], bool):
            raise CovarFplReplayError(f"player outcome for {pid} requires explicit played boolean")

    picks = official.get("picks")
    official_points = official.get("player_total_points")
    if not isinstance(picks, list) or len(picks) != 15:
        raise CovarFplReplayError("official_final.picks must contain all 15 players")
    if not isinstance(official_points, Mapping) or set(map(str, official_points)) != set(player_ids):
        raise CovarFplReplayError("official player_total_points must cover all 15 players")

    official_multipliers: dict[str, int] = {}
    captain_ids: list[str] = []
    vice_ids: list[str] = []
    for pick in picks:
        if not isinstance(pick, Mapping):
            raise CovarFplReplayError("each official pick must be an object")
        pid = str(pick.get("element", ""))
        if pid not in set(player_ids) or pid in official_multipliers:
            raise CovarFplReplayError("official picks contain an unknown or duplicate player")
        multiplier = pick.get("multiplier")
        if isinstance(multiplier, bool) or multiplier not in (0, 1, 2, 3):
            raise CovarFplReplayError("official pick multiplier must be 0, 1, 2 or 3")
        if not isinstance(pick.get("is_captain"), bool) or not isinstance(pick.get("is_vice_captain"), bool):
            raise CovarFplReplayError("official picks require explicit captain and vice-captain booleans")
        if pick["is_captain"]:
            captain_ids.append(pid)
        if pick["is_vice_captain"]:
            vice_ids.append(pid)
        official_multipliers[pid] = int(multiplier)
    if len(captain_ids) != 1 or len(vice_ids) != 1 or captain_ids[0] == vice_ids[0]:
        raise CovarFplReplayError("official picks must identify distinct captain and vice-captain")

    official_player_points = {
        str(pid): _finite(value, f"official player_total_points[{pid}]")
        for pid, value in official_points.items()
    }
    scenario_points = {
        pid: _finite(points[pid], f"player_outcomes[{pid}].fpl_points")
        for pid in player_ids
    }
    point_mismatches = [
        pid for pid in player_ids
        if not math.isclose(scenario_points[pid], official_player_points[pid], rel_tol=0, abs_tol=1e-9)
    ]

    resolution = resolve_fpl_lineup(
        player_ids=player_ids,
        starting_player_ids=lineup["starting_player_ids"],
        starting_goalkeeper_id=str(lineup["starting_goalkeeper_id"]),
        reserve_goalkeeper_id=str(lineup["reserve_goalkeeper_id"]),
        bench_order=lineup["bench_order"],
        player_positions=lineup["player_positions"],
        captain_id=str(lineup["captain_id"]),
        vice_captain_id=str(lineup["vice_captain_id"]),
        player_minutes=minutes,
        player_played=played,
        player_points=scenario_points,
        active_chip=lineup.get("active_chip"),
        mode=case.get("mode", "REGULAR_GW"),
    )
    expected_multipliers = _expected_pick_multipliers(resolution, player_ids)
    multiplier_mismatches = [
        pid for pid in player_ids
        if expected_multipliers[pid] != official_multipliers[pid]
    ]
    official_total = sum(
        official_player_points[pid] * official_multipliers[pid]
        for pid in player_ids
    )
    official_active_captain = next(
        (pid for pid, multiplier in official_multipliers.items() if multiplier in (2, 3)),
        None,
    )
    active_captain_mismatch = official_active_captain != resolution["active_captain_id"]
    team_points_mismatch = False
    supplied_team_points = official.get("team_points")
    if supplied_team_points is not None:
        team_points_mismatch = not math.isclose(
            _finite(supplied_team_points, "official_final.team_points"),
            official_total,
            rel_tol=0,
            abs_tol=1e-9,
        )

    passed = not point_mismatches and not multiplier_mismatches and not active_captain_mismatch and not team_points_mismatch
    return {
        "replay_id": str(case.get("replay_id", "local-replay")),
        "status": "PASS" if passed else "FAIL",
        "scenario_mode": resolution["mode"],
        "official_multiplier_match": not multiplier_mismatches,
        "player_points_match": not point_mismatches,
        "active_captain_match": not active_captain_mismatch,
        "official_team_points_reconcile": not team_points_mismatch,
        "mismatched_player_multipliers": multiplier_mismatches,
        "mismatched_player_points": point_mismatches,
        "resolver_active_captain_id": resolution["active_captain_id"],
        "official_active_captain_id": official_active_captain,
        "resolver_total_points": resolution["total_points"],
        "official_total_points_from_picks": official_total,
        "resolved_starting_xi": resolution["resolved_starting_xi"],
        "resolver_substitutions": resolution["substitutions"],
        "production_eligible": False,
        "decision_weight": 0.0,
    }


def validate_replay_batch(document: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(document, Mapping) or not isinstance(document.get("replays"), list) or not document["replays"]:
        raise CovarFplReplayError("input must contain a non-empty replays list")
    results = [validate_official_replay_case(case) for case in document["replays"]]
    passed = sum(row["status"] == "PASS" for row in results)
    return {
        "schema_version": "1.0.0",
        "status": "PASS" if passed == len(results) else "FAIL",
        "replay_count": len(results),
        "passed_count": passed,
        "failed_count": len(results) - passed,
        "results": results,
        "production_eligible": False,
        "decision_weight": 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Private normalized replay JSON, outside the repository")
    args = parser.parse_args()
    input_path = args.input.resolve()
    repository_root = Path(__file__).resolve().parents[3]
    if not input_path.is_absolute() or input_path.is_relative_to(repository_root):
        raise ValueError("--input must be an absolute private local path outside the repository")
    report = validate_replay_batch(json.loads(input_path.read_text(encoding="utf-8")))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
