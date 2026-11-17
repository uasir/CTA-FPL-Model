import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from evaluate_fpl_naive_baselines import evaluate,metrics,ranks

class BaselineEvaluationTests(unittest.TestCase):
    def test_average_ranks_handle_ties(self):
        self.assertEqual(ranks([10,10,20]),[1.5,1.5,3.0])
    def test_rolling_baselines_are_reported_as_exploratory(self):
        rows=[
          {"gameweek":"4","prior_gameweeks_count":"3","prior_gw_points":"5","prior3_gw_points_avg":"4","prior5_gw_points_avg":"","target_total_points":"6"},
          {"gameweek":"4","prior_gameweeks_count":"3","prior_gw_points":"2","prior3_gw_points_avg":"3","prior5_gw_points_avg":"","target_total_points":"1"},
          {"gameweek":"4","prior_gameweeks_count":"3","prior_gw_points":"4","prior3_gw_points_avg":"3.5","prior5_gw_points_avg":"","target_total_points":"4"},
          {"gameweek":"4","prior_gameweeks_count":"3","prior_gw_points":"1","prior3_gw_points_avg":"2","prior5_gw_points_avg":"","target_total_points":"2"},
          {"gameweek":"4","prior_gameweeks_count":"3","prior_gw_points":"3","prior3_gw_points_avg":"3","prior5_gw_points_avg":"","target_total_points":"3"},
        ]
        report=evaluate(rows,"2026-27")
        self.assertEqual(report["status"],"EXPLORATORY_ONLY")
        self.assertFalse(report["model_trained"])
        self.assertEqual(report["baselines"]["last3_gameweeks"]["n"],5)
        self.assertIsNotNone(report["baselines"]["last3_gameweeks"]["mae"])
    def test_rows_without_enough_history_are_excluded(self):
        rows=[{"gameweek":"2","prior_gameweeks_count":"1","prior_gw_points":"5","prior3_gw_points_avg":"","prior5_gw_points_avg":"","target_total_points":"3"}]
        report=evaluate(rows)
        self.assertEqual(report["baselines"]["last3_gameweeks"]["n"],0)
if __name__=="__main__":unittest.main()
