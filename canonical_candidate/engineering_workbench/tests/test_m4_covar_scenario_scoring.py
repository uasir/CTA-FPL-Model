from __future__ import annotations

import copy
import unittest

from m4_covar_scenario_scoring import CovarScoringError, score_scenario_portfolios
from test_m4_covar_scenario_contract import fixture


class TestM4CovarScenarioScoring(unittest.TestCase):
    def test_scores_portfolios_and_defaults_to_regular_gameweek(self):
        result = score_scenario_portfolios(fixture())
        self.assertEqual(result["mode"], "REGULAR_GW")
        self.assertEqual(result["input_validation_status"], "VALID_SYNTHETIC_RESEARCH_INPUT")
        self.assertEqual(result["portfolio_results"]["conventional"]["expected_points"], 22.5)
        self.assertEqual(result["portfolio_results"]["covar-stack"]["expected_points"], 19.0)
        self.assertEqual(result["field_comparison_status"], "NOT_AVAILABLE_NO_EXPLICIT_FIELD_PORTFOLIO")
        self.assertEqual(result["decision_weight"], 0.0)
        self.assertFalse(result["production_eligible"])

    def test_variance_decomposition_reconciles_to_portfolio_variance(self):
        result = score_scenario_portfolios(fixture())
        for portfolio in result["portfolio_results"].values():
            self.assertAlmostEqual(
                portfolio["variance_decomposition_total"],
                portfolio["variance"],
                places=9,
            )

    def test_explicit_baseline_comparison_is_scenario_matched(self):
        result = score_scenario_portfolios(
            fixture(), baseline_portfolio_id="conventional"
        )
        stack = result["portfolio_results"]["covar-stack"]["baseline_comparison"]
        self.assertEqual(stack["baseline_portfolio_id"], "conventional")
        self.assertAlmostEqual(stack["expected_points_difference"], -3.5)
        self.assertEqual(stack["probability_outscoring_baseline"], 0.5)
        self.assertEqual(result["portfolio_results"]["conventional"]["baseline_comparison"]["expected_points_difference"], 0)

    def test_rejects_unknown_baseline(self):
        with self.assertRaisesRegex(CovarScoringError, "not present"):
            score_scenario_portfolios(fixture(), baseline_portfolio_id="field")

    def test_free_hit_requires_explicit_mode_and_is_labelled(self):
        doc = fixture()
        doc["mode"] = "FREE_HIT"
        result = score_scenario_portfolios(doc)
        self.assertEqual(result["mode"], "FREE_HIT")

    def test_same_team_defensive_stack_concentrates_fixture_outcome_variance(self):
        result = score_scenario_portfolios(fixture())
        stack = result["portfolio_results"]["covar-stack"]
        # Both A players rise together in A's clean-sheet scenario and fall together in B's win.
        pair = next(
            row for row in stack["variance_decomposition"]
            if row["player_a"] == "a1" and row["player_b"] == "a2"
        )
        self.assertGreater(pair["covariance_contribution"], 0)
        self.assertGreater(stack["variance"], 0)

    def test_opposing_player_pair_can_reduce_portfolio_variance(self):
        result = score_scenario_portfolios(fixture())
        conventional = result["portfolio_results"]["conventional"]
        pair = next(
            row for row in conventional["variance_decomposition"]
            if row["player_a"] == "a1" and row["player_b"] == "b1"
        )
        self.assertLess(pair["covariance_contribution"], 0)

    def test_lower_effective_ownership_captain_multiplier_is_explicit_not_free_upside(self):
        doc = fixture()
        doc["players"][1]["effective_ownership_pct"] = 8
        doc["players"][1]["captain_pct"] = 0.5
        doc["portfolios"].append({
            "portfolio_id": "low-eo-captain",
            "player_ids": ["a1", "a2"],
            "captain_id": "a2",
            "captain_multiplier": 2,
        })
        result = score_scenario_portfolios(doc, baseline_portfolio_id="covar-stack")
        low_eo = result["portfolio_results"]["low-eo-captain"]
        self.assertEqual(low_eo["expected_points"], 14.0)
        self.assertEqual(
            low_eo["baseline_comparison"]["expected_points_difference"], -5.0
        )
        self.assertEqual(doc["players"][1]["effective_ownership_pct"], 8)

    def test_rejects_unknown_mode(self):
        doc = fixture()
        doc["mode"] = "AUTO"
        with self.assertRaisesRegex(CovarScoringError, "mode must be"):
            score_scenario_portfolios(doc)

    def test_captain_multiplier_is_applied_to_scenario_points(self):
        doc = fixture()
        doc["portfolios"][0]["captain_multiplier"] = 3
        result = score_scenario_portfolios(doc)
        # a1 contributes 3x 12 in scenario one and 3x 2 in scenario two.
        scores = result["portfolio_results"]["conventional"]["scenario_scores"]
        self.assertEqual([row["points"] for row in scores], [38.0, 21.0])


if __name__ == "__main__":
    unittest.main()
