from __future__ import annotations

import unittest

from m4_covar_unified_research_validation_report import (
    CovarResearchValidationReportError,
    build_covar_research_validation_report,
)


def _inputs():
    anchor = {
        "acceptance_status": "ACCEPTED_PLAYER_LEVEL_FORECAST_ANCHOR_ONLY",
        "forecast_snapshot_id": "m3-gw11-snapshot",
        "season": "2026-27",
        "target_gameweek": 11,
        "player_forecast_count": 2,
        "joint_distribution_available": False,
        "joint_probabilities_inferred": False,
        "decision_weight": 0.0,
        "production_eligible": False,
    }
    alignment = {
        "alignment_status": "PASS_EXPLICIT_SCENARIO_MARGINAL_ALIGNMENT_COMPUTED",
        "forecast_snapshot_id": "m3-gw11-snapshot",
        "season": "2026-27",
        "target_gameweek": 11,
        "scenario_source_id": "explicit-joint-scenario-catalogue-v1",
        "scenario_count": 4,
        "player_count": 2,
        "mean_absolute_error": 0.35,
        "root_mean_squared_error": 0.42,
        "mean_bias_scenario_minus_m3": -0.1,
        "maximum_absolute_error": 0.8,
        "joint_distribution_was_inferred": False,
        "fixture_independence_assumed": False,
        "calibration_established": False,
        "decision_weight": 0.0,
        "production_eligible": False,
    }
    realized = {
        "schema_version": "1.0.0",
        "season": "2026-27",
        "status": "PASS_STRUCTURAL_ONLY",
        "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_OFFICIAL_API_HISTORY",
        "fixture_rows": 6500,
        "player_gameweek_rows": 650,
        "finished_gameweeks": [1, 2],
        "missing_player_fixture_rows_zero_filled": 0,
    }
    audits = [
        {
            "season": "2026-27",
            "event_id": 1,
            "status": "PASS_EXACT_MATCH",
            "finality_reconciled": True,
            "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_FINAL_SCORING_AUDIT",
        },
        {
            "season": "2026-27",
            "event_id": 2,
            "status": "PASS_EXACT_MATCH",
            "finality_reconciled": True,
            "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_FINAL_SCORING_AUDIT",
        },
    ]
    calibration = {
        "evaluation_status": "HISTORICAL_BACKTEST_ONLY",
        "forecast_count": 3,
        "gameweek_count": 2,
        "by_gameweek": {
            "1": {"forecast_count": 2},
            "2": {"forecast_count": 1},
        },
        "mean_model_brier_score": 0.42,
        "mean_reference_brier_score": 0.5,
        "brier_skill_score_vs_reference": 0.16,
        "mean_model_log_loss": 0.8,
        "gameweek_cluster_confidence_intervals": {
            "independent_clusters": 2,
            "intervals": {"mean_model_brier_score": {"lower": 0.2, "upper": 0.7}},
        },
        "decision_weight": 0.0,
        "production_eligible": False,
    }
    return anchor, alignment, realized, audits, calibration


class TestCovarUnifiedResearchValidationReport(unittest.TestCase):
    def _build(self, values=None):
        anchor, alignment, realized, audits, calibration = values or _inputs()
        return build_covar_research_validation_report(
            anchor_acceptance=anchor,
            scenario_alignment=alignment,
            realized_dataset_report=realized,
            finality_audits=audits,
            joint_calibration_report=calibration,
        )

    def test_assembles_linked_evidence_and_preserves_boundaries(self):
        report = self._build()
        self.assertEqual(report["report_status"], "EVIDENCE_ASSEMBLED_WITH_EXPLICIT_LIMITATIONS")
        self.assertEqual(report["m3_anchor"]["forecast_snapshot_id"], "m3-gw11-snapshot")
        self.assertEqual(report["scenario_alignment"]["interpretation"], "MARGINAL_MEAN_CONSISTENCY_ONLY_NOT_JOINT_CALIBRATION")
        self.assertEqual(report["realized_outcomes"]["finality_audited_gameweeks"], [1, 2])
        self.assertEqual(report["joint_probability_calibration"]["independent_gameweek_clusters"], 2)
        self.assertEqual(report["joint_probability_calibration"]["readiness"], "LIMITED_HISTORICAL_EVIDENCE_FEW_INDEPENDENT_GAMEWEEKS")
        self.assertFalse(report["statistical_boundaries"]["m3_expected_points_used_as_joint_probabilities"])
        self.assertFalse(report["statistical_boundaries"]["predictive_validity_established"])
        self.assertEqual(report["decision_weight"], 0.0)
        self.assertFalse(report["production_eligible"])
        self.assertFalse(report["recommendations_changed"])
        self.assertFalse(report["transfers_changed"])
        self.assertFalse(report["starting_xi_changed"])
        self.assertFalse(report["captaincy_changed"])

    def test_rejects_anchor_that_claims_joint_distribution(self):
        values = list(_inputs())
        values[0]["joint_distribution_available"] = True
        with self.assertRaisesRegex(CovarResearchValidationReportError, "must not be represented"):
            self._build(tuple(values))

    def test_rejects_snapshot_or_gameweek_mismatch(self):
        values = list(_inputs())
        values[1]["forecast_snapshot_id"] = "different-snapshot"
        with self.assertRaisesRegex(CovarResearchValidationReportError, "snapshot"):
            self._build(tuple(values))

    def test_requires_exact_finality_audit_for_every_realized_gameweek(self):
        values = list(_inputs())
        values[3].pop()
        with self.assertRaisesRegex(CovarResearchValidationReportError, "lack exact finality audits"):
            self._build(tuple(values))

    def test_rejects_failed_finality_reconciliation(self):
        values = list(_inputs())
        values[3][0]["status"] = "FAIL_MISMATCH"
        with self.assertRaisesRegex(CovarResearchValidationReportError, "must pass exact"):
            self._build(tuple(values))

    def test_rejects_calibration_gameweek_outside_realized_coverage(self):
        values = list(_inputs())
        del values[4]["by_gameweek"]["2"]
        values[4]["by_gameweek"]["3"] = {"forecast_count": 1}
        with self.assertRaisesRegex(CovarResearchValidationReportError, "outside the reconciled"):
            self._build(tuple(values))

    def test_rejects_non_historical_calibration_status(self):
        values = list(_inputs())
        values[4]["evaluation_status"] = "CALIBRATED"
        with self.assertRaisesRegex(CovarResearchValidationReportError, "historical backtest"):
            self._build(tuple(values))


if __name__ == "__main__":
    unittest.main()
