from __future__ import annotations

import unittest

from m4_covar_realized_joint_state_resolver import (
    RealizedJointStateResolverError,
    canonical_json_sha256,
    resolve_realized_joint_state,
)


def _actual():
    return [
        {"season": "2026-27", "gameweek": 1, "fpl_element_id": 101, "minutes": 90, "total_points": 8, "played_any_fixture": True},
        {"season": "2026-27", "gameweek": 1, "fpl_element_id": 202, "minutes": 0, "total_points": 0, "played_any_fixture": False},
    ]


def _catalogue():
    return [
        {
            "scenario_id": "state-upside",
            "player_outcomes": [
                {"player_id": "101", "minutes": 90, "played": True, "fpl_points": 8},
                {"player_id": "202", "minutes": 0, "played": False, "fpl_points": 0},
            ],
        },
        {
            "scenario_id": "state-downside",
            "player_outcomes": [
                {"player_id": "101", "minutes": 60, "played": True, "fpl_points": 2},
                {"player_id": "202", "minutes": 90, "played": True, "fpl_points": 6},
            ],
        },
    ]


def _audit():
    return {
        "season": "2026-27",
        "event_id": 1,
        "status": "PASS_EXACT_MATCH",
        "finality_reconciled": True,
        "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_FINAL_SCORING_AUDIT",
    }


class TestRealizedJointStateResolver(unittest.TestCase):
    def _resolve(self, actual=None, catalogue=None, audit=None):
        return resolve_realized_joint_state(
            realized_player_gameweek_rows=actual or _actual(),
            joint_state_catalogue=catalogue or _catalogue(),
            season="2026-27",
            gameweek_id="1",
            realized_source_bytes=b"official-realized-player-gameweek-source",
            finality_audit=audit or _audit(),
        )

    def test_resolves_exact_complete_observed_state(self):
        result = self._resolve()
        self.assertEqual(result["mapping_status"], "PASS_EXACT_OBSERVED_STATE_RESOLUTION")
        self.assertEqual(result["observed_state_id"], "state-upside")
        self.assertEqual(result["mapped_player_count"], 2)
        self.assertEqual(result["missing_player_count"], 0)
        self.assertEqual(result["unexpected_player_count"], 0)
        self.assertFalse(result["mapping_inferred_from_marginals"])
        self.assertEqual(len(result["state_catalogue_sha256"]), 64)
        self.assertEqual(len(result["player_universe_sha256"]), 64)
        self.assertEqual(len(result["mapping_source_sha256"]), 64)
        self.assertFalse(result["production_eligible"])
        self.assertEqual(result["decision_weight"], 0.0)

    def test_catalogue_and_player_hashes_are_deterministic(self):
        first = self._resolve()
        second = self._resolve(actual=list(reversed(_actual())), catalogue=list(reversed(_catalogue())))
        self.assertEqual(first["state_catalogue_sha256"], second["state_catalogue_sha256"])
        self.assertEqual(first["player_universe_sha256"], second["player_universe_sha256"])
        self.assertEqual(first["observed_state_id"], second["observed_state_id"])
        self.assertEqual(canonical_json_sha256(["101", "202"]), first["player_universe_sha256"])

    def test_reports_no_match_without_nearest_scenario_substitution(self):
        actual = _actual()
        actual[0]["total_points"] = 7
        result = self._resolve(actual=actual)
        self.assertEqual(result["mapping_status"], "FAIL_NO_EXACT_STATE_MATCH")
        self.assertIsNone(result["observed_state_id"])
        self.assertEqual(result["matching_state_ids"], [])
        self.assertFalse(result["mapping_inferred_from_marginals"])

    def test_rejects_ambiguous_duplicate_outcome_vectors(self):
        catalogue = _catalogue()
        catalogue.append({"scenario_id": "duplicate-state", "player_outcomes": _catalogue()[0]["player_outcomes"]})
        result = self._resolve(catalogue=catalogue)
        self.assertEqual(result["mapping_status"], "FAIL_AMBIGUOUS_STATE_MATCH")
        self.assertIsNone(result["observed_state_id"])

    def test_rejects_incomplete_scenario_player_universe(self):
        catalogue = _catalogue()
        catalogue[0]["player_outcomes"].pop()
        with self.assertRaisesRegex(RealizedJointStateResolverError, "player universe"):
            self._resolve(catalogue=catalogue)

    def test_rejects_duplicate_realized_player_rows(self):
        actual = _actual()
        actual.append(dict(actual[0]))
        with self.assertRaisesRegex(RealizedJointStateResolverError, "duplicate player outcome"):
            self._resolve(actual=actual)

    def test_rejects_cross_gameweek_rows(self):
        actual = _actual()
        actual[1]["gameweek"] = 2
        with self.assertRaisesRegex(RealizedJointStateResolverError, "match requested"):
            self._resolve(actual=actual)

    def test_rejects_failed_or_wrong_finality_audit(self):
        audit = _audit()
        audit["status"] = "FAIL_MISMATCH"
        with self.assertRaisesRegex(RealizedJointStateResolverError, "finality audit"):
            self._resolve(audit=audit)

    def test_rejects_non_boolean_played_flag(self):
        actual = _actual()
        actual[0]["played_any_fixture"] = 1
        with self.assertRaisesRegex(RealizedJointStateResolverError, "must be boolean"):
            self._resolve(actual=actual)

    def test_rejects_missing_or_nonfinite_points(self):
        actual = _actual()
        actual[0]["total_points"] = None
        with self.assertRaisesRegex(RealizedJointStateResolverError, "finite numeric"):
            self._resolve(actual=actual)
        actual = _actual()
        actual[0]["minutes"] = float("nan")
        with self.assertRaisesRegex(RealizedJointStateResolverError, "finite numeric"):
            self._resolve(actual=actual)


if __name__ == "__main__":
    unittest.main()
