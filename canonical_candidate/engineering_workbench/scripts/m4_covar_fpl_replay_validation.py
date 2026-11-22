#!/usr/bin/env python3
"""Validate normalized official FPL lineup replays against final picks.

The validator is shared by the single-manager replay, aggregate-only public
field stress-test (rank-stratified across five Overall pages), and synthetic
full-Gameweek scoring test paths. Real manager-level picks are consumed in
memory and are never retained in reports.
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
        minutes[pid] = _finite(row.get("minutes"), f"player_outcomes[{pid}].minutes")
        played[pid] = row.get("played")
        points[pid] = row.get("fpl_points")
        if minutes[pid] < 0:
            raise CovarFplReplayError(f"player outcome for {pid} has negative minutes")
        if not isinstance(played[pid], bool):
            raise CovarFplReplayError(f"player outcome for {pid} requires explicit played boolean")
        if minutes[pid] > 0 and not played[pid]:
            raise CovarFplReplayError(f"player outcome for {pid} played status conflicts with positive minutes")

    picks = official.get("picks")
    official_points = official.get("player_total_points")
    if not isinstance(picks, list) or len(picks) != 15:
        raise CovarFplReplayError("official_final.picks must contain all 15 players")
    if not isinstance(official_points, Mapping) or set(map(str, official_points)) != set(player_ids):
        raise CovarFplReplayError("official player_total_points must cover all 15 players")

    official_multipliers: dict[str, int] = {}
    captain_ids: list[str] = []
    vice_ids: list[str] = []
    for index, pick in enumerate(picks, start=1):
        if not isinstance(pick, Mapping):
            raise CovarFplReplayError("each official pick must be an object")
        pid = str(pick.get("element", ""))
        if pid not in set(player_ids) or pid in official_multipliers:
            raise CovarFplReplayError("official picks contain an unknown or duplicate player")
        position = pick.get("position")
        if isinstance(position, bool) or position != index or pid != player_ids[index - 1]:
            raise CovarFplReplayError("official pick order must match lineup positions 1 through 15")
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
    if captain_ids[0] != str(lineup.get("captain_id")):
        raise CovarFplReplayError("official captain does not match submitted lineup captain")
    if vice_ids[0] != str(lineup.get("vice_captain_id")):
        raise CovarFplReplayError("official vice-captain does not match submitted lineup vice-captain")

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
    # Final pick multipliers are the authoritative record of which squad
    # players actually scored. The separate API automatic_subs field is kept
    # only as a diagnostic: live captures have shown it can disagree with
    # final picks even when every multiplier and team point reconciles.
    automatic_substitution_match = not multiplier_mismatches
    official_automatic_subs = official.get("automatic_subs")
    automatic_substitution_metadata_match = None
    automatic_substitution_mismatches: list[dict[str, Any]] = []
    if official_automatic_subs is not None and str(lineup.get("active_chip") or "").lower() != "bboost":
        if not isinstance(official_automatic_subs, list):
            raise CovarFplReplayError("official_final.automatic_subs must be a list")
        actual_pairs: list[tuple[str, str]] = []
        for index, row in enumerate(official_automatic_subs):
            if not isinstance(row, Mapping):
                raise CovarFplReplayError("each official automatic substitution must be an object")
            element_in = str(row.get("element_in", ""))
            element_out = str(row.get("element_out", ""))
            if element_in not in player_ids or element_out not in player_ids or element_in == element_out:
                raise CovarFplReplayError("official automatic substitution contains an invalid player pair")
            actual_pairs.append((element_in, element_out))
        expected_pairs = [
            (str(row["in"]), str(row["out"]))
            for row in resolution["substitutions"]
        ]
        if len(actual_pairs) != len(set(actual_pairs)):
            raise CovarFplReplayError("official automatic substitutions contain duplicate pairs")
        automatic_substitution_metadata_match = sorted(actual_pairs) == sorted(expected_pairs)
        if not automatic_substitution_metadata_match:
            automatic_substitution_mismatches.append({
                "resolver_pairs": sorted(expected_pairs),
                "api_metadata_pairs": sorted(actual_pairs),
            })
    official_total = sum(
        official_player_points[pid] * official_multipliers[pid]
        for pid in player_ids
    )
    official_active_captain = next(
        (pid for pid, multiplier in official_multipliers.items() if multiplier in (2, 3)),
        None,
    )
    active_captain_mismatch = official_active_captain != resolution["active_captain_id"]
    supplied_team_points = official.get("team_points")
    team_points_reconciliation_basis = None
    team_points_mismatch = None
    if supplied_team_points is not None:
        reported_points = _finite(supplied_team_points, "official_final.team_points")
        transfer_cost = _finite(
            official.get("event_transfers_cost", 0),
            "official_final.event_transfers_cost",
        )
        if transfer_cost < 0 or not transfer_cost.is_integer():
            raise CovarFplReplayError("official_final.event_transfers_cost must be a non-negative integer")
        if math.isclose(reported_points, official_total, rel_tol=0, abs_tol=1e-9):
            team_points_reconciliation_basis = "ENTRY_HISTORY_POINTS_MATCH"
            team_points_mismatch = False
        elif math.isclose(reported_points + transfer_cost, official_total, rel_tol=0, abs_tol=1e-9):
            team_points_reconciliation_basis = "ENTRY_HISTORY_POINTS_PLUS_TRANSFER_COST_MATCH"
            team_points_mismatch = False
        else:
            team_points_mismatch = True

    passed = (
        not point_mismatches
        and not multiplier_mismatches
        and not active_captain_mismatch
        and automatic_substitution_match is not False
        and team_points_mismatch is not True
    )
    event_id = case.get("event_id")
    if event_id is not None and (
        isinstance(event_id, bool) or not isinstance(event_id, int) or event_id < 1
    ):
        raise CovarFplReplayError("event_id must be a positive integer when supplied")
    return {
        "replay_id": str(case.get("replay_id", "local-replay")),
        "event_id": event_id,
        "status": "PASS" if passed else "FAIL",
        "scenario_mode": resolution["mode"],
        "active_chip": str(lineup.get("active_chip") or "NONE"),
        "official_multiplier_match": not multiplier_mismatches,
        "player_points_match": not point_mismatches,
        "active_captain_match": not active_captain_mismatch,
        "official_automatic_substitution_match": automatic_substitution_match,
        "automatic_substitution_metadata_match": automatic_substitution_metadata_match,
        "mismatched_automatic_substitutions": automatic_substitution_mismatches,
        "official_team_points_reconcile": (not team_points_mismatch) if team_points_mismatch is not None else None,
        "team_points_reconciliation_basis": team_points_reconciliation_basis,
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
    by_event: dict[str, dict[str, int]] = {}
    by_mode: dict[str, int] = {}
    by_chip: dict[str, int] = {}
    for row in results:
        event_key = str(row["event_id"]) if row["event_id"] is not None else "unknown"
        event_summary = by_event.setdefault(
            event_key, {"replay_count": 0, "passed_count": 0, "failed_count": 0}
        )
        event_summary["replay_count"] += 1
        event_summary["passed_count"] += int(row["status"] == "PASS")
        event_summary["failed_count"] += int(row["status"] == "FAIL")
        mode = str(row["scenario_mode"])
        by_mode[mode] = by_mode.get(mode, 0) + 1
        chip = str(row["active_chip"])
        by_chip[chip] = by_chip.get(chip, 0) + 1
    return {
        "schema_version": "1.1.0",
        "status": "PASS" if passed == len(results) else "FAIL",
        "replay_count": len(results),
        "passed_count": passed,
        "failed_count": len(results) - passed,
        "gameweek_count": len([key for key in by_event if key != "unknown"]),
        "gameweeks": sorted(int(key) for key in by_event if key != "unknown"),
        "by_gameweek": by_event,
        "by_mode": by_mode,
        "by_chip": by_chip,
        "multiplier_mismatch_replays": sum(not row["official_multiplier_match"] for row in results),
        "player_points_mismatch_replays": sum(not row["player_points_match"] for row in results),
        "captain_mismatch_replays": sum(not row["active_captain_match"] for row in results),
        "automatic_substitution_mismatch_replays": sum(row["official_automatic_substitution_match"] is False for row in results),
        "team_points_reconciliation_cases": sum(row["official_team_points_reconcile"] is not None for row in results),
        "team_points_reconciliation_failures": sum(row["official_team_points_reconcile"] is False for row in results),
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
