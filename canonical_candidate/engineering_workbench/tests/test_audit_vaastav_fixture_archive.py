from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_vaastav_fixture_archive import audit_archive


TEAMS = [
    {"id": "1", "name": "Arsenal"},
    {"id": "2", "name": "Aston Villa"},
]
FIXTURES = [{
    "id": "10", "event": "1", "finished": "True", "team_h": "1",
    "team_a": "2", "kickoff_time": "2026-08-22T14:00:00Z",
}]
ROWS = [
    {"fixture": "10", "round": "1", "element": "101", "team": "Arsenal",
     "opponent_team": "2", "was_home": "True", "minutes": "90",
     "kickoff_time": "2026-08-22T14:00:00Z"},
    {"fixture": "10", "round": "1", "element": "202", "team": "Aston Villa",
     "opponent_team": "1", "was_home": "False", "minutes": "0",
     "kickoff_time": "2026-08-22T14:00:00Z"},
]


class FixtureArchiveAuditTests(unittest.TestCase):
    def test_valid_fixture_has_both_sides_and_reports_zero_minutes(self):
        report = audit_archive(ROWS, FIXTURES, TEAMS, "2026-27")
        self.assertEqual(report["status"], "PASS_FIXTURE_ARCHIVE_AUDIT")
        self.assertEqual(report["fixture_summaries"][0]["zero_minute_rows"], 1)

    def test_finished_fixture_without_player_rows_fails(self):
        # A non-empty archive from another fixture keeps the input contract valid.
        other = dict(FIXTURES[0], id="11")
        row = dict(ROWS[0], fixture="11", team="Arsenal", opponent_team="2")
        report = audit_archive([row], FIXTURES + [other], TEAMS, "2026-27")
        self.assertEqual(report["status"], "FAIL_FIXTURE_ARCHIVE_AUDIT")
        self.assertIn("10", report["finished_fixtures_missing_player_rows"])

    def test_duplicate_player_fixture_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "duplicate fixture/player"):
            audit_archive(ROWS + [ROWS[0]], FIXTURES, TEAMS, "2026-27")

    def test_team_side_mismatch_is_reported(self):
        rows = [dict(r) for r in ROWS]
        rows[0]["opponent_team"] = "1"
        report = audit_archive(rows, FIXTURES, TEAMS, "2026-27")
        self.assertEqual(report["status"], "FAIL_FIXTURE_ARCHIVE_AUDIT")
        self.assertTrue(report["fixture_metadata_errors"])


if __name__ == "__main__":
    unittest.main()
