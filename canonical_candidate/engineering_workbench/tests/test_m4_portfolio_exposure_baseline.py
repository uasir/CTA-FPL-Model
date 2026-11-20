from __future__ import annotations

import unittest

from m4_portfolio_exposure_baseline import (
    PortfolioBaselineError, build_portfolio_exposure_baseline,
)
from test_m4_candidate_field_comparison import binding_fixture
from m4_candidate_field_comparison import compare_frozen_candidate_to_field


class TestM4PortfolioExposureBaseline(unittest.TestCase):
    def test_reports_non_covariance_hold_and_transfer_baselines(self):
        binding = binding_fixture()
        for row in binding["field_eo_rows"]:
            row["owned_by_pct"] = 40.0
            row["effective_ownership_pct"] = 30.0
            row["starting_pct"] = 25.0
            row["captain_pct"] = 5.0
            row["triple_captain_pct"] = 0.0
            row["scoring_exposure_pct"] = 35.0
        comparison = compare_frozen_candidate_to_field(binding)
        report = build_portfolio_exposure_baseline(binding, comparison)
        self.assertEqual(report["status"], "PASS_NONCOVARIANCE_PORTFOLIO_EXPOSURE_BASELINE")
        self.assertEqual(len(report["scenarios"]), 2)
        self.assertEqual(report["scenarios"][0]["field_eo_concentration_within_squad"]["hhi"], round(1/15, 10))
        self.assertEqual(report["scenarios"][1]["scenario"], "TRANSFER")
        self.assertEqual(report["covar"], "DISABLED")
        self.assertFalse(report["release_eligible"])

    def test_keeps_nulls_and_withholds_concentration_when_any_value_missing(self):
        binding = binding_fixture()
        binding["field_eo_rows"][0]["effective_ownership_pct"] = None
        report = build_portfolio_exposure_baseline(binding)
        hold = report["scenarios"][0]
        self.assertIsNone(hold["field_exposure_sums"]["effective_ownership_pct"]["squad_sum_pct_points"])
        self.assertEqual(hold["field_exposure_sums"]["effective_ownership_pct"]["squad_missing_count"], 1)
        self.assertFalse(hold["field_eo_concentration_within_squad"]["available"])

    def test_rejects_missing_squad_coverage(self):
        binding = binding_fixture()
        binding["field_eo_rows"] = [
            row for row in binding["field_eo_rows"] if row["fpl_element_id"] != "15"
        ]
        with self.assertRaisesRegex(PortfolioBaselineError, "missing squad players"):
            build_portfolio_exposure_baseline(binding)


if __name__ == "__main__":
    unittest.main()
