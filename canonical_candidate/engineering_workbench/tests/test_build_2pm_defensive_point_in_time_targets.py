from __future__ import annotations

import tempfile
import unittest
from types import SimpleNamespace

import pandas as pd
from pathlib import Path

from build_2pm_defensive_point_in_time_targets import (
    MERGED_GW_SCHEMA_NORMALIZATION_LOG,
    _source_status,
    install_relevant_understat_player_filter,
    read_merged_gw_with_schema_normalization,
)


class PointInTimeTargetCandidateTests(unittest.TestCase):
    def test_source_status_records_both_pinned_sources(self):
        value = _source_status("vaastavsha", "fplcachesha", "cache/2026/10/23/1652.json.xz")
        self.assertIn("vaastavsha", value)
        self.assertIn("fplcachesha", value)
        self.assertIn("1652.json.xz", value)

    def test_understat_player_selection_uses_target_dataset_and_excludes_failed_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "vaastav" / "2025-26"
            raw.mkdir(parents=True)
            pd.DataFrame({
                "id": [10, 11, 12, 13],
                "code": [100, 101, 102, 103],
            }).to_csv(raw / "players_raw.csv", index=False)
            pd.DataFrame({"element": [10, 11, 10, 12]}).to_csv(
                raw / "merged_gw.csv", index=False
            )
            mappings = SimpleNamespace(
                assignments_for_seasons=lambda seasons: pd.DataFrame({
                    "season": ["2025-26"] * 4,
                    "fpl_code": [100, 101, 102, 103],
                    "understat_id": [500, 76, 87, 700],
                })
            )
            sources = SimpleNamespace(
                _needed_understat_ids=lambda _raw, _seasons: {500, 76, 87, 700}
            )
            report = install_relevant_understat_player_filter(
                sources, mappings, Path(tmp), "2025-26"
            )
            self.assertEqual(sources._needed_understat_ids(Path(tmp), ["2024-25", "2025-26"]), {500})
            self.assertEqual(report["dataset_fpl_element_count"], 3)
            self.assertEqual(report["mapped_target_player_count"], 1)
            self.assertEqual(report["understat_player_ids"], [500])
            self.assertEqual(report["excluded_understat_player_ids"], [76, 87])

    def test_unions_manager_columns_and_preserves_older_rows_as_missing(self):
        MERGED_GW_SCHEMA_NORMALIZATION_LOG.clear()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "merged_gw.csv"
            path.write_text(
                "name,position,team,minutes,round,GW\n"
                "Older Player,DEF,Arsenal,90,1,1\n"
                "Later Player,MID,Arsenal,0,0,0,0,0,0,0,0,22,22\n",
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
