from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from m4_predeadline_field_artifact_adapter import (
    PredeadlineArtifactError, load_predeadline_field_artifact,
)
from m4_predeadline_field_comparison import (
    adapt_m3_evaluation_candidate, build_predeadline_comparison,
)


def fixture(root: Path, *, status="CAPTURED_PRE_DEADLINE_CURRENT_PICKS",
            picks_at="2026-11-20T20:32:00Z", lock_verified=False):
    csv_path, report_path, candidate_path = root / "field.csv", root / "report.json", root / "candidate.json"
    fields = ["gameweek", "fpl_element_id", "sample_managers", "sample_weight",
              "owned_by_pct", "starting_pct", "captain_pct", "triple_captain_pct",
              "effective_ownership_pct", "scoring_exposure_pct",
              "effective_ownership_pct_ci95_low", "effective_ownership_pct_ci95_high"]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for player_id in range(1, 16):
            writer.writerow({"gameweek": 12, "fpl_element_id": player_id,
                             "sample_managers": 100, "sample_weight": 100,
                             "owned_by_pct": 50, "starting_pct": 45, "captain_pct": 10,
                             "triple_captain_pct": 0, "effective_ownership_pct": 60,
                             "scoring_exposure_pct": 55,
                             "effective_ownership_pct_ci95_low": 50,
                             "effective_ownership_pct_ci95_high": 70})
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    report = {
        "status": status, "evidence_role": "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE",
        "picks_lock_verified": lock_verified, "provisional_picks": True,
        "deadline_time_utc": "2026-11-20T21:00:00Z",
        "capture_started_at_utc": "2026-11-20T20:29:00Z",
        "rank_cohort_captured_at_utc": "2026-11-20T20:30:00Z",
        "picks_captured_at_utc": picks_at, "gameweek": 12,
        "sample_size_captured": 100, "sample_managers": 100,
        "effective_sample_size": 98.2, "rank_limit": 10000,
        "rank_min": 1, "rank_max": 9999, "rank_strata_count": 200,
        "cohort": "overall global rank", "sample_weight": 100,
        "csv_sha256": digest,
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")
    candidate = {
        "manager_team_id": 421025, "season": "2026-27", "target_gameweek": 12,
        "deadline_utc": "2026-11-20T21:00:00Z", "as_of_utc": "2026-11-20T20:33:00Z",
        "frozen_decision": {"action": "HOLD", "decision_sha256": "b" * 64},
        "manager_state": {"manager_state": {
            "squad_15": list(range(1, 16)), "starting_xi": list(range(1, 12)),
            "bench_order": [12, 13, 14], "reserve_goalkeeper_id": 15,
            "captain_id": 1, "vice_captain_id": 2, "formation": "4-3-3",
        }},
    }
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    return csv_path, report_path, candidate_path


class TestM4PredeadlineFieldIntegration(unittest.TestCase):
    def test_adapts_real_m3_evaluation_candidate_envelope(self):
        roster = [{"fpl_element_id": player_id} for player_id in range(1, 16)]
        hold_plan = {
            "squad_ids": list(range(1, 16)), "starting_xi": list(range(1, 12)),
            "bench_order": [12, 13, 14], "reserve_goalkeeper_id": 15,
            "captain_id": 1, "vice_captain_id": 2, "formation": "4-3-3",
        }
        decision = {
            "action": "TRANSFER", "transfer_out_id": 12, "transfer_in_id": 16,
            "decision_sha256": "c" * 64,
            "squad_plan": {
                "squad_ids": list(range(1, 12)) + [13, 14, 15, 16],
                "starting_xi": list(range(1, 12)), "bench_order": [16, 13, 14],
                "reserve_goalkeeper_id": 15, "captain_id": 1,
                "vice_captain_id": 2, "formation": "4-3-3",
            },
        }
        m3 = {"evaluation_candidate": {
            "manager_team_id": 421025, "season": "2026-27",
            "target_gameweek": 12, "deadline_utc": "2026-11-20T21:00:00Z",
            "as_of_utc": "2026-11-20T20:33:00Z",
            "manager_state": {"squad_snapshot": roster, "hold_plan": hold_plan},
            "frozen_decision": decision,
        }}
        adapted = adapt_m3_evaluation_candidate(m3)
        state = adapted["manager_state"]["manager_state"]
        self.assertEqual(adapted["frozen_decision"]["action"], "TRANSFER")
        self.assertEqual(state["squad_15"], list(range(1, 16)))
        self.assertEqual(state["bench_order"], [12, 13, 14])

    def test_rejects_m3_transfer_plan_that_reshuffles_lineup(self):
        roster = [{"fpl_element_id": player_id} for player_id in range(1, 16)]
        hold_plan = {
            "squad_ids": list(range(1, 16)), "starting_xi": list(range(1, 12)),
            "bench_order": [12, 13, 14], "reserve_goalkeeper_id": 15,
            "captain_id": 1, "vice_captain_id": 2, "formation": "4-3-3",
        }
        decision = {
            "action": "TRANSFER", "transfer_out_id": 12, "transfer_in_id": 16,
            "decision_sha256": "c" * 64,
            "squad_plan": {
                "squad_ids": list(range(1, 12)) + [13, 14, 15, 16],
                "starting_xi": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 16],
                "bench_order": [12, 13, 14], "reserve_goalkeeper_id": 15,
                "captain_id": 1, "vice_captain_id": 2, "formation": "4-3-3",
            },
        }
        m3 = {"evaluation_candidate": {
            "manager_team_id": 421025, "season": "2026-27",
            "target_gameweek": 12, "deadline_utc": "2026-11-20T21:00:00Z",
            "as_of_utc": "2026-11-20T20:33:00Z",
            "manager_state": {"squad_snapshot": roster, "hold_plan": hold_plan},
            "frozen_decision": decision,
        }}
        with self.assertRaisesRegex(ValueError, "starting_xi"):
            adapt_m3_evaluation_candidate(m3)

    def test_adapter_and_contract_feed_candidate_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = fixture(Path(temp))
            result = build_predeadline_comparison(
                *paths, season="2026-27", source_url="https://github.com/example/run/1"
            )
        self.assertEqual(result["status"], "PASS_PREDEADLINE_FIELD_COMPARISON")
        self.assertEqual(result["evidence_role"], "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE")
        self.assertEqual(result["comparison"]["hold"]["scenario"], "HOLD")
        self.assertEqual(result["field_diagnostics"]["status"], "PASS_FIELD_CONTEXT_DIAGNOSTICS")
        self.assertFalse(result["release_eligible"])
        self.assertEqual(result["comparison"]["covar"], "DISABLED")

    def test_rejects_capture_after_deadline(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = fixture(Path(temp), picks_at="2026-11-20T21:00:01Z")
            with self.assertRaisesRegex(PredeadlineArtifactError, "precede deadline"):
                load_predeadline_field_artifact(paths[0], paths[1],
                    season="2026-27", source_url="https://example.test/run")

    def test_rejects_postlock_or_wrong_status_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = fixture(Path(temp), status="CAPTURED_POST_DEADLINE_PICKS", lock_verified=True)
            with self.assertRaisesRegex(PredeadlineArtifactError, "not a successful"):
                load_predeadline_field_artifact(paths[0], paths[1],
                    season="2026-27", source_url="https://example.test/run")

    def test_rejects_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = fixture(Path(temp))
            paths[1].write_text(paths[1].read_text().replace('"csv_sha256":', '"csv_sha256": "wrong", "ignored":'))
            with self.assertRaisesRegex(PredeadlineArtifactError, "SHA-256"):
                load_predeadline_field_artifact(paths[0], paths[1],
                    season="2026-27", source_url="https://example.test/run")

    def test_rejects_candidate_after_deadline(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = fixture(Path(temp))
            candidate = json.loads(paths[2].read_text())
            candidate["as_of_utc"] = "2026-11-20T21:00:00Z"
            paths[2].write_text(json.dumps(candidate))
            from m4_field_context_contract import FieldContextContractError
            with self.assertRaisesRegex(FieldContextContractError, "before deadline"):
                build_predeadline_comparison(*paths, season="2026-27",
                    source_url="https://example.test/run")


if __name__ == "__main__":
    unittest.main()
