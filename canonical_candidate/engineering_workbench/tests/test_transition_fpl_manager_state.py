import copy
import pytest

from transition_fpl_manager_state import (
    calculate_selling_price_tenths,
    transition_manager_state,
)


POSITIONS = (
    ["GKP", "GKP"]
    + ["DEF"] * 5
    + ["MID"] * 5
    + ["FWD"] * 3
)


def make_state(gameweek=11, free_transfers=2, bank=10):
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
    return {
        "schema_version": "1.0",
        "season": "2026-27",
        "gameweek": gameweek,
        "deadline_utc": f"2026-11-{20 + gameweek - 11:02d}T11:00:00Z",
        "bank_tenths": bank,
        "free_transfers": free_transfers,
        "chip_inventory": {
            chip: {"first_half_remaining": 1, "second_half_remaining": 1}
            for chip in ("wildcard", "free_hit", "bench_boost", "triple_captain")
        },
        "squad": squad,
        "transfer_history": [],
    }


def make_action(state, transfers=None, chip=None):
    squad_ids = {p["player_id"] for p in state["squad"]}
    positions = {p["player_id"]: p["position"] for p in state["squad"]}
    if transfers:
        for row in transfers:
            squad_ids.remove(row["out_player_id"])
            squad_ids.add(row["in_player"]["player_id"])
            positions[row["in_player"]["player_id"]] = row["in_player"]["position"]
    # Maintain a legal 4-4-2 lineup and use p15 as reserve goalkeeper.
    xi = ["p1", "p3", "p4", "p5", "p6", "p8", "p9", "p10", "p13", "p14", "p15"]
    bench = ["p7", "p11", "p12", "p2"]
    if transfers:
        for row in transfers:
            out_id = row["out_player_id"]
            in_id = row["in_player"]["player_id"]
            if out_id in xi:
                xi[xi.index(out_id)] = in_id
            elif out_id in bench:
                bench[bench.index(out_id)] = in_id
    return {
        "transfers": transfers or [],
        "starting_xi": xi,
        "bench_order": bench,
        "captain": xi[-1],
        "vice_captain": xi[5],
        "chip": chip,
    }


def next_prices(state, replacements=None):
    replacements = replacements or {}
    result = {}
    for player in state["squad"]:
        result[player["player_id"]] = {
            "current_price_tenths": 50,
            "team_id": player["team_id"],
        }
    for player_id, row in replacements.items():
        result[player_id] = row
    return result


def test_selling_price_retains_half_price_rise_rounded_down():
    assert calculate_selling_price_tenths(75, 78) == 76
    assert calculate_selling_price_tenths(75, 77) == 76
    assert calculate_selling_price_tenths(75, 74) == 74


def test_no_transfer_rolls_free_transfer_and_caps_at_five():
    state = make_state(free_transfers=2)
    action = make_action(state)
    result = transition_manager_state(
        state, action, next_prices(state), 12, "2026-11-27T11:00:00Z"
    )
    assert result["next_free_transfers"] == 3
    assert result["next_bank_tenths"] == 10
    assert result["next_state"]["lineup"] == result["gameweek_lineup"]

    state["free_transfers"] = 5
    result = transition_manager_state(
        state, make_action(state), next_prices(state), 12, "2026-11-27T11:00:00Z"
    )
    assert result["next_free_transfers"] == 5


def test_paid_transfer_updates_squad_bank_and_free_transfer_balance():
    state = make_state(free_transfers=1, bank=10)
    transfer = {
        "out_player_id": "p7",
        "in_player": {"player_id": "new_def", "position": "DEF", "team_id": "new_team",
                      "current_price_tenths": 55},
    }
    action = make_action(state, [transfer])
    prices = next_prices(state)
    prices.pop("p7")
    prices["new_def"] = {"current_price_tenths": 56, "team_id": "new_team"}
    result = transition_manager_state(
        state, action, prices, 12, "2026-11-27T11:00:00Z"
    )
    assert result["transfer_hit_points"] == 0
    assert result["next_bank_tenths"] == 5
    assert result["next_free_transfers"] == 1
    new_player = next(p for p in result["next_state"]["squad"] if p["player_id"] == "new_def")
    assert new_player["purchase_price_tenths"] == 55
    assert new_player["current_price_tenths"] == 56
    assert new_player["selling_price_tenths"] == 55


def test_transfer_hit_is_charged_and_next_free_transfer_resets_to_one():
    state = make_state(free_transfers=1, bank=20)
    transfers = [
        {"out_player_id": "p7", "in_player": {"player_id": "new_def1", "position": "DEF", "team_id": "x", "current_price_tenths": 50}},
        {"out_player_id": "p6", "in_player": {"player_id": "new_def2", "position": "DEF", "team_id": "y", "current_price_tenths": 50}},
    ]
    action = make_action(state, transfers)
    prices = next_prices(state)
    prices.pop("p7")
    prices.pop("p6")
    prices["new_def1"] = {"current_price_tenths": 50, "team_id": "x"}
    prices["new_def2"] = {"current_price_tenths": 50, "team_id": "y"}
    result = transition_manager_state(
        state, action, prices, 12, "2026-11-27T11:00:00Z"
    )
    assert result["transfer_hit_points"] == 4
    assert result["next_free_transfers"] == 1


def test_wildcard_is_permanent_free_and_preserves_banked_transfers():
    state = make_state(free_transfers=3)
    transfer = {
        "out_player_id": "p7",
        "in_player": {"player_id": "new_def", "position": "DEF", "team_id": "new_team",
                      "current_price_tenths": 55},
    }
    action = make_action(state, [transfer], chip="wildcard")
    prices = next_prices(state)
    prices.pop("p7")
    prices["new_def"] = {"current_price_tenths": 55, "team_id": "new_team"}
    result = transition_manager_state(
        state, action, prices, 12, "2026-11-27T11:00:00Z"
    )
    assert result["transfer_hit_points"] == 0
    assert result["next_free_transfers"] == 3
    assert "new_def" in {p["player_id"] for p in result["next_state"]["squad"]}
    assert result["next_state"]["chip_inventory"]["wildcard"]["first_half_remaining"] == 0


def test_free_hit_uses_temporary_squad_then_restores_original_squad_bank_and_free_transfers():
    state = make_state(free_transfers=2, bank=10)
    original_action = make_action(state)
    original_lineup = {key: original_action[key] for key in ("starting_xi", "bench_order", "captain", "vice_captain")}
    state["lineup"] = original_lineup
    transfer = {
        "out_player_id": "p7",
        "in_player": {"player_id": "temporary_def", "position": "DEF", "team_id": "temp",
                      "current_price_tenths": 60},
    }
    action = make_action(state, [transfer], chip="free_hit")
    prices = next_prices(state)
    result = transition_manager_state(
        state, action, prices, 12, "2026-11-27T11:00:00Z"
    )
    assert "temporary_def" in {p["player_id"] for p in result["gameweek_squad"]}
    assert "temporary_def" not in {p["player_id"] for p in result["next_state"]["squad"]}
    assert result["next_bank_tenths"] == 10
    assert result["next_free_transfers"] == 2
    assert result["next_state"]["chip_inventory"]["free_hit"]["first_half_remaining"] == 0
    assert result["next_state"]["lineup"] == original_lineup


def test_insufficient_budget_and_wrong_position_transfer_are_rejected():
    state = make_state(bank=0)
    expensive = {"out_player_id": "p7", "in_player": {
        "player_id": "new_def", "position": "DEF", "team_id": "x", "current_price_tenths": 60
    }}
    with pytest.raises(ValueError, match="available budget"):
        transition_manager_state(
            state, make_action(state, [expensive]), next_prices(state), 12, "2026-11-27T11:00:00Z"
        )

    wrong_position = {"out_player_id": "p7", "in_player": {
        "player_id": "new_mid", "position": "MID", "team_id": "x", "current_price_tenths": 50
    }}
    with pytest.raises(ValueError, match="same FPL position"):
        transition_manager_state(
            state, make_action(state, [wrong_position]), next_prices(state), 12, "2026-11-27T11:00:00Z"
        )


def test_any_transfer_must_leave_club_limit_at_three():
    state = make_state()
    for player in state["squad"][1:4]:
        player["team_id"] = "same_club"
    transfer = {"out_player_id": "p7", "in_player": {
        "player_id": "new_def", "position": "DEF", "team_id": "same_club", "current_price_tenths": 50
    }}
    with pytest.raises(ValueError, match="three players"):
        transition_manager_state(
            state, make_action(state, [transfer]), next_prices(state), 12, "2026-11-27T11:00:00Z"
        )


def test_existing_real_world_club_limit_exception_can_be_carried_without_transfers():
    state = make_state()
    for player in state["squad"][:4]:
        player["team_id"] = "same_club"
    prices = next_prices(state)
    for player in state["squad"][:4]:
        prices[player["player_id"]]["team_id"] = "same_club"
    result = transition_manager_state(
        state, make_action(state), prices, 12, "2026-11-27T11:00:00Z"
    )
    assert sum(p["team_id"] == "same_club" for p in result["next_state"]["squad"]) == 4


def test_second_half_chip_inventory_applies_from_gameweek_twenty():
    state = make_state(gameweek=20)
    action = make_action(state, chip="bench_boost")
    result = transition_manager_state(
        state, action, next_prices(state), 21, "2027-01-15T11:00:00Z"
    )
    assert result["next_state"]["chip_inventory"]["bench_boost"]["second_half_remaining"] == 0
    assert result["next_state"]["chip_inventory"]["bench_boost"]["first_half_remaining"] == 1


def test_free_hit_in_gameweek_one_and_consecutive_gw19_gw20_free_hits_are_rejected():
    state = make_state(gameweek=1)
    with pytest.raises(ValueError, match="Gameweek 1"):
        transition_manager_state(
            state, make_action(state, chip="free_hit"), next_prices(state), 2, "2026-11-11T11:00:00Z"
        )

    state = make_state(gameweek=20)
    state["previous_gameweek_chip"] = "free_hit"
    with pytest.raises(ValueError, match="GW19"):
        transition_manager_state(
            state, make_action(state, chip="free_hit"), next_prices(state), 21, "2027-01-15T11:00:00Z"
        )


def test_incorrect_existing_selling_price_is_rejected():
    state = make_state()
    state["squad"][0]["purchase_price_tenths"] = 75
    state["squad"][0]["current_price_tenths"] = 78
    state["squad"][0]["selling_price_tenths"] = 78
    with pytest.raises(ValueError, match="selling price mismatch"):
        transition_manager_state(
            state, make_action(state), next_prices(state), 12, "2026-11-27T11:00:00Z"
        )


def test_terminal_gameweek_applies_action_without_synthetic_next_state():
    state = make_state(free_transfers=1, bank=20)
    transfers = [
        {"out_player_id": "p7", "in_player": {"player_id": "terminal_def1", "position": "DEF", "team_id": "x", "current_price_tenths": 50}},
        {"out_player_id": "p6", "in_player": {"player_id": "terminal_def2", "position": "DEF", "team_id": "y", "current_price_tenths": 50}},
    ]
    action = make_action(state, transfers)
    result = transition_manager_state(state, action, terminal=True)
    assert result["status"] == "TERMINAL_GAMEWEEK_ACTION_APPLIED"
    assert result["next_state"] is None
    assert result["next_gameweek"] is None
    assert result["transfer_hit_points"] == 4
    assert len(result["gameweek_squad"]) == 15
    assert "terminal_def1" in {p["player_id"] for p in result["gameweek_squad"]}


def test_terminal_transition_does_not_create_a_future_state():
    state = make_state()
    result = transition_manager_state(state, make_action(state), terminal=True)
    assert result["next_state"] is None
    assert result["status"] == "TERMINAL_GAMEWEEK_ACTION_APPLIED"
