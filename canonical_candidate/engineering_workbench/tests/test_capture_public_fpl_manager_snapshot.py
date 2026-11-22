import json

from capture_public_fpl_manager_snapshot import capture_public_manager_snapshot


def test_public_manager_snapshot_preserves_official_picks_and_target_transfers():
    picks = [
        {
            "element": player_id,
            "position": position,
            "is_captain": position == 1,
            "is_vice_captain": position == 2,
        }
        for position, player_id in enumerate(range(1, 16), start=1)
    ]
    payloads = {
        "https://fantasy.premierleague.com/api/entry/421025/event/11/picks/": {
            "picks": picks,
            "entry_history": {"event": 11, "bank": 20, "event_transfers": 1, "total_transfers": 8},
        },
        "https://fantasy.premierleague.com/api/entry/421025/history/": {
            "current": [{"event": 11, "bank": 20, "event_transfers": 1, "total_transfers": 8}],
        },
        "https://fantasy.premierleague.com/api/entry/421025/transfers/": [
            {
                "event": 12, "time": "2026-11-22T05:00:00Z",
                "element_in": 16, "element_out": 15,
                "element_in_cost": 55, "element_out_cost": 50,
            }
        ],
        "https://fantasy.premierleague.com/api/bootstrap-static/": {
            "elements": [
                {
                    "id": player_id,
                    "first_name": f"First{player_id}",
                    "second_name": f"Last{player_id}",
                    "element_type": 1 if player_id in (1, 12, 16) else (2 if player_id <= 6 else (3 if player_id <= 11 else 4)),
                    "team": 1 + (player_id % 5),
                }
                for player_id in range(1, 17)
            ]
        },
    }

    def fetcher(url):
        return json.dumps(payloads[url]).encode("utf-8")

    result = capture_public_manager_snapshot(
        421025, 12, fetcher=fetcher, clock=lambda: "2026-11-22T06:00:00Z"
    )

    previous = result["previous_gameweek_state"]
    assert previous["squad_ids"] == list(range(1, 16))
    assert previous["starting_xi_ids"] == list(range(1, 12))
    assert previous["outfield_bench_ids"] == [13, 14, 15]
    assert previous["reserve_goalkeeper_id"] == 12
    assert previous["players_in_official_pick_order"][0]["purchase_price"] is None
    assert previous["captain_id"] == 1
    assert previous["vice_captain_id"] == 2
    assert previous["bank_at_previous_deadline"] == 2.0
    assert result["target_gameweek_transfer_activity"]["transfers_reported"] == 1
    assert result["target_gameweek_transfer_activity"]["squad_ids_after_reported_target_transfers"] == list(range(1, 15)) + [16]
    assert "current free-transfer count" in result["not_inferred"]
    assert result["capture_type"] == "PUBLIC_FPL_MANAGER_STATE_REVIEW_NOT_DECISION_EVIDENCE"
