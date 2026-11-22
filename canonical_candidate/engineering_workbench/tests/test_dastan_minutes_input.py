import unittest

from build_dastan_minutes_input import build_rows


class DastanMinutesInputTests(unittest.TestCase):
    def setUp(self):
        self.schema = {
            "schema_version": "1.0.0",
            "feature_count": 2,
            "feature_order": ["feature_a", "feature_b"],
            "upstream": {"feature_cols_blob_sha": "pinned"},
        }
        self.row = {
            "fpl_element_id": "101",
            "fixture_id": "9001",
            "position": "MID",
            "feature_a": "1.25",
            "feature_b": "-1",
        }

    def test_orders_and_accepts_complete_numeric_features(self):
        rows, report = build_rows([self.row], self.schema)
        self.assertEqual(list(rows[0]), ["fpl_element_id", "fixture_id", "position", "feature_a", "feature_b"])
        self.assertEqual(rows[0]["feature_b"], -1.0)
        self.assertEqual(report["status"], "PASS_SCHEMA_ONLY_NOT_MODEL_VALIDATION")

    def test_rejects_missing_feature_instead_of_imputing(self):
        row = dict(self.row)
        row["feature_b"] = ""
        with self.assertRaisesRegex(ValueError, "missing feature value"):
            build_rows([row], self.schema)

    def test_rejects_duplicate_player_fixture(self):
        with self.assertRaisesRegex(ValueError, "duplicate player-fixture"):
            build_rows([self.row, self.row], self.schema)

    def test_rejects_unknown_position(self):
        row = dict(self.row, position="UNKNOWN")
        with self.assertRaisesRegex(ValueError, "unsupported position"):
            build_rows([row], self.schema)


if __name__ == "__main__":
    unittest.main()
