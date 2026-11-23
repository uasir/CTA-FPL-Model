import unittest
from copy import deepcopy
from unittest.mock import patch
from fetch_fpl_official_api import build_tables, infer_season, reconcile_snapshot

class FPLIngestionTests(unittest.TestCase):
    def setUp(self):
        self.bootstrap = {
            "events":[{"deadline_time":"2026-08-14T17:30:00Z"}],
            "teams":[{"id":1,"name":"Arsenal"},{"id":2,"name":"Chelsea"}],
            "element_types":[{"id":1,"singular_name":"Goalkeeper"}],
            "elements":[{"id":10,"code":90010,"first_name":"Test","second_name":"Keeper","web_name":"Keeper",
                         "team":1,"element_type":1,"status":"a","minutes":90,"total_points":6,"now_cost":50,
                         "selected_by_percent":"1.0","chance_of_playing_next_round":100,
                         "ep_next":"4.8","ep_this":"5.1","form":"3.2","points_per_game":"4.0",
                         "expected_goals":"0.4","expected_assists":"0.2","expected_goal_involvements":"0.6",
                         "expected_goals_conceded":"1.1","ict_index":"12.3","influence":"8.1",
                         "creativity":"2.2","threat":"2.0","starts":1,"bonus":1,"bps":25,
                         "clean_sheets":1,"goals_scored":0,"assists":0,"saves":3,
                         "penalties_saved":0,"penalties_missed":0,"yellow_cards":0,"red_cards":0,
                         "own_goals":0,"goals_conceded":0}]
        }
        self.fixtures=[{"id":100,"event":1,"kickoff_time":"2026-08-15T14:00:00Z","team_h":1,"team_a":2,
                        "finished":True,"finished_provisional":True,"team_h_score":1,"team_a_score":0,
                        "team_h_difficulty":2,"team_a_difficulty":4}]
        self.summaries={10:{"history":[{"fixture":100,"round":1,"opponent_team":2,"was_home":True,
                         "kickoff_time":"2026-08-15T14:00:00Z","minutes":90,"total_points":6,
                         "goals_scored":0,"assists":0,"clean_sheets":1,"goals_conceded":0,"own_goals":0,
                         "penalties_saved":0,"penalties_missed":0,"yellow_cards":0,"red_cards":0,
                         "saves":3,"bonus":1,"bps":25,"selected":500,"transfers_balance":12,"transfers_in":20,"transfers_out":8,"value":50}]}}

    def test_season_inference(self):
        self.assertEqual(infer_season(self.bootstrap["events"]),"2026-27")

    def test_normalizes_player_fixture_history(self):
        players,fixtures,history,report=build_tables(self.bootstrap,self.fixtures,self.summaries,"2026-27")
        self.assertEqual(len(players),1); self.assertEqual(players[0]["fpl_element_id"],10)
        self.assertEqual(players[0]["fpl_player_code"],90010)
        self.assertEqual(players[0]["ep_next"],"4.8")
        self.assertEqual(players[0]["ep_this"],"5.1")
        self.assertEqual(players[0]["expected_goals"],"0.4")
        self.assertEqual(report["official_ep_next_coverage_count"],1)
        self.assertEqual(len(fixtures),1)
        self.assertEqual(len(history),1); self.assertEqual(history[0]["fixture_id"],100)
        self.assertEqual(history[0]["minutes"],90); self.assertEqual(history[0]["selected"],500); self.assertEqual(history[0]["value"],50); self.assertEqual(report["status"],"PASS")

    def test_bootstrap_minutes_and_points_must_reconcile(self):
        bad = {10: {"history": [{
            "fixture": 100, "round": 1, "opponent_team": 2, "was_home": True,
            "minutes": 89, "total_points": 5
        }]}}
        _, _, _, report = build_tables(self.bootstrap, self.fixtures, bad, "2026-27")
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["minutes_reconciliation_mismatches"][0]["delta"], 1)
        self.assertEqual(report["total_points_reconciliation_mismatches"][0]["delta"], 1)

    def test_missing_player_summary_blocks_ingestion(self):
        _,_,_,report=build_tables(self.bootstrap,self.fixtures,{},"2026-27")
        self.assertEqual(report["status"],"BLOCKED")
        self.assertEqual(report["summaries_missing_for_players_with_minutes"],[10])

    def test_orphan_fixture_is_reported(self):
        bad={10:{"history":[{"fixture":999,"round":1,"minutes":90}]}}
        _,_,_,report=build_tables(self.bootstrap,self.fixtures,bad,"2026-27")
        self.assertEqual(report["status"],"BLOCKED")
        self.assertEqual(report["orphan_fixture_rows"][0]["fixture_id"],999)


    def test_reconcile_snapshot_refreshes_mismatched_player_summary(self):
        stale = deepcopy(self.summaries)
        stale[10]["history"][0]["total_points"] = 5
        with patch("fetch_fpl_official_api.fetch_json", side_effect=[
            self.bootstrap, self.fixtures, self.summaries[10], self.bootstrap, self.fixtures
        ]) as fetch:
            _, _, summaries, _, _, _, report = reconcile_snapshot(
                self.bootstrap, self.fixtures, stale, "2026-27",
                max_retries=1, retry_delay=0,
            )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(summaries[10]["history"][0]["total_points"], 6)
        self.assertEqual(len(report["consistency_capture_attempts"]), 2)
        self.assertEqual(report["consistency_capture_attempts"][0]["total_points_mismatch_count"], 1)
        self.assertEqual(report["consistency_capture_attempts"][1]["total_points_mismatch_count"], 0)
        self.assertEqual(fetch.call_args_list[2].args[0],
                         "https://fantasy.premierleague.com/api/element-summary/10/")

    def test_reconcile_snapshot_keeps_persistent_mismatch_blocked(self):
        stale = deepcopy(self.summaries)
        stale[10]["history"][0]["total_points"] = 5
        with patch("fetch_fpl_official_api.fetch_json", side_effect=[
            self.bootstrap, self.fixtures, stale[10], self.bootstrap, self.fixtures
        ]):
            _, _, _, _, _, _, report = reconcile_snapshot(
                self.bootstrap, self.fixtures, stale, "2026-27",
                max_retries=1, retry_delay=0,
            )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["total_points_reconciliation_mismatches"][0]["delta"], 1)

if __name__=="__main__": unittest.main()
