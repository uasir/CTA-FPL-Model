import tempfile
import unittest
from pathlib import Path

import pandas as pd

from audit_2pm_2025_26_labelled_gw_coverage import audit_metadata


class LabelledGameweekCoverageTests(unittest.TestCase):
    def write_metadata(self, root, rows):
        root.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(root / "metadata_player_gw_00000.csv", index=False)
        return root

    def test_reports_counts_and_possible_cutoffs_without_selecting_one(self):
        rows = []
        for gw in range(1, 16):
            for player in range(1, 4):
                rows.append({
                    "season": "2025-26", "gameweek": gw,
                    "fpl_code": player, "target_points": player - 2,
                })
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_metadata(self.write_metadata(Path(tmp), rows))
        self.assertEqual(report["labelled_player_gameweek_samples"], 45)
        self.assertEqual(report["per_gameweek_labelled_samples"]["1"], 3)
        self.assertTrue(report["candidate_chronological_cutoffs"])
        self.assertFalse(report["cutoff_policy"]["cutoff_selected"])
        self.assertFalse(report["training_authorized"])

    def test_rejects_2026_27_rows(self):
        row = {
            "season": "2026-27", "gameweek": 1,
            "fpl_code": 1, "target_points": 2,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_metadata(Path(tmp), [row])
            with self.assertRaisesRegex(ValueError, "Only 2025-26"):
                audit_metadata(path)

    def test_rejects_duplicate_player_gameweek(self):
        row = {
            "season": "2025-26", "gameweek": 1,
            "fpl_code": 1, "target_points": 2,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_metadata(Path(tmp), [row, row])
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                audit_metadata(path)


if __name__ == "__main__":
    unittest.main()
