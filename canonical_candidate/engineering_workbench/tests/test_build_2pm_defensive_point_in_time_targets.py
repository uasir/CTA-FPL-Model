from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from build_2pm_defensive_point_in_time_targets import (
    MERGED_GW_REPAIR_LOG,
    _source_status,
    read_merged_gw_with_name_repair,
)


class PointInTimeTargetCandidateTests(unittest.TestCase):
    def test_source_status_records_both_pinned_sources(self):
        value = _source_status("vaastavsha", "fplcachesha", "cache/2026/10/23/1652.json.xz")
        self.assertIn("vaastavsha", value)
        self.assertIn("fplcachesha", value)
        self.assertIn("1652.json.xz", value)

    def test_repairs_only_unquoted_leading_name_commas_without_dropping_row(self):
        MERGED_GW_REPAIR_LOG.clear()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "merged_gw.csv"
            path.write_text(
                "name,position,team,element,fixture,kickoff_time,minutes,GW\n"
                "Doe, John,DEF,Arsenal,123,456,2025-09-27T12:30:00Z,90,6\n",
                encoding="utf-8",
            )
            frame = read_merged_gw_with_name_repair(path)
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.loc[0, "name"], "Doe, John")
        self.assertEqual(frame.loc[0, "position"], "DEF")
        self.assertEqual(int(frame.loc[0, "element"]), 123)
        self.assertEqual(int(frame.loc[0, "minutes"]), 90)
        self.assertEqual(len(MERGED_GW_REPAIR_LOG), 1)
        self.assertEqual(MERGED_GW_REPAIR_LOG[0]["extra_fields"], 1)

    def test_unrepairable_malformed_row_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "merged_gw.csv"
            path.write_text(
                "name,position,team,element,fixture,kickoff_time,minutes,GW\n"
                "Doe, John,UNKNOWN,Arsenal,123,456,2025-09-27T12:30:00Z,90,6\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                read_merged_gw_with_name_repair(path)


if __name__ == "__main__":
    unittest.main()
