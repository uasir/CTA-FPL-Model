from __future__ import annotations

import unittest

from m4_covar_field_portfolio_adapter import (
    CovarFieldPortfolioError,
    adapt_field_portfolios_for_scenario,
    anonymize_manager_pick_rows,
    canonical_artifact_sha256,
    verify_field_portfolio_artifact,
)


DEADLINE = "2026-11-20T22:00:00Z"
CAPTURED = "2026-11-20T21:00:00Z"
AS_OF = "2026-11-20T21:30:00Z"


def pick_rows():
    rows = []
    managers = [
        (900001, 1, list(range(1, 16)), 1, "3xc"),
        (900002, 51, list(range(16, 31)), 20, ""),
        (900003, 101, list(range(31, 46)), 31, ""),
    ]
    for entry, rank, players, captain, chip in managers:
        for position, player in enumerate(players, start=1):
            rows.append({
                "gameweek": 12,
                "entry_id": entry,
                "rank_before_deadline": rank,
                "sample_weight": 100 / 3,
                "fpl_element_id": player,
                "position": position,
                "is_captain": player == captain,
                "is_vice_captain": position == 2,
                "active_chip": chip,
            })
    return rows


def artifact():
    return anonymize_manager_pick_rows(
        pick_rows(),
        gameweek=12,
        deadline_utc=DEADLINE,
        captured_at_utc=CAPTURED,
        evidence_role="PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE",
        cohort="overall top 150",
        rank_limit=150,
    )


class TestCovarFieldPortfolioAdapter(unittest.TestCase):
    def test_anonymizes_manager_ids_and_preserves_weighted_15_player_portfolios(self):
        result = artifact()
        self.assertEqual(result["metadata"]["manager_count"], 3)
        self.assertFalse(result["metadata"]["manager_identifiers_retained"])
        self.assertEqual(len(result["portfolios"]), 3)
        self.assertAlmostEqual(sum(row["field_weight"] for row in result["portfolios"]), 1.0)
        self.assertEqual(len(result["portfolios"][0]["player_ids"]), 15)
        self.assertNotIn("900001", str(result))
        self.assertEqual(result["portfolios"][0]["captain_multiplier"], 3)

    def test_projects_to_fixture_players_and_retains_zero_exposure_managers(self):
        result = adapt_field_portfolios_for_scenario(
            artifact(), ["1", "2", "16"], expected_gameweek=12,
            deadline_utc=DEADLINE, as_of_utc=AS_OF,
        )
        portfolios = result["portfolios"]
        self.assertEqual(portfolios[0]["player_ids"], ["1", "2"])
        self.assertEqual(portfolios[0]["captain_id"], "1")
        self.assertEqual(portfolios[0]["captain_multiplier"], 3)
        self.assertEqual(portfolios[1]["player_ids"], ["16"])
        self.assertIsNone(portfolios[1]["captain_id"])
        self.assertEqual(portfolios[1]["captain_multiplier"], 1)
        self.assertEqual(portfolios[2]["player_ids"], [])
        self.assertEqual(result["metadata"]["selected_manager_count"], 3)
        self.assertAlmostEqual(result["metadata"]["manager_projection_coverage"], 2 / 3)

    def test_rank_stratum_filter_renormalizes_original_sample_weights(self):
        result = adapt_field_portfolios_for_scenario(
            artifact(), ["16", "17", "31"], expected_gameweek=12,
            deadline_utc=DEADLINE, as_of_utc=AS_OF, rank_strata=[2, 3],
        )
        self.assertEqual(result["metadata"]["rank_strata"], [2, 3])
        self.assertEqual(len(result["portfolios"]), 2)
        self.assertAlmostEqual(sum(row["field_weight"] for row in result["portfolios"]), 1.0)
        self.assertAlmostEqual(result["portfolios"][0]["field_weight"], 0.5)

    def test_rejects_post_deadline_evidence(self):
        with self.assertRaisesRegex(CovarFieldPortfolioError, "only pre-deadline"):
            anonymize_manager_pick_rows(
                pick_rows(), gameweek=12, deadline_utc=DEADLINE,
                captured_at_utc="2026-11-20T22:01:00Z",
                evidence_role="POST_DEADLINE_LOCKED_FIELD",
                cohort="overall top 150", rank_limit=150,
            )

    def test_rejects_capture_after_decision_as_of(self):
        with self.assertRaisesRegex(CovarFieldPortfolioError, "must precede decision as_of"):
            adapt_field_portfolios_for_scenario(
                artifact(), ["1"], expected_gameweek=12,
                deadline_utc=DEADLINE, as_of_utc="2026-11-20T20:59:00Z",
            )

    def test_rejects_gameweek_or_deadline_mismatch(self):
        with self.assertRaisesRegex(CovarFieldPortfolioError, "Gameweek mismatch"):
            adapt_field_portfolios_for_scenario(
                artifact(), ["1"], expected_gameweek=13,
                deadline_utc=DEADLINE, as_of_utc=AS_OF,
            )
        with self.assertRaisesRegex(CovarFieldPortfolioError, "deadline mismatch"):
            adapt_field_portfolios_for_scenario(
                artifact(), ["1"], expected_gameweek=12,
                deadline_utc="2026-11-20T23:00:00Z", as_of_utc=AS_OF,
            )

    def test_binds_artifact_to_capture_report_hash_and_temporal_identity(self):
        field_artifact = artifact()
        report = {
            "status": "CAPTURED_PRE_DEADLINE_CURRENT_PICKS",
            "evidence_role": "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE",
            "gameweek": 12,
            "deadline_time_utc": DEADLINE,
            "picks_captured_at_utc": CAPTURED,
            "manager_portfolio_artifact": {
                "sha256": canonical_artifact_sha256(field_artifact),
                "manager_count": 3,
                "manager_identifiers_retained": False,
            },
        }
        result = verify_field_portfolio_artifact(field_artifact, report)
        self.assertEqual(result["status"], "PASS_ANONYMIZED_FIELD_PORTFOLIO_PROVENANCE")
        self.assertFalse(result["manager_identifiers_retained"])
        field_artifact["portfolios"][0]["player_ids"][0] = "999"
        with self.assertRaisesRegex(CovarFieldPortfolioError, "SHA-256"):
            verify_field_portfolio_artifact(field_artifact, report)

    def test_rejects_malformed_manager_squad(self):
        rows = pick_rows()
        rows.pop()
        with self.assertRaisesRegex(CovarFieldPortfolioError, "exactly 15 picks"):
            anonymize_manager_pick_rows(
                rows, gameweek=12, deadline_utc=DEADLINE,
                captured_at_utc=CAPTURED,
                evidence_role="PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE",
                cohort="overall top 150", rank_limit=150,
            )


if __name__ == "__main__":
    unittest.main()
