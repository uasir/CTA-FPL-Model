#!/usr/bin/env python3
"""Reconcile the local FPL manager scorer against a completed official FPL event.

Input is an archived, post-finalisation manager picks response plus official
event live points and the local scorer's hold-plan result. This module is an
independent oracle comparison; it does not admit REAL_CANDIDATE records into
the historical evaluation cohort.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


class OfficialReconciliationError(ValueError):
    """Raised when official FPL data cannot independently reconcile a score."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise OfficialReconciliationError(message)


def reconcile_official_manager_result(
    local_score: Mapping[str, Any],
    official_picks: Mapping[str, Any],
    official_live: Mapping[str, Any],
    *,
    manager_team_id: int,
    target_gameweek: int,
    expected_starting_xi: list[int],
    expected_bench_order: list[int],
    expected_reserve_goalkeeper_id: int,
    expected_captain_id: int,
    expected_vice_captain_id: int,
) -> dict[str, Any]:
    """Compare local substitutions/captaincy/score with FPL's completed-GW oracle."""
    _require(isinstance(local_score, Mapping), "local_score must be an object")
    _require(isinstance(official_picks, Mapping), "official_picks must be an object")
    _require(isinstance(official_live, Mapping), "official_live must be an object")

    history = official_picks.get("entry_history")
    _require(isinstance(history, Mapping), "official picks response requires entry_history")
    _require(history.get("event") == target_gameweek, "official picks response gameweek mismatch")
    _require(isinstance(history.get("points"), int), "official entry_history.points must be an integer")
    _require("event_transfers_cost" in history,
             "official entry_history requires event_transfers_cost")
    transfer_cost = history["event_transfers_cost"]
    _require(isinstance(transfer_cost, int) and not isinstance(transfer_cost, bool) and transfer_cost >= 0,
             "official event_transfers_cost must be a non-negative integer")
    _require(official_picks.get("active_chip") in (None, ""),
             "chip gameweeks are outside the initial reconciliation contract")

    picks = official_picks.get("picks")
    _require(isinstance(picks, list) and len(picks) == 15,
             "official picks must contain exactly 15 players")
    _require(all(isinstance(p, Mapping) for p in picks), "official picks rows must be objects")
    ids = [p.get("element") for p in picks]
    positions = [p.get("position") for p in picks]
    _require(all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in ids),
             "official picks contain invalid player IDs")
    _require(len(set(ids)) == 15, "official picks contain duplicate player IDs")
    _require(sorted(positions) == list(range(1, 16)),
             "official picks positions must be the unique range 1..15")
    # Historical picks positions reflect the post-autosub lineup. Reverse each
    # official autosub pair to reconstruct the deadline-frozen XI and bench order.
    automatic_subs = official_picks.get("automatic_subs", [])
    _require(isinstance(automatic_subs, list), "official automatic_subs must be a list")
    position_by_id = {p["element"]: p["position"] for p in picks}
    for sub in automatic_subs:
        _require(isinstance(sub, Mapping), "official automatic substitution rows must be objects")
        player_in, player_out = sub.get("element_in"), sub.get("element_out")
        _require(isinstance(player_in, int) and not isinstance(player_in, bool)
                 and isinstance(player_out, int) and not isinstance(player_out, bool),
                 "official automatic substitution has invalid player IDs")
        _require(player_in in position_by_id and player_out in position_by_id,
                 "official automatic substitution references a player outside the picks")
        in_position, out_position = position_by_id[player_in], position_by_id[player_out]
        _require(in_position <= 11 and out_position >= 12,
                 "official autosub positions are not in post-substitution XI/bench order")
        position_by_id[player_in], position_by_id[player_out] = out_position, in_position
    by_deadline_position = sorted(picks, key=lambda p: position_by_id[p["element"]])
    deadline_xi = [p["element"] for p in by_deadline_position[:11]]
    deadline_bench = [p["element"] for p in by_deadline_position[12:15]]
    deadline_reserve_gk = by_deadline_position[11]["element"]
    _require(set(deadline_xi) == set(expected_starting_xi),
             "official deadline starting XI does not match the frozen local hold plan")
    _require(deadline_bench == expected_bench_order,
             "official deadline outfield bench order does not match the frozen local hold plan")
    _require(deadline_reserve_gk == expected_reserve_goalkeeper_id,
             "official deadline reserve goalkeeper does not match the frozen local hold plan")

    captain_ids = [p["element"] for p in picks if p.get("is_captain") is True]
    vice_ids = [p["element"] for p in picks if p.get("is_vice_captain") is True]
    _require(captain_ids == [expected_captain_id], "official captain does not match the frozen hold plan")
    _require(vice_ids == [expected_vice_captain_id], "official vice-captain does not match the frozen hold plan")

    live_elements = official_live.get("elements")
    _require(isinstance(live_elements, list), "official live response requires elements list")
    live: dict[int, Mapping[str, Any]] = {}
    for row in live_elements:
        _require(isinstance(row, Mapping), "official live element rows must be objects")
        player_id = row.get("id")
        stats = row.get("stats")
        _require(isinstance(player_id, int) and not isinstance(player_id, bool),
                 "official live element has invalid ID")
        _require(player_id not in live, "official live response contains duplicate player IDs")
        _require(isinstance(stats, Mapping), f"official live stats missing for player {player_id}")
        _require(isinstance(stats.get("total_points"), int),
                 f"official total_points missing for player {player_id}")
        live[player_id] = stats
    _require(set(ids).issubset(live), "official live points do not cover all 15 manager picks")

    multipliers = [p.get("multiplier") for p in picks]
    _require(all(isinstance(v, int) and not isinstance(v, bool) and v in (0, 1, 2)
                 for v in multipliers),
             "unsupported official multiplier or chip multiplier")
    official_gross = sum(live[p["element"]]["total_points"] * p["multiplier"] for p in picks)
    # FPL entry_history.points is the gross event score; transfer cost is exposed separately.
    official_net = official_gross - transfer_cost
    _require(official_gross == history["points"],
             f"official picks/live gross mismatch: calculated={official_gross}, "
             f"entry_history.points={history['points']}, "
             f"separate_transfer_cost={transfer_cost}, net_after_hit={official_net}")

    official_pairs = []
    for sub in automatic_subs:
        _require(isinstance(sub, Mapping), "official automatic substitution rows must be objects")
        player_in, player_out = sub.get("element_in"), sub.get("element_out")
        _require(isinstance(player_in, int) and not isinstance(player_in, bool)
                 and isinstance(player_out, int) and not isinstance(player_out, bool),
                 "official automatic substitution has invalid player IDs")
        if "event" in sub:
            _require(sub["event"] == target_gameweek,
                     "official automatic substitution gameweek mismatch")
        official_pairs.append((player_out, player_in))
    _require(len(set(official_pairs)) == len(official_pairs),
             "official automatic_subs contains duplicate substitution pairs")

    local_pairs = [
        (sub["player_out_id"], sub["player_in_id"])
        for sub in local_score.get("outfield_substitutions", [])
    ]
    goalkeeper_sub = local_score.get("goalkeeper_substitution")
    if goalkeeper_sub is not None:
        local_pairs.append((goalkeeper_sub["player_out_id"], goalkeeper_sub["player_in_id"]))
    _require(
        sorted(local_pairs) == sorted(official_pairs),
        "local automatic substitutions do not match official automatic_subs: "
        f"local={sorted(local_pairs)}, official={sorted(official_pairs)}",
    )

    official_effective_captains = [p["element"] for p in picks if p["multiplier"] == 2]
    _require(len(official_effective_captains) <= 1,
             "official picks contain multiple effective captains")
    official_effective_captain = official_effective_captains[0] if official_effective_captains else None
    _require(local_score.get("effective_captain_id") == official_effective_captain,
             "local captain/vice fallback does not match official multiplier")

    local_gross = local_score.get("gross_points")
    _require(isinstance(local_gross, (int, float)) and not isinstance(local_gross, bool),
             "local gross_points must be numeric")
    _require(local_gross == official_gross,
             "local gross score does not match official multiplier-weighted score")
    return {
        "status": "RECONCILED",
        "manager_team_id": manager_team_id,
        "target_gameweek": target_gameweek,
        "official_gross_points": official_gross,
        "official_transfer_cost": transfer_cost,
        "official_net_points": official_net,
        "local_gross_points": local_gross,
        "automatic_substitutions": [
            {"player_out_id": out_id, "player_in_id": in_id}
            for out_id, in_id in sorted(official_pairs)
        ],
        "effective_captain_id": official_effective_captain,
        "score_delta": local_gross - official_gross,
        "historical_evidence_admitted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reconciliation_input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.reconciliation_input.read_text(encoding="utf-8"))
    result = reconcile_official_manager_result(
        payload["local_score"],
        payload["official_picks"],
        payload["official_live"],
        manager_team_id=payload["manager_team_id"],
        target_gameweek=payload["target_gameweek"],
        expected_starting_xi=payload["expected_starting_xi"],
        expected_bench_order=payload["expected_bench_order"],
        expected_reserve_goalkeeper_id=payload["expected_reserve_goalkeeper_id"],
        expected_captain_id=payload["expected_captain_id"],
        expected_vice_captain_id=payload["expected_vice_captain_id"],
    )
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
