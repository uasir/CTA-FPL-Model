from __future__ import annotations

import copy
import unittest

from m4_field_context_contract import validate_field_context
from m4_candidate_field_comparison import (
    CandidateFieldComparisonError,
    compare_frozen_candidate_to_field,
)


def binding_fixture():
    snapshot = {
        "snapshot_id": "livefpl-gw11-top100k-2026-27",
        "season": "2026-27", "target_gameweek": 11,
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
        "manager_team_id": 421025, "season": "2026-27", "target_gameweek": 11,
        "deadline_utc": "2026-11-21T11:00:00Z",
        "as_of_utc": "2026-11-20T20:01:00Z",
        "manager_state": {"manager_state": {
            "squad_15": list(range(1, 16)), "starting_xi": list(range(1, 12)),
            "bench_order": [12, 13, 14], "reserve_goalkeeper_id": 15,
            "captain_id": 1, "vice_captain_id": 2, "formation": "4-3-3",
        }},
        "frozen_decision": {"action": "TRANSFER", "transfer_out_id": "11",
                            "transfer_in_id": "16", "decision_sha256": "b" * 64},
    }
    rows = [{
        "gameweek": "11", "fpl_element_id": str(i),
        "owned_by_pct": 30.0, "effective_ownership_pct": 45.0 if i == 1 else 20.0,
        "starting_pct": 25.0, "captain_pct": None, "triple_captain_pct": None,
        "scoring_exposure_pct": None, "effective_ownership_ci_low": None,
        "effective_ownership_ci_high": None,
    } for i in range(1, 17)]
    return validate_field_context(snapshot, rows, candidate)


class TestM4CandidateFieldComparison(unittest.TestCase):
    def test_compares_hold_and_transfer_without_combining_ev_and_eo(self):
        result = compare_frozen_candidate_to_field(binding_fixture())
        self.assertEqual(result["status"], "PASS_FROZEN_CANDIDATE_FIELD_EXPOSURE_COMPARISON")
        self.assertEqual(result["manager_team_id"], 421025)
        self.assertEqual(result["hold"]["squad_player_count"], 15)
        self.assertEqual(result["frozen_candidate"]["squad_player_count"], 15)
        self.assertEqual(result["frozen_candidate"]["starting_xi_count"], 11)
        self.assertEqual(result["covar"], "DISABLED")
        self.assertEqual(result["expected_points"], "NOT_COMBINED_WITH_EO")
        changes = {row["fpl_element_id"]: row for row in result["decision_exposure_changes"]}
        self.assertEqual(changes["11"]["personal_eo_change_pct_points"], -100.0)
        self.assertEqual(changes["16"]["personal_eo_change_pct_points"], 100.0)
        self.assertEqual(changes["11"]["personal_starting_exposure_change_pct_points"], -100.0)
        self.assertEqual(changes["16"]["personal_starting_exposure_change_pct_points"], 100.0)

    def test_hold_candidate_has_no_exposure_changes(self):
        binding = binding_fixture()
        binding["candidate"]["action"] = "HOLD"
        binding["candidate"]["transfer_out_id"] = None
        binding["candidate"]["transfer_in_id"] = None
        result = compare_frozen_candidate_to_field(binding)
        self.assertEqual(result["decision_exposure_changes"], [])
        self.assertEqual(result["frozen_candidate"]["scenario"], "HOLD")

    def test_rejects_missing_field_coverage(self):
        binding = binding_fixture()
        binding["field_eo_rows"] = [row for row in binding["field_eo_rows"]
                                    if row["fpl_element_id"] != "16"]
        with self.assertRaisesRegex(CandidateFieldComparisonError, "missing candidate players"):
            compare_frozen_candidate_to_field(binding)

    def test_rejects_release_eligible_input(self):
        binding = binding_fixture()
        binding["release_eligible"] = True
        with self.assertRaisesRegex(CandidateFieldComparisonError, "non-release-eligible"):
            compare_frozen_candidate_to_field(binding)

    def test_rejects_transfer_of_reserve_goalkeeper(self):
        binding = binding_fixture()
        binding["candidate"]["transfer_out_id"] = "15"
        binding["candidate"]["transfer_in_id"] = "16"
        with self.assertRaisesRegex(CandidateFieldComparisonError, "reserve goalkeeper"):
            compare_frozen_candidate_to_field(binding)


if __name__ == "__main__":
    unittest.main()
