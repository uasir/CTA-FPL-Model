from __future__ import annotations

import copy
import unittest

from m4_covar_fpl_replay_validation import (
    CovarFplReplayError,
    played_from_official_element_stats,
    validate_official_replay_case,
    validate_replay_batch,
)


def replay(chip=None, event_id=7):
    ids = [f"p{i}" for i in range(1, 16)]
    positions = {
        "p1": "GK",
        "p2": "DEF", "p3": "DEF", "p4": "DEF", "p5": "DEF",
        "p6": "MID", "p7": "MID", "p8": "MID", "p9": "MID",
        "p10": "FWD", "p11": "FWD",
        "p12": "GK", "p13": "DEF", "p14": "MID", "p15": "FWD",
    }
    lineup = {
        "player_ids": ids,
        "starting_player_ids": ids[:11],
        "starting_goalkeeper_id": "p1",
        "reserve_goalkeeper_id": "p12",
        "bench_order": ids[12:],
        "player_positions": positions,
        "captain_id": "p10",
        "vice_captain_id": "p11",
        "active_chip": chip,
    }
    outcomes = {
        pid: {"minutes": 90, "played": True, "fpl_points": 2}
        for pid in ids
    }
    multiplier = 3 if chip == "3xc" else 2
    scoring_ids = ids if chip == "bboost" else ids[:11]
    official_picks = []
    for pid in ids:
        value = 0
        if pid in scoring_ids:
            value = 1
        if pid == "p10":
            value = multiplier
        official_picks.append({
            "element": pid,
            "position": ids.index(pid) + 1,
            "multiplier": value,
            "is_captain": pid == "p10",
            "is_vice_captain": pid == "p11",
        })
    official_total = sum(
        outcomes[row["element"]]["fpl_points"] * row["multiplier"]
        for row in official_picks
    )
    return {
        "replay_id": f"synthetic-gw{event_id}-replay",
        "event_id": event_id,
        "lineup": lineup,
        "player_outcomes": outcomes,
        "official_final": {
            "picks": official_picks,
            "player_total_points": {pid: 2 for pid in ids},
            "team_points": official_total,
        },
    }


class TestM4CovarFplReplayValidation(unittest.TestCase):
    def test_official_replay_passes_when_all_pick_multipliers_match(self):
        result = validate_official_replay_case(replay())
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["official_multiplier_match"])
        self.assertTrue(result["player_points_match"])
        self.assertTrue(result["active_captain_match"])
        self.assertTrue(result["official_team_points_reconcile"])
        self.assertEqual(result["resolver_total_points"], 24.0)

    def test_accepts_official_double_gameweek_minutes_above_120(self):
        case = replay()
        case["player_outcomes"]["p2"]["minutes"] = 165
        result = validate_official_replay_case(case)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["resolver_total_points"], 24.0)

    def test_detects_official_autosub_multiplier_mismatch(self):
        case = replay()
        case["official_final"]["picks"][12]["multiplier"] = 1
        result = validate_official_replay_case(case)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("p13", result["mismatched_player_multipliers"])

    def test_detects_captain_fallback_mismatch(self):
        case = replay()
        case["player_outcomes"]["p10"].update({"minutes": 0, "played": False, "fpl_points": 0})
        case["player_outcomes"]["p11"]["fpl_points"] = 4
        for pick in case["official_final"]["picks"]:
            if pick["element"] == "p10":
                pick["multiplier"] = 0
            if pick["element"] == "p11":
                pick["multiplier"] = 2
            if pick["element"] == "p13":
                pick["multiplier"] = 1
        case["official_final"]["player_total_points"]["p10"] = 0
        case["official_final"]["player_total_points"]["p11"] = 4
        case["official_final"]["team_points"] = sum(
            case["official_final"]["player_total_points"][pick["element"]] * pick["multiplier"]
            for pick in case["official_final"]["picks"]
        )
        result = validate_official_replay_case(case)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["resolver_active_captain_id"], "p11")

    def test_supports_card_only_appearance_from_official_stats(self):
        self.assertTrue(played_from_official_element_stats({
            "minutes": 0, "yellow_cards": 1, "red_cards": 0,
        }))
        self.assertTrue(played_from_official_element_stats({
            "minutes": 0, "yellow_cards": 0, "red_cards": 1,
        }))
        self.assertFalse(played_from_official_element_stats({
            "minutes": 0, "yellow_cards": 0, "red_cards": 0,
        }))
        self.assertTrue(played_from_official_element_stats({
            "minutes": 1, "yellow_cards": 0, "red_cards": 0,
        }))

    def test_replays_triple_captain_and_bench_boost_multipliers(self):
        triple = validate_official_replay_case(replay("3xc"))
        self.assertEqual(triple["status"], "PASS")
        self.assertEqual(triple["resolver_total_points"], 26.0)
        bench = validate_official_replay_case(replay("bboost"))
        self.assertEqual(bench["status"], "PASS")
        self.assertEqual(bench["resolver_total_points"], 32.0)

    def test_detects_player_point_and_total_reconciliation_mismatches(self):
        case = replay()
        case["official_final"]["player_total_points"]["p2"] = 1
        case["official_final"]["team_points"] = 22
        result = validate_official_replay_case(case)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("p2", result["mismatched_player_points"])
        self.assertFalse(result["official_team_points_reconcile"])

    def test_requires_complete_official_picks_and_outcomes(self):
        case = replay()
        case["official_final"]["picks"].pop()
        with self.assertRaisesRegex(CovarFplReplayError, "all 15"):
            validate_official_replay_case(case)
        case = replay()
        case["player_outcomes"].pop("p15")
        with self.assertRaisesRegex(CovarFplReplayError, "exactly all 15"):
            validate_official_replay_case(case)

    def test_rejects_missing_played_boolean_and_invalid_multiplier(self):
        case = replay()
        del case["player_outcomes"]["p1"]["played"]
        with self.assertRaisesRegex(CovarFplReplayError, "explicit played boolean"):
            validate_official_replay_case(case)
        case = replay()
        case["official_final"]["picks"][0]["multiplier"] = 4
        with self.assertRaisesRegex(CovarFplReplayError, "multiplier must be"):
            validate_official_replay_case(case)

    def test_rejects_manager_identifiers_in_replay_input(self):
        case = replay()
        case["manager_id"] = "private"
        with self.assertRaisesRegex(CovarFplReplayError, "restricted manager identifier"):
            validate_official_replay_case(case)

    def test_rejects_official_pick_order_mismatch(self):
        case = replay()
        case["official_final"]["picks"][0]["position"] = 2
        with self.assertRaisesRegex(CovarFplReplayError, "pick order"):
            validate_official_replay_case(case)

    def test_rejects_official_captain_or_vice_mismatch(self):
        case = replay()
        case["official_final"]["picks"][9]["is_captain"] = False
        case["official_final"]["picks"][8]["is_captain"] = True
        with self.assertRaisesRegex(CovarFplReplayError, "captain does not match"):
            validate_official_replay_case(case)

    def test_rejects_inconsistent_minutes_and_played_status(self):
        case = replay()
        case["player_outcomes"]["p1"]["minutes"] = 90
        case["player_outcomes"]["p1"]["played"] = False
        with self.assertRaisesRegex(CovarFplReplayError, "conflicts with positive minutes"):
            validate_official_replay_case(case)
        case = replay()
        case["player_outcomes"]["p1"]["minutes"] = -1
        with self.assertRaisesRegex(CovarFplReplayError, "negative minutes"):
            validate_official_replay_case(case)

    def test_batch_report_is_aggregated_and_research_only(self):
        result = validate_replay_batch({"replays": [replay(), replay("3xc", event_id=8)]})
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["passed_count"], 2)
        self.assertEqual(result["gameweek_count"], 2)
        self.assertEqual(result["gameweeks"], [7, 8])
        self.assertEqual(result["by_gameweek"]["7"]["passed_count"], 1)
        self.assertEqual(result["by_mode"], {"REGULAR_GW": 2})
        self.assertEqual(result["by_chip"], {"NONE": 1, "3xc": 1})
        self.assertEqual(result["multiplier_mismatch_replays"], 0)
        self.assertFalse(result["production_eligible"])
        self.assertEqual(result["decision_weight"], 0.0)

    def test_batch_report_counts_failures_by_gameweek_and_mismatch_type(self):
        first = replay(event_id=7)
        first["official_final"]["picks"][12]["multiplier"] = 1
        second = replay(event_id=8)
        second["official_final"]["player_total_points"]["p2"] = 0
        result = validate_replay_batch({"replays": [first, second]})
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["failed_count"], 2)
        self.assertEqual(result["by_gameweek"]["7"]["failed_count"], 1)
        self.assertEqual(result["by_gameweek"]["8"]["failed_count"], 1)
        self.assertEqual(result["multiplier_mismatch_replays"], 1)
        self.assertEqual(result["player_points_mismatch_replays"], 1)

    def test_rejects_invalid_gameweek_identity(self):
        case = replay()
        case["event_id"] = True
        with self.assertRaisesRegex(CovarFplReplayError, "event_id must be a positive integer"):
            validate_official_replay_case(case)


if __name__ == "__main__":
    unittest.main()
