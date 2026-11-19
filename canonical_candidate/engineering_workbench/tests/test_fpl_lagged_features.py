import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from build_fpl_lagged_features import build_dataset

class LaggedFeatureTests(unittest.TestCase):
    def setUp(self):
        self.players=[{"fpl_element_id":"1","fpl_player_code":"100","minutes_season":"225"}]
        self.bootstrap={"events":[{"id":1,"deadline_time":"2026-07-31T17:00:00Z","ranked_count":1000},{"id":2,"deadline_time":"2026-08-07T17:00:00Z","ranked_count":1000}]}
        self.fixtures=[
            {"fixture_id":"11","team_h_id":"1","team_a_id":"2","team_h_difficulty":"2","team_a_difficulty":"4"},
            {"fixture_id":"12","team_h_id":"2","team_a_id":"1","team_h_difficulty":"3","team_a_difficulty":"2"},
            {"fixture_id":"13","team_h_id":"1","team_a_id":"3","team_h_difficulty":"2","team_a_difficulty":"4"},
        ]
        self.history=[
            {"season":"2026-27","fpl_element_id":"1","fpl_player_code":"100","fixture_id":"11","gameweek":"1","kickoff_time":"2026-08-01","was_home":"True","opponent_team_id":"2","minutes":"90","total_points":"6","goals_scored":"1","assists":"0","expected_goals":"0.5","expected_assists":"0.1","starts":"1","selected":"700"},
            {"season":"2026-27","fpl_element_id":"1","fpl_player_code":"100","fixture_id":"12","gameweek":"1","kickoff_time":"2026-08-02","was_home":"False","opponent_team_id":"1","minutes":"45","total_points":"4","goals_scored":"0","assists":"1","expected_goals":"0.2","expected_assists":"0.3","starts":"0","selected":"700"},
            {"season":"2026-27","fpl_element_id":"1","fpl_player_code":"100","fixture_id":"13","gameweek":"2","kickoff_time":"2026-08-08","was_home":"True","opponent_team_id":"3","minutes":"90","total_points":"8","goals_scored":"1","assists":"0","expected_goals":"0.6","expected_assists":"0.2","starts":"1","selected":"700"},
        ]
    def test_prior_gameweek_aggregate_is_used_not_current_target(self):
        rows,report=build_dataset(self.players,self.fixtures,self.history,self.bootstrap)
        gw2=next(x for x in rows if x["gameweek"]==2)
        self.assertEqual(gw2["season_to_date_points"],10.0)
        self.assertEqual(gw2["season_to_date_minutes"],135.0)
        self.assertAlmostEqual(gw2["season_to_date_points_per90"],10*90/135)
        self.assertEqual(gw2["target_total_points"],"8")
        self.assertEqual(gw2["prior_gw_selected_count"],700.0)
        self.assertEqual(gw2["prior_gw_selected_pct"],70.0)
        self.assertEqual(gw2["prior3_gw_selected_pct_avg"],70.0)
        self.assertEqual(report["status"],"PASS_STRUCTURAL_ONLY")
        self.assertEqual(report["point_in_time_status"],"NOT_VERIFIED")
    def test_double_gameweek_features_are_same_pre_deadline_snapshot(self):
        rows,_=build_dataset(self.players,self.fixtures,self.history,self.bootstrap)
        gw1=[x for x in rows if x["gameweek"]==1]
        self.assertEqual(len(gw1),2)
        self.assertEqual(gw1[0]["prior_gameweeks_count"],0)
        self.assertEqual(gw1[1]["prior_gameweeks_count"],0)
    def test_home_away_team_context_uses_fixture(self):
        rows,_=build_dataset(self.players,self.fixtures,self.history,self.bootstrap)
        gw1=next(x for x in rows if x["fixture_id"]=="11")
        gw2=next(x for x in rows if x["fixture_id"]=="13")
        self.assertEqual(gw1["team_id_at_fixture"],1)
        self.assertEqual(gw2["team_id_at_fixture"],1)
        self.assertEqual(gw2["team_difficulty_snapshot"],"2")
    def test_postponed_prior_gameweek_fixture_after_deadline_is_excluded(self):
        history=[dict(x) for x in self.history]
        history[1]["kickoff_time"]="2026-08-20T14:00:00Z"
        rows,_=build_dataset(self.players,self.fixtures,history,self.bootstrap)
        gw2=next(x for x in rows if x["gameweek"]==2)
        self.assertEqual(gw2["season_to_date_points"],6.0)
        self.assertEqual(gw2["season_to_date_minutes"],90.0)
        self.assertEqual(gw2["features_as_of_deadline"],"2026-08-07T17:00:00+00:00")

    def test_unknown_fixture_blocks_build(self):
        bad=[dict(self.history[0],fixture_id="999")]
        with self.assertRaises(ValueError):
            build_dataset(self.players,self.fixtures,bad,self.bootstrap)

    def test_missing_historical_xg_is_not_aggregated_as_zero(self):
        history = [dict(row) for row in self.history]
        history[0]["expected_goals"] = ""
        history[1]["expected_goals"] = ""
        history[0]["expected_assists"] = ""
        history[1]["expected_assists"] = ""
        rows, _ = build_dataset(self.players, self.fixtures, history, self.bootstrap)
        gw2 = next(row for row in rows if row["gameweek"] == 2)
        self.assertEqual(gw2["season_to_date_points"], 10.0)
        self.assertEqual(gw2["prior3_gw_points_avg"], 10.0)
        self.assertEqual(gw2["season_to_date_xg"], "")
        self.assertEqual(gw2["prior3_gw_xg_avg"], "")
        self.assertEqual(gw2["season_to_date_xa"], "")
        self.assertEqual(gw2["prior3_gw_xa_avg"], "")

if __name__=="__main__":unittest.main()

