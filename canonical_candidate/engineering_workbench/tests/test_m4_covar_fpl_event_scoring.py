from __future__ import annotations

import unittest

from m4_covar_scenario_scoring import score_scenario_portfolios
from m4_covar_fpl_event_scoring import (
    CovarEventScoringError,
    calculate_fpl_points_2026_27,
    score_scenario_events,
)
from test_m4_covar_scenario_contract import fixture


class TestM4CovarFplEventScoring(unittest.TestCase):
    def test_goalkeeper_scoring(self):
        result = calculate_fpl_points_2026_27("GK", {
            "minutes": 90, "goals": 1, "assists": 0, "clean_sheet": True,
            "saves": 4, "penalty_saves": 1, "defensive_contribution_count": 0,
            "penalty_misses": 0, "bonus_points": 3,
            "yellow_cards": 0,
            "red_cards": 0, "own_goals": 0,
        })
        self.assertEqual(result["fpl_points"], 25)
        self.assertEqual(result["point_breakdown"]["saves"], 1)
        self.assertEqual(result["point_breakdown"]["penalty_saves"], 5)

    def test_defender_scoring_and_goals_conceded_floor(self):
        result = calculate_fpl_points_2026_27("DEF", {
            "minutes": 90, "goals": 1, "assists": 1, "clean_sheet": False,
            "saves": 0, "penalty_saves": 0, "defensive_contribution_count": 20,
            "penalty_misses": 0, "bonus_points": 2,
            "yellow_cards": 1,
            "red_cards": 0, "own_goals": 1,
        })
        self.assertEqual(result["fpl_points"], 11)
        self.assertEqual(result["point_breakdown"]["defensive_contribution"], 2)
        self.assertEqual(result["point_breakdown"]["goals_conceded"], -1)

    def test_midfielder_and_forward_defensive_contribution_thresholds(self):
        mid = calculate_fpl_points_2026_27("MID", {
            "minutes": 60, "goals": 1, "assists": 1, "clean_sheet": True,
            "goals_conceded_while_on_pitch": 0, "defensive_contribution_count": 12, "bonus_points": 1,
            "penalty_misses": 1, "yellow_cards": 1, "red_cards": 1,
        })
        fwd = calculate_fpl_points_2026_27("FWD", {
            "minutes": 59, "goals": 2, "assists": 1, "clean_sheet": True,
            "goals_conceded_while_on_pitch": 0, "defensive_contribution_count": 12, "bonus_points": 0,
            "penalty_misses": 1, "yellow_cards": 1, "own_goals": 1,
        })
        self.assertEqual(mid["fpl_points"], 8)
        self.assertEqual(fwd["fpl_points"], 9)
        self.assertEqual(fwd["point_breakdown"]["clean_sheet"], 0)

    def test_appearance_and_clean_sheet_minute_threshold(self):
        result = calculate_fpl_points_2026_27("DEF", {
            "minutes": 59, "goals": 0, "assists": 0, "clean_sheet": True,
            "goals_conceded_while_on_pitch": 0,
        })
        self.assertEqual(result["fpl_points"], 1)

    def test_rejects_non_goalkeeper_save_events(self):
        with self.assertRaisesRegex(CovarEventScoringError, "only scored for GK"):
            calculate_fpl_points_2026_27("MID", {
                "minutes": 90, "goals": 0, "assists": 0, "clean_sheet": False,
                "goals_conceded_while_on_pitch": 0, "saves": 3,
            })

    def test_rejects_bonus_above_three_and_unknown_position(self):
        with self.assertRaisesRegex(CovarEventScoringError, "between 0 and 3"):
            calculate_fpl_points_2026_27("FWD", {
                "minutes": 90, "goals": 0, "assists": 0, "clean_sheet": False,
                "goals_conceded_while_on_pitch": 0, "bonus_points": 4,
            })
        with self.assertRaisesRegex(CovarEventScoringError, "position must be"):
            calculate_fpl_points_2026_27("MIDFIELDER", {"minutes": 90})

    def test_event_scoring_replaces_supplied_points(self):
        doc = fixture()
        for player in doc["players"]:
            player["position"] = "MID"
        for scenario in doc["scenarios"]:
            goals_conceded_by_team = {
                row["team_id"]: row["goals_against"] for row in scenario["team_states"]
            }
            for outcome in scenario["player_outcomes"]:
                player_id = outcome["player_id"]
                player = next(row for row in doc["players"] if row["player_id"] == player_id)
                outcome.update({
                    "saves": 0, "penalty_saves": 0,
                    "defensive_contribution_count": 0, "penalty_misses": 0,
                    "bonus_points": 0,
                    "goals_conceded_while_on_pitch": goals_conceded_by_team[player["team_id"]],
                    "yellow_cards": 0, "red_cards": 0, "own_goals": 0,
                })
                outcome.pop("fpl_points", None)
        doc["scenarios"][0]["player_outcomes"][0]["fpl_points"] = 999
        scored = score_scenario_events(doc)
        self.assertNotEqual(
            scored["scenarios"][0]["player_outcomes"][0]["fpl_points"], 999
        )
        self.assertEqual(
            scored["scenarios"][0]["player_outcomes"][0]["scoring_version"],
            "FPL_2026_27",
        )
        portfolio_result = score_scenario_portfolios(scored)
        self.assertIn("conventional", portfolio_result["portfolio_results"])

    def test_portfolio_aggregator_rejects_unscored_event_inputs(self):
        doc = fixture()
        for scenario in doc["scenarios"]:
            for outcome in scenario["player_outcomes"]:
                outcome.pop("fpl_points", None)
        with self.assertRaisesRegex(ValueError, "run event scoring first"):
            score_scenario_portfolios(doc)

    def test_event_scoring_requires_position(self):
        with self.assertRaisesRegex(CovarEventScoringError, "requires a position"):
            score_scenario_events(fixture())


if __name__ == "__main__":
    unittest.main()
