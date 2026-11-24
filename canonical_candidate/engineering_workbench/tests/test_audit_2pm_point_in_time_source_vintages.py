from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from audit_2pm_point_in_time_source_vintages import select_commit


class PointInTimeSourceVintageTests(unittest.TestCase):
    def test_selects_latest_commit_strictly_before_safety_cutoff(self):
        deadline = datetime(2026, 10, 24, 18, 30, tzinfo=timezone.utc)
        commits = [
            {"sha": "old", "committed_at": deadline - timedelta(days=3)},
            {"sha": "safe", "committed_at": deadline - timedelta(hours=1)},
            {"sha": "inside_buffer", "committed_at": deadline - timedelta(minutes=2)},
            {"sha": "after", "committed_at": deadline + timedelta(hours=1)},
        ]
        self.assertEqual(select_commit(commits, deadline)["sha"], "safe")

    def test_returns_none_when_no_source_commit_precedes_deadline(self):
        deadline = datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc)
        commits = [
            {"sha": "after", "committed_at": deadline + timedelta(hours=1)}
        ]
        self.assertIsNone(select_commit(commits, deadline))


if __name__ == "__main__":
    unittest.main()
