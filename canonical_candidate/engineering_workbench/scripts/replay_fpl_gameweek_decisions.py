#!/usr/bin/env python3
"""Deterministic one-gameweek FPL decision replay from frozen decisions.

Scores a submitted legal squad/lineup against official player outcomes. It
does not optimize decisions or infer missing historical state.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from collections import Counter, defaultdict
from pathlib import Path
from math import isfinite
from typing import Mapping, Sequence

POSITIONS = {"GKP", "DEF", "MID", "FWD"}
REQUIRED_SQUAD = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
CHIPS = {None, "bench_boost", "triple_captain", "free_hit", "wildcard"}
HIT_PER_TRANSFER = 4


def _id(value) -> str:
    if value is None or str(value).strip() == "":
        raise ValueError("Player IDs must be non-empty")
    return str(value)


def _lookup(mapping: Mapping, player_id: str, label: str):
    if player_id in mapping:
        return mapping[player_id]
    for key, value in mapping.items():
        if str(key) == player_id:
            return value
    raise ValueError(f"Missing {label} for player {player_id}")


def _number(value, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be numeric") from None
    if not isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _legal_formation(xi: Sequence[str], positions: Mapping[str, str]) -> bool:
    counts = Counter(positions[player] for player in xi if positions[player] != "GKP")
    return (len(xi) == 11 and sum(positions[p] == "GKP" for p in xi) == 1
            and 3 <= counts["DEF"] <= 5
            and 2 <= counts["MID"] <= 5
            and 1 <= counts["FWD"] <= 3
            and sum(counts.values()) == 10)


def _validate_roster(decision: Mapping, positions: Mapping[str, str]) -> tuple[list[str], list[str]]:
    xi = [_id(v) for v in decision.get("starting_xi", [])]
    bench = [_id(v) for v in decision.get("bench_order", [])]
    if len(xi) != 11 or len(bench) != 4 or len(set(xi + bench)) != 15:
        raise ValueError("A replay roster requires 11 starters and 4 distinct bench players")
    squad = xi + bench
    normalized_positions = {player: str(_lookup(positions, player, "position")).upper()
                            for player in squad}
    if any(position not in POSITIONS for position in normalized_positions.values()):
        raise ValueError("Unknown player position")
    if Counter(normalized_positions.values()) != Counter(REQUIRED_SQUAD):
        raise ValueError("Squad must contain exactly 2 GKP, 5 DEF, 5 MID and 3 FWD")
    if sum(normalized_positions[p] == "GKP" for p in xi) != 1:
        raise ValueError("Starting XI must contain exactly one goalkeeper")
    if any(normalized_positions[p] == "GKP" for p in bench[:3]) or normalized_positions[bench[3]] != "GKP":
        raise ValueError("Bench order must contain three outfield players followed by the goalkeeper")
    if not _legal_formation(xi, normalized_positions):
        raise ValueError("Starting XI does not use a legal FPL formation")
    return xi, bench


def replay_gameweek(decision: Mapping, official_points: Mapping,
                    minutes: Mapping, positions: Mapping,
                    team_by_player: Mapping | None = None) -> dict:
    """Score one frozen legal lineup against official player outcomes.

    action_legality_verified must be true: this scorer does not validate
    transfers, prices, team limits, or chip availability.
    """
    if decision.get("action_legality_verified") is not True:
        raise ValueError("Decision must be explicitly marked action_legality_verified")
    chip = decision.get("chip")
    if chip not in CHIPS:
        raise ValueError("Unsupported chip")
    if chip is not None and decision.get("chip_legality_verified") is not True:
        raise ValueError("A used chip requires chip_legality_verified=true")

    xi, bench = _validate_roster(decision, positions)
    squad = xi + bench
    pos = {p: str(_lookup(positions, p, "position")).upper() for p in squad}
    if team_by_player is not None:
        teams = {p: _id(_lookup(team_by_player, p, "team ID")) for p in squad}
        if max(Counter(teams.values()).values()) > 3:
            raise ValueError("Squad exceeds the three-player-per-team limit")

    pts = {p: _number(_lookup(official_points, p, "official points"), "Official points")
           for p in squad}
    mins = {p: _number(_lookup(minutes, p, "minutes"), "Minutes") for p in squad}
    if any(value < 0 for value in mins.values()):
        raise ValueError("Minutes cannot be negative")
    played = {p: mins[p] > 0 for p in squad}

    starting_keeper = next(p for p in xi if pos[p] == "GKP")
    bench_keeper = bench[3]
    active_xi = list(xi)
    substitutions = []

    if chip != "bench_boost":
        if not played[starting_keeper] and played[bench_keeper]:
            active_xi[active_xi.index(starting_keeper)] = bench_keeper
            substitutions.append({"out": starting_keeper, "in": bench_keeper, "reason": "goalkeeper_absent"})

        for substitute in bench[:3]:
            if not played[substitute]:
                continue
            replacement = None
            for absent in active_xi:
                if pos[absent] == "GKP" or played[absent]:
                    continue
                candidate_xi = [substitute if p == absent else p for p in active_xi]
                if _legal_formation(candidate_xi, pos):
                    replacement = absent
                    break
            if replacement is not None:
                active_xi[active_xi.index(replacement)] = substitute
                substitutions.append({"out": replacement, "in": substitute, "reason": "outfield_absence"})

    active_score = sum(pts[p] for p in active_xi)
    bench_score = sum(pts[p] for p in bench)
    if chip == "bench_boost":
        active_score += bench_score

    captain = _id(decision.get("captain"))
    vice = _id(decision.get("vice_captain"))
    if captain not in xi or vice not in xi or captain == vice:
        raise ValueError("Captain and vice-captain must be distinct starting XI players")
    effective_captain = captain if played[captain] else vice if played[vice] else None
    captain_extra_multiplier = 2 if chip == "triple_captain" else 1
    captain_extra_points = (pts[effective_captain] * captain_extra_multiplier
                            if effective_captain is not None else 0.0)

    transfers_made = int(decision.get("transfers_made", 0))
    free_transfers = int(decision.get("free_transfers", 1))
    if transfers_made < 0 or free_transfers < 0:
        raise ValueError("Transfer counts cannot be negative")
    hit_transfers = 0 if chip in {"free_hit", "wildcard"} else max(0, transfers_made - free_transfers)
    hits = hit_transfers * HIT_PER_TRANSFER
    gross_points = active_score + captain_extra_points
    net_points = gross_points - hits

    return {
        "status": "REPLAYED_ONE_GAMEWEEK",
        "gross_points": gross_points,
        "transfer_hit_points": hits,
        "net_points": net_points,
        "starting_xi_base_points_after_autosubs": active_score,
        "bench_points_added": bench_score if chip == "bench_boost" else 0.0,
        "captain": captain,
        "vice_captain": vice,
        "effective_captain": effective_captain,
        "captain_extra_points": captain_extra_points,
        "chip": chip,
        "substitutions": substitutions,
        "final_active_xi": active_xi,
        "transfers_made": transfers_made,
        "free_transfers": free_transfers,
        "hit_transfers": hit_transfers,
        "scope": "ONE_GAMEWEEK_FROZEN_ACTION; NO_MULTIWEEK_STATE_TRANSITION",
    }


def compare_policy_replays(rows: Sequence[Mapping], baseline_policy: str = "hold") -> dict:
    """Paired policy comparison; each policy must share the deadline's start state.

    Row schema: deadline_id, starting_state_id, policy, decision,
    official_points, minutes, positions, and optional team_by_player.
    """
    if not rows:
        raise ValueError("At least one replay row is required")
    by_deadline = defaultdict(dict)
    for row in rows:
        deadline = str(row.get("deadline_id", "")).strip()
        state = str(row.get("starting_state_id", "")).strip()
        policy = str(row.get("policy", "")).strip()
        if not deadline or not state or not policy:
            raise ValueError("Every row requires deadline_id, starting_state_id and policy")
        if policy in by_deadline[deadline]:
            raise ValueError(f"Duplicate policy {policy} for deadline {deadline}")
        by_deadline[deadline][policy] = row

    policy_totals = defaultdict(list)
    paired_deltas = defaultdict(list)
    deadline_reports = []
    expected_policy_set = None
    for deadline in sorted(by_deadline):
        policies = by_deadline[deadline]
        current_policy_set = set(policies)
        if expected_policy_set is None:
            expected_policy_set = current_policy_set
        elif current_policy_set != expected_policy_set:
            raise ValueError("All deadlines must contain the same matched policy set")
        if baseline_policy not in policies:
            raise ValueError(f"Missing baseline policy {baseline_policy} for {deadline}")
        for row in policies.values():
            decision_time = str(row.get("decision_frozen_at", "")).replace("Z", "+00:00")
            deadline_time = str(row.get("deadline_at", "")).replace("Z", "+00:00")
            if not decision_time or not deadline_time:
                raise ValueError("Every policy row requires decision_frozen_at and deadline_at")
            try:
                frozen_at = datetime.fromisoformat(decision_time)
                deadline_at = datetime.fromisoformat(deadline_time)
            except ValueError:
                raise ValueError("Decision and deadline timestamps must be ISO-8601") from None
            if frozen_at.tzinfo is None or deadline_at.tzinfo is None:
                raise ValueError("Decision and deadline timestamps must include timezone offsets")
            if frozen_at >= deadline_at:
                raise ValueError("Decision must be frozen strictly before the deadline")
        states = {str(row["starting_state_id"]) for row in policies.values()}
        if len(states) != 1:
            raise ValueError(f"Policies do not share the same starting state for {deadline}")
        scores = {}
        for policy, row in policies.items():
            result = replay_gameweek(
                row["decision"], row["official_points"], row["minutes"], row["positions"],
                row.get("team_by_player")
            )
            scores[policy] = result["net_points"]
            policy_totals[policy].append(result["net_points"])
        baseline_score = scores[baseline_policy]
        for policy, score in scores.items():
            paired_deltas[policy].append(score - baseline_score)
        deadline_reports.append({
            "deadline_id": deadline,
            "starting_state_id": next(iter(states)),
            "net_points_by_policy": scores,
            "delta_vs_baseline": {p: score - baseline_score for p, score in scores.items()},
        })

    summaries = {}
    for policy, scores in sorted(policy_totals.items()):
        deltas = paired_deltas[policy]
        summaries[policy] = {
            "n_deadlines": len(scores),
            "mean_net_points": sum(scores) / len(scores),
            "total_net_points": sum(scores),
            "mean_delta_vs_baseline": sum(deltas) / len(deltas),
            "total_delta_vs_baseline": sum(deltas),
            "positive_deadline_rate_vs_baseline": sum(value > 0 for value in deltas) / len(deltas),
            "negative_deadline_rate_vs_baseline": sum(value < 0 for value in deltas) / len(deltas),
            "tie_deadline_rate_vs_baseline": sum(value == 0 for value in deltas) / len(deltas),
        }
    return {
        "status": "RESEARCH_ONLY_PAIRED_ONE_STEP_REPLAY",
        "baseline_policy": baseline_policy,
        "n_deadlines": len(deadline_reports),
        "policies": summaries,
        "deadlines": deadline_reports,
        "limitations": [
            "Requires externally verified legal action and chip-availability flags.",
            "One-step replay does not propagate squad, bank, purchase-price or free-transfer state.",
            "Timestamp checks establish pre-deadline freeze ordering but do not independently verify source-data vintages.",
            "Does not estimate rank gain or field-relative outcomes.",
            "No statistical uncertainty interval is calculated by this deterministic scorer.",
        ],
    }



def main():
    parser = argparse.ArgumentParser(description="Replay frozen FPL decisions against official gameweek outcomes")
    parser.add_argument("--input", required=True, type=Path, help="JSON file containing rows and optional baseline_policy")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON report path")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    report = compare_policy_replays(payload["rows"], payload.get("baseline_policy", "hold"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
