from __future__ import annotations

import copy
import hashlib
import json
import unittest

from m4_m3_optionality_adapter import (
    M3M4OptionalityError, attach_optional_m4_context,
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def m3_fixture():
    squad = list(range(1, 16))
    hold = {
        "squad_ids": squad, "starting_xi": list(range(1, 12)),
        "bench_order": [12, 13, 14], "reserve_goalkeeper_id": 15,
        "captain_id": 1, "vice_captain_id": 2, "formation": "4-3-3",
    }
    body = {
        "action": "TRANSFER", "transfer_out_id": 11, "transfer_in_id": 16,
        "incoming_player": {"fpl_element_id": 16, "position": "MID"},
        "transfer_hit_points": 0.0,
        "squad_plan": {
            "squad_ids": list(range(1, 11)) + [12, 13, 14, 15, 16],
            "starting_xi": list(range(1, 11)) + [16],
            "bench_order": [12, 13, 14], "reserve_goalkeeper_id": 15,
            "captain_id": 1, "vice_captain_id": 2, "formation": "4-3-3",
        },
    }
    decision = {**body, "decision_sha256": hashlib.sha256(_canonical(body)).hexdigest()}
    evaluation = {
        "manager_team_id": 421025, "season": "2026-27", "target_gameweek": 12,
        "deadline_utc": "2026-11-20T21:00:00Z", "as_of_utc": "2026-11-20T20:33:00Z",
        "manager_state": {
            "squad_snapshot": [{"fpl_element_id": player_id} for player_id in squad],
            "hold_plan": hold,
        },
        "frozen_decision": decision,
    }
    return {
        "run_type": "M3_CONVENTIONAL_PERSONAL_SQUAD_RECOMMENDATION",
        "manager_team_id": 421025, "season": "2026-27", "target_gameweek": 12,
        "decision_as_of_utc": "2026-11-20T20:33:00Z",
        "deadline_utc": "2026-11-20T21:00:00Z",
        "recommendation": {"expected_points": 61.4, "legality": "PASS"},
        "frozen_decision": decision, "evaluation_candidate": evaluation,
        "release_eligible": False,
    }


def m4_fixture(m3):
    decision = m3["frozen_decision"]
    return {
        "status": "PASS_PREDEADLINE_FIELD_COMPARISON", "release_eligible": False,
        "field_context": {
            "snapshot_id": "pre-gw12-sample",
            "season": "2026-27", "target_gameweek": 12,
            "deadline_utc": "2026-11-20T21:00:00Z",
            "captured_at_utc": "2026-11-20T20:32:00Z",
            "candidate": {
                "manager_team_id": 421025, "season": "2026-27", "target_gameweek": 12,
                "deadline_utc": "2026-11-20T21:00:00Z",
                "decision_sha256": decision["decision_sha256"], "action": "TRANSFER",
                "transfer_out_id": 11, "transfer_in_id": 16,
                "squad_15": list(map(str, range(1, 16))),
                "starting_xi": list(map(str, range(1, 12))),
                "bench_order": ["12", "13", "14"], "reserve_goalkeeper_id": "15",
                "captain_id": "1", "vice_captain_id": "2", "formation": "4-3-3",
            },
        },
        "field_diagnostics": {"status": "PASS_FIELD_CONTEXT_DIAGNOSTICS"},
        "portfolio_exposure_baseline": {
            "status": "PASS_NONCOVARIANCE_PORTFOLIO_EXPOSURE_BASELINE",
            "covar": "DISABLED", "expected_points": "NOT_COMBINED_WITH_EO",
        },
        "comparison": {"covar": "DISABLED", "expected_points": "NOT_COMBINED_WITH_EO"},
    }


class TestM4M3Optionality(unittest.TestCase):
    def test_m3_is_unchanged_when_m4_is_absent(self):
        m3 = m3_fixture()
        original = copy.deepcopy(m3)
        result = attach_optional_m4_context(m3)
        self.assertEqual(result["m4_status"], "NOT_SUPPLIED")
        self.assertIsNone(result["m4_context"])
        self.assertEqual(result["m3_output"], original)
        self.assertEqual(result["m3_output_sha256"], hashlib.sha256(_canonical(original)).hexdigest())

    def test_candidate_only_season_is_supported(self):
        m3 = m3_fixture()
        m3.pop("season")
        original = copy.deepcopy(m3)
        result = attach_optional_m4_context(m3)
        self.assertEqual(result["m4_status"], "NOT_SUPPLIED")
        self.assertEqual(result["m3_output"], original)

    def test_valid_m4_is_attached_when_season_exists_only_in_candidate(self):
        m3 = m3_fixture()
        m3.pop("season")
        result = attach_optional_m4_context(m3, m4_fixture(m3))
        self.assertEqual(result["m4_status"], "ATTACHED_DESCRIPTIVE_CONTEXT")
        self.assertEqual(result["m3_output"], m3)

    def test_valid_m4_is_attached_without_mutating_m3_ev_or_decision(self):
        m3 = m3_fixture()
        original = copy.deepcopy(m3)
        result = attach_optional_m4_context(m3, m4_fixture(m3))
        self.assertEqual(result["m4_status"], "ATTACHED_DESCRIPTIVE_CONTEXT")
        self.assertEqual(result["m3_output"], original)
        self.assertEqual(result["m3_output"]["recommendation"], original["recommendation"])
        self.assertEqual(result["m3_frozen_decision_sha256"], m3["frozen_decision"]["decision_sha256"])

    def test_stale_or_invalid_m4_degrades_without_changing_m3(self):
        m3 = m3_fixture()
        original = copy.deepcopy(m3)
        m4 = m4_fixture(m3)
        m4["field_context"]["captured_at_utc"] = "2026-11-20T20:34:00Z"
        result = attach_optional_m4_context(m3, m4)
        self.assertEqual(result["m4_status"], "WITHHELD_DEGRADED_MODE")
        self.assertIn("predate M3 decision", result["m4_withheld_reason"])
        self.assertIsNone(result["m4_context"])
        self.assertEqual(result["m3_output"], original)

    def test_m4_bench_order_mismatch_is_withheld(self):
        m3 = m3_fixture()
        m4 = m4_fixture(m3)
        m4["field_context"]["candidate"]["bench_order"] = ["13", "12", "14"]
        result = attach_optional_m4_context(m3, m4)
        self.assertEqual(result["m4_status"], "WITHHELD_DEGRADED_MODE")
        self.assertIn("bench_order", result["m4_withheld_reason"])
        self.assertEqual(result["m3_output"], m3)

    def test_m4_bound_to_different_decision_is_withheld(self):
        m3 = m3_fixture()
        m4 = m4_fixture(m3)
        m4["field_context"]["candidate"]["decision_sha256"] = "f" * 64
        result = attach_optional_m4_context(m3, m4)
        self.assertEqual(result["m4_status"], "WITHHELD_DEGRADED_MODE")
        self.assertIn("different frozen M3 decision", result["m4_withheld_reason"])
        self.assertEqual(result["m3_output"], m3)

    def test_rejects_tampered_m3_frozen_decision_instead_of_masking_it(self):
        m3 = m3_fixture()
        m3["frozen_decision"]["transfer_in_id"] = 999
        with self.assertRaisesRegex(M3M4OptionalityError, "hash"):
            attach_optional_m4_context(m3)


if __name__ == "__main__":
    unittest.main()
