from __future__ import annotations

import copy
import unittest

from aggregate_m3_multigameweek_evaluations import (
    AggregationError,
    aggregate_evaluation_results,
)


def event(gw: int, delta: float, action: str = "TRANSFER", digest: str | None = None) -> dict:
    hold = 50.0
    hits = 4.0 if action == "TRANSFER" else 0.0
    return {
        "evidence_class": "REAL_CANDIDATE",
        "evaluation_status": "REAL_DECISION_BACKTEST_EVENT_SCORED_NOT_PROMOTION_EVIDENCE",
        "historical_performance_validated": False,
        "manager_team_id": 421025,
        "target_gameweek": gw,
        "provider_identity": {"name": "FPL Cat", "product": "FPL points", "variant": "player-GW"},
        "recommended_action": action,
        "recommended": {"net_points": hold + delta, "transfer_hit_points": hits},
        "hold": {"net_points": hold, "transfer_hit_points": 0.0},
        "net_points_delta_vs_hold": delta,
        "evaluation_input_sha256": digest or f"{gw:064x}",
        "frozen_decision_sha256": f"{gw + 100:064x}",
        "software_commit": "a" * 40,
        "source_provenance": [{"source_type": "provider", "raw_sha256": "b" * 64}],
    }


class MultiGameweekAggregationTests(unittest.TestCase):
    def test_aggregates_net_value_and_hit_costs(self) -> None:
        result = aggregate_evaluation_results([
            event(11, 3.0, "TRANSFER"),
            event(12, -1.0, "TRANSFER"),
            event(13, 0.0, "HOLD"),
        ])
        cohort = result["provider_cohorts"][0]
        self.assertEqual(cohort["event_count"], 3)
        self.assertEqual(cohort["cumulative_net_points_delta_vs_hold"], 2.0)
        self.assertEqual(cohort["total_transfer_hit_points"], 8.0)
        self.assertEqual(cohort["positive_delta_events"], 1)
        self.assertEqual(cohort["negative_delta_events"], 1)
        self.assertEqual(cohort["neutral_delta_events"], 1)
        self.assertFalse(result["promotion_eligible"])

    def test_rejects_synthetic_or_unadmitted_event(self) -> None:
        row = event(11, 1.0)
        row["evidence_class"] = "SYNTHETIC_TEST"
        with self.assertRaisesRegex(AggregationError, "independently admitted"):
            aggregate_evaluation_results([row])

    def test_rejects_duplicate_gameweek_provider(self) -> None:
        with self.assertRaisesRegex(AggregationError, "duplicate manager/Gameweek/provider"):
            aggregate_evaluation_results([event(11, 1.0), event(11, 2.0, digest="c" * 64)])

    def test_rejects_duplicate_input_hash(self) -> None:
        with self.assertRaisesRegex(AggregationError, "duplicate evaluation input"):
            aggregate_evaluation_results([event(11, 1.0, digest="d" * 64),
                                          event(12, 2.0, digest="d" * 64)])

    def test_rejects_delta_inconsistent_with_net_scores(self) -> None:
        row = event(11, 2.0)
        row["net_points_delta_vs_hold"] = 3.0
        with self.assertRaisesRegex(AggregationError, "does not equal"):
            aggregate_evaluation_results([row])

    def test_keeps_provider_variants_in_separate_cohorts(self) -> None:
        first = event(11, 1.0)
        second = event(12, 2.0)
        second["provider_identity"]["variant"] = "alternate"
        result = aggregate_evaluation_results([first, second])
        self.assertEqual(len(result["provider_cohorts"]), 2)

    def test_rejects_mixed_managers(self) -> None:
        second = event(12, 2.0)
        second["manager_team_id"] = 123
        with self.assertRaisesRegex(AggregationError, "only one manager"):
            aggregate_evaluation_results([event(11, 1.0), second])

    def test_rejects_missing_provenance(self) -> None:
        row = event(11, 1.0)
        row["source_provenance"] = []
        with self.assertRaisesRegex(AggregationError, "source_provenance"):
            aggregate_evaluation_results([row])


if __name__ == "__main__":
    unittest.main()
