from __future__ import annotations

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
                "season": output.get("season"),
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

    def test_report_replay_is_deterministic(self):
        output = fixture("HOLD")
        first = build_conventional_delivery_report(output)
        second = build_conventional_delivery_report(output)
        self.assertEqual(first, second)
        self.assertEqual(first["report_sha256"], second["report_sha256"])


if __name__ == "__main__":
    unittest.main()
