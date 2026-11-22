from __future__ import annotations
import unittest
from m4_covar_joint_fixture_scenario_composer import (
    CovarJointScenarioCompositionError, compose_joint_fixture_scenarios,
)

def catalogs():
    return {
      "f1":[
        {"scenario_id":"home-win","player_outcomes":[{"player_id":"a","minutes":90,"yellow_cards":0,"red_cards":0,"fpl_points":8}]},
        {"scenario_id":"home-loss","player_outcomes":[{"player_id":"a","minutes":90,"yellow_cards":1,"red_cards":0,"fpl_points":1}]},
      ],
      "f2":[
        {"scenario_id":"away-win","player_outcomes":[{"player_id":"b","minutes":90,"yellow_cards":0,"red_cards":0,"fpl_points":7}]},
        {"scenario_id":"away-loss","player_outcomes":[{"player_id":"b","minutes":60,"yellow_cards":0,"red_cards":0,"fpl_points":2}]},
      ],
    }

def joint():
    return [
      {"scenario_id":"linked-upside","probability":0.4,"fixture_scenario_ids":{"f1":"home-win","f2":"away-win"}},
      {"scenario_id":"linked-downside","probability":0.6,"fixture_scenario_ids":{"f1":"home-loss","f2":"away-loss"}},
    ]

class TestJointFixtureScenarioComposer(unittest.TestCase):
    def test_uses_explicit_joint_rows_and_preserves_probabilities(self):
        result=compose_joint_fixture_scenarios(fixture_catalogs=catalogs(),joint_scenarios=joint())
        self.assertEqual([x["scenario_id"] for x in result],["linked-upside","linked-downside"])
        self.assertEqual([x["probability"] for x in result],[0.4,0.6])
        self.assertEqual(result[0]["fixtures"][0]["player_outcomes"][0]["fpl_points"],8)
        self.assertEqual(result[1]["fixtures"][1]["player_outcomes"][0]["fpl_points"],2)
        self.assertEqual(len(result),2)  # no implicit 2x2 Cartesian expansion
    def test_rejects_missing_fixture_reference(self):
        rows=joint(); rows[0]["fixture_scenario_ids"].pop("f2")
        with self.assertRaisesRegex(CovarJointScenarioCompositionError,"every declared fixture"):
            compose_joint_fixture_scenarios(fixture_catalogs=catalogs(),joint_scenarios=rows)
    def test_rejects_unknown_fixture_scenario_reference(self):
        rows=joint(); rows[0]["fixture_scenario_ids"]["f1"]="not-found"
        with self.assertRaisesRegex(CovarJointScenarioCompositionError,"unknown scenario"):
            compose_joint_fixture_scenarios(fixture_catalogs=catalogs(),joint_scenarios=rows)
    def test_rejects_inconsistent_player_universe_within_fixture(self):
        data=catalogs(); data["f1"][1]["player_outcomes"].append({"player_id":"x","minutes":0,"yellow_cards":0,"red_cards":0,"fpl_points":0})
        with self.assertRaisesRegex(CovarJointScenarioCompositionError,"identical player coverage"):
            compose_joint_fixture_scenarios(fixture_catalogs=data,joint_scenarios=joint())
    def test_rejects_invalid_joint_probabilities(self):
        rows=joint(); rows[0]["probability"]=0.9
        with self.assertRaisesRegex(CovarJointScenarioCompositionError,"sum to 1"):
            compose_joint_fixture_scenarios(fixture_catalogs=catalogs(),joint_scenarios=rows)
    def test_rejects_nonfinite_fixture_values(self):
        data=catalogs(); data["f1"][0]["player_outcomes"][0]["fpl_points"]=float("nan")
        with self.assertRaisesRegex(CovarJointScenarioCompositionError,"finite"):
            compose_joint_fixture_scenarios(fixture_catalogs=data,joint_scenarios=joint())
if __name__=="__main__": unittest.main()
