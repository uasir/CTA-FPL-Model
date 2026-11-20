from __future__ import annotations

import unittest
from datetime import datetime, timezone

from capture_predeadline_field_eo import capture_predeadline


def make_bootstrap(deadline="2026-11-20T21:00:00Z"):
    return {"events": [{"id": 12, "deadline_time": deadline}],
            "elements": [{"id": element} for element in range(1, 16)]}


class Clock:
    def __init__(self, values):
        self.values = iter(values)
    def __call__(self):
        return next(self.values)


class TestPredeadlineFieldCapture(unittest.TestCase):
    def _fetch(self, url, delay=0):
        if "standings" in url:
            page = int(url.split("page_standings=")[1])
            first = (page - 1) * 50 + 1
            return {"standings": {"results": [
                {"rank": rank, "entry": rank + 100000} for rank in range(first, first + 50)
            ]}}
        entry = int(url.split("/entry/")[1].split("/")[0])
        return {"entry_history": {"event": 12}, "active_chip": None, "picks": [
            {"element": element, "position": pos, "is_captain": pos == 1,
             "is_vice_captain": pos == 2}
            for pos, element in enumerate(range(1, 16), start=1)
        ]}

    def test_captures_provisional_picks_before_deadline(self):
        clock = Clock([
            datetime(2026, 11, 20, 20, 30, tzinfo=timezone.utc),
            datetime(2026, 11, 20, 20, 31, tzinfo=timezone.utc),
            datetime(2026, 11, 20, 20, 32, tzinfo=timezone.utc),
            datetime(2026, 11, 20, 20, 33, tzinfo=timezone.utc),
        ])
        rows, report = capture_predeadline(
            make_bootstrap(), fetch=self._fetch, rank_limit=100, sample_size=100,
            delay=0, workers=2, deadline_window_minutes=35, now_fn=clock,
        )
        self.assertEqual(len(rows), 15)
        self.assertEqual(report["status"], "CAPTURED_PRE_DEADLINE_CURRENT_PICKS")
        self.assertFalse(report["picks_lock_verified"])
        self.assertTrue(report["provisional_picks"])
        self.assertLess(datetime.fromisoformat(report["picks_captured_at_utc"]),
                        datetime.fromisoformat(report["deadline_time_utc"]))
        self.assertEqual(report["sample_managers"], 100)
        field_artifact = report["anonymized_manager_portfolios"]
        self.assertEqual(field_artifact["metadata"]["manager_count"], 100)
        self.assertFalse(field_artifact["metadata"]["manager_identifiers_retained"])
        self.assertNotIn("entry_id", str(field_artifact))
        self.assertAlmostEqual(
            sum(row["field_weight"] for row in field_artifact["portfolios"]), 1.0
        )

    def test_rejects_capture_that_crosses_deadline(self):
        clock = Clock([
            datetime(2026, 11, 20, 20, 30, tzinfo=timezone.utc),
            datetime(2026, 11, 20, 20, 31, tzinfo=timezone.utc),
            datetime(2026, 11, 20, 21, 0, tzinfo=timezone.utc),
        ])
        with self.assertRaisesRegex(RuntimeError, "crossed deadline"):
            capture_predeadline(
                make_bootstrap(), fetch=self._fetch, rank_limit=100, sample_size=100,
                delay=0, workers=2, deadline_window_minutes=35, now_fn=clock,
            )

    def test_skips_when_outside_capture_window(self):
        clock = Clock([datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)])
        rows, report = capture_predeadline(
            make_bootstrap(), fetch=self._fetch, rank_limit=100, sample_size=100,
            delay=0, workers=2, deadline_window_minutes=35, now_fn=clock,
        )
        self.assertEqual(rows, [])
        self.assertEqual(report["status"], "SKIPPED_OUTSIDE_DEADLINE_WINDOW")


if __name__ == "__main__":
    unittest.main()
