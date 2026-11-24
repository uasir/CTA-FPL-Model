import unittest

from prepare_2pm_defensive_feature_arms import build_manifest


def make_schema(features):
    return {
        "component": "test_schema",
        "upstream_commit": "test-commit",
        "feature_count": len(features),
        "feature_order": features,
    }


class DefensiveFeatureArmManifestTests(unittest.TestCase):
    def test_derives_exact_27_and_complementary_arms(self):
        prefixes = [
            "ar_defensive_contribution_", "ar_cbit_", "ar_recoveries_",
            "ar_tackles_", "ar_dc_hit_rate_", "ar_dc_near_rate_",
            "ar_dc_ppg_", "ar_opp_dc_allowed_", "ar_opp_tackles_allowed_",
        ]
        defensive = [prefixes[i % len(prefixes)] + str(i) for i in range(27)]
        ordinary = [f"ordinary_{i}" for i in range(259)]
        features = ordinary[:100] + defensive + ordinary[100:]
        schema = make_schema(features)
        manifest = build_manifest(schema, b"schema")
        self.assertEqual(manifest["defensive_feature_count"], 27)
        self.assertEqual(manifest["arms"]["baseline"]["feature_count"], 259)
        self.assertEqual(manifest["arms"]["defensive_enhanced"]["feature_count"], 286)
        self.assertEqual(manifest["defensive_features_in_schema_order"], defensive)
        self.assertEqual(
            manifest["arms"]["baseline"]["features_in_schema_order"],
            [name for name in features if name not in set(defensive)],
        )

    def test_fails_closed_when_defensive_count_is_not_27(self):
        features = [f"ordinary_{i}" for i in range(286)]
        with self.assertRaisesRegex(ValueError, "defensive features"):
            build_manifest(make_schema(features), b"schema")

    def test_fails_closed_on_duplicate_feature_names(self):
        features = [f"ordinary_{i}" for i in range(286)]
        features[-1] = features[0]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_manifest(make_schema(features), b"schema")

    def test_fails_closed_when_schema_count_is_not_286(self):
        with self.assertRaisesRegex(ValueError, "schema features"):
            build_manifest(make_schema(["ordinary"]), b"schema")


if __name__ == "__main__":
    unittest.main()
