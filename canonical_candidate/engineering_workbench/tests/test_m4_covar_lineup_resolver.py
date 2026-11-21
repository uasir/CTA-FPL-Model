from __future__ import annotations

import unittest

from m4_covar_lineup_resolver import (
    CovarLineupResolutionError,
    resolve_fpl_lineup,
)


def lineup():
    # 1 GK, 4 DEF, 4 MID, 2 FWD; reserve GK; then DEF, MID, FWD bench.
    players = [f"p{i}" for i in range(1, 16)]
    positions = {
        "p1": "GK",
        "p2": "DEF", "p3": "DEF", "p4": "DEF", "p5": "DEF",
        "p6": "MID", "p7": "MID", "p8": "MID", "p9": "MID",
        "p10": "FWD", "p11": "FWD",
        "p12": "GK", "p13": "DEF", "p14": "MID", "p15": "FWD",
    }
    return {
        "player_ids": players,
        "starting_player_ids": players[:11],
        "starting_goalkeeper_id": "p1",
        "reserve_goalkeeper_id": "p12",
        "bench_order": players[12:],
        "player_positions": positions,
        "captain_id": "p10",
        "vice_captain_id": "p11",
        "player_minutes": {pid: 90 for pid in players},
        "player_played": {pid: True for pid in players},
        "player_points": {pid: 2 for pid in players},
    }


def resolve(**overrides):
    data = lineup()
    data.update(overrides)
    if "player_played" not in overrides:
        data["player_played"] = {pid: minutes > 0 for pid, minutes in data["player_minutes"].items()}
    return resolve_fpl_lineup(**data)


class TestM4CovarLineupResolver(unittest.TestCase):
    def test_default_mode_is_regular_gameweek(self):
        data = lineup()
        data.pop("mode", None)
        result = resolve_fpl_lineup(**data)
        self.assertEqual(result["mode"], "REGULAR_GW")
        self.assertFalse(result["production_eligible"])
        self.assertEqual(result["decision_weight"], 0.0)

    def test_goalkeeper_substitution_only_when_starting_goalkeeper_does_not_play(self):
        minutes = lineup()["player_minutes"]
        minutes["p1"] = 0
        result = resolve(player_minutes=minutes)
        self.assertIn({"out": "p1", "in": "p12", "type": "GOALKEEPER"}, result["substitutions"])
        self.assertIn("p12", result["resolved_starting_xi"])

    def test_reserve_goalkeeper_does_not_enter_if_they_do_not_play(self):
        minutes = lineup()["player_minutes"]
        minutes["p1"] = 0
        minutes["p12"] = 0
        result = resolve(player_minutes=minutes)
        self.assertNotIn("p12", result["resolved_starting_xi"])
        self.assertEqual(result["resolved_starting_xi"].count("p1"), 1)

    def test_first_eligible_outfield_substitute_enters_in_bench_order(self):
        minutes = lineup()["player_minutes"]
        minutes["p2"] = 0
        result = resolve(player_minutes=minutes)
        self.assertEqual(result["substitutions"][0]["in"], "p13")
        self.assertEqual(result["substitutions"][0]["out"], "p2")

    def test_illegal_substitute_is_skipped_and_later_eligible_substitute_considered(self):
        data = lineup()
        # Start with 3 DEF, 4 MID, 3 FWD; losing a DEF cannot be repaired by
        # the first bench MID, but the later bench DEF can enter.
        data["starting_player_ids"] = ["p1", "p2", "p3", "p4", "p6", "p7", "p8", "p9", "p10", "p11", "p15"]
        data["player_ids"] = [*data["starting_player_ids"], "p12", "p5", "p14", "p13"]
        data["starting_goalkeeper_id"] = "p1"
        data["reserve_goalkeeper_id"] = "p12"
        data["bench_order"] = ["p5", "p14", "p13"]
        data["player_positions"] = {
            **data["player_positions"],
            "p5": "DEF", "p14": "MID", "p13": "DEF", "p15": "FWD",
        }
        data["player_minutes"] = {pid: 90 for pid in data["player_ids"]}
        data["player_played"] = {pid: True for pid in data["player_ids"]}
        data["player_points"] = {pid: 2 for pid in data["player_ids"]}
        data["captain_id"] = "p10"
        data["vice_captain_id"] = "p11"
        data["player_minutes"]["p2"] = 0
        data["player_played"]["p2"] = False
        # Bench order starts with DEF, so it is eligible; use MID first instead.
        data["bench_order"] = ["p14", "p5", "p13"]
        result = resolve_fpl_lineup(**data)
        self.assertEqual(result["substitutions"][0]["in"], "p5")
        self.assertEqual(result["substitutions"][0]["out"], "p2")

    def test_player_with_positive_minutes_is_never_substituted_off(self):
        minutes = lineup()["player_minutes"]
        minutes["p2"] = 1
        result = resolve(player_minutes=minutes)
        self.assertFalse(any(row["out"] == "p2" for row in result["substitutions"]))

    def test_multiple_absences_process_bench_in_submitted_order(self):
        minutes = lineup()["player_minutes"]
        minutes.update({"p2": 0, "p6": 0, "p10": 0})
        result = resolve(player_minutes=minutes)
        self.assertEqual([row["in"] for row in result["substitutions"]], ["p13", "p14", "p15"])
        self.assertEqual([row["out"] for row in result["substitutions"]], ["p2", "p6", "p10"])

    def test_captain_falls_back_to_vice_only_if_captain_does_not_play(self):
        minutes = lineup()["player_minutes"]
        minutes["p10"] = 0
        result = resolve(player_minutes=minutes)
        self.assertEqual(result["active_captain_id"], "p11")
        self.assertEqual(result["captain_multiplier"], 2)

    def test_no_captain_bonus_when_neither_captain_nor_vice_plays(self):
        minutes = lineup()["player_minutes"]
        minutes.update({"p10": 0, "p11": 0})
        result = resolve(player_minutes=minutes)
        self.assertIsNone(result["active_captain_id"])
        self.assertEqual(result["captain_multiplier"], 1)

    def test_captain_keeps_place_after_one_minute_even_if_later_substituted(self):
        minutes = lineup()["player_minutes"]
        minutes["p10"] = 1
        result = resolve(player_minutes=minutes)
        self.assertEqual(result["active_captain_id"], "p10")
        self.assertNotEqual(result["captain_multiplier"], 1)

    def test_card_only_appearance_counts_as_played_for_autosubs_and_captaincy(self):
        minutes = lineup()["player_minutes"]
        played = lineup()["player_played"]
        minutes["p10"] = 0
        played["p10"] = True  # Explicit card-only appearance.
        minutes["p2"] = 0
        played["p2"] = False
        result = resolve(player_minutes=minutes, player_played=played)
        self.assertEqual(result["active_captain_id"], "p10")
        self.assertFalse(any(row["out"] == "p10" for row in result["substitutions"]))
        self.assertTrue(any(row["out"] == "p2" for row in result["substitutions"]))

    def test_triple_captain_applies_three_times_to_captain_or_vice_fallback(self):
        result = resolve(active_chip="3xc")
        self.assertEqual(result["player_contributions"]["p10"], 6)
        minutes = lineup()["player_minutes"]
        minutes["p10"] = 0
        fallback = resolve(active_chip="3xc", player_minutes=minutes)
        self.assertEqual(fallback["player_contributions"]["p11"], 6)

    def test_bench_boost_scores_all_15_once_and_keeps_captain_bonus(self):
        result = resolve(active_chip="bboost")
        self.assertEqual(len(result["scoring_player_ids"]), 15)
        self.assertEqual(len(result["player_contributions"]), 15)
        self.assertEqual(result["player_contributions"]["p10"], 4)
        self.assertEqual(result["total_points"], 32)

    def test_negative_player_points_are_preserved(self):
        points = lineup()["player_points"]
        points["p3"] = -2
        result = resolve(player_points=points)
        self.assertEqual(result["player_contributions"]["p3"], -2)

    def test_free_hit_requires_explicit_mode(self):
        result = resolve(mode="FREE_HIT")
        self.assertEqual(result["mode"], "FREE_HIT")
        with self.assertRaisesRegex(CovarLineupResolutionError, "mode must be"):
            resolve(mode="freehit")

    def test_rejects_missing_minutes_or_points_instead_of_defaulting_to_zero(self):
        minutes = lineup()["player_minutes"]
        minutes.pop("p15")
        with self.assertRaisesRegex(CovarLineupResolutionError, "cover all 15"):
            resolve(player_minutes=minutes)
        points = lineup()["player_points"]
        points.pop("p14")
        with self.assertRaisesRegex(CovarLineupResolutionError, "cover all 15"):
            resolve(player_points=points)
        played = lineup()["player_played"]
        played.pop("p13")
        with self.assertRaisesRegex(CovarLineupResolutionError, "cover all 15"):
            resolve(player_played=played)

    def test_rejects_invalid_lineup_and_captaincy(self):
        data = lineup()
        data["starting_player_ids"] = data["starting_player_ids"][:-1]
        with self.assertRaisesRegex(CovarLineupResolutionError, "exactly 11"):
            resolve_fpl_lineup(**data)
        data = lineup()
        data["vice_captain_id"] = data["captain_id"]
        with self.assertRaisesRegex(CovarLineupResolutionError, "distinct starting"):
            resolve_fpl_lineup(**data)
        data = lineup()
        data["player_positions"]["p2"] = "FWD"
        data["player_positions"]["p3"] = "FWD"
        data["player_positions"]["p4"] = "FWD"
        data["player_positions"]["p5"] = "FWD"
        with self.assertRaisesRegex(CovarLineupResolutionError, "legal FPL formation"):
            resolve_fpl_lineup(**data)

    def test_rejects_nonfinite_or_out_of_range_minutes(self):
        minutes = lineup()["player_minutes"]
        minutes["p2"] = float("nan")
        with self.assertRaisesRegex(CovarLineupResolutionError, "finite"):
            resolve(player_minutes=minutes)
        minutes = lineup()["player_minutes"]
        minutes["p2"] = 121
        with self.assertRaisesRegex(CovarLineupResolutionError, "cannot exceed 120"):
            resolve(player_minutes=minutes)


if __name__ == "__main__":
    unittest.main()
