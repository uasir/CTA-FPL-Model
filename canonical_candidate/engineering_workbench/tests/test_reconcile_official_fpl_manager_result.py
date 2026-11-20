import copy

import pytest

from reconcile_official_fpl_manager_result import (
    OfficialReconciliationError,
    reconcile_official_manager_result,
)


def _payload():
    ids = list(range(1, 16))
    points = {player_id: 2 for player_id in ids}
    points.update({10: 2, 11: 5, 13: 4, 14: 6})
    # Starting players 3 and 11 did not play. Bench 13 and 14 replace them.
    multipliers = {
        1: 1, 2: 1, 3: 0, 4: 1, 5: 1, 6: 1, 7: 1, 8: 1, 9: 1,
        10: 2, 11: 0, 12: 0, 13: 1, 14: 1, 15: 0,
    }
    picks = []
    for position, player_id in enumerate(ids[:11], 1):
        picks.append({
            "element": player_id, "position": position,
            "is_captain": player_id == 11,
            "is_vice_captain": player_id == 10,
            "multiplier": multipliers[player_id],
        })
    picks.append({
        "element": 12, "position": 12, "is_captain": False,
        "is_vice_captain": False, "multiplier": multipliers[12],
    })
    for position, player_id in enumerate(ids[12:], 13):
        picks.append({
            "element": player_id, "position": position,
            "is_captain": False, "is_vice_captain": False,
            "multiplier": multipliers[player_id],
        })
    return {
        "local_score": {
            "gross_points": 30,
            "outfield_substitutions": [
                {"player_out_id": 3, "player_in_id": 13},
                {"player_out_id": 11, "player_in_id": 14},
            ],
            "goalkeeper_substitution": None,
            "effective_captain_id": 10,
        },
        "official_picks": {
            "active_chip": None,
            "picks": picks,
            "automatic_subs": [
                {"element_out": 3, "element_in": 13, "event": 10},
                {"element_out": 11, "element_in": 14, "event": 10},
            ],
            "entry_history": {
                "event": 10, "points": 30, "event_transfers_cost": 0,
            },
        },
        "official_live": {
            "elements": [
                {"id": player_id, "stats": {"total_points": points[player_id]}}
                for player_id in ids
            ]
        },
        "manager_team_id": 421025,
        "target_gameweek": 10,
        "expected_starting_xi": list(range(1, 12)),
        "expected_bench_order": [13, 14, 15],
        "expected_reserve_goalkeeper_id": 12,
        "expected_captain_id": 11,
        "expected_vice_captain_id": 10,
    }


def _run(payload):
    return reconcile_official_manager_result(
        payload["local_score"], payload["official_picks"], payload["official_live"],
        manager_team_id=payload["manager_team_id"],
        target_gameweek=payload["target_gameweek"],
        expected_starting_xi=payload["expected_starting_xi"],
        expected_bench_order=payload["expected_bench_order"],
        expected_reserve_goalkeeper_id=payload["expected_reserve_goalkeeper_id"],
        expected_captain_id=payload["expected_captain_id"],
        expected_vice_captain_id=payload["expected_vice_captain_id"],
    )


def test_reconciles_official_autosubs_captain_fallback_and_net_score():
    result = _run(_payload())
    assert result["status"] == "RECONCILED"
    assert result["official_gross_points"] == 30
    assert result["official_net_points"] == 30
    assert result["effective_captain_id"] == 10
    assert result["score_delta"] == 0
    assert result["historical_evidence_admitted"] is False


def test_rejects_local_autosub_mismatch():
    payload = _payload()
    payload["local_score"]["outfield_substitutions"][0]["player_in_id"] = 15
    with pytest.raises(OfficialReconciliationError, match="do not match official"):
        _run(payload)


def test_rejects_local_score_mismatch():
    payload = _payload()
    payload["local_score"]["gross_points"] = 29
    with pytest.raises(OfficialReconciliationError, match="gross score"):
        _run(payload)


def test_rejects_inconsistent_official_event_points():
    payload = _payload()
    payload["official_picks"]["entry_history"]["points"] = 29
    with pytest.raises(OfficialReconciliationError, match="does not reconcile|mismatch"):
        _run(payload)


def test_rejects_captain_fallback_mismatch():
    payload = _payload()
    payload["local_score"]["effective_captain_id"] = 11
    with pytest.raises(OfficialReconciliationError, match="captain/vice fallback"):
        _run(payload)


def test_rejects_different_deadline_starting_xi():
    payload = _payload()
    payload["expected_starting_xi"][0] = 15
    with pytest.raises(OfficialReconciliationError, match="starting XI"):
        _run(payload)


def test_rejects_chips_and_incomplete_live_points():
    payload = _payload()
    payload["official_picks"]["active_chip"] = "bboost"
    with pytest.raises(OfficialReconciliationError, match="chip gameweeks"):
        _run(payload)
    payload = _payload()
    payload["official_live"]["elements"].pop()
    with pytest.raises(OfficialReconciliationError, match="do not cover"):
        _run(payload)
