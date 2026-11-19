import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from aggregate_fpl_gameweek_rows import aggregate

def row(fixture,points,minutes,home=True):
    return {
      "season":"2026-27","fpl_element_id":"1","fpl_player_code":"100","gameweek":"1",
      "features_as_of_deadline":"2026-07-31T17:00:00+00:00","prior_gameweeks_count":"0",
      "prior_gw_points":"","prior_gw_minutes":"","prior3_gw_points_avg":"",
      "prior3_gw_minutes_avg":"","prior3_gw_xg_avg":"","prior3_gw_xa_avg":"",
      "prior5_gw_points_avg":"","prior5_gw_minutes_avg":"","season_to_date_points":"0",
      "season_to_date_minutes":"0","season_to_date_xg":"0","season_to_date_xa":"0",
      "season_to_date_points_per90":"","fixture_id":str(fixture),"was_home":str(home),
      "team_id_at_fixture":"1","opponent_team_id":str(2 if home else 3),
      "team_difficulty_snapshot":"2","opponent_difficulty_snapshot":"4",
      "target_minutes":str(minutes),"target_total_points":str(points),"target_goals":"0",
      "target_assists":"0","target_expected_goals":"0.2","target_expected_assists":"0.1"
    }

class GameweekAggregationTests(unittest.TestCase):
    def test_double_gameweek_sums_targets_and_preserves_one_feature_snapshot(self):
        rows,report=aggregate([row(11,6,90,True),row(12,4,45,False)])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["target_total_points"],10.0)
        self.assertEqual(rows[0]["target_minutes"],135.0)
        self.assertEqual(rows[0]["target_fixtures_count"],2)
        self.assertEqual(rows[0]["home_fixtures_count"],1)
        self.assertEqual(rows[0]["opponent_team_ids"],"2;3")
        self.assertEqual(report["status"],"PASS_STRUCTURAL_ONLY")
    def test_inconsistent_features_within_gameweek_are_rejected(self):
        first=row(11,6,90);second=row(12,4,45)
        second["prior3_gw_points_avg"]="3.5"
        with self.assertRaisesRegex(ValueError,"differs within player"):
            aggregate([first,second])
if __name__=="__main__":unittest.main()


def test_missing_targets_and_fixture_difficulty_are_not_converted_to_zero():
    first = row(11, 6, 90, True)
    first["target_expected_goals"] = ""
    first["opponent_difficulty_snapshot"] = ""
    rows, _ = aggregate([first])
    assert rows[0]["target_total_points"] == 6.0
    assert rows[0]["target_expected_goals"] == ""
    assert rows[0]["opponent_difficulty_snapshot_avg"] == ""


def test_double_gameweek_target_is_missing_if_any_fixture_target_is_missing():
    first = row(11, 6, 90, True)
    second = row(12, 4, 45, False)
    second["target_expected_assists"] = ""
    rows, _ = aggregate([first, second])
    assert rows[0]["target_total_points"] == 10.0
    assert rows[0]["target_expected_assists"] == ""
