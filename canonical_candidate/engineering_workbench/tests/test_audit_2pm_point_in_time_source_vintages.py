from __future__ import annotations

import json
import lzma
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone

from audit_2pm_point_in_time_source_vintages import (
    _field_parity,
    _probe_payload,
    _snapshot_for_deadline,
    _season_capture_bounds,
    select_commit,
)


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

    def test_season_capture_bounds_are_season_scoped(self):
        start, end = _season_capture_bounds("2021-22")
        self.assertEqual(start, datetime(2021, 6, 1, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2022, 7, 1, tzinfo=timezone.utc))

    def test_probe_finds_2020_21_from_its_archived_capture_window(self):
        payload = {
            "events": [
                {"id": 38, "deadline_time": "2021-05-23T15:00:00Z"}
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json.xz"
            path.write_bytes(lzma.compress(json.dumps(payload).encode("utf-8")))
            captured = datetime(2021, 5, 23, 12, 0, tzinfo=timezone.utc)
            selected_at, selected_path, selected_payload = _probe_payload(
                [(captured, path)], "2020-21"
            )
        self.assertEqual(selected_at, captured)
        self.assertEqual(selected_path, path)
        self.assertEqual(selected_payload, payload)

    def test_previous_season_snapshot_is_not_used_for_next_seasons_deadline(self):
        previous_season_payload = {
            "events": [
                {"id": 1, "deadline_time": "2020-09-12T10:00:00Z"}
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "previous-season.json.xz"
            path.write_bytes(
                lzma.compress(json.dumps(previous_season_payload).encode("utf-8"))
            )
            captured = datetime(2021, 4, 18, 6, 24, tzinfo=timezone.utc)
            result = _snapshot_for_deadline(
                [(captured, path)],
                "2021-22",
                1,
                datetime(2021, 7, 30, 10, 0, tzinfo=timezone.utc),
            )
        self.assertEqual(result["status"], "no_pre_deadline_snapshot")

    def test_prior_match_field_parity_detects_source_revisions(self):
        historical = __import__("pandas").DataFrame({
            "fixture": ["101", "102"],
            "element": [1, 1],
            "total_points": [4, 2],
        })
        final = __import__("pandas").DataFrame({
            "fixture": ["101", "102"],
            "element": [1, 1],
            "total_points": [4, 3],
        })
        report = _field_parity(historical, final, ("total_points",))
        self.assertEqual(report["common_prior_keys"], 2)
        self.assertEqual(report["fields"]["total_points"]["exact_match_rows"], 1)
        self.assertEqual(report["fields"]["total_points"]["changed_rows"], 1)
        self.assertEqual(report["fields"]["total_points"]["exact_match_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
