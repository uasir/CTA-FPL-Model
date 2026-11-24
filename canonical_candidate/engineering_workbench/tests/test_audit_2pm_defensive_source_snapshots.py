import unittest

import pandas as pd

from audit_2pm_defensive_source_snapshots import audit_frame


class DefensiveSourceAuditTests(unittest.TestCase):
    def test_counts_zero_nonzero_and_missing_without_scores(self):
        frame = pd.DataFrame({
            "element": [1, 1, 2, 2],
            "GW": [1, 1, 1, 2],
            "minutes": [90, 0, 60, 30],
            "defensive_contribution": [0, 99, 12, None],
            "clearances_blocks_interceptions": [1, 99, 0, 2],
            "recoveries": [2, 99, None, 3],
            "tackles": [0, 99, 4, 1],
        })
        result = audit_frame(frame)
        self.assertEqual(result["played_player_fixture_rows"], 3)
        self.assertEqual(result["fields"]["defensive_contribution"]["observed_zero_values"], 1)
        self.assertEqual(result["fields"]["defensive_contribution"]["observed_nonzero_values"], 1)
        self.assertEqual(result["fields"]["defensive_contribution"]["missing_values"], 1)
        self.assertEqual(result["gameweeks"]["1"]["played_player_fixture_rows"], 2)

    def test_structurally_absent_field_is_not_zero_filled(self):
        frame = pd.DataFrame({
            "element": [1, 2],
            "GW": [1, 2],
            "minutes": [90, 60],
            "defensive_contribution": [0, 4],
        })
        result = audit_frame(frame)
        field = result["fields"]["tackles"]
        self.assertFalse(field["source_column_present"])
        self.assertEqual(field["finite_values"], 0)
        self.assertEqual(field["missing_values"], 2)


if __name__ == "__main__":
    unittest.main()
