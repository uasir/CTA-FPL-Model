from __future__ import annotations

import unittest

from m4_covar_field_portfolio_adapter import (
    CovarFieldPortfolioError,
    adapt_field_portfolios_for_scenario,
    strip_manager_identifiers_from_manager_picks,
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


def positions_for(rows):
    result = {}
    for row in rows:
        slot = (int(row["position"]) - 1) % 15 + 1
        result[str(row["fpl_element_id"])] = (
            "GK" if slot in (1, 12) else
            "DEF" if 2 <= slot <= 5 else
            "MID" if 6 <= slot <= 10 else "FWD"
        )
    return result


def artifact(rows=None):
    rows = rows or pick_rows()
    return strip_manager_identifiers_from_manager_picks(
        rows,
        gameweek=12,
        deadline_utc=DEADLINE,
        captured_at_utc=CAPTURED,
        evidence_role="PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE",
        cohort="overall top 150",
        rank_limit=150,
        player_positions_by_id=positions_for(rows),
    )


class TestCovarFieldPortfolioAdapter(unittest.TestCase):
    def test_strips_manager_ids_and_preserves_weighted_15_player_portfolios(self):
        result = artifact()
        self.assertEqual(result["metadata"]["manager_count"], 3)
        self.assertFalse(result["metadata"]["manager_entry_ids_retained"])
        self.assertIn("may remain identifiable", result["metadata"]["privacy_note"])
        self.assertEqual(len(result["portfolios"]), 3)
        self.assertAlmostEqual(sum(row["field_weight"] for row in result["portfolios"]), 1.0)
        self.assertEqual(len(result["portfolios"][0]["player_ids"]), 15)
        self.assertNotIn("900001", str(result))
        self.assertEqual(result["portfolios"][0]["captain_multiplier"], 3)
        first = result["portfolios"][0]
        self.assertEqual(len(first["starting_player_ids"]), 11)
        self.assertEqual(first["starting_goalkeeper_id"], "1")
        self.assertEqual(first["reserve_goalkeeper_id"], "12")
        self.assertEqual(first["bench_order"], ["13", "14", "15"])
        self.assertEqual(first["vice_captain_id"], "2")
        self.assertEqual(first["player_positions"]["1"], "GK")
        self.assertEqual(result["schema_version"], "1.1.0")

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
            strip_manager_identifiers_from_manager_picks(
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
            "picks_lock_verified": False,
            "provisional_picks": True,
            "gameweek": 12,
            "deadline_time_utc": DEADLINE,
            "picks_captured_at_utc": CAPTURED,
            "manager_portfolio_artifact": {
                "sha256": canonical_artifact_sha256(field_artifact),
                "manager_count": 3,
                "manager_entry_ids_retained": False,
            },
        }
        result = verify_field_portfolio_artifact(field_artifact, report)
        self.assertEqual(result["status"], "PASS_MANAGER_ID_STRIPPED_FIELD_PORTFOLIO_PROVENANCE")
        self.assertFalse(result["manager_entry_ids_retained"])
        field_artifact["portfolios"][0]["player_ids"][0] = "999"
        with self.assertRaisesRegex(CovarFieldPortfolioError, "SHA-256"):
            verify_field_portfolio_artifact(field_artifact, report)

    def test_rejects_missing_vice_captain(self):
        rows = pick_rows()
        for row in rows:
            row["is_vice_captain"] = False
        with self.assertRaisesRegex(CovarFieldPortfolioError, "exactly one starting vice-captain"):
            artifact(rows)

    def test_rejects_illegal_starting_formation(self):
        rows = pick_rows()
        positions = positions_for(rows)
        for row in rows:
            if row["position"] == 11:
                positions[str(row["fpl_element_id"])] = "DEF"
        with self.assertRaisesRegex(CovarFieldPortfolioError, "legal FPL formation"):
            strip_manager_identifiers_from_manager_picks(
                rows, gameweek=12, deadline_utc=DEADLINE, captured_at_utc=CAPTURED,
                evidence_role="PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE",
                cohort="overall top 150", rank_limit=150, player_positions_by_id=positions,
            )

    def test_rejects_missing_bootstrap_player_position(self):
        positions = positions_for(pick_rows())
        positions.pop("1")
        with self.assertRaisesRegex(CovarFieldPortfolioError, "bootstrap player positions missing"):
            strip_manager_identifiers_from_manager_picks(
                pick_rows(), gameweek=12, deadline_utc=DEADLINE, captured_at_utc=CAPTURED,
                evidence_role="PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE",
                cohort="overall top 150", rank_limit=150, player_positions_by_id=positions,
            )

    def test_rejects_malformed_manager_squad(self):
        rows = pick_rows()
        rows.pop()
        with self.assertRaisesRegex(CovarFieldPortfolioError, "exactly 15 picks"):
            strip_manager_identifiers_from_manager_picks(
                rows, gameweek=12, deadline_utc=DEADLINE,
                captured_at_utc=CAPTURED,
                evidence_role="PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE",
                cohort="overall top 150", rank_limit=150,
                player_positions_by_id=positions_for(rows),
            )


if __name__ == "__main__":
    unittest.main()
