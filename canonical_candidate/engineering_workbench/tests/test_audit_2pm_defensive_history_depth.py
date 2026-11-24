from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from audit_2pm_defensive_history_depth import (
    _depth_record, _summarize, audit_history_depth,
)


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

    def test_history_depth_uses_only_completed_prior_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "merged_gw.csv"
            fixtures_path = root / "fixtures.csv"
            metadata_dir = root / "metadata"
            metadata_dir.mkdir()

            source = pd.DataFrame([
                {"fixture": 1, "element": 10, "team": 1, "opponent_team": 2,
                 "kickoff_time": "2026-01-01T12:00:00Z", "defensive_contribution": 2,
                 "clearances_blocks_interceptions": 1, "recoveries": 2, "tackles": 1},
                {"fixture": 2, "element": 10, "team": 1, "opponent_team": 2,
                 "kickoff_time": "2026-01-02T12:00:00Z", "defensive_contribution": None,
                 "clearances_blocks_interceptions": 0, "recoveries": 1, "tackles": 0},
                {"fixture": 3, "element": 10, "team": 1, "opponent_team": 2,
                 "kickoff_time": "2026-01-03T12:00:00Z", "defensive_contribution": 0,
                 "clearances_blocks_interceptions": 2, "recoveries": 0, "tackles": 3},
                {"fixture": 4, "element": 10, "team": 1, "opponent_team": 2,
                 "kickoff_time": "2026-01-05T12:00:00Z", "defensive_contribution": 99,
                 "clearances_blocks_interceptions": 99, "recoveries": 99, "tackles": 99},
            ])
            source.to_csv(source_path, index=False)
            pd.DataFrame([
                {"id": 1, "kickoff_time": "2026-01-01T12:00:00Z", "finished": True},
                {"id": 2, "kickoff_time": "2026-01-02T12:00:00Z", "finished": True},
                {"id": 3, "kickoff_time": "2026-01-03T12:00:00Z", "finished": True},
                {"id": 4, "kickoff_time": "2026-01-05T12:00:00Z", "finished": False},
            ]).to_csv(fixtures_path, index=False)
            pd.DataFrame([{
                "season": "2025-26", "gameweek": 4, "fpl_code": 10,
                "target_deadline_time": "2026-01-04T12:30:00Z",
                "fixture_ids": json.dumps(["4"]),
            }]).to_csv(metadata_dir / "metadata_player_gw_00000.csv", index=False)

            report, detail = audit_history_depth(
                source_path, fixtures_path, metadata_dir
            )
            player = detail.loc[detail["feature"].eq("ar_defensive_contribution_3")].iloc[0]
            opponent = detail.loc[detail["feature"].eq("ar_opp_dc_allowed_3")].iloc[0]
            self.assertEqual(player["selected_match_rows"], 3)
            self.assertEqual(player["finite_observations"], 2)
            self.assertEqual(opponent["selected_match_rows"], 3)
            self.assertEqual(opponent["finite_observations"], 2)
            self.assertEqual(report["target_fixture_queries"], 1)
            self.assertFalse(report["label_isolation"]["target_points_loaded"])


if __name__ == "__main__":
    unittest.main()
