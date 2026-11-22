from __future__ import annotations

from m4_covar_fpl_api_replay_batch import acquire_replay_batch
from m4_covar_fpl_replay_validation import validate_replay_batch
from m4_covar_fpl_api_replay_fetch import BASE_URL


def payloads(events=(1, 2), unfinished=()):
    ids = list(range(1, 16))
    element_types = {
        1: 1, 2: 2, 3: 2, 4: 2, 5: 2,
        6: 3, 7: 3, 8: 3, 9: 3, 10: 4, 11: 4,
        12: 1, 13: 2, 14: 3, 15: 4,
    }
    bootstrap = {
        "events": [{"id": event, "finished": event not in unfinished} for event in events],
        "elements": [{"id": pid, "element_type": element_types[pid]} for pid in ids],
    }
    def event_payload(event):
        picks = []
        for position, pid in enumerate(ids, start=1):
            picks.append({
                "element": pid,
                "position": position,
                "multiplier": 2 if pid == 10 else (1 if position <= 11 else 0),
                "is_captain": pid == 10,
                "is_vice_captain": pid == 11,
            })
        return {
            "entry_history": {"event": event},
            "active_chip": None,
            "picks": picks,
        }
    live = {
        "elements": [
            {"id": pid, "stats": {
                "minutes": 90, "yellow_cards": 0, "red_cards": 0, "total_points": 2,
            }}
            for pid in ids
        ]
    }
    mapping = {f"{BASE_URL}/bootstrap-static/": bootstrap}
    for event in events:
        mapping[f"{BASE_URL}/entry/421025/event/{event}/picks/"] = event_payload(event)
        mapping[f"{BASE_URL}/event/{event}/live/"] = live
    return mapping


def test_captures_multiple_completed_gameweeks_and_validates_them():
    mapping = payloads((7, 8))
    result = acquire_replay_batch(
        421025, [7, 8], fetch=lambda url: mapping[url], min_successful=2
    )
    assert result["capture_report"]["status"] == "PASS"
    assert result["capture_report"]["captured_event_ids"] == [7, 8]
    assert result["capture_report"]["manager_entry_id_in_output"] is False
    assert "421025" not in str(result)
    validation = validate_replay_batch(result)
    assert validation["status"] == "PASS"
    assert validation["gameweeks"] == [7, 8]


def test_records_unfinished_gameweeks_without_blocking_completed_captures():
    mapping = payloads((7, 8), unfinished=(8,))
    result = acquire_replay_batch(
        421025, [7, 8], fetch=lambda url: mapping[url], min_successful=1
    )
    assert result["capture_report"]["status"] == "PASS"
    assert result["capture_report"]["captured_event_ids"] == [7]
    assert result["capture_report"]["skipped_unfinished_event_ids"] == [8]
    assert result["capture_report"]["failed_event_ids"] == []
    assert result["capture_report"]["skipped_count"] == 1


def test_rejects_duplicate_or_invalid_event_lists():
    mapping = payloads((7,))
    fetch = lambda url: mapping[url]
    try:
        acquire_replay_batch(421025, [7, 7], fetch=fetch)
    except ValueError as exc:
        assert "duplicates" in str(exc)
    else:
        raise AssertionError("duplicate event IDs were accepted")
    try:
        acquire_replay_batch(421025, [True], fetch=fetch)
    except ValueError as exc:
        assert "positive integers" in str(exc)
    else:
        raise AssertionError("boolean event ID was accepted")
