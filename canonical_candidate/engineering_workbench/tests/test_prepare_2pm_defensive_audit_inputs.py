from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from prepare_2pm_defensive_audit_inputs import prepare_inputs


class PrepareDefensiveAuditInputsTests(unittest.TestCase):
    def test_projects_only_defensive_columns_and_copies_2025_26_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "artifact"
            tensor_root = artifact / (
                "2pm-dastan-candidate/postmatch-grouped-dataset/"
                "player_gameweek_tensors"
            )
            tensor_root.mkdir(parents=True)
            postmatch = artifact / (
                "2pm-dastan-candidate/postmatch-grouped-dataset/postmatch_states.parquet"
            )
            postmatch.parent.mkdir(parents=True, exist_ok=True)
            postmatch.write_bytes(b"mock-parquet")
            metadata = tensor_root / "2025-26_gw06/metadata_player_gw_00000.csv"
            metadata.parent.mkdir(parents=True)
            pd.DataFrame({
                "season": ["2025-26"],
                "gameweek": [6],
                "fpl_code": [1],
                "target_points": [2],
            }).to_csv(metadata, index=False)

            schema_path = root / "schema.json"
            schema_path.write_text(json.dumps({
                "feature_order": [
                    "ar_defensive_contribution_3",
                    "ar_defensive_contribution_5",
                    "ar_defensive_contribution_10",
                    "ar_defensive_contribution_38",
                    "ar_cbit_3", "ar_cbit_5", "ar_cbit_10", "ar_cbit_38",
                    "ar_recoveries_3", "ar_recoveries_5", "ar_recoveries_10",
                    "ar_recoveries_38", "ar_tackles_3", "ar_tackles_5",
                    "ar_tackles_10", "ar_tackles_38", "ar_dc_hit_rate_3",
                    "ar_dc_hit_rate_5", "ar_dc_hit_rate_10", "ar_dc_near_rate_3",
                    "ar_dc_near_rate_5", "ar_dc_near_rate_10", "ar_dc_ppg_5",
                    "ar_opp_dc_allowed_3", "ar_opp_dc_allowed_5",
                    "ar_opp_dc_allowed_10", "ar_opp_tackles_allowed_5",
                    *[f"other_{i}" for i in range(259)],
                ]
            }), encoding="utf-8")

            requested_columns = []
            def fake_read_parquet(path, columns):
                requested_columns.extend(columns)
                return pd.DataFrame({
                    "season": ["2024-25", "2025-26"],
                    "gameweek": [38, 6],
                    "fpl_code": [1, 1],
                    "fixture": ["old", "new"],
                    **{name: [None, 1.0] for name in columns if name.startswith("ar_")},
                })

            output = root / "out"
            with patch("prepare_2pm_defensive_audit_inputs.pd.read_parquet",
                       side_effect=fake_read_parquet), \
                 patch("prepare_2pm_defensive_audit_inputs.pd.DataFrame.to_parquet"):
                report = prepare_inputs(artifact, schema_path, output)

            self.assertEqual(report["postmatch_rows_selected"], 1)
            self.assertEqual(report["defensive_feature_count"], 27)
            self.assertFalse(report["target_points_loaded_for_warmup"])
            self.assertNotIn("target_points", requested_columns)
            self.assertNotIn("total_points", requested_columns)
            self.assertEqual(report["metadata_files_copied"], 1)
            self.assertTrue((output / "metadata_2025-26" / metadata.name).is_file())


if __name__ == "__main__":
    unittest.main()
