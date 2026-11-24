from __future__ import annotations

import unittest

from audit_2pm_defensive_history_depth import _depth_record, _summarize


class DefensiveHistoryDepthTests(unittest.TestCase):
    def test_partial_history_is_not_mistaken_for_full_window(self):
        record = _depth_record(
            season="2025-26", gameweek=6, fpl_code=10, fixture=None,
            feature="ar_defensive_contribution_38", window=38,
            selected_rows=5, finite_observations=5,
        )
        self.assertFalse(record["full_window_depth"])
        self.assertEqual(record["selected_match_rows"], 5)
        self.assertEqual(record["finite_observations"], 5)

    def test_true_zero_observation_is_distinct_from_missing_within_window(self):
        partial = _depth_record(
            season="2025-26", gameweek=6, fpl_code=10, fixture=None,
            feature="ar_cbit_5", window=5, selected_rows=5, finite_observations=3,
        )
        zero = _depth_record(
            season="2025-26", gameweek=6, fpl_code=11, fixture=None,
            feature="ar_cbit_5", window=5, selected_rows=0, finite_observations=0,
        )
        summary = _summarize([partial, zero])
        self.assertEqual(summary["partial_or_shallow_rows"], 1)
        self.assertEqual(summary["zero_observation_rows"], 1)
        self.assertEqual(summary["min_finite_observations"], 0)
        self.assertEqual(summary["max_finite_observations"], 3)


if __name__ == "__main__":
    unittest.main()
