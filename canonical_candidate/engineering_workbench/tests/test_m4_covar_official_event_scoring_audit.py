from __future__ import annotations

from m4_covar_official_event_scoring_audit import (
    OfficialEventScoringAuditError,
    audit_completed_gameweeks,
    audit_official_event_payload,
)


def payload(events=(1,)):
    bootstrap = {
        "events": [{"id": event, "finished": True, "data_checked": True} for event in events],
        "elements": [{"id": 10, "element_type": 1}],
    }
    live = {
        "elements": [{
            "id": 10,
            "stats": {"total_points": 8},
            "explain": [{
                "fixture": 100 + events[0],
                "stats": [
                    {"identifier": "minutes", "value": 90, "points": 2},
                    {"identifier": "clean_sheets", "value": 1, "points": 4},
                    {"identifier": "saves", "value": 3, "points": 1},
                    {"identifier": "bonus", "value": 1, "points": 1},
                ],
            }],
        }]
    }
    return bootstrap, live


def test_reconciles_fixture_points_with_official_fpl_explain():
    bootstrap, live = payload()
    report = audit_official_event_payload(live, bootstrap, event_id=1)
    assert report["mismatch_count"] == 0
    assert report["matched_fixture_rows"] == 1
    assert report["official_gameweek_points_sum"] == 8
    assert report["calculated_gameweek_points_sum"] == 8


def test_reconciles_double_gameweek_fixture_rows_independently():
    bootstrap, _ = payload((2,))
    live = {
        "elements": [{
            "id": 10,
            "stats": {"total_points": 10},
            "explain": [
                {"fixture": 201, "stats": [
                    {"identifier": "minutes", "value": 90, "points": 2},
                    {"identifier": "saves", "value": 3, "points": 1},
                ]},
                {"fixture": 202, "stats": [
                    {"identifier": "minutes", "value": 75, "points": 2},
                    {"identifier": "clean_sheets", "value": 1, "points": 4},
                    {"identifier": "bonus", "value": 1, "points": 1},
                ]},
            ],
        }]
    }
    report = audit_official_event_payload(live, bootstrap, event_id=2)
    assert report["mismatch_count"] == 0
    assert report["fixture_rows"] == 2
    assert report["official_gameweek_points_sum"] == 10
    assert report["calculated_gameweek_points_sum"] == 10


def test_fails_on_unmapped_positive_official_scoring_identifier():
    bootstrap, live = payload()
    live["elements"][0]["explain"][0]["stats"].append({
        "identifier": "unmapped_new_bonus", "value": 1, "points": 2,
    })
    report = audit_official_event_payload(live, bootstrap, event_id=1)
    assert report["mismatch_count"] == 1
    assert report["unknown_positive_identifiers"] == {"unmapped_new_bonus": 1}


def test_skips_unfinished_or_not_data_checked_gameweeks():
    bootstrap, live = payload((1, 2))
    bootstrap["events"][1]["data_checked"] = False
    mapping = {
        "https://fantasy.premierleague.com/api/bootstrap-static/": bootstrap,
        "https://fantasy.premierleague.com/api/event/1/live/": live,
    }
    report = audit_completed_gameweeks(
        [1, 2], fetch=lambda url: mapping[url], sleep=lambda _: None
    )
    assert report["status"] == "PASS"
    assert report["audited_event_ids"] == [1]
    assert report["skipped_event_ids"] == [2]
    assert report["mismatch_count"] == 0


def test_rejects_duplicate_fixture_rows_for_same_player():
    bootstrap, live = payload()
    live["elements"][0]["explain"].append(live["elements"][0]["explain"][0].copy())
    try:
        audit_official_event_payload(live, bootstrap, event_id=1)
    except OfficialEventScoringAuditError as exc:
        assert "duplicate fixture" in str(exc)
    else:
        raise AssertionError("duplicate fixture explain row was accepted")
