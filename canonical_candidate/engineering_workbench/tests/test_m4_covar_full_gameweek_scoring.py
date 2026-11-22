from __future__ import annotations

import copy
import unittest

from m4_covar_full_gameweek_scoring import (
    CovarFullGameweekScoringError,
    score_full_gameweek_portfolios,
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
    players = [{"player_id": pid, "position": positions[pid], "expected_points": 3.4 if pid == "p10" else 1.6, "expected_minutes": 90.0} for pid in ids]
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
        "portfolio_id": "field",
        "portfolio_role": "FIELD",
        "captain_id": "p9",
        "vice_captain_id": "p8",
        "field_weight": 1.0,
    })
    outcomes = []
    for scenario_id, probability, base in (("low", 0.4, 1), ("high", 0.6, 2)):
        rows = []
        for pid in ids:
            points = base
            if scenario_id == "high" and pid == "p10":
                points = 5
            rows.append({
                "player_id": pid,
                "minutes": 90,
                "played": True,
                "fpl_points": points,
            })
        outcomes.append({
            "scenario_id": scenario_id,
            "probability": probability,
            "player_outcomes": rows,
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
            "minutes_mean_preserved": True,
        },
        "players": players,
        "scenarios": outcomes,
        "portfolios": [candidate, field],
    }

def research_fixture():
    doc = fixture()
    doc["data_status"] = "RESEARCH_RESIDUAL_BLOCK_BOOTSTRAP_ONLY"
    doc["production_eligible"] = False
    doc["decision_weight"] = 0.0
    doc["covar_used"] = False
    doc["metadata"].update({
        "forecast_snapshot_id": "m3-gw12-snapshot",
        "model_version": "fplcat-v2",
        "training_cutoff_utc": "2026-11-27T17:00:00Z",
        "scenario_probability_method": "EQUAL_WEIGHT_EMPIRICAL_COMPLETE_GAMEWEEK_BLOCKS",
        "played_status_method": "POSITIVE_MINUTES_PROXY_CARD_ONLY_UNOBSERVED",
        "complete_historical_gameweeks": [10, 11],
        "probability_calibrated": False,
        "marginal_expected_points_preserved": True,
        "minutes_mean_preserved": True,
        "residual_bootstrap_payload_sha256": "a" * 64,
    })
    for scenario, gw in zip(doc["scenarios"], (10, 11)):
        scenario["source_gameweek"] = gw
        scenario["probability"] = 0.5
    return doc




class TestM4CovarFullGameweekScoring(unittest.TestCase):
    def test_scores_research_residual_blocks_without_enabling_covar(self):
        result = score_full_gameweek_portfolios(research_fixture(), baseline_portfolio_id="field")
        self.assertEqual(result["data_status"], "RESEARCH_RESIDUAL_BLOCK_BOOTSTRAP_ONLY")
        self.assertEqual(result["input_validation_status"], "VALID_RESEARCH_RESIDUAL_BLOCK_FULL_GAMEWEEK_INPUT")
        self.assertFalse(result["production_eligible"])
        self.assertEqual(result["decision_weight"], 0.0)
        self.assertFalse(result["covar_used"])
        self.assertEqual(result["shared_scenario_ids"], ["low", "high"])

    def test_scores_every_portfolio_on_identical_scenario_ids(self):
        result = score_full_gameweek_portfolios(fixture(), baseline_portfolio_id="field")
        self.assertEqual(result["shared_scenario_ids"], ["low", "high"])
        self.assertEqual(
            result["portfolio_results"]["candidate"]["scenario_scores"],
            [
                {"scenario_id": "low", "points": 12.0, "probability": 0.4},
                {"scenario_id": "high", "points": 30.0, "probability": 0.6},
            ],
        )
        self.assertAlmostEqual(result["portfolio_results"]["candidate"]["expected_points"], 22.8)
        self.assertAlmostEqual(
            result["portfolio_results"]["candidate"]["field_comparison"]["expected_points_difference_vs_weighted_field"],
            1.8,
        )
        self.assertEqual(result["field_comparison_status"], "AVAILABLE_EXPLICIT_FIELD_PORTFOLIOS")
        self.assertAlmostEqual(result["portfolio_results"]["candidate"]["field_comparison"]["probability_outscoring_weighted_field_portfolio"], 0.6)
        self.assertEqual(result["portfolio_results"]["candidate"]["baseline_comparison"]["baseline_portfolio_id"], "field")

    def test_resolves_goalkeeper_and_outfield_autosubs_before_scoring(self):
        doc = fixture()
        for scenario in doc["scenarios"]:
            outcomes = {row["player_id"]: row for row in scenario["player_outcomes"]}
            outcomes["p1"].update({"minutes": 0, "played": False})
            outcomes["p12"].update({"minutes": 90, "played": True})
            outcomes["p2"].update({"minutes": 0, "played": False})
            outcomes["p13"].update({"minutes": 90, "played": True})
        result = score_full_gameweek_portfolios(doc)
        resolution = result["portfolio_results"]["candidate"]["scenario_resolutions"][0]
        self.assertIn("p12", resolution["resolved_starting_xi"])
        self.assertIn("p13", resolution["resolved_starting_xi"])
        self.assertEqual(
            [(row["out"], row["in"]) for row in resolution["substitutions"]],
            [("p1", "p12"), ("p2", "p13")],
        )

    def test_double_gameweek_aggregate_minutes_above_120_are_scored(self):
        doc = fixture()
        for scenario in doc["scenarios"]:
            outcomes = {row["player_id"]: row for row in scenario["player_outcomes"]}
            outcomes["p2"].update({"minutes": 165, "played": True})
        result = score_full_gameweek_portfolios(doc)
        resolution = result["portfolio_results"]["candidate"]["scenario_resolutions"][0]
        self.assertIn("p2", resolution["resolved_starting_xi"])
        self.assertEqual(resolution["total_points"], 12.0)

    def test_card_only_appearance_blocks_autosub_and_keeps_captain(self):
        doc = fixture()
        for scenario in doc["scenarios"]:
            outcomes = {row["player_id"]: row for row in scenario["player_outcomes"]}
            outcomes["p10"].update({"minutes": 0, "played": True})
            outcomes["p2"].update({"minutes": 0, "played": False})
        result = score_full_gameweek_portfolios(doc)
        resolution = result["portfolio_results"]["candidate"]["scenario_resolutions"][0]
        self.assertEqual(resolution["active_captain_id"], "p10")
        self.assertNotIn("p10", [row["out"] for row in resolution["substitutions"]])
        self.assertIn("p2", [row["out"] for row in resolution["substitutions"]])

    def test_triple_captain_and_bench_boost_are_applied_by_resolver(self):
        doc = fixture()
        doc["portfolios"][0]["active_chip"] = "3xc"
        result = score_full_gameweek_portfolios(doc)
        self.assertEqual(result["portfolio_results"]["candidate"]["scenario_resolutions"][0]["captain_multiplier"], 3)
        doc = fixture()
        doc["portfolios"][0]["active_chip"] = "bboost"
        result = score_full_gameweek_portfolios(doc)
        resolution = result["portfolio_results"]["candidate"]["scenario_resolutions"][0]
        self.assertTrue(resolution["bench_boost_active"])
        self.assertEqual(len(result["portfolio_results"]["candidate"]["scenario_scores"]), 2)
        self.assertEqual(len(resolution["resolved_starting_xi"]), 11)

    def test_variance_decomposition_reconciles_to_total_portfolio_variance(self):
        result = score_full_gameweek_portfolios(fixture())
        row = result["portfolio_results"]["candidate"]
        self.assertTrue(row["variance_decomposition_matches_total"])
        self.assertAlmostEqual(row["variance_decomposition_total"], row["variance"], places=8)

    def test_regular_gameweek_is_default_and_free_hit_requires_explicit_mode(self):
        self.assertEqual(score_full_gameweek_portfolios(fixture())["mode"], "REGULAR_GW")
        doc = fixture()
        doc["mode"] = "FREE_HIT"
        self.assertEqual(score_full_gameweek_portfolios(doc)["mode"], "FREE_HIT")

    def test_rejects_invalid_contract_and_unknown_baseline(self):
        doc = fixture()
        doc["scenarios"][0]["player_outcomes"].pop()
        with self.assertRaisesRegex(CovarFullGameweekScoringError, "input validation failed"):
            score_full_gameweek_portfolios(doc)
        with self.assertRaisesRegex(CovarFullGameweekScoringError, "not present"):
            score_full_gameweek_portfolios(fixture(), baseline_portfolio_id="missing")

    def test_keeps_research_only_guardrails(self):
        result = score_full_gameweek_portfolios(fixture())
        self.assertFalse(result["production_eligible"])
        self.assertEqual(result["decision_weight"], 0.0)


if __name__ == "__main__":
    unittest.main()
