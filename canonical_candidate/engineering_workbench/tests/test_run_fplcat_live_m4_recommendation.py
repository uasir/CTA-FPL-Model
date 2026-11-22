from run_fplcat_live_m4_recommendation import build_manager_state, derive_free_transfers


def test_free_transfer_reconstruction_accounts_for_wildcard_and_free_hit():
    events = []
    transfer_data = {
        2: (0, 0), 3: (2, 0), 4: (10, 0), 5: (1, 0),
        6: (2, 4), 7: (2, 4), 8: (1, 0), 9: (11, 0),
        10: (3, 8), 11: (1, 0),
    }
    for event, (count, cost) in transfer_data.items():
        events.append({
            "event": event,
            "event_transfers": count,
            "event_transfers_cost": cost,
        })
    history = {
        "current": events,
        "chips": [
            {"name": "wildcard", "event": 4},
            {"name": "freehit", "event": 9},
        ],
    }
    assert derive_free_transfers(history, 12) == 1


def test_manager_state_uses_official_gw11_squad_and_lineup_as_gw12_baseline():
    players = []
    for position, player_id in enumerate(range(1, 16), start=1):
        element_type = (
            1 if position in (1, 12)
            else 2 if position in (2, 3, 4, 5, 15)
            else 3 if position in (6, 7, 8, 13, 14)
            else 4
        )
        players.append({
            "fpl_element_id": player_id,
            "position": position,
            "element_type": element_type,
        })
    snapshot = {
        "capture_type": "PUBLIC_FPL_MANAGER_STATE_REVIEW_NOT_DECISION_EVIDENCE",
        "target_gameweek": 12,
        "previous_gameweek_state": {
            "squad_ids": list(range(1, 16)),
            "starting_xi_ids": list(range(1, 12)),
            "outfield_bench_ids": [13, 14, 15],
            "reserve_goalkeeper_id": 12,
            "captain_id": 11,
            "vice_captain_id": 6,
            "bank_at_previous_deadline": 1.8,
            "players_in_official_pick_order": players,
        },
        "target_gameweek_transfer_activity": {"transfers_reported": 0},
    }
    transfer_data = {
        2: (0, 0), 3: (2, 0), 4: (10, 0), 5: (1, 0),
        6: (2, 4), 7: (2, 4), 8: (1, 0), 9: (11, 0),
        10: (3, 8), 11: (1, 0),
    }
    history = {
        "current": [
            {"event": event, "event_transfers": count, "event_transfers_cost": cost}
            for event, (count, cost) in transfer_data.items()
        ],
        "chips": [
            {"name": "wildcard", "event": 4},
            {"name": "freehit", "event": 9},
        ],
    }
    state = build_manager_state(snapshot, history, chip_state="NONE")
    assert state["squad_15"] == list(range(1, 16))
    assert state["bank"] == 1.8
    assert state["free_transfers"] == 1
    assert state["formation"] == "4-3-3"
    assert state["starting_xi"] == list(range(1, 12))
    assert state["bench_order"] == [13, 14, 15]
    assert state["reserve_goalkeeper_id"] == 12
    assert state["captain_id"] == 11
    assert state["vice_captain_id"] == 6
