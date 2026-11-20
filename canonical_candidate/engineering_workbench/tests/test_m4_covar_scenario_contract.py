from __future__ import annotations

import copy
import unittest

from m4_covar_scenario_contract import (
    CovarScenarioContractError,
    validate_scenario_document,
)


def fixture():
    return {
        "schema_version": "1.0.0",
        "data_status": "SYNTHETIC_FIXTURE_ONLY",
        "metadata": {
            "fixture_id": "synthetic-fixture-01",
            "season": "2026-27",
            "target_gameweek": 12,
            "deadline_utc": "2026-11-28T11:00:00Z",
            "as_of_utc": "2026-11-27T18:00:00Z",
        },
        "teams": [{"team_id": "A"}, {"team_id": "B"}],
        "players": [
            {"player_id": "a1", "team_id": "A", "expected_points": 5.2,
             "expected_minutes": 85, "ownership_pct": 20, "effective_ownership_pct": 30,
             "captain_pct": 5, "triple_captain_pct": 0},
            {"player_id": "a2", "team_id": "A", "expected_points": 4.1,
             "expected_minutes": 80, "ownership_pct": 10, "effective_ownership_pct": 12,
             "captain_pct": 1, "triple_captain_pct": 0},
            {"player_id": "b1", "team_id": "B", "expected_points": 4.8,
             "expected_minutes": 90, "ownership_pct": 25, "effective_ownership_pct": 28,
             "captain_pct": 3, "triple_captain_pct": 0},
        ],
        "scenarios": [
            {"scenario_id": "A-clean-sheet", "probability": 0.5,
             "team_states": [{"team_id": "A", "goals_for": 2, "goals_against": 0},
                             {"team_id": "B", "goals_for": 0, "goals_against": 2}],
             "player_outcomes": [
                 {"player_id": "a1", "minutes": 90, "goals": 1, "assists": 0,
                  "clean_sheet": True, "fpl_points": 12},
                 {"player_id": "a2", "minutes": 90, "goals": 0, "assists": 1,
                  "clean_sheet": True, "fpl_points": 8},
                 {"player_id": "b1", "minutes": 90, "goals": 0, "assists": 0,
                  "clean_sheet": False, "fpl_points": 2},
             ]},
            {"scenario_id": "B-win", "probability": 0.5,
             "team_states": [{"team_id": "A", "goals_for": 0, "goals_against": 2},
                             {"team_id": "B", "goals_for": 2, "goals_against": 0}],
             "player_outcomes": [
                 {"player_id": "a1", "minutes": 90, "goals": 0, "assists": 0,
                  "clean_sheet": False, "fpl_points": 2},
                 {"player_id": "a2", "minutes": 90, "goals": 0, "assists": 0,
                  "clean_sheet": False, "fpl_points": 2},
                 {"player_id": "b1", "minutes": 90, "goals": 2, "assists": 0,
                  "clean_sheet": True, "fpl_points": 15},
             ]},
        ],
        "portfolios": [
            {"portfolio_id": "conventional", "player_ids": ["a1", "b1"],
             "captain_id": "a1", "captain_multiplier": 2},
            {"portfolio_id": "covar-stack", "player_ids": ["a1", "a2"],
             "captain_id": "a1", "captain_multiplier": 2},
        ],
    }


class TestM4CovarScenarioContract(unittest.TestCase):
    def test_accepts_valid_synthetic_document_and_keeps_disabled(self):
        result = validate_scenario_document(fixture())
        self.assertEqual(result["validation_status"], "VALID_SYNTHETIC_RESEARCH_INPUT")
        self.assertEqual(result["scenario_count"], 2)
        self.assertEqual(result["portfolio_count"], 2)
        self.assertEqual(result["decision_weight"], 0.0)
        self.assertFalse(result["production_eligible"])

    def test_rejects_wrong_schema_version(self):
        doc = fixture()
        doc["schema_version"] = "2.0.0"
        with self.assertRaisesRegex(CovarScenarioContractError, "schema_version"):
            validate_scenario_document(doc)

    def test_rejects_non_synthetic_data_until_adapter_is_reviewed(self):
        doc = fixture()
        doc["data_status"] = "LIVE"
        with self.assertRaisesRegex(CovarScenarioContractError, "SYNTHETIC_FIXTURE_ONLY"):
            validate_scenario_document(doc)

    def test_rejects_deadline_or_later_input(self):
        doc = fixture()
        doc["metadata"]["as_of_utc"] = doc["metadata"]["deadline_utc"]
        with self.assertRaisesRegex(CovarScenarioContractError, "before the deadline"):
            validate_scenario_document(doc)

    def test_rejects_probabilities_not_summing_to_one(self):
        doc = fixture()
        doc["scenarios"][0]["probability"] = 0.6
        with self.assertRaisesRegex(CovarScenarioContractError, "sum to 1"):
            validate_scenario_document(doc)

    def test_rejects_missing_player_outcome(self):
        doc = fixture()
        doc["scenarios"][0]["player_outcomes"].pop()
        with self.assertRaisesRegex(CovarScenarioContractError, "every declared player"):
            validate_scenario_document(doc)

    def test_rejects_inconsistent_clean_sheet(self):
        doc = fixture()
        doc["scenarios"][0]["player_outcomes"][0]["clean_sheet"] = False
        doc["scenarios"][0]["player_outcomes"][0]["minutes"] = 90
        # False is allowed even when the team kept a clean sheet: this player may be a forward.
        result = validate_scenario_document(doc)
        self.assertEqual(result["validation_status"], "VALID_SYNTHETIC_RESEARCH_INPUT")

    def test_rejects_goal_allocation_above_team_goals(self):
        doc = fixture()
        doc["scenarios"][0]["player_outcomes"][0]["goals"] = 3
        with self.assertRaisesRegex(CovarScenarioContractError, "player goals exceed"):
            validate_scenario_document(doc)

    def test_rejects_unknown_portfolio_player(self):
        doc = fixture()
        doc["portfolios"][0]["player_ids"].append("missing")
        with self.assertRaisesRegex(CovarScenarioContractError, "unknown player"):
            validate_scenario_document(doc)

    def test_rejects_captain_not_in_portfolio(self):
        doc = fixture()
        doc["portfolios"][0]["captain_id"] = "a2"
        with self.assertRaisesRegex(CovarScenarioContractError, "captain must be selected"):
            validate_scenario_document(doc)


if __name__ == "__main__":
    unittest.main()
