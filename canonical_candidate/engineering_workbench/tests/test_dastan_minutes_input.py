import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_dastan_minutes_input import build_rows


class DastanMinutesInputTests(unittest.TestCase):
    def setUp(self):
        self.schema = {
            "schema_version": "1.0.0",
            "feature_count": 4,
            "feature_order": ["feature_a", "feature_b", "ar_ep_next", "sig_status_risk"],
            "upstream": {"feature_cols_blob_sha": "pinned"},
        }
        self.row = {
            "fpl_element_id": "101",
            "fixture_id": "9001",
            "position": "MID",
            "feature_a": "1.25",
            "feature_b": "-1",
            "ar_ep_next": "",
            "sig_status_risk": "0",
        }

    def test_orders_and_accepts_complete_numeric_features(self):
        rows, report = build_rows([self.row], self.schema)
        self.assertEqual(list(rows[0]), ["fpl_element_id", "fixture_id", "position", "feature_a", "feature_b", "ar_ep_next", "sig_status_risk"])
        self.assertEqual(rows[0]["feature_b"], -1.0)
        self.assertEqual(rows[0]["ar_ep_next"], -1.0)
        self.assertEqual(report["missing_value_policy"]["snapshot_absence_sentinel"], -1.0)
        self.assertEqual(report["status"], "PASS_SCHEMA_ONLY_NOT_MODEL_VALIDATION")

    def test_residual_missing_feature_is_zero_filled(self):
        row = dict(self.row, feature_a="")
        rows, report = build_rows([row], self.schema)
        self.assertEqual(rows[0]["feature_a"], 0.0)
        self.assertEqual(report["missing_value_policy"]["residual_nan_fills"], 1)

    def test_rejects_duplicate_player_fixture(self):
        with self.assertRaisesRegex(ValueError, "duplicate player-fixture"):
            build_rows([self.row, self.row], self.schema)

    def test_rejects_unknown_position(self):
        row = dict(self.row, position="UNKNOWN")
        with self.assertRaisesRegex(ValueError, "unsupported position"):
            build_rows([row], self.schema)


if __name__ == "__main__":
    unittest.main()
