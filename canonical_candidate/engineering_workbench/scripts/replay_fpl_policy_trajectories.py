#!/usr/bin/env python3
"""Sequential paired FPL policy replay.

Each policy starts from the same manager state, then evolves its own squad,
bank, free transfers and chip inventory. Official outcomes and market snapshots
are shared across policies at each Gameweek. This is not a points forecaster.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

from replay_fpl_gameweek_decisions import replay_gameweek
from transition_fpl_manager_state import transition_manager_state

POLICIES = ("hold", "conventional", "cta_informed")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def canonical_hash(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_timestamp(value, label):
    if not value:
        raise ValueError(f"Missing {label}")
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{label} must be ISO-8601") from None
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed


def validate_frozen_action(policy: str, record: Mapping, deadline_utc: str, state: Mapping):
    if not isinstance(record, Mapping):
        raise ValueError(f"{policy} action record must be an object")
    deadline = parse_timestamp(deadline_utc, "deadline_utc")
    decision_time = parse_timestamp(record.get("decision_frozen_at_utc"), "decision_frozen_at_utc")
    if policy == "hold" and not record.get("forecast_frozen_at_utc"):
        forecast_time = decision_time
    else:
        forecast_time = parse_timestamp(record.get("forecast_frozen_at_utc"), "forecast_frozen_at_utc")
    if forecast_time > decision_time:
        raise ValueError(f"{policy} forecast must be frozen no later than its decision")
    if decision_time >= deadline or forecast_time >= deadline:
        raise ValueError(f"{policy} forecast and decision must be frozen strictly before deadline")
    if record.get("starting_state_sha256") != canonical_hash(state):
        raise ValueError(f"{policy} action starting_state_sha256 does not match its policy trajectory state")
    if policy != "hold":
        forecast_hash = str(record.get("forecast_sha256", ""))
        if not SHA256_RE.fullmatch(forecast_hash):
            raise ValueError(f"{policy} action requires a valid forecast_sha256")
    action = record.get("action")
    if not isinstance(action, Mapping):
        raise ValueError(f"{policy} action payload is missing")
    if not isinstance(action.get("transfers"), list):
        raise ValueError(f"{policy} action transfers must be a list")
    if policy == "hold":
        if action["transfers"] or action.get("chip") is not None:
            raise ValueError("Hold must make no transfers and use no chip")
        prior_lineup = state.get("lineup")
        if not isinstance(prior_lineup, Mapping):
            raise ValueError("Hold requires the prior lineup in the manager state")
        for key in ("starting_xi", "bench_order", "captain", "vice_captain"):
            if action.get(key) != prior_lineup.get(key):
                raise ValueError(f"Hold must preserve the existing {key}")


def _score_transition(state: Mapping, action: Mapping, transition: Mapping, outcomes: Mapping):
    squad = transition["gameweek_squad"]
    positions = {str(row["player_id"]): str(row["position"]) for row in squad}
    decision = {
        "action_legality_verified": True,
        "chip_legality_verified": action.get("chip") is not None,
        "starting_xi": transition["gameweek_lineup"]["starting_xi"],
        "bench_order": transition["gameweek_lineup"]["bench_order"],
        "captain": transition["gameweek_lineup"]["captain"],
        "vice_captain": transition["gameweek_lineup"]["vice_captain"],
        "chip": action.get("chip"),
        "transfers_made": len(action.get("transfers") or []),
        "free_transfers": int(state["free_transfers"]),
        "transfer_hit_cost": transition["transfer_hit_points"],
    }
    return replay_gameweek(
        decision,
        outcomes["official_points"],
        outcomes["minutes"],
        positions,
        team_by_player=None,
        played_by_player=outcomes.get("played_by_player"),
        autosub_absence_order="forward",
    )


def run_policy_trajectory(bundle: Mapping) -> dict:
    initial_state = deepcopy(bundle.get("initial_state"))
    if not isinstance(initial_state, Mapping):
        raise ValueError("Trajectory bundle requires initial_state")
    manager_id = str(bundle.get("manager_id", initial_state.get("manager_id", ""))).strip()
    if not manager_id:
        raise ValueError("Trajectory bundle requires a private manager_id")
    if initial_state.get("manager_id") not in {None, manager_id}:
        raise ValueError("Bundle manager_id does not match initial_state manager_id")
    weeks = bundle.get("gameweeks")
    if not isinstance(weeks, list) or not weeks:
        raise ValueError("Trajectory bundle requires a non-empty gameweeks list")
    sampling_weight = float(bundle.get("sampling_weight", 0.0))
    if not 0 < sampling_weight <= 1:
        raise ValueError("sampling_weight must be in (0, 1]")

    states = {policy: deepcopy(initial_state) for policy in POLICIES}
    results = {policy: [] for policy in POLICIES}
    initial_hash = canonical_hash(initial_state)

    for week_index, week in enumerate(weeks):
        gameweek = int(week.get("gameweek", 0))
        deadline_utc = str(week.get("deadline_utc", ""))
        outcomes = week.get("official_outcomes")
        actions = week.get("policy_actions")
        if not isinstance(outcomes, Mapping) or not isinstance(actions, Mapping):
            raise ValueError(f"GW{gameweek} requires official_outcomes and policy_actions")
        if set(actions) != set(POLICIES):
            raise ValueError(f"GW{gameweek} must include exactly the three frozen policies")
        terminal = week_index == len(weeks) - 1

        for policy in POLICIES:
            state = states[policy]
            if int(state.get("gameweek", 0)) != gameweek:
                raise ValueError(f"{policy} state is not at the expected GW{gameweek}")
            if str(state.get("deadline_utc", "")) != deadline_utc:
                raise ValueError(f"{policy} state deadline does not match GW{gameweek}")
            action_record = actions[policy]
            validate_frozen_action(policy, action_record, deadline_utc, state)
            action = action_record["action"]

            if terminal:
                if week.get("next_deadline_utc") is not None or week.get("next_player_data") is not None:
                    raise ValueError("Terminal Gameweek must not provide a synthetic next deadline or market snapshot")
                transition = transition_manager_state(
                    state, action, terminal=True
                )
            else:
                next_deadline = week.get("next_deadline_utc")
                next_prices = week.get("next_player_data")
                if not isinstance(next_prices, Mapping):
                    raise ValueError(f"GW{gameweek} requires next_player_data for sequential state transition")
                transition = transition_manager_state(
                    state, action, next_prices, gameweek + 1, next_deadline
                )

            score = _score_transition(state, action, transition, outcomes)
            results[policy].append({
                "gameweek": gameweek,
                "gross_points": score["gross_points"],
                "net_points": score["net_points"],
                "transfer_hit_points": score["transfer_hit_points"],
                "transfers_made": score["transfers_made"],
                "chip": score["chip"],
                "effective_captain": score["effective_captain"],
                "substitution_count": len(score["substitutions"]),
                "starting_state_sha256": canonical_hash(state),
                "decision_frozen_at_utc": action_record["decision_frozen_at_utc"],
                "forecast_sha256": action_record.get("forecast_sha256"),
            })
            if not terminal:
                states[policy] = transition["next_state"]

    totals = {}
    for policy in POLICIES:
        rows = results[policy]
        totals[policy] = {
            "total_gross_points": sum(row["gross_points"] for row in rows),
            "total_net_points": sum(row["net_points"] for row in rows),
            "total_transfer_hit_points": sum(row["transfer_hit_points"] for row in rows),
            "total_transfers": sum(row["transfers_made"] for row in rows),
            "gameweeks": rows,
        }
    hold_total = totals["hold"]["total_net_points"]
    paired = {
        policy: {
            "net_points_delta_vs_hold": totals[policy]["total_net_points"] - hold_total,
            "gameweek_deltas_vs_hold": [
                totals[policy]["gameweeks"][i]["net_points"] - totals["hold"]["gameweeks"][i]["net_points"]
                for i in range(len(weeks))
            ],
        }
        for policy in POLICIES
    }
    return {
        "status": "REPLAYED_SEQUENTIAL_POLICY_TRAJECTORY",
        "manager_id": manager_id,
        "season": str(bundle.get("season", initial_state.get("season", ""))),
        "sampling_weight": sampling_weight,
        "starting_gameweek": int(weeks[0]["gameweek"]),
        "ending_gameweek": int(weeks[-1]["gameweek"]),
        "initial_state_sha256": initial_hash,
        "per_policy": totals,
        "paired_vs_hold": paired,
        "scope": "SEQUENTIAL_COUNTERFACTUAL_REPLAY; POLICIES_SHARE_INITIAL_STATE_THEN_DIVERGE",
    }


def _weighted_mean(values, weights):
    denominator = sum(weights)
    return sum(value * weight for value, weight in zip(values, weights)) / denominator if denominator else None


def aggregate_trajectory_results(results: Sequence[Mapping], manifest: Mapping) -> dict:
    if not results:
        raise ValueError("At least one manager trajectory result is required")
    manifest_rows = manifest.get("managers") or []
    manifest_weights = {str(row["manager_id"]): float(row["sampling_weight"]) for row in manifest_rows}
    if len(manifest_weights) != len(manifest_rows) or not manifest_weights:
        raise ValueError("Panel manifest must contain unique manager IDs and weights")
    if abs(sum(manifest_weights.values()) - 1.0) > 1e-6:
        raise ValueError("Panel manifest sampling weights must sum to one")

    by_manager = {}
    for row in results:
        manager_id = str(row.get("manager_id", ""))
        if not manager_id or manager_id in by_manager:
            raise ValueError("Trajectory results must have unique non-empty manager IDs")
        if manager_id not in manifest_weights:
            raise ValueError("Trajectory result manager is outside the frozen panel")
        if abs(float(row["sampling_weight"]) - manifest_weights[manager_id]) > 1e-9:
            raise ValueError("Trajectory result sampling weight does not match frozen manifest")
        by_manager[manager_id] = row

    captured_ids = set(by_manager)
    captured_weight = sum(manifest_weights[manager_id] for manager_id in captured_ids)
    missing_weight = 1.0 - captured_weight
    policies = {}
    for policy in POLICIES:
        values = [float(row["per_policy"][policy]["total_net_points"]) for row in by_manager.values()]
        weights = [manifest_weights[manager_id] for manager_id in by_manager]
        policies[policy] = {
            "manager_count": len(values),
            "unweighted_mean_net_points_captured_subset": statistics.mean(values),
            "median_net_points_captured_subset": statistics.median(values),
            "weighted_mean_net_points_captured_subset": _weighted_mean(values, weights),
            "original_design_weighted_sum_observed": sum(v * w for v, w in zip(values, weights)),
        }

    paired = {}
    for policy in POLICIES:
        if policy == "hold":
            continue
        deltas = [
            float(row["paired_vs_hold"][policy]["net_points_delta_vs_hold"])
            for row in by_manager.values()
        ]
        weights = [manifest_weights[manager_id] for manager_id in by_manager]
        paired[policy] = {
            "unweighted_mean_delta_captured_subset": statistics.mean(deltas),
            "median_delta_captured_subset": statistics.median(deltas),
            "weighted_mean_delta_captured_subset": _weighted_mean(deltas, weights),
            "original_design_weighted_sum_delta_observed": sum(d * w for d, w in zip(deltas, weights)),
            "positive_manager_rate": sum(value > 0 for value in deltas) / len(deltas),
            "negative_manager_rate": sum(value < 0 for value in deltas) / len(deltas),
            "tie_rate": sum(value == 0 for value in deltas) / len(deltas),
        }

    return {
        "status": "CAPTURED_SUBSET_ONLY" if missing_weight > 1e-9 else "FULL_PANEL_WEIGHT_COVERAGE",
        "selected_manager_count": len(manifest_weights),
        "captured_manager_count": len(captured_ids),
        "missing_manager_count": len(manifest_weights) - len(captured_ids),
        "captured_weight_share": captured_weight,
        "missing_weight_share": missing_weight,
        "full_population_weighted_estimate_available": missing_weight <= 1e-9,
        "per_policy": policies,
        "paired_vs_hold": paired,
        "interpretation": (
            "Conditional estimates for captured managers only. Missing design weight is not renormalized into a population claim."
            if missing_weight > 1e-9 else
            "All selected panel managers and original design weights are represented."
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="Private JSONL trajectory bundles")
    parser.add_argument("--manifest", type=Path, required=True, help="Private frozen panel manifest")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    bundles = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    results = [run_policy_trajectory(bundle) for bundle in bundles]
    summary = aggregate_trajectory_results(results, manifest)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "manager_trajectory_results.jsonl").open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, sort_keys=True) + "\n")
    (args.output_dir / "aggregate_policy_results.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
