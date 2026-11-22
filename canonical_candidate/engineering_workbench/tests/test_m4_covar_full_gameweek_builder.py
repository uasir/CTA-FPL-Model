from __future__ import annotations

import copy
import hashlib
import json
import unittest

from m4_covar_full_gameweek_builder import (
    CovarFullGameweekBuildError,
    build_full_gameweek_document,
)


def inputs():
    ids = [f"p{i}" for i in range(1, 16)]
    positions = {
        "p1": "GK",
        "p2": "DEF", "p3": "DEF", "p4": "DEF", "p5": "DEF",
        "p6": "MID", "p7": "MID", "p8": "MID", "p9": "MID",
        "p10": "FWD", "p11": "FWD",
        "p12": "GK", "p13": "DEF", "p14": "MID", "p15": "FWD",
    }
    candidate = {
        "portfolio_id": "candidate-1",
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
        "portfolio_id": "field_sample_0001",
        "portfolio_role": "FIELD",
        "captain_id": "p9",
        "vice_captain_id": "p8",
        "field_weight": 1.0,
        "rank_stratum": 2,
    })
    adaptation = {
        "schema_version": "1.0.0",
        "metadata": {
            "gameweek": 12,
            "deadline_utc": "2026-11-28T11:00:00+00:00",
            "captured_at_utc": "2026-11-27T17:00:00+00:00",
            "as_of_utc": "2026-11-27T18:00:00+00:00",
            "evidence_role": "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE",
            "manager_entry_ids_retained": False,
            "cohort": "top_10k",
            "selected_manager_count": 1,
        },
        "portfolios": [field],
    }
    scenario = {
        "scenario_id": "s1",
        "probability": 1.0,
        "player_outcomes": [
            {"player_id": pid, "minutes": 90, "played": True, "fpl_points": 2}
            for pid in ids
        ],
    }
    return candidate, adaptation, [scenario]


class TestM4CovarFullGameweekBuilder(unittest.TestCase):
    def build(self, candidate=None, adaptation=None, scenarios=None, mode="REGULAR_GW", scenario_provenance=None):
        original_candidate, original_adaptation, original_scenarios = inputs()
        return build_full_gameweek_document(
            season="2026/27",
            target_gameweek=12,
            deadline_utc="2026-11-28T11:00:00Z",
            as_of_utc="2026-11-27T18:00:00+00:00",
            scenarios=original_scenarios if scenarios is None else scenarios,
            candidate_portfolios=[original_candidate if candidate is None else candidate],
            field_adaptation=original_adaptation if adaptation is None else adaptation,
            mode=mode,
            scenario_provenance=scenario_provenance,
        )

    def test_composes_full_universe_and_candidate_field_portfolios(self):
        doc = self.build()
        self.assertEqual(doc["scenario_scope"], "FULL_GAMEWEEK")
        self.assertEqual(len(doc["players"]), 15)
        self.assertEqual(len(doc["portfolios"]), 2)
        self.assertEqual(doc["portfolios"][0]["portfolio_role"], "CANDIDATE")
        self.assertEqual(doc["portfolios"][1]["portfolio_role"], "FIELD")
        self.assertNotIn("rank_stratum", doc["portfolios"][1])
        self.assertFalse(doc["production_eligible"])
        self.assertEqual(doc["decision_weight"], 0.0)

    def test_composes_research_residual_scenarios_for_full_gameweek_lineup_scoring(self):
        candidate, adaptation, base_scenarios = inputs()
        scenarios = [copy.deepcopy(base_scenarios[0]), copy.deepcopy(base_scenarios[0])]
        for scenario, gw in zip(scenarios, (10, 11)):
            scenario["scenario_id"] = f"residual-gw-{gw}"
            scenario["source_gameweek"] = gw
            scenario["probability"] = 0.5
        provenance = {
            "dataset_type": "M4_COVAR_PLAYER_GAMEWEEK_RESIDUAL_BOOTSTRAP_RESEARCH_ONLY",
            "season": "2026/27",
            "target_gameweek": 12,
            "forecast_snapshot_id": "m3-gw12-snapshot",
            "model_version": "fplcat-v2",
            "training_cutoff_utc": "2026-11-27T17:00:00Z",
            "scenario_probability_method": "EQUAL_WEIGHT_EMPIRICAL_COMPLETE_GAMEWEEK_BLOCKS",
            "complete_historical_gameweeks": [10, 11],
            "marginal_expected_points_preserved": True,
            "minutes_mean_preserved": True,
            "probability_calibrated": False,
            "decision_weight": 0.0,
            "production_eligible": False,
            "covar_used": False,
            "payload_sha256": "a" * 64,
            "scenarios": scenarios,
        }
        provenance["payload_sha256"] = hashlib.sha256(
            json.dumps({key: value for key, value in provenance.items() if key != "payload_sha256"},
                       sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest()
        doc = self.build(candidate=candidate, adaptation=adaptation, scenarios=scenarios,
                         scenario_provenance=provenance)
        self.assertEqual(doc["data_status"], "RESEARCH_RESIDUAL_BLOCK_BOOTSTRAP_ONLY")
        self.assertEqual(doc["validation_status"], "VALID_RESEARCH_RESIDUAL_BLOCK_FULL_GAMEWEEK_INPUT")
        self.assertFalse(doc["production_eligible"])
        self.assertFalse(doc["covar_used"])
        self.assertEqual(doc["metadata"]["forecast_snapshot_id"], "m3-gw12-snapshot")

    def test_rejects_scenario_rows_not_bound_to_residual_provenance(self):
        candidate, adaptation, base_scenarios = inputs()
        scenarios = [copy.deepcopy(base_scenarios[0]), copy.deepcopy(base_scenarios[0])]
        for scenario, gw in zip(scenarios, (10, 11)):
            scenario["scenario_id"] = f"residual-gw-{gw}"
            scenario["source_gameweek"] = gw
            scenario["probability"] = 0.5
        provenance = {
            "dataset_type": "M4_COVAR_PLAYER_GAMEWEEK_RESIDUAL_BOOTSTRAP_RESEARCH_ONLY",
            "season": "2026/27", "target_gameweek": 12,
            "forecast_snapshot_id": "m3-gw12-snapshot", "model_version": "fplcat-v2",
            "training_cutoff_utc": "2026-11-27T17:00:00Z",
            "scenario_probability_method": "EQUAL_WEIGHT_EMPIRICAL_COMPLETE_GAMEWEEK_BLOCKS",
            "complete_historical_gameweeks": [10, 11], "marginal_expected_points_preserved": True,
            "probability_calibrated": False, "decision_weight": 0.0,
            "production_eligible": False, "covar_used": False, "payload_sha256": "a" * 64,
            "scenarios": scenarios,
        }
        provenance["payload_sha256"] = hashlib.sha256(
            json.dumps({key: value for key, value in provenance.items() if key != "payload_sha256"},
                       sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest()
        altered = copy.deepcopy(scenarios)
        altered[0]["player_outcomes"][0]["fpl_points"] = 99
        with self.assertRaisesRegex(CovarFullGameweekBuildError, "exact residual-bootstrap scenario rows"):
            self.build(candidate=candidate, adaptation=adaptation, scenarios=altered,
                       scenario_provenance=provenance)

    def test_accepts_explicit_free_hit_mode(self):
        self.assertEqual(self.build(mode="FREE_HIT")["mode"], "FREE_HIT")

    def test_rejects_field_adaptation_from_different_gameweek_or_deadline(self):
        candidate, adaptation, scenarios = inputs()
        adaptation["metadata"]["gameweek"] = 13
        with self.assertRaisesRegex(CovarFullGameweekBuildError, "Gameweek mismatch"):
            self.build(adaptation=adaptation)
        candidate, adaptation, scenarios = inputs()
        adaptation["metadata"]["deadline_utc"] = "2026-11-29T11:00:00+00:00"
        with self.assertRaisesRegex(CovarFullGameweekBuildError, "deadline mismatch"):
            self.build(adaptation=adaptation)

    def test_rejects_field_adaptation_from_different_as_of_time(self):
        candidate, adaptation, scenarios = inputs()
        adaptation["metadata"]["as_of_utc"] = "2026-11-27T17:30:00+00:00"
        with self.assertRaisesRegex(CovarFullGameweekBuildError, "as_of_utc mismatch"):
            self.build(adaptation=adaptation)

    def test_rejects_manager_identifiers_and_missing_privacy_attestation(self):
        candidate, adaptation, scenarios = inputs()
        adaptation["portfolios"][0]["entry_id"] = "private"
        with self.assertRaisesRegex(CovarFullGameweekBuildError, "restricted manager identifier"):
            self.build(adaptation=adaptation)
        candidate, adaptation, scenarios = inputs()
        adaptation["metadata"]["manager_entry_ids_retained"] = True
        with self.assertRaisesRegex(CovarFullGameweekBuildError, "discarded"):
            self.build(adaptation=adaptation)

    def test_rejects_partial_field_projection_for_full_gameweek(self):
        candidate, adaptation, scenarios = inputs()
        adaptation["portfolios"][0]["player_ids"] = ["p1", "p2", "p3"]
        with self.assertRaisesRegex(CovarFullGameweekBuildError, "failed validation"):
            self.build(adaptation=adaptation)

    def test_rejects_conflicting_player_positions(self):
        candidate, adaptation, scenarios = inputs()
        adaptation["portfolios"][0]["player_positions"]["p2"] = "MID"
        with self.assertRaisesRegex(CovarFullGameweekBuildError, "conflicting position"):
            self.build(adaptation=adaptation)

    def test_rejects_incomplete_scenario_coverage(self):
        candidate, adaptation, scenarios = inputs()
        scenarios[0]["player_outcomes"].pop()
        with self.assertRaisesRegex(CovarFullGameweekBuildError, "failed validation"):
            self.build(scenarios=scenarios)

    def test_rejects_non_provisional_field_evidence(self):
        candidate, adaptation, scenarios = inputs()
        adaptation["metadata"]["evidence_role"] = "LOCK_VERIFIED"
        with self.assertRaisesRegex(CovarFullGameweekBuildError, "pre-deadline provisional"):
            self.build(adaptation=adaptation)


if __name__ == "__main__":
    unittest.main()
