import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_provider_identity_crosswalk.py"
SPEC = importlib.util.spec_from_file_location("provider_crosswalk", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

def row(**changes):
    value = {field: "x" for field in MODULE.FIELDS}
    value.update({
        "season": "2026-27", "competition_id": "PL", "provider_player_id": "p-1",
        "fpl_element_id": "42", "verification_status": "verified",
        "match_method": "provider_id_crosswalk", "evidence_url": "https://example.org/source",
    })
    value.update(changes)
    return value

class ProviderCrosswalkTests(unittest.TestCase):
    def test_complete_header_schema_is_accepted(self):
        self.assertEqual(MODULE.validate_headers(MODULE.FIELDS, "wyscout"), [])

    def test_missing_header_is_a_schema_error_not_an_empty_template(self):
        errors = MODULE.validate_headers(MODULE.FIELDS[:-1], "wyscout")
        self.assertTrue(any("missing required crosswalk columns" in item for item in errors))

    def test_duplicate_header_is_rejected(self):
        errors = MODULE.validate_headers(MODULE.FIELDS + ["season"], "opta_pulselive")
        self.assertTrue(any("duplicate CSV columns" in item for item in errors))

    def test_absent_header_row_is_rejected(self):
        self.assertEqual(MODULE.validate_headers(None, "11footy"), ["CSV header row is missing"])

    def test_empty_template_is_not_ready(self):
        accepted, report = MODULE.validate_rows([], "wyscout")
        self.assertEqual(report["status"], "EMPTY_NOT_READY")
        self.assertFalse(report["join_ready"])
        self.assertEqual(accepted, [])

    def test_evidenced_verified_row_passes(self):
        accepted, report = MODULE.validate_rows([row()], "opta_pulselive")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(len(accepted), 1)

    def test_opta_provider_team_id_must_match_fpl_team_code(self):
        accepted, report = MODULE.validate_rows(
            [row(provider_team_id="3", fpl_team_code="1")], "opta_pulselive"
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(accepted, [])

    def test_opta_crosswalk_requires_fpl_team_code(self):
        accepted, report = MODULE.validate_rows(
            [row(fpl_team_code="")], "opta_pulselive"
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(accepted, [])

    def test_11footy_verified_crosswalk_uses_season_scoped_provider_and_fpl_ids(self):
        accepted, report = MODULE.validate_rows(
            [row(
                season="2026/27", competition_id="1", provider_player_id="10790",
                provider_player_name="Illan Meslier", fpl_element_id="3",
                fpl_player_code="12345", fpl_player_name="Illan Meslier",
                provider_team_id="1", provider_team_name="Arsenal",
                fpl_team_id="1", fpl_team_name="Arsenal",
                verification_status="verified", match_method="manual_source_verified",
                evidence_source="Official FPL, 11footy and independent club profile",
                evidence_url="https://example.org/player-profile",
                provider_birth_date="2000-03-02", fpl_birth_date="2000-03-02",
                source_release="11footy-2026-11-10",
                confidence_level="very_high",
            )],
            "11footy",
        )
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["join_ready"])
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["provider_source_sha256"], "x")

    def test_11footy_verified_mapping_requires_numeric_ids_and_matching_team(self):
        accepted, report = MODULE.validate_rows(
            [row(
                season="2026/27", competition_id="1", provider_player_id="10790",
                fpl_element_id="3", provider_team_id="12", fpl_team_id="1",
                provider_team_name="Liverpool", fpl_team_name="Arsenal",
                verification_status="verified", match_method="manual_source_verified",
            )],
            "11footy",
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(accepted, [])
        self.assertEqual(
            report["errors"][0]["error"],
            "11footy_provider_and_fpl_team_names_do_not_match",
        )

    def test_11footy_pending_candidates_are_excluded_from_join(self):
        accepted, report = MODULE.validate_rows(
            [row(verification_status="pending")], "11footy"
        )
        self.assertEqual(report["status"], "NO_VERIFIED_MAPPINGS")
        self.assertFalse(report["join_ready"])
        self.assertEqual(accepted, [])

    def test_name_only_method_is_not_accepted(self):
        accepted, report = MODULE.validate_rows([row(match_method="fuzzy_name")], "wyscout")
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(accepted, [])

    def test_missing_team_or_evidence_blocks(self):
        accepted, report = MODULE.validate_rows([row(provider_team_id="")], "wyscout")
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(accepted, [])

    def test_one_provider_id_cannot_map_to_two_fpl_elements(self):
        accepted, report = MODULE.validate_rows([row(), row(fpl_element_id="43")], "wyscout")
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(accepted, [])

    def test_one_fpl_element_cannot_map_to_two_provider_ids(self):
        accepted, report = MODULE.validate_rows([row(), row(provider_player_id="p-2")], "wyscout")
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(accepted, [])

    def test_pending_candidates_do_not_become_verified(self):
        accepted, report = MODULE.validate_rows([row(verification_status="pending")], "wyscout")
        self.assertEqual(report["status"], "NO_VERIFIED_MAPPINGS")
        self.assertEqual(accepted, [])
        self.assertEqual(report["non_verified_rows_excluded"], 1)

if __name__ == "__main__":
    unittest.main()
