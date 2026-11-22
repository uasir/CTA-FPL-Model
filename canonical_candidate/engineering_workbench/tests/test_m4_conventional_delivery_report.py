from __future__ import annotations

import base64
import copy
import hashlib
import json
import unittest

from m4_conventional_delivery_report import build_conventional_delivery_report
from test_m5_conventional_delivery_contract import canonical, fixture


def field_context_for(output):
    decision = output["frozen_decision"]
    candidate = output["evaluation_candidate"]
    hold = candidate["manager_state"]["hold_plan"]
    return {
        "status": "PASS_PREDEADLINE_FIELD_COMPARISON",
        "release_eligible": False,
        "field_context": {
            "snapshot_id": "predecision-sample",
            "captured_at_utc": "2026-11-20T09:59:00Z",
            "candidate": {
                "manager_team_id": output["manager_team_id"],
                "season": (
                    candidate.get("season")
                    if candidate.get("season") is not None else output.get("season")
                ),
                "target_gameweek": output["target_gameweek"],
                "deadline_utc": output["deadline_utc"],
                "decision_sha256": decision["decision_sha256"],
                "action": decision["action"],
                "transfer_out_id": decision.get("transfer_out_id"),
                "transfer_in_id": decision.get("transfer_in_id"),
                "squad_15": list(map(str, [
                    row["fpl_element_id"]
                    for row in candidate["manager_state"]["squad_snapshot"]
                ])),
                "starting_xi": list(map(str, hold["starting_xi"])),
                "bench_order": list(map(str, hold["bench_order"])),
                "reserve_goalkeeper_id": str(hold["reserve_goalkeeper_id"]),
                "captain_id": str(hold["captain_id"]),
                "vice_captain_id": str(hold["vice_captain_id"]),
                "formation": hold["formation"],
            },
        },
        "field_diagnostics": {"status": "PASS_FIELD_CONTEXT_DIAGNOSTICS"},
        "portfolio_exposure_baseline": {
            "status": "PASS_NONCOVARIANCE_PORTFOLIO_EXPOSURE_BASELINE",
            "covar": "DISABLED", "expected_points": "NOT_COMBINED_WITH_EO",
        },
        "comparison": {"covar": "DISABLED", "expected_points": "NOT_COMBINED_WITH_EO"},
    }


def replay_evidence_for(output):
    candidate = output["evaluation_candidate"]
    candidate["season"] = "2026-27"
    candidate["software_commit"] = "m3-replay-commit"
    candidate["provider_identity"] = copy.deepcopy(output["provider_identity"])
    candidate["provider_snapshot_id"] = output["provider_snapshot_id"]
    candidate_state = candidate["manager_state"]
    candidate_state["chip"] = "NONE"
    candidate_state["formation"] = candidate_state["hold_plan"]["formation"]
    payload = base64.b64encode(b"frozen-provider-source").decode("ascii")
    source_time = "2026-11-20T09:59:00Z"
    generated_time = "2026-11-20T09:30:00Z"
    raw_sha = hashlib.sha256(base64.b64decode(payload)).hexdigest()
    raw_snapshot_id = f"sha256:{raw_sha}"
    source_url = "https://fplcat.com/api/v1/projections"
    candidate["source_archives"] = [{
        "captured_at_utc": source_time,
        "generated_at_utc": generated_time,
        "raw_payload_base64": payload,
        "raw_sha256": raw_sha,
        "raw_snapshot_id": raw_snapshot_id,
        "source_url": source_url,
    }]
    evidence_state = {
        "bank": candidate_state["bank"],
        "free_transfers": candidate_state["free_transfers"],
        "formation": candidate_state["formation"],
        "chip_state": candidate_state["chip"],
        "squad_15": list(candidate_state["hold_plan"]["squad_ids"]),
        "starting_xi": list(candidate_state["hold_plan"]["starting_xi"]),
        "bench_order": list(candidate_state["hold_plan"]["bench_order"]),
        "reserve_goalkeeper_id": candidate_state["hold_plan"]["reserve_goalkeeper_id"],
        "captain_id": candidate_state["hold_plan"]["captain_id"],
        "vice_captain_id": candidate_state["hold_plan"]["vice_captain_id"],
    }
    provider = copy.deepcopy(output["provider_identity"])
    evidence = {
        "12": {
            "deadline_utc": output["deadline_utc"],
            "decision_as_of_utc": output["decision_as_of_utc"],
            "evidence_is_point_in_time": True,
            "manager_team_id": output["manager_team_id"],
            "target_gameweek": output["target_gameweek"],
            "season": "2026-27",
            "manager_state": evidence_state,
            "provider_snapshot": {
                "snapshot_id": output["provider_snapshot_id"],
                "provider": provider,
                "target_gameweek": output["target_gameweek"],
                "season": "2026-27",
            },
            "sources": [{
                "provider_id": "fpl-cat",
                "captured_at_utc": source_time,
                "generated_at_utc": generated_time,
                "raw_payload_base64": payload,
                "raw_sha256": raw_sha,
                "raw_snapshot_id": raw_snapshot_id,
                "source_url": source_url,
            }],
        }
    }
    decision = output["frozen_decision"]
    decision_body = {key: value for key, value in decision.items() if key != "decision_sha256"}
    replay = {
        "status": "PASSED",
        "replay_type": "DETERMINISTIC_RAW_AND_CANONICAL_INPUT_REEXECUTION",
        "manager_team_id": output["manager_team_id"],
        "target_gameweek": output["target_gameweek"],
        "release_eligible": False,
        "frozen_decision_match": True,
        "recommendation_match": True,
        "raw_archive_hashes_verified": True,
        "software_commit": "m3-replay-commit",
        "decision_sha256": hashlib.sha256(canonical(decision_body)).hexdigest(),
        "replayed_payload_sha256": hashlib.sha256(canonical(decision)).hexdigest(),
    }
    return replay, evidence


class TestConventionalDeliveryReport(unittest.TestCase):
    def test_report_succeeds_without_field_context(self):
        output = fixture("TRANSFER")
        original = copy.deepcopy(output)
        report = build_conventional_delivery_report(output)
        self.assertEqual(report["conventional"]["action"], "TRANSFER")
        self.assertEqual(report["field_context"]["status"], "NOT_SUPPLIED")
        self.assertIsNone(report["field_context"]["context"])
        self.assertEqual(output, original)
        self.assertFalse(report["guardrails"]["release_eligible"])

    def test_report_accepts_season_stored_only_in_live_candidate(self):
        output = fixture("TRANSFER")
        output["evaluation_candidate"]["season"] = "2026-27"
        original = copy.deepcopy(output)
        report = build_conventional_delivery_report(output)
        self.assertEqual(report["field_context"]["status"], "NOT_SUPPLIED")
        self.assertEqual(report["conventional"]["action"], "TRANSFER")
        self.assertEqual(output, original)

    def test_field_context_accepts_season_from_live_candidate_only(self):
        output = fixture("HOLD")
        output["evaluation_candidate"]["season"] = "2026-27"
        output.pop("season", None)
        report = build_conventional_delivery_report(output, field_context_for(output))
        self.assertEqual(report["field_context"]["status"], "ATTACHED_DESCRIPTIVE_CONTEXT")
        self.assertEqual(report["conventional"]["action"], "HOLD")

    def test_conflicting_top_level_and_candidate_seasons_are_rejected(self):
        output = fixture("TRANSFER")
        output["season"] = "2025-26"
        output["evaluation_candidate"]["season"] = "2026-27"
        with self.assertRaisesRegex(ValueError, "season differs from top-level output"):
            build_conventional_delivery_report(output)

    def test_valid_field_context_is_descriptive_only(self):
        output = fixture("HOLD")
        original = copy.deepcopy(output)
        report = build_conventional_delivery_report(output, field_context_for(output))
        self.assertEqual(report["field_context"]["status"], "ATTACHED_DESCRIPTIVE_CONTEXT")
        self.assertEqual(report["conventional"]["recommendation"], original["recommendation"])
        self.assertEqual(report["conventional"]["frozen_decision_sha256"],
                         original["frozen_decision"]["decision_sha256"])
        self.assertFalse(report["guardrails"]["ev_eo_blended"])
        self.assertEqual(report["guardrails"]["covar_decision_weight"], 0)
        self.assertEqual(output, original)

    def test_invalid_field_context_is_withheld_without_blocking_report(self):
        output = fixture("TRANSFER")
        context = field_context_for(output)
        context["field_context"]["captured_at_utc"] = output["decision_as_of_utc"]
        report = build_conventional_delivery_report(output, context)
        self.assertEqual(report["status"], "PASS_CONVENTIONAL_DELIVERY_WITH_OPTIONAL_FIELD_CONTEXT")
        self.assertEqual(report["field_context"]["status"], "WITHHELD_DEGRADED_MODE")
        self.assertIn("predate M3 decision", report["field_context"]["withheld_reason"])
        self.assertEqual(report["conventional"]["action"], "TRANSFER")

    def test_report_binds_to_verified_frozen_m3_replay_evidence(self):
        output = fixture("TRANSFER")
        replay, evidence = replay_evidence_for(output)
        report = build_conventional_delivery_report(
            output, m3_replay_report=replay, decision_evidence=evidence,
        )
        self.assertEqual(report["m3_replay_evidence"]["status"], "VERIFIED")
        self.assertEqual(report["m3_replay_evidence"]["target_gameweek"], 12)
        self.assertEqual(report["m3_replay_evidence"]["source_archive_count"], 1)
        self.assertTrue(report["guardrails"]["frozen_m3_replay_verified"])
        self.assertFalse(report["guardrails"]["release_eligible"])

    def test_report_rejects_unpassed_frozen_m3_replay(self):
        output = fixture("HOLD")
        replay, evidence = replay_evidence_for(output)
        replay["status"] = "FAILED"
        with self.assertRaisesRegex(ValueError, "frozen replay did not pass"):
            build_conventional_delivery_report(
                output, m3_replay_report=replay, decision_evidence=evidence,
            )

    def test_report_rejects_raw_source_archive_mismatch(self):
        output = fixture("HOLD")
        replay, evidence = replay_evidence_for(output)
        evidence["12"]["sources"][0]["raw_payload_base64"] = base64.b64encode(b"tampered").decode("ascii")
        with self.assertRaisesRegex(ValueError, "raw payload SHA-256"):
            build_conventional_delivery_report(
                output, m3_replay_report=replay, decision_evidence=evidence,
            )

    def test_report_rejects_evidence_manager_squad_mismatch(self):
        output = fixture("HOLD")
        replay, evidence = replay_evidence_for(output)
        evidence["12"]["manager_state"]["squad_15"][0] = 999
        with self.assertRaisesRegex(ValueError, "manager squad IDs"):
            build_conventional_delivery_report(
                output, m3_replay_report=replay, decision_evidence=evidence,
            )

    def test_report_requires_replay_report_and_evidence_together(self):
        output = fixture("HOLD")
        replay, _ = replay_evidence_for(output)
        with self.assertRaisesRegex(ValueError, "must be supplied together"):
            build_conventional_delivery_report(output, m3_replay_report=replay)

    def test_report_replay_is_deterministic(self):
        output = fixture("HOLD")
        first = build_conventional_delivery_report(output)
        second = build_conventional_delivery_report(output)
        self.assertEqual(first, second)
        self.assertEqual(first["report_sha256"], second["report_sha256"])


if __name__ == "__main__":
    unittest.main()
