from datetime import datetime, timezone

import capture_predeadline_field_eo as capture


def test_capture_emits_explicit_provisional_predeadline_contract(monkeypatch):
    times = iter([
        datetime(2026, 11, 21, 10, 30, tzinfo=timezone.utc),
        datetime(2026, 11, 21, 10, 31, tzinfo=timezone.utc),
        datetime(2026, 11, 21, 10, 32, tzinfo=timezone.utc),
    ])
    monkeypatch.setattr(capture, "choose_pages", lambda *args: [1])
    monkeypatch.setattr(capture, "select_managers", lambda *args: [
        {"entry_id": 123, "rank_before_deadline": 10, "sample_weight": 10000.0}
    ])
    monkeypatch.setattr(capture, "normalize_picks", lambda *args: [{"entry_id": 123}])
    monkeypatch.setattr(capture, "official_player_ids", lambda bootstrap: [1])
    monkeypatch.setattr(capture, "estimate_effective_ownership", lambda *args, **kwargs: (
        [{
            "gameweek": 12, "fpl_element_id": "1", "sample_managers": 1,
            "sample_weight": 10000, "owned_by_pct": 100,
            "starting_pct": 100, "captain_pct": 100,
            "triple_captain_pct": 0, "effective_ownership_pct": 200,
            "scoring_exposure_pct": 200,
            "effective_ownership_pct_ci95_low": 190,
            "effective_ownership_pct_ci95_high": 210,
        }],
        {"sample_weight": 10000, "effective_sample_size": 1},
    ))
    monkeypatch.setattr(capture, "fetch_json", lambda url, delay=0.15: {})
    bootstrap = {"events": [{
        "id": 12, "deadline_time": "2026-11-21T11:00:00Z"
    }]}
    rows, report = capture.capture_predeadline(
        bootstrap, rank_limit=10000, sample_size=200,
        now_fn=lambda: next(times), deadline_window_minutes=35,
    )
    assert len(rows) == 1
    assert report["status"] == "CAPTURED_PRE_DEADLINE_CURRENT_PICKS"
    assert report["evidence_role"] == "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE"
    assert report["picks_lock_verified"] is False
    assert report["provisional_picks"] is True
    assert report["picks_captured_at_utc"] < report["deadline_time_utc"]


def test_capture_skips_outside_predeadline_window():
    bootstrap = {"events": [{
        "id": 12, "deadline_time": "2026-11-21T11:00:00Z"
    }]}
    rows, report = capture.capture_predeadline(
        bootstrap,
        now_fn=lambda: datetime(2026, 11, 21, 9, 0, tzinfo=timezone.utc),
    )
    assert rows is None
    assert report["status"] == "SKIPPED_OUTSIDE_PREDEADLINE_WINDOW"
