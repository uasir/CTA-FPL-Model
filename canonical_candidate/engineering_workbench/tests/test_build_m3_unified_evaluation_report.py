from __future__ import annotations

import copy
import unittest

from build_m3_unified_evaluation_report import (
    UnifiedReportError,
    build_unified_report,
)


def event(gw: int, delta: float, action: str = "TRANSFER", digest: str | None = None) -> dict:
    hold = 50.0
    return {
        "evidence_class": "REAL_CANDIDATE",
        "evaluation_status": "REAL_DECISION_BACKTEST_EVENT_SCORED_NOT_PROMOTION_EVIDENCE",
        "historical_performance_validated": False,
        "manager_team_id": 421025,
        "target_gameweek": gw,
        "provider_identity": {"name": "FPL Cat", "product": "FPL points", "variant": "player-GW"},
        "recommended_action": action,
        "recommended": {"net_points": hold + delta, "transfer_hit_points": 4.0 if action == "TRANSFER" else 0.0},
        "hold": {"net_points": hold, "transfer_hit_points": 0.0},
        "net_points_delta_vs_hold": delta,
        "evaluation_input_sha256": digest or f"{gw:064x}",
        "frozen_decision_sha256": f"{gw + 100:064x}",
        "software_commit": "a" * 40,
        "source_provenance": [{"source_type": "provider", "raw_sha256": "b" * 64}],
    }


def sample(n: int = 20) -> list[dict]:
    return [event(gw, 2.0 if gw <= 10 else 0.0,
                  "TRANSFER" if gw <= 10 else "HOLD") for gw in range(1, n + 1)]


class UnifiedM3EvaluationReportTests(unittest.TestCase):
    def test_report_contains_descriptive_and_statistical_outputs(self):
        report = build_unified_report(sample(), bootstrap_replicates=1000)
        self.assertEqual(report["source_event_count"], 20)
        self.assertEqual(report["descriptive_performance"]["evidence_class"],
                         "AGGREGATED_REAL_EVENT_SCORES")
        self.assertIn("mean_delta_gameweek_bootstrap_95_ci",
                      report["statistical_evidence"]["provider_cohorts"][0])
        self.assertEqual(report["aggregation_input_sha256"],
                         report["statistical_evidence"]["aggregation_input_sha256"])
        self.assertFalse(report["promotion_eligible"])
        self.assertFalse(report["historical_performance_validated"])
        self.assertFalse(report["release_eligible"])

    def test_report_is_invariant_to_input_order(self):
        rows = sample()
        forward = build_unified_report(rows, bootstrap_replicates=1000)
        reverse = build_unified_report(list(reversed(rows)), bootstrap_replicates=1000)
        self.assertEqual(forward, reverse)

    def test_provider_variants_stay_separate(self):
        rows = sample()
        other = copy.deepcopy(rows[0])
        other["target_gameweek"] = 21
        other["evaluation_input_sha256"] = "c" * 64
        other["frozen_decision_sha256"] = "d" * 64
        other["provider_identity"]["variant"] = "fixture"
        rows.append(other)
        report = build_unified_report(rows, bootstrap_replicates=1000)
        self.assertEqual(len(report["descriptive_performance"]["provider_cohorts"]), 2)
        self.assertEqual(len(report["statistical_evidence"]["provider_cohorts"]), 2)

    def test_empty_input_fails_closed(self):
        with self.assertRaisesRegex(UnifiedReportError, "at least one"):
            build_unified_report([])

    def test_unadmitted_input_fails_closed(self):
        rows = sample()
        rows[0]["evidence_class"] = "SYNTHETIC_TEST"
        with self.assertRaisesRegex(ValueError, "independently admitted"):
            build_unified_report(rows)


if __name__ == "__main__":
    unittest.main()
