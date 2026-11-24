import unittest

import pandas as pd

from audit_2pm_defensive_warmup import audit_frame, derive_defensive_features


PREFIXES = [
    "ar_defensive_contribution_", "ar_cbit_", "ar_recoveries_",
    "ar_tackles_", "ar_dc_hit_rate_", "ar_dc_near_rate_",
    "ar_dc_ppg_", "ar_opp_dc_allowed_", "ar_opp_tackles_allowed_",
]


def make_features():
    return [PREFIXES[i % len(PREFIXES)] + str(i) for i in range(27)]


class DefensiveWarmupAuditTests(unittest.TestCase):
    def test_schema_derives_exact_27(self):
        features = make_features()
        schema = {"feature_order": [f"ordinary_{i}" for i in range(259)] + features}
        self.assertEqual(derive_defensive_features(schema), features)

    def test_schema_count_guard(self):
        with self.assertRaisesRegex(ValueError, "exactly 286"):
            derive_defensive_features({"feature_order": ["x"]})

    def test_missingness_is_not_zero_and_is_reported_by_gw(self):
        features = make_features()
        rows = []
        for gw, player, value in [(1, 10, None), (1, 11, 0.0), (2, 10, 2.0), (2, 11, 0.0)]:
            row = {"season": "2025-26", "gameweek": gw, "fpl_code": player, "fixture": f"fx-{gw}-{player}"}
            row.update({name: value for name in features})
            rows.append(row)
        report = audit_frame(pd.DataFrame(rows), features)
        first = report["feature_level"][features[0]]
        self.assertEqual(first["missing"], 1)
        self.assertEqual(first["zero"], 2)
        self.assertEqual(report["gameweek_level"]["1"]["complete_27_feature_rows"], 1)
        self.assertEqual(report["gameweek_level"]["2"]["complete_27_feature_rows"], 2)
        self.assertFalse(report["label_isolation"]["target_points_loaded"])

    def test_rejects_non_2025_26_rows(self):
        features = make_features()
        row = {"season": "2026-27", "gameweek": 1, "fpl_code": 10, "fixture": "fx-1"}
        row.update({name: 0.0 for name in features})
        with self.assertRaisesRegex(ValueError, "only 2025-26"):
            audit_frame(pd.DataFrame([row]), features)


if __name__ == "__main__":
    unittest.main()
