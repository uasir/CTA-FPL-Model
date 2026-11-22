from __future__ import annotations

from m4_covar_public_field_replay_audit import (
    _autosub_pair_diagnostic,
    audit_public_field_replays,
    sample_public_entries,
)
from m4_covar_fpl_api_replay_fetch import BASE_URL


def manager_payload(event, chip=None):
    ids = list(range(1, 16))
    types = {1: 1, 2: 2, 3: 2, 4: 2, 5: 2, 6: 3, 7: 3, 8: 3, 9: 3, 10: 4, 11: 4, 12: 1, 13: 2, 14: 3, 15: 4}
    picks = []
    for position, pid in enumerate(ids, 1):
        picks.append({
            "element": pid, "position": position,
            "multiplier": 2 if pid == 10 else (1 if position <= 11 else 0),
            "is_captain": pid == 10, "is_vice_captain": pid == 11,
        })
    bootstrap = {
        "events": [{"id": event, "finished": True, "data_checked": True}],
        "elements": [{"id": pid, "element_type": types[pid]} for pid in ids],
    }
    live = {"elements": [{
        "id": pid,
        "stats": {"minutes": 90, "yellow_cards": 0, "red_cards": 0, "total_points": 2},
    } for pid in ids]}
    picks_response = {
        "entry_history": {"event": event, "points": 24, "event_transfers_cost": 0},
        "active_chip": chip, "picks": picks, "automatic_subs": [],
    }
    return bootstrap, live, picks_response


def test_autosub_pair_diagnostic_reports_positions_without_player_ids():
    case = {
        "lineup": {
            "player_ids": [str(i) for i in range(101, 116)],
            "player_positions": {
                **{"101": "GK", "112": "GK"},
                **{str(i): "DEF" for i in [102, 103, 104, 105, 113]},
                **{str(i): "MID" for i in [106, 107, 108, 109, 114]},
                **{str(i): "FWD" for i in [110, 111, 115]},
            },
        }
    }
    result = {
        "mismatched_automatic_substitutions": [{
            "resolver_pairs": [("113", "102")],
            "api_metadata_pairs": [("114", "102")],
        }],
        "official_multiplier_match": True,
        "official_team_points_reconcile": True,
    }
    diagnostic = _autosub_pair_diagnostic(case, result, event_id=8, rank_page=2000)
    assert diagnostic["same_incoming_player_set"] is False
    assert diagnostic["same_outgoing_player_set"] is True
    assert diagnostic["resolver_pairs_by_position"] == [{
        "incoming_original_position": 13,
        "incoming_role": "DEF",
        "outgoing_original_position": 2,
        "outgoing_role": "DEF",
    }]
    assert "113" not in str(diagnostic)
    assert "114" not in str(diagnostic)


def test_samples_public_entries_without_retaining_identity_in_report():
    pages = {
        1: {"standings": {"results": [
            {"entry": 100, "rank": 1},
            {"entry": 200, "rank": 2},
            {"entry": 300, "rank": 3},
        ]}},
        200: {"standings": {"results": [
            {"entry": 100, "rank": 1},
            {"entry": 400, "rank": 10000},
        ]}},
    }
    selected = sample_public_entries(pages, rank_pages=[1, 200], sample_positions=[0, 1])
    assert selected == [
        {"entry_id": 100, "rank_page": 1},
        {"entry_id": 200, "rank_page": 1},
        {"entry_id": 400, "rank_page": 200},
    ]


def test_audits_public_manager_replays_and_emits_aggregate_only():
    bootstrap, live, picks = manager_payload(7)
    mapping = {
        f"{BASE_URL}/bootstrap-static/": bootstrap,
        f"{BASE_URL}/leagues-classic/314/standings/?page_standings=1": {
            "standings": {"results": [{"entry": 100, "rank": 1}]}
        },
        f"{BASE_URL}/event/7/live/": live,
        f"{BASE_URL}/entry/100/event/7/picks/": picks,
    }
    report = audit_public_field_replays(
        [7], rank_pages=[1], sample_positions=[0], min_replays=1,
        fetch=lambda url: mapping[url], sleep=lambda _: None,
    )
    assert report["status"] == "PASS"
    assert report["replay_count"] == 1
    assert report["passed_count"] == 1
    assert report["team_points_reconciliation_cases"] == 1
    assert report["team_points_reconciliation_failures"] == 0
    assert report["autosub_replay_count"] == 0
    assert report["automatic_substitution_metadata_mismatch_replays"] == 0
    assert report["manager_entry_ids_retained"] is False
    assert "100" not in str(report)


def test_counts_real_outfield_autosub_from_final_pick_multipliers():
    bootstrap, live, picks = manager_payload(7)
    live["elements"][1]["stats"].update({"minutes": 0, "total_points": 0})
    live["elements"][12]["stats"].update({"minutes": 90, "total_points": 2})
    picks["picks"][1]["position"] = 13
    picks["picks"][1]["multiplier"] = 0
    picks["picks"][12]["position"] = 2
    picks["picks"][12]["multiplier"] = 1
    picks["automatic_subs"] = [{"element_in": 13, "element_out": 2, "event": 7}]
    mapping = {
        f"{BASE_URL}/bootstrap-static/": bootstrap,
        f"{BASE_URL}/leagues-classic/314/standings/?page_standings=1": {
            "standings": {"results": [{"entry": 100, "rank": 1}]}
        },
        f"{BASE_URL}/event/7/live/": live,
        f"{BASE_URL}/entry/100/event/7/picks/": picks,
    }
    report = audit_public_field_replays(
        [7], rank_pages=[1], sample_positions=[0], min_replays=1,
        fetch=lambda url: mapping[url], sleep=lambda _: None,
    )
    assert report["validation_status"] == "PASS"
    assert report["autosub_replay_count"] == 1
    assert report["autosub_player_count"] == 1
    assert report["outfield_autosub_count"] == 1
    assert report["goalkeeper_autosub_count"] == 0
    assert report["automatic_substitution_metadata_mismatch_replays"] == 0


def test_skips_unfinished_events_and_excludes_bench_boost_from_autosub_counts():
    bootstrap, live, picks = manager_payload(7, chip="bboost")
    bootstrap["events"].append({"id": 8, "finished": False, "data_checked": False})
    mapping = {
        f"{BASE_URL}/bootstrap-static/": bootstrap,
        f"{BASE_URL}/leagues-classic/314/standings/?page_standings=1": {
            "standings": {"results": [{"entry": 100, "rank": 1}]}
        },
        f"{BASE_URL}/event/7/live/": live,
        f"{BASE_URL}/entry/100/event/7/picks/": {
            **picks, "active_chip": "bboost",
            "picks": [{**row, "multiplier": 2 if row["element"] == 10 else 1} for row in picks["picks"]],
            "entry_history": {"event": 7, "points": 32, "event_transfers_cost": 0},
        },
    }
    report = audit_public_field_replays(
        [7, 8], rank_pages=[1], sample_positions=[0], min_replays=1,
        fetch=lambda url: mapping[url], sleep=lambda _: None,
    )
    assert report["status"] == "PASS"
    assert report["skipped_unfinalized_event_ids"] == [8]
    assert report["autosub_replay_count"] == 0
