from __future__ import annotations

import copy
import unittest

from m4_field_context_contract import (
    FieldContextContractError,
    validate_field_context,
)


def fixture():
    snapshot = {
        "snapshot_id": "livefpl-gw11-top100k-2026-27",
        "season": "2026-27",
        "target_gameweek": 11,
        "deadline_utc": "2026-11-21T11:00:00Z",
        "captured_at_utc": "2026-11-20T20:00:00Z",
        "cohort": {"name": "top_100k", "rank_min": 1, "rank_max": 100000},
        "sample": {"manager_count": 500, "effective_sample_size": 480.5,
                   "weighting": "rank_stratified_equal_page"},
        "coverage": {"covered_player_ids": [str(i) for i in range(1, 17)],
                     "missing_player_ids": []},
        "source": {"source_url": "https://example.invalid/field-eo.csv",
                   "artifact_sha256": "a" * 64},
    }
    candidate = {
        "manager_team_id": 421025,
        "season": "2026-27",
        "target_gameweek": 11,
        "deadline_utc": "2026-11-21T11:00:00Z",
        "as_of_utc": "2026-11-20T20:01:00Z",
        "manager_state": {"manager_state": {
            "squad_15": list(range(1, 16)),
            "starting_xi": list(range(1, 12)),
            "bench_order": [12, 13, 14],
            "reserve_goalkeeper_id": 15,
            "captain_id": 1,
            "vice_captain_id": 2,
            "formation": "4-3-3",
        }},
        "frozen_decision": {
            "action": "TRANSFER", "transfer_out_id": "11",
            "transfer_in_id": "16", "decision_sha256": "b" * 64,
        },
    }
    rows = [
        {"gameweek": "11", "fpl_element_id": str(i),
         "owned_by_pct": 10.0, "effective_ownership_pct": 12.0,
         "starting_pct": 8.0, "captain_pct": None, "triple_captain_pct": None,
         "scoring_exposure_pct": None, "effective_ownership_pct_ci95_low": None,
         "effective_ownership_pct_ci95_high": None}
        for i in range(1, 17)
    ]
    return snapshot, rows, candidate


class TestM4FieldContextContract(unittest.TestCase):
    def test_valid_candidate_is_bound_to_exact_field_snapshot(self):
        snapshot, rows, candidate = fixture()
        result = validate_field_context(snapshot, rows, candidate)
        self.assertEqual(result["contract_version"], "1.0.0")
        self.assertEqual(result["candidate"]["manager_team_id"], 421025)
        self.assertEqual(result["candidate"]["transfer_in_id"], "16")
        self.assertFalse(result["release_eligible"])
        self.assertEqual(result["units_policy"]["combination"], "PROHIBITED")
        self.assertEqual(result["units_policy"]["covar"], "DISABLED")

    def test_rejects_post_deadline_snapshot(self):
        snapshot, rows, candidate = fixture()
        snapshot["captured_at_utc"] = "2026-11-21T11:01:00Z"
        with self.assertRaisesRegex(FieldContextContractError, "before deadline"):
            validate_field_context(snapshot, rows, candidate)

    def test_rejects_field_snapshot_captured_after_frozen_decision(self):
        snapshot, rows, candidate = fixture()
        snapshot["captured_at_utc"] = "2026-11-20T20:02:00Z"
        with self.assertRaisesRegex(FieldContextContractError, "strictly before the frozen M3 decision"):
            validate_field_context(snapshot, rows, candidate)

    def test_rejects_candidate_gameweek_mismatch(self):
        snapshot, rows, candidate = fixture()
        candidate["target_gameweek"] = 12
        with self.assertRaisesRegex(FieldContextContractError, "Gameweek"):
            validate_field_context(snapshot, rows, candidate)

    def test_rejects_candidate_deadline_mismatch(self):
        snapshot, rows, candidate = fixture()
        candidate["deadline_utc"] = "2026-11-22T11:00:00Z"
        with self.assertRaisesRegex(FieldContextContractError, "deadline"):
            validate_field_context(snapshot, rows, candidate)

    def test_rejects_missing_candidate_player(self):
        snapshot, rows, candidate = fixture()
        rows.pop()
        snapshot["coverage"]["covered_player_ids"].remove("16")
        with self.assertRaisesRegex(FieldContextContractError, "lacks candidate squad"):
            validate_field_context(snapshot, rows, candidate)

    def test_rejects_duplicate_player_rows(self):
        snapshot, rows, candidate = fixture()
        rows.append(copy.deepcopy(rows[0]))
        with self.assertRaisesRegex(FieldContextContractError, "duplicate"):
            validate_field_context(snapshot, rows, candidate)

    def test_rejects_wrong_gameweek_in_eo_rows(self):
        snapshot, rows, candidate = fixture()
        rows[0]["gameweek"] = "10"
        with self.assertRaisesRegex(FieldContextContractError, "target Gameweek"):
            validate_field_context(snapshot, rows, candidate)

    def test_preserves_null_eo_instead_of_zero_filling(self):
        snapshot, rows, candidate = fixture()
        rows[0]["effective_ownership_pct"] = None
        result = validate_field_context(snapshot, rows, candidate)
        self.assertIsNone(result["field_eo_rows"][0]["effective_ownership_pct"])

    def test_rejects_invalid_source_hash(self):
        snapshot, rows, candidate = fixture()
        snapshot["source"]["artifact_sha256"] = "not-a-hash"
        with self.assertRaisesRegex(FieldContextContractError, "SHA-256"):
            validate_field_context(snapshot, rows, candidate)

    def test_hold_candidate_does_not_require_transfer_ids(self):
        snapshot, rows, candidate = fixture()
        candidate["frozen_decision"] = {
            "action": "HOLD", "decision_sha256": "c" * 64,
        }
        result = validate_field_context(snapshot, rows, candidate)
        self.assertEqual(result["candidate"]["action"], "HOLD")
        self.assertIsNone(result["candidate"]["transfer_in_id"])


if __name__ == "__main__":
    unittest.main()
