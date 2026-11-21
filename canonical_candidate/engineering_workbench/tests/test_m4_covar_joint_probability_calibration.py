from __future__ import annotations
import copy
import unittest
from m4_covar_joint_probability_calibration import (
    JointProbabilityCalibrationError, evaluate_joint_probability_calibration,
)

def forecast(fid="gw1-a", gw="1", observed="linked-upside"):
    return {
      "forecast_id":fid,"gameweek_id":gw,
      "as_of_utc":"2026-08-01T10:00:00Z",
      "training_cutoff_utc":"2026-07-31T23:59:00Z",
      "first_kickoff_utc":"2026-08-01T11:00:00Z",
      "probabilities":{"linked-upside":0.7,"linked-downside":0.3},
      "reference_probabilities":{"linked-upside":0.5,"linked-downside":0.5},
      "observed_state_id":observed,
    }

class TestJointProbabilityCalibration(unittest.TestCase):
    def test_scores_joint_forecasts_against_reference(self):
        result=evaluate_joint_probability_calibration([forecast()])
        self.assertEqual(result["forecast_count"],1)
        self.assertEqual(result["gameweek_count"],1)
        self.assertLess(result["mean_model_brier_score"],result["mean_reference_brier_score"])
        self.assertGreater(result["brier_skill_score_vs_reference"],0)
        self.assertFalse(result["production_eligible"])
        self.assertEqual(result["decision_weight"],0.0)
    def test_groups_results_by_gameweek(self):
        result=evaluate_joint_probability_calibration([forecast(),forecast("gw2-a","2","linked-downside")])
        self.assertEqual(result["gameweek_count"],2)
        self.assertEqual(result["by_gameweek"]["1"]["forecast_count"],1)
        self.assertEqual(result["by_gameweek"]["2"]["forecast_count"],1)
    def test_rejects_forecast_after_first_kickoff(self):
        row=forecast(); row["as_of_utc"]="2026-08-01T11:00:00Z"
        with self.assertRaisesRegex(JointProbabilityCalibrationError,"precede first kickoff"):
            evaluate_joint_probability_calibration([row])
    def test_rejects_training_cutoff_after_forecast(self):
        row=forecast(); row["training_cutoff_utc"]="2026-08-01T10:01:00Z"
        with self.assertRaisesRegex(JointProbabilityCalibrationError,"training cutoff"):
            evaluate_joint_probability_calibration([row])
    def test_rejects_probability_sum_or_catalogue_mismatch(self):
        row=forecast(); row["probabilities"]["linked-upside"]=0.8
        with self.assertRaisesRegex(JointProbabilityCalibrationError,"sum to 1"):
            evaluate_joint_probability_calibration([row])
        row=forecast(); row["reference_probabilities"]={"other":1.0}
        with self.assertRaisesRegex(JointProbabilityCalibrationError,"same joint state catalogue"):
            evaluate_joint_probability_calibration([row])
    def test_zero_probability_actual_is_not_silently_clipped(self):
        row=forecast(); row["probabilities"]={"linked-upside":0.0,"linked-downside":1.0}
        result=evaluate_joint_probability_calibration([row])
        self.assertEqual(result["zero_probability_actual_count_model"],1)
        self.assertIsNone(result["mean_model_log_loss"])
    def test_rejects_duplicate_forecast_ids(self):
        with self.assertRaisesRegex(JointProbabilityCalibrationError,"unique"):
            evaluate_joint_probability_calibration([forecast(),forecast()])
    def test_rejects_timezone_naive_timestamps(self):
        row=forecast(); row["as_of_utc"]="2026-08-01T10:00:00"
        with self.assertRaisesRegex(JointProbabilityCalibrationError,"timezone"):
            evaluate_joint_probability_calibration([row])


    def test_integrates_gameweek_cluster_confidence_intervals(self):
        rows = [
            forecast("gw1-a", "1"),
            forecast("gw1-b", "1", "linked-downside"),
            forecast("gw2-a", "2"),
        ]
        result = evaluate_joint_probability_calibration(rows, bootstrap_resamples=250, bootstrap_seed=7)
        self.assertEqual(result["schema_version"], "1.1.0")
        self.assertEqual(result["gameweek_cluster_confidence_intervals"]["independent_clusters"], 2)
        self.assertEqual(result["gameweek_cluster_confidence_intervals"]["seed"], 7)
        self.assertEqual(result["aggregation_estimands"]["top_level_brier_and_log_loss"], "FORECAST_ROW_WEIGHTED")
        self.assertEqual(result["aggregation_estimands"]["gameweek_cluster_bootstrap"], "GAMEWEEK_EQUAL_WEIGHTED_AFTER_WITHIN_GAMEWEEK_FORECAST_AVERAGING")
        self.assertIn("mean_model_brier_score", result["gameweek_cluster_confidence_intervals"]["intervals"])

    def test_rejects_invalid_bootstrap_configuration(self):
        with self.assertRaisesRegex(JointProbabilityCalibrationError, "bootstrap_resamples"):
            evaluate_joint_probability_calibration([forecast()], bootstrap_resamples=50)
        with self.assertRaisesRegex(JointProbabilityCalibrationError, "bootstrap_seed"):
            evaluate_joint_probability_calibration([forecast()], bootstrap_seed=True)

if __name__=="__main__": unittest.main()
