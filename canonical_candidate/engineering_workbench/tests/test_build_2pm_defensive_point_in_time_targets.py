from __future__ import annotations

import unittest

from build_2pm_defensive_point_in_time_targets import _source_status


class PointInTimeTargetCandidateTests(unittest.TestCase):
    def test_source_status_records_both_pinned_sources(self):
        value = _source_status("vaastavsha", "fplcachesha", "cache/2026/10/23/1652.json.xz")
        self.assertIn("vaastavsha", value)
        self.assertIn("fplcachesha", value)
        self.assertIn("1652.json.xz", value)


if __name__ == "__main__":
    unittest.main()
