from __future__ import annotations

import copy
import unittest

from m4_covar_full_gameweek_contract import (
    CovarFullGameweekContractError,
    validate_full_gameweek_document,
)


def fixture():
    ids = [f"p{i}" for i in range(1, 16)]
    positions = {
        "p1": "GK",
        "p2": "DEF", "p3": "DEF", "p4": "DEF", "p5": "DEF",
        "p6": "MID", "p7": "MID", "p8": "MID", "p9": "MID",
        "p10": "FWD", "p11": "FWD",
        "p12": "GK", "p13": "DEF", "p14": "MID", "p15": "FWD",
    }
    players = [{"player_id": pid, "position": positions[pid]} for pid in ids]
    candidate = {
        "portfolio_id": "candidate",
        "portfolio_role": "CANDIDATE",
        "player_ids": ids,
        "starting_player_ids": ids[:11],
        "starting_goalkeeper_id": "p1",
        "reserve_goalkeeper_id": "p12",
        "bench_order": ids[12:],
        "player_positions": positions,
        "captain_id": "p10",
        "vice_captain_id": "p11",
        "active_chip": None,
    }
    field = copy.deepcopy(candidate)
    field.update({
        "portfolio_id": "field-1",
        "portfolio_role": "FIELD",
        "captain_id": "p9",
        "vice_captain_id": "p8",
        "field_weight": 1.0,
    })
    scenarios = []
    for scenario_id, probability, points in (("low", 0.4, 1), ("high", 0.6, 3)):
        scenarios.append({
            "scenario_id": scenario_id,
            "probability": probability,
            "player_outcomes": [
                {"player_id": pid, "minutes": 90, "played": True, "fpl_points": points}
                for pid in ids
            ],
        })
    return {
        "schema_version": "1.0.0",
        "data_status": "SYNTHETIC_FULL_GAMEWEEK_ONLY",
        "scenario_scope": "FULL_GAMEWEEK",
        "metadata": {
            "season": "2026/27",
            "target_gameweek": 12,
            "deadline_utc": "2026-11-28T11:00:00Z",
            "as_of_utc": "2026-11-27T18:00:00Z",
        },
        "players": players,
        "scenarios": scenarios,
        "portfolios": [candidate, field],
    }


class TestM4CovarFullGameweekContract(unittest.TestCase):
    def test_accepts_complete_full_gameweek_document_and_defaults_to_regular_mode(self):
        result = validate_full_gameweek_document(fixture())
        self.assertEqual(result["mode"], "REGULAR_GW")
        self.assertEqual(result["validation_status"], "VALID_SYNTHETIC_FULL_GAMEWEEK_INPUT")
        self.assertEqual(result["player_count"], 15)
        self.assertEqual(result["scenario_count"], 2)
        self.assertEqual(result["portfolio_count"], 2)
        self.assertEqual(result["field_portfolio_count"], 1)
        self.assertFalse(result["production_eligible"])
        self.assertEqual(result["decision_weight"], 0.0)

    def test_accepts_explicit_free_hit_mode_only(self):
        doc = fixture()
        doc["mode"] = "FREE_HIT"
        self.assertEqual(validate_full_gameweek_document(doc)["mode"], "FREE_HIT")
        doc["mode"] = "freehit"
        with self.assertRaisesRegex(CovarFullGameweekContractError, "mode must be"):
            validate_full_gameweek_document(doc)

    def test_requires_full_gameweek_scope_and_synthetic_data_status(self):
        doc = fixture()
        doc["scenario_scope"] = "FIXTURE_SLICE"
        with self.assertRaisesRegex(CovarFullGameweekContractError, "scenario_scope"):
            validate_full_gameweek_document(doc)
        doc = fixture()
        doc["data_status"] = "LIVE"
        with self.assertRaisesRegex(CovarFullGameweekContractError, "SYNTHETIC_FULL_GAMEWEEK_ONLY"):
            validate_full_gameweek_document(doc)

    def test_rejects_missing_player_outcome(self):
        doc = fixture()
        doc["scenarios"][0]["player_outcomes"].pop()
        with self.assertRaisesRegex(CovarFullGameweekContractError, "every player"):
            validate_full_gameweek_document(doc)

    def test_rejects_unknown_or_duplicate_player_outcomes(self):
        doc = fixture()
        doc["scenarios"][0]["player_outcomes"][0]["player_id"] = "unknown"
        with self.assertRaisesRegex(CovarFullGameweekContractError, "unknown or duplicate"):
            validate_full_gameweek_document(doc)
        doc = fixture()
        doc["scenarios"][0]["player_outcomes"][1]["player_id"] = "p1"
        with self.assertRaisesRegex(CovarFullGameweekContractError, "unknown or duplicate"):
            validate_full_gameweek_document(doc)

    def test_requires_explicit_played_boolean_and_consistent_minutes(self):
        doc = fixture()
        del doc["scenarios"][0]["player_outcomes"][0]["played"]
        with self.assertRaisesRegex(CovarFullGameweekContractError, "explicit boolean"):
            validate_full_gameweek_document(doc)
        doc = fixture()
        doc["scenarios"][0]["player_outcomes"][0]["played"] = False
        with self.assertRaisesRegex(CovarFullGameweekContractError, "positive minutes"):
            validate_full_gameweek_document(doc)

    def test_allows_aggregate_minutes_above_120_for_double_gameweeks(self):
        doc = fixture()
        doc["scenarios"][0]["player_outcomes"][0]["minutes"] = 165
        self.assertEqual(validate_full_gameweek_document(doc)["validation_status"], "VALID_SYNTHETIC_FULL_GAMEWEEK_INPUT")

    def test_allows_zero_minute_card_only_appearance(self):
        doc = fixture()
        outcome = doc["scenarios"][0]["player_outcomes"][0]
        outcome["minutes"] = 0
        outcome["played"] = True
        self.assertEqual(validate_full_gameweek_document(doc)["validation_status"], "VALID_SYNTHETIC_FULL_GAMEWEEK_INPUT")

    def test_allows_negative_fpl_points_and_rejects_nonfinite_points(self):
        doc = fixture()
        doc["scenarios"][0]["player_outcomes"][0]["fpl_points"] = -2
        validate_full_gameweek_document(doc)
        doc["scenarios"][0]["player_outcomes"][0]["fpl_points"] = float("nan")
        with self.assertRaisesRegex(CovarFullGameweekContractError, "finite"):
            validate_full_gameweek_document(doc)

    def test_requires_exact_union_of_complete_portfolio_squads_as_player_universe(self):
        doc = fixture()
        doc["players"].append({"player_id": "orphan", "position": "MID"})
        with self.assertRaisesRegex(CovarFullGameweekContractError, "union of all complete"):
            validate_full_gameweek_document(doc)

    def test_rejects_portfolio_player_outside_declared_universe(self):
        doc = fixture()
        doc["portfolios"][0]["player_ids"][0] = "unknown"
        with self.assertRaisesRegex(CovarFullGameweekContractError, "outside the scenario universe"):
            validate_full_gameweek_document(doc)

    def test_rejects_incomplete_or_invalid_lineup(self):
        doc = fixture()
        doc["portfolios"][0]["starting_player_ids"].pop()
        with self.assertRaisesRegex(CovarFullGameweekContractError, "starting XI must contain 11"):
            validate_full_gameweek_document(doc)
        doc = fixture()
        doc["portfolios"][0]["vice_captain_id"] = doc["portfolios"][0]["captain_id"]
        with self.assertRaisesRegex(CovarFullGameweekContractError, "distinct starters"):
            validate_full_gameweek_document(doc)

    def test_rejects_position_metadata_mismatch_and_illegal_formation(self):
        doc = fixture()
        doc["portfolios"][0]["player_positions"]["p2"] = "MID"
        with self.assertRaisesRegex(CovarFullGameweekContractError, "conflicts with player metadata"):
            validate_full_gameweek_document(doc)
        doc = fixture()
        for pid in ("p2", "p3", "p4", "p5"):
            doc["players"][int(pid[1:]) - 1]["position"] = "FWD"
            doc["portfolios"][0]["player_positions"][pid] = "FWD"
        with self.assertRaisesRegex(CovarFullGameweekContractError, "legal FPL formation"):
            validate_full_gameweek_document(doc)

    def test_rejects_invalid_field_weights(self):
        doc = fixture()
        doc["portfolios"][1]["field_weight"] = 0
        with self.assertRaisesRegex(CovarFullGameweekContractError, "must be > 0"):
            validate_full_gameweek_document(doc)
        doc = fixture()
        doc["portfolios"][1]["field_weight"] = 0.5
        with self.assertRaisesRegex(CovarFullGameweekContractError, "sum to 1"):
            validate_full_gameweek_document(doc)

    def test_requires_unique_scenario_and_portfolio_ids_and_probability_sum(self):
        doc = fixture()
        doc["scenarios"][1]["scenario_id"] = "low"
        with self.assertRaisesRegex(CovarFullGameweekContractError, "scenario IDs"):
            validate_full_gameweek_document(doc)
        doc = fixture()
        doc["portfolios"][1]["portfolio_id"] = "candidate"
        with self.assertRaisesRegex(CovarFullGameweekContractError, "portfolio IDs"):
            validate_full_gameweek_document(doc)
        doc = fixture()
        doc["scenarios"][0]["probability"] = 0.2
        with self.assertRaisesRegex(CovarFullGameweekContractError, "sum to 1"):
            validate_full_gameweek_document(doc)

    def test_rejects_post_deadline_and_unsupported_chip(self):
        doc = fixture()
        doc["metadata"]["as_of_utc"] = "2026-11-28T11:00:00Z"
        with self.assertRaisesRegex(CovarFullGameweekContractError, "before the deadline"):
            validate_full_gameweek_document(doc)
        doc = fixture()
        doc["portfolios"][0]["active_chip"] = "mystery"
        with self.assertRaisesRegex(CovarFullGameweekContractError, "unsupported active_chip"):
            validate_full_gameweek_document(doc)


if __name__ == "__main__":
    unittest.main()
