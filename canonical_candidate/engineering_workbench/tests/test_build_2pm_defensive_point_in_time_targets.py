from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from build_2pm_defensive_point_in_time_targets import (
    MERGED_GW_SCHEMA_NORMALIZATION_LOG,
    _source_status,
    read_merged_gw_with_schema_normalization,
)


class PointInTimeTargetCandidateTests(unittest.TestCase):
    def test_source_status_records_both_pinned_sources(self):
        value = _source_status("vaastavsha", "fplcachesha", "cache/2026/10/23/1652.json.xz")
        self.assertIn("vaastavsha", value)
        self.assertIn("fplcachesha", value)
        self.assertIn("1652.json.xz", value)

    def test_unions_manager_columns_and_preserves_older_rows_as_missing(self):
        MERGED_GW_SCHEMA_NORMALIZATION_LOG.clear()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "merged_gw.csv"
            path.write_text(
                "name,position,team,minutes,round,GW\n"
                "Older Player,DEF,Arsenal,90,1,1\n"
                "Later Player,MID,Arsenal,0,0,22,0,0,0,0,0,0,0,0,22\n",
                encoding="utf-8",
            )
            frame = read_merged_gw_with_schema_normalization(path)
        expected_manager_columns = [
            "mng_clean_sheets", "mng_draw", "mng_goals_scored", "mng_loss",
            "mng_underdog_draw", "mng_underdog_win", "mng_win",
        ]
        self.assertEqual(len(frame), 2)
        self.assertEqual(frame.columns[4:11].tolist(), expected_manager_columns)
        self.assertTrue(frame.loc[0, expected_manager_columns].isna().all())
        self.assertEqual(frame.loc[1, expected_manager_columns].tolist(), [0] * 7)
        self.assertEqual(int(frame.loc[1, "round"]), 22)
        self.assertEqual(int(frame.loc[1, "GW"]), 22)
        self.assertEqual(MERGED_GW_SCHEMA_NORMALIZATION_LOG[0]["rows_with_manager_columns"], 1)
        self.assertEqual(MERGED_GW_SCHEMA_NORMALIZATION_LOG[0]["rows_without_manager_columns_preserved_as_missing"], 1)

    def test_unrecognized_mixed_row_width_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "merged_gw.csv"
            path.write_text(
                "name,position,team,minutes,round,GW\n"
                "Player,DEF,Arsenal,90,1,1,unexpected\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                read_merged_gw_with_schema_normalization(path)


if __name__ == "__main__":
    unittest.main()
