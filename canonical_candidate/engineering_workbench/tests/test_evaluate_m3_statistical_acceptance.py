from __future__ import annotations

import copy
import unittest

from evaluate_m3_statistical_acceptance import (
    StatisticalGateError, assess_aggregation, assess_cohort,
)


def event(gw: int, delta: float, action: str = "TRANSFER") -> dict:
    return {"target_gameweek": gw, "recommended_action": action,
            "net_points_delta_vs_hold": delta}


def cohort(n: int = 20, transfers: int = 10, delta: float = 2.0) -> dict:
    rows = [event(i + 1, delta if i < transfers else 0.0,
                  "TRANSFER" if i < transfers else "HOLD") for i in range(n)]
    return {"provider_identity": {"name": "FPL Cat", "product": "xP", "variant": "player-GW"},
            "events": rows}


def aggregation(c: dict | None = None) -> dict:
    return {"evidence_class": "AGGREGATED_REAL_EVENT_SCORES", "manager_team_id": 421025,
            "aggregation_input_sha256": "a" * 64, "promotion_eligible": False,
            "historical_performance_validated": False, "provider_cohorts": [c or cohort()]}


class StatisticalAcceptanceTests(unittest.TestCase):
    def test_positive_sample_meets_statistical_screen_but_not_promotion(self):
        result = assess_aggregation(aggregation(), bootstrap_replicates=1000)
        self.assertEqual(result["overall_evidence_status"], "EVIDENCE_THRESHOLD_MET")
        self.assertFalse(result["promotion_eligible"])
        self.assertFalse(result["historical_performance_validated"])

    def test_small_sample_is_insufficient(self):
        result = assess_aggregation(aggregation(cohort(n=12, transfers=10)), bootstrap_replicates=1000)
        self.assertEqual(result["provider_cohorts"][0]["evidence_status"], "INSUFFICIENT_EVIDENCE")

    def test_too_few_transfer_decisions_is_insufficient(self):
        result = assess_aggregation(aggregation(cohort(n=20, transfers=9)), bootstrap_replicates=1000)
        self.assertEqual(result["provider_cohorts"][0]["evidence_status"], "INSUFFICIENT_EVIDENCE")

    def test_interval_crossing_zero_is_inconclusive(self):
        c = cohort(n=20, transfers=20)
        c["events"] = [event(i + 1, 1.0 if i % 2 == 0 else -1.0) for i in range(20)]
        result = assess_cohort(c, "a" * 64, bootstrap_replicates=1000)
        self.assertEqual(result["evidence_status"], "INCONCLUSIVE")

    def test_material_effect_threshold_applied(self):
        result = assess_aggregation(aggregation(), material_effect_points=3.0, bootstrap_replicates=1000)
        self.assertEqual(result["overall_evidence_status"], "INCONCLUSIVE")

    def test_duplicate_gameweek_rejected(self):
        c = cohort()
        c["events"][1]["target_gameweek"] = 1
        with self.assertRaisesRegex(StatisticalGateError, "duplicate Gameweek"):
            assess_cohort(c, "a" * 64)

    def test_invalid_aggregate_cannot_be_promoted_or_relabelled(self):
        source = aggregation()
        source["promotion_eligible"] = True
        with self.assertRaisesRegex(StatisticalGateError, "non-promotion"):
            assess_aggregation(source)

    def test_provider_cohorts_remain_separate(self):
        source = aggregation()
        other = copy.deepcopy(cohort())
        other["provider_identity"]["variant"] = "fixture"
        source["provider_cohorts"].append(other)
        result = assess_aggregation(source, bootstrap_replicates=1000)
        self.assertEqual(len(result["provider_cohorts"]), 2)

    def test_bootstrap_is_reproducible(self):
        c = cohort()
        first = assess_cohort(c, "a" * 64, bootstrap_replicates=1000)
        second = assess_cohort(c, "a" * 64, bootstrap_replicates=1000)
        self.assertEqual(first["mean_delta_gameweek_bootstrap_95_ci"],
                         second["mean_delta_gameweek_bootstrap_95_ci"])

    def test_bootstrap_seed_changes_with_input_digest(self):
        c = cohort()
        first = assess_cohort(c, "a" * 64, bootstrap_replicates=1000)
        second = assess_cohort(c, "b" * 64, bootstrap_replicates=1000)
        self.assertNotEqual(first["mean_delta_gameweek_bootstrap_95_ci"]["seed_sha256"],
                            second["mean_delta_gameweek_bootstrap_95_ci"]["seed_sha256"])

    def test_hold_event_must_have_zero_delta(self):
        c = cohort()
        c["events"][-1]["net_points_delta_vs_hold"] = 1.0
        with self.assertRaisesRegex(StatisticalGateError, "HOLD decision must have zero"):
            assess_cohort(c, "a" * 64)

    def test_rejects_too_few_bootstrap_replicates(self):
        with self.assertRaisesRegex(StatisticalGateError, "replicates must be"):
            assess_aggregation(aggregation(), bootstrap_replicates=999)


if __name__ == "__main__":
    unittest.main()
