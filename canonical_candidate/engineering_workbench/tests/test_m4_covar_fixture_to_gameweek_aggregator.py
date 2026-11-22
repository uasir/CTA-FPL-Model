from __future__ import annotations
import copy
import unittest
from m4_covar_fixture_to_gameweek_aggregator import CovarFixtureAggregationError, aggregate_fixture_scenarios

def inputs():
    return {"player_ids":["a","b","c"],"fixture_player_ids":{"f1":["a","b"],"f2":["a","c"]},
    "joint_scenarios":[{"scenario_id":"joint-1","probability":1.0,"fixtures":[
      {"fixture_id":"f1","player_outcomes":[
       {"player_id":"a","minutes":90,"yellow_cards":0,"red_cards":0,"fpl_points":6},
       {"player_id":"b","minutes":0,"yellow_cards":1,"red_cards":0,"fpl_points":-1}]},
      {"fixture_id":"f2","player_outcomes":[
       {"player_id":"a","minutes":75,"yellow_cards":1,"red_cards":0,"fpl_points":2},
       {"player_id":"c","minutes":0,"yellow_cards":0,"red_cards":0,"fpl_points":0}]}]}]}

class TestFixtureToGameweekAggregator(unittest.TestCase):
    def test_double_gameweek_and_card_only_appearance(self):
        result=aggregate_fixture_scenarios(**inputs())[0]
        rows={x["player_id"]:x for x in result["player_outcomes"]}
        self.assertEqual(rows["a"]["minutes"],165); self.assertEqual(rows["a"]["fpl_points"],8)
        self.assertTrue(rows["a"]["played"]); self.assertEqual(rows["b"]["minutes"],0)
        self.assertEqual(rows["b"]["fpl_points"],-1); self.assertTrue(rows["b"]["played"])
        self.assertFalse(rows["c"]["played"])
    def test_missing_fixture_or_player_coverage_rejected(self):
        x=inputs(); x["joint_scenarios"][0]["fixtures"].pop()
        with self.assertRaisesRegex(CovarFixtureAggregationError,"every declared fixture"): aggregate_fixture_scenarios(**x)
        x=inputs(); x["joint_scenarios"][0]["fixtures"][0]["player_outcomes"].pop()
        with self.assertRaisesRegex(CovarFixtureAggregationError,"declared player universe"): aggregate_fixture_scenarios(**x)
    def test_duplicate_player_rejected(self):
        x=inputs(); x["joint_scenarios"][0]["fixtures"][0]["player_outcomes"].append(copy.deepcopy(x["joint_scenarios"][0]["fixtures"][0]["player_outcomes"][0]))
        with self.assertRaisesRegex(CovarFixtureAggregationError,"unknown or duplicate"): aggregate_fixture_scenarios(**x)
    def test_invalid_minutes_and_nonfinite_points_rejected(self):
        x=inputs(); x["joint_scenarios"][0]["fixtures"][0]["player_outcomes"][0]["minutes"]=121
        with self.assertRaisesRegex(CovarFixtureAggregationError,"120 per fixture"): aggregate_fixture_scenarios(**x)
        x=inputs(); x["joint_scenarios"][0]["fixtures"][0]["player_outcomes"][0]["fpl_points"]=float("nan")
        with self.assertRaisesRegex(CovarFixtureAggregationError,"finite"): aggregate_fixture_scenarios(**x)
    def test_probabilities_must_sum_to_one(self):
        x=inputs(); x["joint_scenarios"][0]["probability"]=0.5
        with self.assertRaisesRegex(CovarFixtureAggregationError,"sum to 1"): aggregate_fixture_scenarios(**x)
if __name__=="__main__": unittest.main()
