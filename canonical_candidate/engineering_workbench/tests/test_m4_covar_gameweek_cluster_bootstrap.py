import unittest
from m4_covar_gameweek_cluster_bootstrap import evaluate_gameweek_cluster_bootstrap, GameweekClusterBootstrapError

def row(fid, gw, m, r):
    return {"forecast_id": fid, "gameweek_id": gw, "model_brier_score": m, "reference_brier_score": r, "brier_score_difference_model_minus_reference": m-r}

class TestGameweekClusterBootstrap(unittest.TestCase):
    def test_reproducible_seed_and_cluster_counts(self):
        data = [row("a", "1", .2, .4), row("b", "1", .4, .6), row("c", "2", .5, .7), row("d", "3", .3, .5)]
        first = evaluate_gameweek_cluster_bootstrap(data, resamples=500, seed=17)
        second = evaluate_gameweek_cluster_bootstrap(data, resamples=500, seed=17)
        self.assertEqual(first, second)
        self.assertEqual(first["independent_clusters"], 3)
        self.assertEqual(first["point_estimate"]["mean_model_brier_score"], (.3+.5+.3)/3)
        self.assertEqual(first["method"], "PAIRED_PERCENTILE_CLUSTER_BOOTSTRAP_BY_GAMEWEEK")
    def test_repeated_forecasts_are_averaged_inside_gameweek(self):
        data = [row("a", "1", .2, .4), row("b", "1", .6, .8), row("c", "2", .4, .6)]
        result = evaluate_gameweek_cluster_bootstrap(data, resamples=200)
        self.assertAlmostEqual(result["point_estimate"]["mean_model_brier_score"], .4)
        self.assertEqual(result["independent_clusters"], 2)
    def test_reports_small_sample_warning(self):
        result = evaluate_gameweek_cluster_bootstrap([row("a", "1", .2, .4)], resamples=100)
        self.assertIsNotNone(result["small_sample_warning"])
    def test_rejects_duplicate_forecast_ids(self):
        with self.assertRaisesRegex(GameweekClusterBootstrapError, "unique"):
            evaluate_gameweek_cluster_bootstrap([row("a", "1", .2, .4), row("a", "2", .3, .5)])
    def test_rejects_too_few_resamples_and_nonfinite_scores(self):
        with self.assertRaises(GameweekClusterBootstrapError):
            evaluate_gameweek_cluster_bootstrap([row("a", "1", .2, .4)], resamples=20)
        bad = row("b", "2", float("nan"), .4)
        with self.assertRaisesRegex(GameweekClusterBootstrapError, "finite"):
            evaluate_gameweek_cluster_bootstrap([bad])

if __name__ == "__main__": unittest.main()
