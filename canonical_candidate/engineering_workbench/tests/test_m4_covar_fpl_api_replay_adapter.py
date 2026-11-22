from __future__ import annotations

import copy
import unittest

from m4_covar_fpl_api_replay_adapter import (
    CovarFplApiReplayAdapterError,
    normalize_official_fpl_replay,
)
from m4_covar_fpl_replay_validation import validate_official_replay_case


def api_payloads(chip=None):
    # Legal 4-4-2: starting GK, four DEF, four MID, two FWD.
    positions = [1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 1, 2, 3, 4]
    picks = []
    for index, element_type in enumerate(positions, start=1):
        picks.append({
            "element": index,
            "position": index,
            "multiplier": 3 if chip == "3xc" and index == 10 else (2 if index == 10 else (1 if index <= 11 or chip == "bboost" else 0)),
            "is_captain": index == 10,
            "is_vice_captain": index == 11,
        })
    official_team_points = sum(2 * row["multiplier"] for row in picks)
    return (
        {"picks": picks, "active_chip": chip, "entry_history": {
            "event": 7, "points": official_team_points, "event_transfers_cost": 0,
        }},
        {"elements": [
            {"id": pid, "stats": {
                "minutes": 90, "yellow_cards": 0, "red_cards": 0,
                "total_points": 2,
            }}
            for pid in range(1, 16)
        ]},
        {"elements": [
            {"id": pid, "element_type": positions[pid - 1]}
            for pid in range(1, 16)
        ]},
    )


class TestM4CovarFplApiReplayAdapter(unittest.TestCase):
    def test_normalizes_official_payload_and_replay_validator_accepts_it(self):
        picks, live, bootstrap = api_payloads()
        case = normalize_official_fpl_replay(picks, live, bootstrap, event_id=7)
        self.assertEqual(case["mode"], "REGULAR_GW")
        self.assertEqual(case["lineup"]["starting_goalkeeper_id"], "1")
        self.assertEqual(case["lineup"]["reserve_goalkeeper_id"], "12")
        self.assertEqual(case["lineup"]["bench_order"], ["13", "14", "15"])
        self.assertEqual(validate_official_replay_case(case)["status"], "PASS")

    def test_normalizes_official_automatic_substitutions_without_entry_identity(self):
        picks, live, bootstrap = api_payloads()
        picks["automatic_subs"] = [{
            "entry": 999999, "element_in": 13, "element_out": 2, "event": 7,
        }]
        case = normalize_official_fpl_replay(picks, live, bootstrap, event_id=7)
        self.assertEqual(case["official_final"]["automatic_subs"], [
            {"element_in": 13, "element_out": 2, "event": 7},
        ])
        self.assertNotIn("999999", str(case))

    def test_infers_free_hit_mode_from_official_chip(self):
        picks, live, bootstrap = api_payloads("freehit")
        case = normalize_official_fpl_replay(picks, live, bootstrap, event_id=7)
        self.assertEqual(case["mode"], "FREE_HIT")
        self.assertEqual(case["lineup"]["active_chip"], "freehit")

    def test_supports_triple_captain_chip(self):
        picks, live, bootstrap = api_payloads("3xc")
        case = normalize_official_fpl_replay(picks, live, bootstrap, event_id=7)
        self.assertEqual(validate_official_replay_case(case)["status"], "PASS")

    def test_derives_card_only_appearance(self):
        picks, live, bootstrap = api_payloads()
        live["elements"][0]["stats"].update({"minutes": 0, "yellow_cards": 1})
        case = normalize_official_fpl_replay(picks, live, bootstrap, event_id=7)
        self.assertTrue(case["player_outcomes"]["1"]["played"])

    def test_rejects_picks_payload_from_a_different_gameweek(self):
        picks, live, bootstrap = api_payloads()
        with self.assertRaisesRegex(CovarFplApiReplayAdapterError, "does not match requested event"):
            normalize_official_fpl_replay(picks, live, bootstrap, event_id=8)

    def test_rejects_incomplete_or_duplicate_picks(self):
        picks, live, bootstrap = api_payloads()
        with self.assertRaisesRegex(CovarFplApiReplayAdapterError, "exactly 15"):
            normalize_official_fpl_replay({**picks, "picks": picks["picks"][:-1]}, live, bootstrap, event_id=7)
        picks, live, bootstrap = api_payloads()
        picks["picks"][1]["position"] = 1
        with self.assertRaisesRegex(CovarFplApiReplayAdapterError, "unique"):
            normalize_official_fpl_replay(picks, live, bootstrap, event_id=7)

    def test_rejects_missing_player_stats_or_position_metadata(self):
        picks, live, bootstrap = api_payloads()
        live["elements"] = live["elements"][:-1]
        with self.assertRaisesRegex(CovarFplApiReplayAdapterError, "missing from event live"):
            normalize_official_fpl_replay(picks, live, bootstrap, event_id=7)
        picks, live, bootstrap = api_payloads()
        bootstrap["elements"] = bootstrap["elements"][:-1]
        with self.assertRaisesRegex(CovarFplApiReplayAdapterError, "missing from bootstrap"):
            normalize_official_fpl_replay(picks, live, bootstrap, event_id=7)

    def test_rejects_invalid_reserve_goalkeeper_and_chip_mode(self):
        picks, live, bootstrap = api_payloads()
        bootstrap["elements"][11]["element_type"] = 2
        with self.assertRaisesRegex(CovarFplApiReplayAdapterError, "reserve goalkeeper"):
            normalize_official_fpl_replay(picks, live, bootstrap, event_id=7)
        picks, live, bootstrap = api_payloads("freehit")
        with self.assertRaisesRegex(CovarFplApiReplayAdapterError, "cannot be normalized"):
            normalize_official_fpl_replay(picks, live, bootstrap, event_id=7, mode="REGULAR_GW")

    def test_output_contains_no_manager_identity_fields(self):
        picks, live, bootstrap = api_payloads()
        picks["entry"] = 123456
        picks["entry_history"]["overall_rank"] = 999
        case = normalize_official_fpl_replay(picks, live, bootstrap, event_id=7)
        serialized = str(case).lower()
        self.assertNotIn("entry_id", serialized)
        self.assertNotIn("manager", serialized)
        self.assertNotIn("overall_rank", serialized)


if __name__ == "__main__":
    unittest.main()
