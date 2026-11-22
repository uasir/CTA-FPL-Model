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
        report = audit_archive([], FIXTURES, TEAMS, "2026-27")
        self.assertEqual(report["status"], "FAIL_FIXTURE_ARCHIVE_AUDIT")
        self.assertEqual(report["finished_fixtures_missing_player_rows"], ["10"])

    def test_exact_duplicate_player_fixture_row_is_collapsed_and_reported(self):
        report = audit_archive(ROWS + [ROWS[0]], FIXTURES, TEAMS, "2026-27")
        self.assertEqual(report["status"], "PASS_FIXTURE_ARCHIVE_AUDIT")
        self.assertEqual(report["exact_duplicate_player_rows_collapsed"], 1)
        self.assertEqual(report["unique_fixture_player_keys"], 2)

    def test_conflicting_duplicate_player_fixture_fails_closed(self):
        duplicate = dict(ROWS[0])
        duplicate["minutes"] = "45"
        report = audit_archive(ROWS + [duplicate], FIXTURES, TEAMS, "2026-27")
        self.assertEqual(report["status"], "FAIL_FIXTURE_ARCHIVE_AUDIT")
        self.assertTrue(any("conflicting duplicate fixture/player key" in item
                            for item in report["fixture_metadata_errors"]))

    def test_revised_fixture_schedule_kickoff_is_a_warning_not_archive_failure(self):
        rows = [dict(row) for row in ROWS]
        for row in rows:
            row["kickoff_time"] = "2022-02-26T15:30:00Z"
        report = audit_archive(rows, FIXTURES, TEAMS, "2021-22")
        self.assertEqual(report["status"], "PASS_FIXTURE_ARCHIVE_AUDIT")
        self.assertEqual(len(report["fixture_kickoff_schedule_differences"]), 1)
        self.assertEqual(
            report["fixture_kickoff_schedule_differences"][0]["player_archive_kickoff_utc"],
            "2022-02-26T15:30:00+00:00",
        )

    def test_inconsistent_player_kickoffs_for_same_fixture_still_fail(self):
        rows = [dict(row) for row in ROWS]
        rows[1]["kickoff_time"] = "2026-08-22T15:00:00Z"
        report = audit_archive(rows, FIXTURES, TEAMS, "2026-27")
        self.assertEqual(report["status"], "FAIL_FIXTURE_ARCHIVE_AUDIT")
        self.assertTrue(any("inconsistent kickoff values" in item
                            for item in report["fixture_metadata_errors"]))

    def test_team_side_mismatch_is_reported(self):
        rows = [dict(r) for r in ROWS]
        rows[0]["opponent_team"] = "1"
        report = audit_archive(rows, FIXTURES, TEAMS, "2026-27")
        self.assertEqual(report["status"], "FAIL_FIXTURE_ARCHIVE_AUDIT")
        self.assertTrue(report["fixture_metadata_errors"])


if __name__ == "__main__":
    unittest.main()
