import pytest

from replay_fpl_gameweek_decisions import replay_gameweek, compare_policy_replays


def make_roster():
    positions = {
        "g1": "GKP", "g2": "GKP",
        "d1": "DEF", "d2": "DEF", "d3": "DEF", "d4": "DEF", "d5": "DEF",
        "m1": "MID", "m2": "MID", "m3": "MID", "m4": "MID", "m5": "MID",
        "f1": "FWD", "f2": "FWD", "f3": "FWD",
    }
    decision = {
        "action_legality_verified": True,
        "starting_xi": ["g1", "d1", "d2", "d3", "d4", "m1", "m2", "m3", "f1", "f2", "f3"],
        "bench_order": ["d5", "m4", "m5", "g2"],
        "captain": "f1", "vice_captain": "m1",
        "transfers_made": 1, "free_transfers": 1,
    }
    return decision, positions


def outcomes(positions, points=None, mins=None):
    points = points or {p: 2 for p in positions}
    mins = mins or {p: 90 for p in positions}
    return points, mins


def test_replay_scores_normal_xi_and_captain():
    decision, positions = make_roster()
    points, mins = outcomes(positions)
    points["f1"] = 8
    result = replay_gameweek(decision, points, mins, positions)
    assert result["starting_xi_base_points_after_autosubs"] == 28
    assert result["captain_extra_points"] == 8
    assert result["net_points"] == 36
    assert result["transfer_hit_points"] == 0


def test_autosub_respects_legal_formation_and_bench_order():
    decision, positions = make_roster()
    points, mins = outcomes(positions)
    mins["d1"] = 0
    points["d5"] = 6
    result = replay_gameweek(decision, points, mins, positions)
    assert result["substitutions"][0] == {"out": "d1", "in": "d5", "reason": "outfield_absence"}
    assert result["net_points"] == 28


def test_captaincy_passes_to_vice_when_captain_does_not_play():
    decision, positions = make_roster()
    points, mins = outcomes(positions)
    mins["f1"] = 0
    points["m1"] = 7
    result = replay_gameweek(decision, points, mins, positions)
    assert result["effective_captain"] == "m1"
    assert result["captain_extra_points"] == 7


def test_triple_captain_adds_two_extra_copies():
    decision, positions = make_roster()
    decision["chip"] = "triple_captain"
    decision["chip_legality_verified"] = True
    points, mins = outcomes(positions)
    points["f1"] = 8
    result = replay_gameweek(decision, points, mins, positions)
    assert result["captain_extra_points"] == 16
    assert result["net_points"] == 44


def test_bench_boost_adds_all_bench_points_and_disables_autosub_double_count():
    decision, positions = make_roster()
    decision["chip"] = "bench_boost"
    decision["chip_legality_verified"] = True
    points, mins = outcomes(positions)
    mins["d1"] = 0
    points["d5"] = 6
    result = replay_gameweek(decision, points, mins, positions)
    assert result["bench_points_added"] == 12
    assert result["substitutions"] == []
    assert result["net_points"] == 34


def test_transfer_hits_and_free_hit_wildcard_waiver():
    decision, positions = make_roster()
    decision["transfers_made"] = 3
    decision["free_transfers"] = 1
    points, mins = outcomes(positions)
    assert replay_gameweek(decision, points, mins, positions)["net_points"] == 16
    for chip in ("free_hit", "wildcard"):
        candidate = dict(decision, chip=chip, chip_legality_verified=True)
        assert replay_gameweek(candidate, points, mins, positions)["net_points"] == 24


def test_replay_requires_explicit_legal_action_and_chip_verification():
    decision, positions = make_roster()
    points, mins = outcomes(positions)
    decision["action_legality_verified"] = False
    with pytest.raises(ValueError, match="action_legality_verified"):
        replay_gameweek(decision, points, mins, positions)
    decision["action_legality_verified"] = True
    decision["chip"] = "bench_boost"
    with pytest.raises(ValueError, match="chip_legality_verified"):
        replay_gameweek(decision, points, mins, positions)


def test_policy_comparison_is_paired_on_identical_start_state():
    decision, positions = make_roster()
    points, mins = outcomes(positions)
    baseline = dict(decision)
    improved = dict(decision, captain="m1", vice_captain="f1")
    rows = [
        {"deadline_id": "GW1", "starting_state_id": "s1", "policy": "hold",
         "decision": baseline, "official_points": points, "minutes": mins, "positions": positions,
         "decision_frozen_at": "2026-01-01T10:00:00Z", "deadline_at": "2026-01-01T11:00:00Z"},
        {"deadline_id": "GW1", "starting_state_id": "s1", "policy": "cta",
         "decision": improved, "official_points": points, "minutes": mins, "positions": positions,
         "decision_frozen_at": "2026-01-01T10:00:00Z", "deadline_at": "2026-01-01T11:00:00Z"},
    ]
    report = compare_policy_replays(rows, baseline_policy="hold")
    assert report["policies"]["cta"]["n_deadlines"] == 1
    assert report["policies"]["cta"]["mean_delta_vs_baseline"] == 0


def test_policy_comparison_rejects_mismatched_initial_states():
    decision, positions = make_roster()
    points, mins = outcomes(positions)
    rows = [
        {"deadline_id": "GW1", "starting_state_id": "s1", "policy": "hold",
         "decision": decision, "official_points": points, "minutes": mins, "positions": positions,
         "decision_frozen_at": "2026-01-01T10:00:00Z", "deadline_at": "2026-01-01T11:00:00Z"},
        {"deadline_id": "GW1", "starting_state_id": "s2", "policy": "cta",
         "decision": decision, "official_points": points, "minutes": mins, "positions": positions,
         "decision_frozen_at": "2026-01-01T10:00:00Z", "deadline_at": "2026-01-01T11:00:00Z"},
    ]
    with pytest.raises(ValueError, match="same starting state"):
        compare_policy_replays(rows)



def test_autosub_skips_first_bench_player_when_formation_would_be_illegal():
    decision, positions = make_roster()
    decision["starting_xi"] = ["g1", "d1", "d2", "d3", "m1", "m2", "m3", "m4", "m5", "f1", "f2"]
    decision["bench_order"] = ["f3", "d4", "d5", "g2"]
    points, mins = outcomes(positions)
    mins["d1"] = 0
    points["f3"] = 9
    points["d4"] = 5
    result = replay_gameweek(decision, points, mins, positions)
    assert result["substitutions"][0]["in"] == "d4"
    assert result["final_active_xi"].count("f3") == 0



def test_policy_replay_rejects_decision_frozen_after_deadline():
    decision, positions = make_roster()
    points, mins = outcomes(positions)
    row = {"deadline_id": "GW1", "starting_state_id": "s1", "policy": "hold",
           "decision": decision, "official_points": points, "minutes": mins, "positions": positions,
           "decision_frozen_at": "2026-01-01T11:00:00Z", "deadline_at": "2026-01-01T11:00:00Z"}
    with pytest.raises(ValueError, match="strictly before"):
        compare_policy_replays([row])


def test_policy_replay_requires_identical_policy_set_each_deadline():
    decision, positions = make_roster()
    points, mins = outcomes(positions)
    def row(gw, policy):
        return {"deadline_id": gw, "starting_state_id": "same", "policy": policy,
                "decision": decision, "official_points": points, "minutes": mins, "positions": positions,
                "decision_frozen_at": "2026-01-01T10:00:00Z", "deadline_at": "2026-01-01T11:00:00Z"}
    with pytest.raises(ValueError, match="same matched policy set"):
        compare_policy_replays([row("GW1", "hold"), row("GW1", "cta"), row("GW2", "hold")])



def test_triple_captain_bonus_passes_to_vice_captain():
    decision, positions = make_roster()
    decision["chip"] = "triple_captain"
    decision["chip_legality_verified"] = True
    points, mins = outcomes(positions)
    mins["f1"] = 0
    points["m1"] = 7
    result = replay_gameweek(decision, points, mins, positions)
    assert result["effective_captain"] == "m1"
    assert result["captain_extra_points"] == 14



def test_zero_minute_card_appearance_can_prevent_autosub_and_trigger_captaincy():
    decision, positions = make_roster()
    points, mins = outcomes(positions)
    mins["d1"] = 0
    points["d1"] = -1
    played = {p: True for p in positions}
    played["d1"] = True  # e.g. card recorded despite zero official minutes
    result = replay_gameweek(decision, points, mins, positions, played_by_player=played)
    assert result["substitutions"] == []
    assert "d1" in result["final_active_xi"]