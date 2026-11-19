import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from verify_11footy_fpl_identity_crosswalk import build_verified_crosswalk
from validate_provider_identity_crosswalk import validate_rows


def candidate(**changes):
    row = {
        "season": "2026/27",
        "competition_id": "1",
        "competition_name": "Premier League",
        "source_release": "11footy-2026-11-10",
        "fpl_element_id": "42",
        "fpl_player_code": "12345",
        "fpl_team_id": "1",
        "fpl_player_name": "Example Player",
        "fpl_team_name": "Arsenal",
        "fpl_birth_date": "2000-03-02",
        "provider_player_id": "10790",
        "provider_team_id": "1",
        "provider_player_name": "Example Player",
        "provider_team_name": "Arsenal",
        "provider_birth_date": "2000-03-02",
        "match_method": "exact_name_team_birth_date",
        "confidence_level": "high",
        "verification_status": "pending",
        "evidence_source": "11footy player catalogue and official FPL bootstrap-static",
        "provider_release_url": "https://github.com/fm-devlab/11footy-dataset/releases/tag/11footy-2026-11-10",
        "fpl_source_url": "https://fantasy.premierleague.com/api/bootstrap-static/",
        "provider_source_sha256": "a" * 64,
        "fpl_bootstrap_sha256": "b" * 64,
        "generated_at_utc": "2026-11-19T00:00:00Z",
    }
    row.update(changes)
    return row


class Verify11footyCrosswalkTests(unittest.TestCase):
    def test_exact_unique_name_team_dob_is_promoted_and_passes_validator(self):
        rows, report = build_verified_crosswalk([candidate()], verified_at="2026-11-19T00:00:00Z")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["verified_crosswalk_rows"], 1)
        self.assertEqual(rows[0]["verification_status"], "verified")
        self.assertEqual(rows[0]["match_method"], "exact_name_team_birth_date")
        accepted, validation = validate_rows(rows, "11footy")
        self.assertEqual(validation["status"], "PASS")
        self.assertTrue(validation["join_ready"])
        self.assertEqual(len(accepted), 1)

    def test_missing_birth_date_stays_out(self):
        rows, report = build_verified_crosswalk([candidate(provider_birth_date="")])
        self.assertEqual(rows, [])
        self.assertEqual(report["status"], "NO_VERIFIED_MAPPINGS")
        self.assertEqual(report["excluded_rows_by_reason"]["birth_date_missing_or_invalid"], 1)

    def test_birth_date_conflict_stays_out(self):
        rows, report = build_verified_crosswalk([candidate(fpl_birth_date="2001-03-02")])
        self.assertEqual(rows, [])
        self.assertEqual(report["excluded_rows_by_reason"]["birth_date_conflict"], 1)

    def test_name_or_team_mismatch_stays_out(self):
        rows, report = build_verified_crosswalk([candidate(fpl_player_name="Example Other")])
        self.assertEqual(rows, [])
        self.assertEqual(report["excluded_rows_by_reason"]["full_name_not_exact"], 1)
        rows, report = build_verified_crosswalk([candidate(fpl_team_name="Chelsea")])
        self.assertEqual(rows, [])
        self.assertEqual(report["excluded_rows_by_reason"]["team_not_exact"], 1)

    def test_name_only_and_missing_dob_candidates_are_not_promoted(self):
        rows, report = build_verified_crosswalk([
            candidate(match_method="exact_name_and_team_birth_date_unavailable",
                      confidence_level="review_required", provider_birth_date=""),
        ])
        self.assertEqual(rows, [])
        self.assertEqual(report["excluded_rows_by_reason"]["not_exact_name_team_birth_date_method"], 1)


    def test_missing_provider_dob_can_be_verified_by_optas_numeric_fpl_code_and_team_bridge(self):
        opta = [{
            "season": "2026-27",
            "provider_player_id": "12345",
            "provider_player_name": "Example Player",
            "provider_team_id": "1",
            "provider_team_name": "Arsenal",
            "fpl_element_id": "42",
            "fpl_player_code": "12345",
            "fpl_player_name": "Example Player",
            "fpl_team_id": "1",
            "fpl_team_code": "1",
            "fpl_team_name": "Arsenal",
            "verification_status": "verified",
            "match_method": "provider_id_crosswalk",
            "evidence_url": "https://github.com/uasir/Opta-PulseLive/blob/abc/2026-2027/players.csv",
        }]
        opta_report = {"status": "PASS", "source_commit": "abc123", "source_sha256": "c" * 64}
        row = candidate(
            match_method="exact_name_team_birth_date_missing",
            confidence_level="review_required",
            provider_birth_date="",
        )
        rows, report = build_verified_crosswalk(
            [row], verified_at="2026-11-19T00:00:00Z",
            opta_crosswalk_rows=opta, opta_report=opta_report,
        )
        self.assertEqual(report["verified_dob_rows"], 0)
        self.assertEqual(report["verified_opta_bridge_rows"], 1)
        self.assertEqual(rows[0]["match_method"], "exact_name_team_opta_numeric_fpl_code_and_team")
        self.assertEqual(rows[0]["corroborating_provider_player_id"], "12345")
        accepted, validation = validate_rows(rows, "11footy")
        self.assertEqual(validation["status"], "PASS")
        self.assertEqual(len(accepted), 1)

    def test_opta_bridge_rejects_provider_fpl_name_or_team_mismatch(self):
        opta = [{
            "provider_player_id": "12345", "provider_player_name": "Other Player",
            "provider_team_id": "1", "provider_team_name": "Arsenal",
            "fpl_element_id": "42", "fpl_player_code": "12345",
            "fpl_player_name": "Example Player", "fpl_team_id": "1",
            "fpl_team_code": "1", "fpl_team_name": "Arsenal",
            "verification_status": "verified", "match_method": "provider_id_crosswalk",
            "evidence_url": "https://github.com/uasir/Opta-PulseLive/blob/abc/players.csv",
        }]
        opta_report = {"status": "PASS", "source_commit": "abc123", "source_sha256": "c" * 64}
        row = candidate(match_method="exact_name_team_birth_date_missing", confidence_level="review_required", provider_birth_date="")
        rows, report = build_verified_crosswalk([row], opta_crosswalk_rows=opta, opta_report=opta_report)
        self.assertEqual(rows, [])
        self.assertGreater(report["opta_bridge_exclusions_by_reason"].get("provider_full_name_disagreement", 0), 0)

    def test_opta_bridge_requires_validated_opta_report(self):
        row = candidate(match_method="exact_name_team", confidence_level="review_required", provider_birth_date="")
        with self.assertRaisesRegex(ValueError, "not validated"):
            build_verified_crosswalk([row], opta_crosswalk_rows=[], opta_report={"status": "REVIEW_REQUIRED", "source_sha256": "c" * 64})

    def test_provider_to_fpl_collisions_are_all_excluded(self):
        rows, report = build_verified_crosswalk([
            candidate(fpl_element_id="42"),
            candidate(fpl_element_id="43"),
        ])
        self.assertEqual(rows, [])
        self.assertEqual(report["excluded_rows_by_reason"]["one_to_one_collision_or_duplicate"], 2)

    def test_fpl_to_provider_collisions_are_all_excluded(self):
        rows, report = build_verified_crosswalk([
            candidate(provider_player_id="10790"),
            candidate(provider_player_id="10791"),
        ])
        self.assertEqual(rows, [])
        self.assertEqual(report["excluded_rows_by_reason"]["one_to_one_collision_or_duplicate"], 2)


if __name__ == "__main__":
    unittest.main()
