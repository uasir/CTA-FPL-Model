from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, parse_qs

from capture_fpl_ranked_manager_picks import capture


def make_event(deadline, gameweek=11):
    return {"id": gameweek, "deadline_time": deadline.isoformat().replace("+00:00", "Z")}


def test_capture_uses_pre_deadline_ranks_and_post_deadline_picks():
    deadline = datetime(2026, 11, 21, 11, 0, tzinfo=timezone.utc)
    clock = [deadline - timedelta(minutes=5)]
    sleep_calls = []
    calls = []

    def now_fn():
        return clock[0]

    def sleep_fn(seconds):
        sleep_calls.append(seconds)
        clock[0] += timedelta(seconds=seconds)

    def fetch(url, delay=0):
        calls.append(url)
        if "leagues-classic/314/standings" in url:
            page = int(parse_qs(urlparse(url).query)["page_standings"][0])
            start = (page - 1) * 50 + 1
            return {"standings": {"results": [
                {"entry": start + offset + 10000, "rank": start + offset}
                for offset in range(50)
            ]}}
        if url.endswith("/bootstrap-static/"):
            return {"events": [make_event(deadline)]}
        if "/picks/" in url:
            entry_id = int(url.split("/entry/")[1].split("/")[0])
            return {
                "entry_history": {"event": 11},
                "active_chip": None,
                "picks": [
                    {"element": position, "position": position,
                     "is_captain": position == 1, "is_vice_captain": position == 2}
                    for position in range(1, 16)
                ],
            }
        raise AssertionError(f"Unexpected URL: {url}")

    rows, metadata = capture(
        {"events": [make_event(deadline)]},
        fetch=fetch,
        rank_limit=100,
        sample_size=2,
        delay=0,
        workers=1,
        deadline_window_minutes=7,
        lock_grace_seconds=60,
        now_fn=now_fn,
        sleep_fn=sleep_fn,
    )

    assert len(rows) == 30
    assert sleep_calls and sleep_calls[0] >= 300
    assert metadata["status"] == "CAPTURED_POST_DEADLINE_PICKS"
    assert metadata["picks_lock_verified"] is True
    assert datetime.fromisoformat(metadata["rank_cohort_captured_at_utc"]) < deadline
    assert datetime.fromisoformat(metadata["picks_captured_at_utc"]) >= deadline + timedelta(seconds=60)
    assert metadata["sample_weight_per_manager"] == 50
    assert sum("/picks/" in url for url in calls) == 2


def test_capture_skips_when_not_inside_pre_deadline_window():
    deadline = datetime(2026, 11, 21, 11, 0, tzinfo=timezone.utc)
    now = deadline - timedelta(minutes=30)
    rows, metadata = capture(
        {"events": [make_event(deadline)]},
        fetch=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("fetch should not run")),
        rank_limit=100,
        sample_size=2,
        deadline_window_minutes=7,
        now_fn=lambda: now,
        sleep_fn=lambda _seconds: None,
    )
    assert rows == []
    assert metadata["status"] == "SKIPPED_OUTSIDE_DEADLINE_WINDOW"
