import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from replay_fpl_policy_trajectories import (
    aggregate_trajectory_results,
    canonical_hash,
    run_policy_trajectory,
)
from transition_fpl_manager_state import transition_manager_state


POSITIONS = (
    ["GKP", "GKP"] + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
)
POLICIES = ("hold", "conventional", "cta_informed")


def make_state(manager_id="m1"):
    squad = []
    for index, position in enumerate(POSITIONS, start=1):
        squad.append({
            "player_id": f"p{index}",
            "position": position,
            "team_id": f"t{index}",
            "purchase_price_tenths": 50,
            "current_price_tenths": 50,
            "selling_price_tenths": 50,
        })
    lineup = {
        "starting_xi": ["p1", "p3", "p4", "p5", "p6", "p8", "p9", "p10", "p11", "p13", "p14"],
        "bench_order": ["p7", "p12", "p15", "p2"],
        "captain": "p13",
        "vice_captain": "p14",
    }
    return {
        "schema_version": "1.0",
        "season": "2026-27",
        "gameweek": 11,
        "deadline_utc": "2026-11-21T11:00:00Z",
        "manager_id": manager_id,
        "bank_tenths": 10,
        "free_transfers": 2,
        "chip_inventory": {
            chip: {"first_half_remaining": 1, "second_half_remaining": 1}
            for chip in ("wildcard", "free_hit", "bench_boost", "triple_captain")
        },
        "squad": squad,
        "lineup": lineup,
        "transfer_history": [],
    }


def prices_for(state, extra=None):
    result = {
        p["player_id"]: {
            "current_price_tenths": 50,
            "team_id": p["team_id"],
        }
        for p in state["squad"]
    }
    result.update(extra or {})
    return result


def action_record(state, policy, action, deadline, decision_time, forecast_time=None):
    row = {
        "starting_state_sha256": canonical_hash(state),
        "decision_frozen_at_utc": decision_time,
        "action": action,
    }
    if forecast_time is not None:
        row["forecast_frozen_at_utc"] = forecast_time
    if policy != "hold":
        row["forecast_sha256"] = ("a" if policy == "conventional" else "b") * 64
    return row


def make_first_week(state):
    hold = {
        "transfers": [],
        **copy.deepcopy(state["lineup"]),
        "chip": None,
    }
    conventional = {
        "transfers": [{
            "out_player_id": "p7",
            "in_player": {
                "player_id": "new_def",
                "position": "DEF",
                "team_id": "new_team",
                "current_price_tenths": 50,
            },
        }],
        "starting_xi": list(state["lineup"]["starting_xi"]),
        "bench_order": ["new_def", "p12", "p15", "p2"],
        "captain": "p13",
        "vice_captain": "p14",
        "chip": None,
    }
    cta = {
        "transfers": [{
            "out_player_id": "p8",
            "in_player": {
                "player_id": "new_mid",
                "position": "MID",
                "team_id": "new_mid_team",
                "current_price_tenths": 50,
            },
        }],
        "starting_xi": ["p1", "p3", "p4", "p5", "p6", "new_mid", "p9", "p10", "p11", "p13", "p14"],
        "bench_order": list(state["lineup"]["bench_order"]),
        "captain": "p14",
        "vice_captain": "p13",
        "chip": None,
    }
    actions = {"hold": hold, "conventional": conventional, "cta_informed": cta}
    records = {
        policy: action_record(
            state, policy, action, "2026-11-21T11:00:00Z",
            "2026-11-21T09:00:00Z",
            None if policy == "hold" else "2026-11-21T08:00:00Z",
        )
        for policy, action in actions.items()
    }
    outcomes = {
        "official_points": {f"p{i}": float(i % 7 + 1) for i in range(1, 16)},
        "minutes": {f"p{i}": 90 for i in range(1, 16)},
        "played_by_player": {f"p{i}": True for i in range(1, 16)},
    }
    outcomes["official_points"].update({"new_def": 4.0, "new_mid": 8.0})
    outcomes["minutes"].update({"new_def": 90, "new_mid": 90})
    outcomes["played_by_player"].update({"new_def": True, "new_mid": True})
    extra = {
        "new_def": {"current_price_tenths": 51, "team_id": "new_team"},
        "new_mid": {"current_price_tenths": 50, "team_id": "new_mid_team"},
    }
    week = {
        "gameweek": 11,
        "deadline_utc": "2026-11-21T11:00:00Z",
        "policy_actions": records,
        "official_outcomes": outcomes,
        "next_deadline_utc": "2026-11-28T11:00:00Z",
        "next_player_data": prices_for(state, extra),
    }
    next_states = {}
    for policy in POLICIES:
        tr = transition_manager_state(
            state, actions[policy], week["next_player_data"], 12, week["next_deadline_utc"]
        )
        next_states[policy] = tr["next_state"]
    return week, next_states


def make_second_week(next_states):
    records = {}
    for policy in POLICIES:
        state = next_states[policy]
        action = {"transfers": [], **copy.deepcopy(state["lineup"]), "chip": None}
        records[policy] = action_record(
            state, policy, action, "2026-11-28T11:00:00Z",
            "2026-11-28T09:00:00Z",
            None if policy == "hold" else "2026-11-28T08:00:00Z",
        )
    player_ids = {f"p{i}" for i in range(1, 16)} | {"new_def", "new_mid"}
    outcomes = {
        "official_points": {player_id: 3.0 for player_id in player_ids},
        "minutes": {player_id: 90 for player_id in player_ids},
        "played_by_player": {player_id: True for player_id in player_ids},
    }
    return {
        "gameweek": 12,
        "deadline_utc": "2026-11-28T11:00:00Z",
        "policy_actions": records,
        "official_outcomes": outcomes,
    }


def make_bundle(manager_id="m1", weight=0.01):
    state = make_state(manager_id)
    week1, next_states = make_first_week(state)
    week2 = make_second_week(next_states)
    return {
        "manager_id": manager_id,
        "season": "2026-27",
        "sampling_weight": weight,
        "initial_state": state,
        "gameweeks": [week1, week2],
    }


def test_three_policies_start_together_then_follow_separate_states():
    result = run_policy_trajectory(make_bundle())
    assert result["status"] == "REPLAYED_SEQUENTIAL_POLICY_TRAJECTORY"
    assert result["starting_gameweek"] == 11
    assert result["ending_gameweek"] == 12
    assert result["scope"].endswith("POLICIES_SHARE_INITIAL_STATE_THEN_DIVERGE")
    assert result["per_policy"]["hold"]["gameweeks"][0]["transfers_made"] == 0
    assert result["per_policy"]["conventional"]["gameweeks"][0]["transfers_made"] == 1
    assert result["per_policy"]["cta_informed"]["gameweeks"][0]["transfers_made"] == 1
    assert result["per_policy"]["hold"]["gameweeks"][1]["starting_state_sha256"] != result["per_policy"]["conventional"]["gameweeks"][1]["starting_state_sha256"]
    assert set(result["paired_vs_hold"]) == {"hold", "conventional", "cta_informed"}


def test_hold_cannot_transfer_change_lineup_or_play_a_chip():
    bundle = make_bundle()
    bundle["gameweeks"][0]["policy_actions"]["hold"]["action"]["transfers"] = [{
        "out_player_id": "p7",
        "in_player": {"player_id": "x", "position": "DEF", "team_id": "x", "current_price_tenths": 50},
    }]
    with pytest.raises(ValueError, match="Hold must make no transfers"):
        run_policy_trajectory(bundle)


def test_stale_or_mismatched_starting_state_hash_is_rejected():
    bundle = make_bundle()
    bundle["gameweeks"][0]["policy_actions"]["cta_informed"]["starting_state_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="does not match"):
        run_policy_trajectory(bundle)


def test_decisions_frozen_at_or_after_deadline_are_rejected():
    bundle = make_bundle()
    bundle["gameweeks"][0]["policy_actions"]["conventional"]["decision_frozen_at_utc"] = "2026-11-21T11:00:00Z"
    with pytest.raises(ValueError, match="strictly before"):
        run_policy_trajectory(bundle)


def test_aggregate_keeps_missing_design_weight_visible():
    manifest = {
        "managers": [
            {"manager_id": "a", "sampling_weight": 0.2},
            {"manager_id": "b", "sampling_weight": 0.3},
            {"manager_id": "c", "sampling_weight": 0.5},
        ]
    }
    results = [
        run_policy_trajectory(make_bundle("a", 0.2)),
        run_policy_trajectory(make_bundle("b", 0.3)),
    ]
    summary = aggregate_trajectory_results(results, manifest)
    assert summary["status"] == "CAPTURED_SUBSET_ONLY"
    assert summary["captured_weight_share"] == pytest.approx(0.5)
    assert summary["missing_weight_share"] == pytest.approx(0.5)
    assert summary["full_population_weighted_estimate_available"] is False
    assert "Conditional estimates" in summary["interpretation"]
