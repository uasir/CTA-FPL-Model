from audit_fpl_replay_against_official_manager_history import (
    build_replay_record, audit_record, autosub_pairs_are_scoring_relevant,
)


def fixture_payload():
    positions = {
        "1": "GKP", "2": "GKP",
        "3": "DEF", "4": "DEF", "5": "DEF", "6": "DEF", "7": "DEF",
        "8": "MID", "9": "MID", "10": "MID", "11": "MID", "12": "MID",
        "13": "FWD", "14": "FWD", "15": "FWD",
    }
    slots = [1, 3, 4, 5, 6, 8, 9, 10, 13, 14, 15, 7, 11, 12, 2]
    picks = []
    for slot, element in enumerate(slots, start=1):
        picks.append({
            "position": slot,
            "element": element,
            "is_captain": element == 13,
            "is_vice_captain": element == 8,
        })
    payload = {
        "picks": picks,
        "active_chip": "3xc",
        "entry_history": {"points": 44, "event_transfers": 2, "event_transfers_cost": 4},
        "automatic_subs": [],
    }
    live = {"elements": []}
    for element in range(1, 16):
        live_points = 8 if element == 13 else 2
        live["elements"].append({
            "id": element,
            "stats": {"total_points": live_points, "minutes": 90, "yellow_cards": 0, "red_cards": 0},
        })
    return payload, live, positions


def test_build_replay_record_maps_official_pick_slots_and_chip():
    payload, live, positions = fixture_payload()
    record = build_replay_record(payload, live, positions)
    assert record["decision"]["starting_xi"] == ["1", "3", "4", "5", "6", "8", "9", "10", "13", "14", "15"]
    assert record["decision"]["bench_order"] == ["7", "11", "12", "2"]
    assert record["decision"]["chip"] == "triple_captain"
    assert record["decision"]["transfer_hit_cost"] == 4


def test_audit_record_matches_official_manager_score():
    payload, live, positions = fixture_payload()
    result = audit_record(payload, live, positions)
    # XI base: 8 + ten players x 2 = 28; Triple Captain adds 16 (gross 44); one hit = -4 (net 40).
    assert result["replay_net_points"] == 40
    assert result["official_team_points"] == 44
    assert result["gross_point_difference"] == 0
    assert result["net_point_difference"] == 0
    assert result["autosub_pairs_match"] is True
    assert result["autosub_pairs_match_reverse"] is True
    assert result["autosub_position_pairs_match"] is True
    assert result["autosub_position_pairs_match_reverse"] is True
    assert result["autosub_count_match"] is True
    assert result["official_bench_slots"] == []
    assert result["replay_bench_slots"] == []


def test_build_replay_record_rejects_missing_slot_or_player_outcome():
    payload, live, positions = fixture_payload()
    payload["picks"].pop()
    try:
        build_replay_record(payload, live, positions)
    except ValueError as exc:
        assert "15 players" in str(exc)
    else:
        raise AssertionError("expected malformed picks to be rejected")


def test_build_replay_record_normalizes_reserve_goalkeeper_from_any_bench_slot():
    payload, live, positions = fixture_payload()
    # The API's raw bench slots can place the reserve goalkeeper before
    # outfield substitutes; the replay contract keeps the outfield order
    # and moves the goalkeeper to the dedicated final bench slot.
    payload["picks"][11]["element"] = 2
    payload["picks"][12]["element"] = 7
    payload["picks"][13]["element"] = 11
    payload["picks"][14]["element"] = 12
    record = build_replay_record(payload, live, positions)
    assert record["decision"]["bench_order"] == ["7", "11", "12", "2"]
    result = audit_record(payload, live, positions)
    assert result["net_point_difference"] == 0

def test_audit_reconstructs_deadline_xi_and_bench_from_post_autosub_picks():
    payload, live, positions = fixture_payload()
    # Simulate the completed-GW picks response: the bench defender has moved
    # into the XI and the absent starter now occupies that bench slot.
    payload["picks"][4]["element"] = 7
    payload["picks"][11]["element"] = 6
    payload["automatic_subs"] = [{"element_in": 7, "element_out": 6, "event": 1}]
    live["elements"][5]["stats"]["minutes"] = 0
    live["elements"][5]["stats"]["total_points"] = 0
    live["elements"][6]["stats"]["minutes"] = 90
    record = build_replay_record(payload, live, positions)
    assert record["decision"]["starting_xi"] == ["1", "3", "4", "5", "6", "8", "9", "10", "13", "14", "15"]
    assert record["decision"]["bench_order"] == ["7", "11", "12", "2"]
    result = audit_record(payload, live, positions)
    assert result["autosub_pairs_match"] is True
    assert result["autosub_position_pairs_match"] is True
    assert result["autosub_count_match"] is True
    assert result["official_bench_slots"] == [1]
    assert result["replay_bench_slots"] == [1]
    assert result["official_out_starting_slots"] == [5]
    assert result["replay_out_starting_slots"] == [5]
    assert result["official_pair_played"] == [(True, False)]
    assert result["official_pair_minutes"] == [(90.0, 0.0)]
    assert result["chip"] == "triple_captain"
    assert result["initial_formation"] == "4-3-3"
    assert result["official_final_formation"] == "4-3-3"


def test_bench_boost_autosub_pairs_are_not_scoring_relevant():
    assert autosub_pairs_are_scoring_relevant(None, []) is True
    assert autosub_pairs_are_scoring_relevant("triple_captain", []) is True
    assert autosub_pairs_are_scoring_relevant("bench_boost", []) is False
    assert autosub_pairs_are_scoring_relevant("bench_boost", None) is False
