from __future__ import annotations
import unittest
from m4_covar_joint_fixture_gameweek_pipeline import build_joint_gameweek_scenarios

class TestJointFixtureGameweekPipeline(unittest.TestCase):
    def test_composes_explicit_joint_draws_then_aggregates_double_gw(self):
        catalogs={
          "f1":[{"scenario_id":"s1","player_outcomes":[
            {"player_id":"a","minutes":90,"yellow_cards":0,"red_cards":0,"fpl_points":5},
            {"player_id":"b","minutes":0,"yellow_cards":0,"red_cards":0,"fpl_points":0}]}],
          "f2":[{"scenario_id":"s2","player_outcomes":[
            {"player_id":"a","minutes":75,"yellow_cards":1,"red_cards":0,"fpl_points":3},
            {"player_id":"c","minutes":90,"yellow_cards":0,"red_cards":0,"fpl_points":6}]}],
        }
        joint=[{"scenario_id":"joint","probability":1.0,"fixture_scenario_ids":{"f1":"s1","f2":"s2"}}]
        rows=build_joint_gameweek_scenarios(player_ids=["a","b","c"],fixture_catalogs=catalogs,joint_scenarios=joint)
        outcomes={x["player_id"]:x for x in rows[0]["player_outcomes"]}
        self.assertEqual(outcomes["a"]["minutes"],165)
        self.assertEqual(outcomes["a"]["fpl_points"],8)
        self.assertTrue(outcomes["a"]["played"])
        self.assertFalse(outcomes["b"]["played"])
        self.assertEqual(rows[0]["probability"],1.0)
if __name__=="__main__": unittest.main()
