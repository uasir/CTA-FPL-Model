from __future__ import annotations

import copy
import unittest

from m4_field_context_diagnostics import (
    FieldDiagnosticsError, build_field_context_diagnostics,
)
from test_m4_candidate_field_comparison import binding_fixture


class TestM4FieldContextDiagnostics(unittest.TestCase):
    def test_reports_sample_coverage_missingness_and_interval_width(self):
        binding = binding_fixture()
        report = build_field_context_diagnostics(binding)
        self.assertEqual(report["status"], "PASS_FIELD_CONTEXT_DIAGNOSTICS")
        self.assertEqual(report["sample"]["manager_count"], 500)
        self.assertEqual(report["coverage"]["field_player_row_count"], 16)
        self.assertFalse(report["release_eligible"])
        self.assertEqual(report["covar"], "DISABLED")

    def test_preserves_null_metrics_and_intervals(self):
        binding = binding_fixture()
        binding["field_eo_rows"][0]["effective_ownership_pct"] = None
        binding["field_eo_rows"][0]["effective_ownership_pct_ci95_low"] = None
        binding["field_eo_rows"][0]["effective_ownership_pct_ci95_high"] = None
        report = build_field_context_diagnostics(binding)
        self.assertEqual(
            report["metric_missingness_and_ranges"]["effective_ownership_pct"]["null_player_count"], 1
        )
        self.assertEqual(report["effective_ownership_ci95"]["missing_interval_count"], 1)

    def test_rejects_half_interval_and_inverted_interval(self):
        binding = binding_fixture()
        binding["field_eo_rows"][0]["effective_ownership_pct_ci95_high"] = None
        with self.assertRaisesRegex(FieldDiagnosticsError, "incomplete"):
            build_field_context_diagnostics(binding)
        binding = binding_fixture()
        binding["field_eo_rows"][0]["effective_ownership_pct_ci95_low"] = 80
        binding["field_eo_rows"][0]["effective_ownership_pct_ci95_high"] = 70
        with self.assertRaisesRegex(FieldDiagnosticsError, "inverted"):
            build_field_context_diagnostics(binding)

    def test_rejects_non_finite_or_negative_metric(self):
        binding = binding_fixture()
        binding["field_eo_rows"][0]["starting_pct"] = float("nan")
        with self.assertRaisesRegex(FieldDiagnosticsError, "finite"):
            build_field_context_diagnostics(binding)


if __name__ == "__main__":
    unittest.main()
