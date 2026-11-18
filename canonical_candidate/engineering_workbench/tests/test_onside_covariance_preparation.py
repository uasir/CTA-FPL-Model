import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from build_onside_fpl_covariance import prepare_covariance_inputs, rolling_correlation_stability
from estimate_fpl_covariance import estimate_covariance


def rows():
    data = []
    points = {
        "1": [2, 4, 6],
        "2": [4, 2, 8],
        "3": [1, 3, 2],
    }
    for player_id, values in points.items():
        for gw, value in enumerate(values, start=1):
            data.append({
                "gw": str(gw), "player_id": player_id,
                "player_name": f"Player {player_id}",
                "actual_points": str(value),
                "onside_xp": "999", "fpl_ep_next": "888",
            })
    # An entirely ungraded future GW must be excluded.
    data.extend([
        {"gw":"4","player_id":"1","player_name":"Player 1","actual_points":"","onside_xp":"9"},
        {"gw":"4","player_id":"2","player_name":"Player 2","actual_points":"","onside_xp":"9"},
    ])
    return data


class OnsideCovariancePreparationTests(unittest.TestCase):
    def test_only_fully_graded_gameweeks_and_actual_points_are_used(self):
        prepared, players, report = prepare_covariance_inputs(rows(), window_size=3)
        self.assertEqual(report["selected_completed_gameweeks"], [1, 2, 3])
        self.assertEqual(report["unfinished_gameweeks_excluded"], [4])
        self.assertFalse(report["provider_forecasts_used"])
        self.assertEqual(len(prepared), 9)
        self.assertEqual(prepared[0]["target_total_points"], 2.0)
        self.assertEqual(len(players), 3)

    def test_window_size_twenty_uses_all_available_completed_gameweeks(self):
        data=[]
        for player_id in ("1","2","3"):
            for gw in range(1,13):
                data.append({
                    "gw":str(gw),"player_id":player_id,
                    "player_name":f"Player {player_id}",
                    "actual_points":str((gw+int(player_id))%8),
                })
        prepared,_,report=prepare_covariance_inputs(data,window_size=20)
        self.assertEqual(report["selected_completed_gameweeks"],list(range(1,13)))
        stability=rolling_correlation_stability(prepared,report["selected_completed_gameweeks"])
        self.assertEqual(stability["first_window"],list(range(1,7)))
        self.assertEqual(stability["second_window"],list(range(7,13)))

    def test_partially_graded_gameweek_is_excluded_as_a_whole(self):
        data = rows()
        data.extend([
            {"gw":"5","player_id":"1","player_name":"Player 1","actual_points":"4"},
            {"gw":"5","player_id":"2","player_name":"Player 2","actual_points":""},
        ])
        prepared, _, report = prepare_covariance_inputs(data, window_size=3)
        self.assertEqual(report["partially_graded_gameweeks_excluded"], [5])
        self.assertNotIn("5", {row["gameweek"] for row in prepared})

    def test_duplicate_player_gameweek_is_rejected(self):
        data = rows()
        data.append(data[0].copy())
        with self.assertRaisesRegex(ValueError, "duplicate player-gameweek"):
            prepare_covariance_inputs(data, window_size=3)

    def test_incomplete_player_panel_is_not_zero_filled(self):
        data = rows()
        data = [row for row in data if not (row["player_id"] == "3" and row["gw"] == "2")]
        prepared, players, _ = prepare_covariance_inputs(data, window_size=3)
        pairs, summaries, report = estimate_covariance(prepared, players, window_size=3)
        self.assertEqual(report["complete_panel_players"], 2)
        self.assertEqual(report["excluded_incomplete_players"], 1)
        self.assertEqual(report["excluded_player_ids"], ["3"])


    def test_rolling_correlation_stability_uses_two_adjacent_windows(self):
        data = []
        values = {
            "1": [1, 2, 3, 4],
            "2": [2, 4, 5, 8],
            "3": [5, 2, 4, 1],
            "4": [1, 3, 2, 6],
        }
        for player_id, scores in values.items():
            for gw, score in enumerate(scores, start=1):
                data.append({
                    "season":"2026-27", "fpl_element_id":player_id,
                    "gameweek":str(gw), "target_total_points":score,
                })
        result = rolling_correlation_stability(data, [1, 2, 3, 4])
        self.assertEqual(result["status"], "EXPLORATORY_STABILITY_DIAGNOSTIC")
        self.assertEqual(result["first_window"], [1, 2])
        self.assertEqual(result["second_window"], [3, 4])
        self.assertEqual(result["players"], 4)
        self.assertEqual(result["pairs"], 6)

    def test_rolling_stability_requires_two_rounds_per_half(self):
        result = rolling_correlation_stability([], [1, 2, 3])
        self.assertEqual(result["status"], "NOT_ENOUGH_GAMEWEEKS")

    def test_requires_at_least_two_fully_graded_gameweeks(self):
        data = [
            {"gw":"1","player_id":"1","actual_points":"2"},
            {"gw":"2","player_id":"1","actual_points":""},
        ]
        with self.assertRaisesRegex(ValueError, "at least two fully graded"):
            prepare_covariance_inputs(data, window_size=10)


if __name__ == "__main__":
    unittest.main()
