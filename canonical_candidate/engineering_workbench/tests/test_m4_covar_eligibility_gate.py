from __future__ import annotations

import unittest

from m4_covar_eligibility_gate import (
    CovarGateError, assess_covar_eligibility, portfolio_variance_sensitivity,
)


def covariance_fixture():
    return [
        {"player1_id": "1", "player2_id": "1", "covariance": 4.0},
        {"player1_id": "1", "player2_id": "2", "covariance": 2.0},
        {"player1_id": "2", "player2_id": "2", "covariance": 9.0},
    ]


def eligible_evidence_fixture():
    return {
        "point_in_time_evidence": {
            "status": "PASSED", "artifact_sha256": "a" * 64,
            "as_of_utc": "2026-01-01T00:00:00Z",
        },
        "uncertainty_assessment": {"status": "PASSED", "artifact_sha256": "b" * 64},
        "out_of_sample_validation": {
            "status": "PASSED", "artifact_sha256": "c" * 64,
            "incremental_utility_lower_ci": 0.01,
        },
    }


def eligible_policy_fixture():
    return {
        "minimum_window_gameweeks": 20,
        "minimum_complete_panel_coverage": 0.75,
        "minimum_correlation_of_correlations": 0.8,
        "maximum_median_absolute_correlation_change": 0.15,
        "maximum_relative_shrinkage_variance_spread": 0.5,
    }


class TestM4CovarEligibilityGate(unittest.TestCase):
    def test_shrinkage_sensitivity_keeps_diagonal_and_scales_off_diagonal(self):
        result = portfolio_variance_sensitivity(
            covariance_fixture(), {"1": 1, "2": 1}
        )
        self.assertEqual(result["status"], "COMPUTED_DESCRIPTIVE_SENSITIVITY")
        values = [row["portfolio_variance_points_squared"] for row in result["scenarios"]]
        self.assertEqual(values, [17.0, 16.0, 15.0, 14.0, 13.0])

    def test_incomplete_covariance_coverage_is_not_zero_filled(self):
        result = portfolio_variance_sensitivity(
            covariance_fixture()[:2], {"1": 1, "2": 1}
        )
        self.assertEqual(result["status"], "INCOMPLETE_COVARIANCE_COVERAGE")
        self.assertEqual(result["missing_player_ids"], ["2"])

    def test_existing_exploratory_artifact_is_blocked(self):
        report = {
            "status": "EXPLORATORY_ONSIDE_ACTUALS_ONLY",
            "point_in_time_status": "NOT_VERIFIED",
            "source_sha256": "a" * 64, "source_url": "https://example.test/source",
            "window_size": 20, "players_in_window": 100, "complete_panel_players": 80,
            "rolling_correlation_stability": {
                "status": "EXPLORATORY_STABILITY_DIAGNOSTIC",
                "correlation_of_correlations": 0.9,
                "median_absolute_correlation_change": 0.05,
            },
        }
        result = assess_covar_eligibility(report, covariance_fixture())
        self.assertEqual(result["status"], "RESEARCH_ONLY_BLOCKED")
        self.assertIn("point_in_time_integrity_not_verified", result["blockers"])
        self.assertIn("window_size_policy_missing_or_not_met", result["blockers"])
        self.assertIn("independent_uncertainty_assessment_missing", result["blockers"])
        self.assertEqual(result["decision_weight"], 0.0)
        self.assertFalse(result["production_eligible"])

    def test_complete_evidence_only_becomes_ready_for_review_not_production(self):
        report = {
            "status": "VALIDATED_RESEARCH_ARTIFACT",
            "point_in_time_status": "VERIFIED",
            "source_sha256": "d" * 64, "source_url": "https://example.test/source",
            "window_size": 30, "players_in_window": 100, "complete_panel_players": 90,
            "rolling_correlation_stability": {
                "status": "PASSED",
                "correlation_of_correlations": 0.9,
                "median_absolute_correlation_change": 0.05,
            },
        }
        result = assess_covar_eligibility(
            report, covariance_fixture(), evidence=eligible_evidence_fixture(),
            policy=eligible_policy_fixture(), portfolio_weights={"1": 1, "2": 1},
        )
        self.assertEqual(result["status"], "READY_FOR_EXPLICIT_REVIEW")
        self.assertEqual(result["decision_weight"], 0.0)
        self.assertFalse(result["production_eligible"])

    def test_rejects_nonfinite_covariance(self):
        rows = covariance_fixture()
        rows[0]["covariance"] = float("nan")
        with self.assertRaisesRegex(CovarGateError, "finite"):
            portfolio_variance_sensitivity(rows, {"1": 1, "2": 1})


if __name__ == "__main__":
    unittest.main()
