import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from estimate_fpl_covariance import estimate_covariance


def make_rows():
    rows = []
    points = {
        "1": [1, 2, 3, 4],
        "2": [2, 4, 6, 8],
        "3": [4, 3, 2, 1],
        "4": [1, 1, 1],  # incomplete panel: must not be zero-filled
        "5": [0, 0, 0, 0],  # complete but zero variance: not eligible for CoVar matrix
    }
    for player_id, values in points.items():
        for index, value in enumerate(values, start=1):
            rows.append({
                "season": "2026-27",
                "fpl_element_id": player_id,
                "gameweek": str(index),
                "target_total_points": str(value),
            })
    return rows


def make_players():
    return [
        {"fpl_element_id": "1", "web_name": "A", "position": "MID"},
        {"fpl_element_id": "2", "web_name": "B", "position": "MID"},
        {"fpl_element_id": "3", "web_name": "C", "position": "FWD"},
        {"fpl_element_id": "4", "web_name": "D", "position": "DEF"},
        {"fpl_element_id": "5", "web_name": "E", "position": "DEF"},
    ]


class CovarianceTests(unittest.TestCase):
    def test_complete_case_panel_and_incomplete_player_exclusion(self):
        pairs, summaries, report = estimate_covariance(
            make_rows(), make_players(), shrinkage=0.5, window_size=4
        )
        self.assertEqual(report["complete_panel_players"], 4)
        self.assertEqual(report["covariance_players"], 3)
        self.assertEqual(report["excluded_zero_variance_players"], 1)
        self.assertEqual(report["zero_variance_player_ids"], ["5"])
        self.assertEqual(report["excluded_incomplete_players"], 1)
        self.assertEqual(report["excluded_player_ids"], ["4"])
        self.assertEqual(len(summaries), 4)
        self.assertFalse(next(x for x in summaries if x["fpl_element_id"] == "5")["eligible_for_covariance"])
        self.assertEqual(report["window_gameweeks"], [1, 2, 3, 4])

    def test_positive_and_negative_relationships_are_detected(self):
        pairs, _, _ = estimate_covariance(
            make_rows(), make_players(), shrinkage=0.5, window_size=4
        )
        lookup = {(row["player1_id"], row["player2_id"]): row for row in pairs}
        self.assertAlmostEqual(lookup[("1", "2")]["correlation"], 1.0)
        self.assertAlmostEqual(lookup[("1", "3")]["correlation"], -1.0)

    def test_diagonal_shrinkage_only_reduces_off_diagonal_covariance(self):
        pairs, _, _ = estimate_covariance(
            make_rows(), make_players(), shrinkage=0.5, window_size=4
        )
        lookup = {(r["player1_id"], r["player2_id"]): r for r in pairs}
        self.assertAlmostEqual(
            lookup[("1", "2")]["shrunk_covariance"],
            lookup[("1", "2")]["covariance"] * 0.5,
        )
        self.assertEqual(
            lookup[("1", "1")]["shrunk_covariance"],
            lookup[("1", "1")]["covariance"],
        )

    def test_report_is_explicitly_exploratory_and_not_point_in_time_verified(self):
        _, _, report = estimate_covariance(
            make_rows(), make_players(), shrinkage=0.5, window_size=4
        )
        self.assertEqual(report["status"], "EXPLORATORY_ONLY")
        self.assertFalse(report["model_trained"])
        self.assertEqual(report["point_in_time_status"], "NOT_VERIFIED")
        self.assertTrue(report["shrinkage"]["positive_semidefinite_by_construction"])
        self.assertTrue(report["shrinkage"]["positive_definite_by_construction"])

    def test_duplicate_player_gameweek_is_rejected(self):
        rows = make_rows()
        rows.append(rows[0].copy())
        with self.assertRaisesRegex(ValueError, "duplicate player-gameweek"):
            estimate_covariance(rows, make_players(), window_size=4)

    def test_multiple_seasons_are_rejected(self):
        rows = make_rows()
        rows[0]["season"] = "2025-26"
        with self.assertRaisesRegex(ValueError, "exactly one FPL season"):
            estimate_covariance(rows, make_players(), window_size=4)

    def test_invalid_shrinkage_and_window_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "shrinkage"):
            estimate_covariance(make_rows(), make_players(), shrinkage=1.5, window_size=4)
        with self.assertRaisesRegex(ValueError, "window_size"):
            estimate_covariance(make_rows(), make_players(), window_size=1)


if __name__ == "__main__":
    unittest.main()
