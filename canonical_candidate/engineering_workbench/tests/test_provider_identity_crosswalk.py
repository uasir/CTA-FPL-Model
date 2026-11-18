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
    def test_empty_template_is_not_ready(self):
        accepted, report = MODULE.validate_rows([], "wyscout")
        self.assertEqual(report["status"], "EMPTY_NOT_READY")
        self.assertFalse(report["join_ready"])
        self.assertEqual(accepted, [])

    def test_evidenced_verified_row_passes(self):
        accepted, report = MODULE.validate_rows([row()], "opta_pulselive")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(len(accepted), 1)

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
