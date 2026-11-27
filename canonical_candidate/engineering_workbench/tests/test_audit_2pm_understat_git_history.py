from __future__ import annotations

import unittest
from unittest.mock import patch

from audit_2pm_understat_git_history import _get_text, _row_key, audit_file


class UnderstatGitHistoryTests(unittest.TestCase):
    def test_player_row_key_uses_mapped_understat_id(self):
        self.assertEqual(
            _row_key({"date": "2024-01-01", "id": 1234}, "player", 987),
            "987|2024-01-01",
        )


    def test_row_history_tracks_removal_reappearance_and_value_revision(self):
        # GitHub's commits API returns newest first; audit_file reverses this.
        commits = [
            {"sha": "c", "commit": {"committer": {"date": "2024-01-03T00:00:00Z"}}},
            {"sha": "b", "commit": {"committer": {"date": "2024-01-02T00:00:00Z"}}},
            {"sha": "a", "commit": {"committer": {"date": "2024-01-01T00:00:00Z"}}},
        ]
        payloads = {
            "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/a/data/player_987.csv":
                b"date,season,xG\n2024-01-01,2023,0.2\n",
            "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/b/data/player_987.csv":
                b"date,season,xG\n",
            "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/c/data/player_987.csv":
                b"date,season,xG\n2024-01-01,2023,0.3\n",
        }
        with patch("audit_2pm_understat_git_history.list_path_commits", return_value=commits):
            with patch("audit_2pm_understat_git_history._get_text",
                       side_effect=lambda session, url: payloads[url]):
                result = audit_file(
                    object(), "vaastav/Fantasy-Premier-League", "c",
                    "data/player_987.csv", "player", 10, 987,
                )
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["commit_rows"]), 3)
        row = result["row_history"]["987|2024-01-01"]
        self.assertEqual(row["missing_revision_count"], 1)
        self.assertEqual(row["reappearance_count"], 1)
        self.assertEqual(row["value_revision_count"], 1)
        self.assertTrue(row["present_in_latest_revision"])
        self.assertEqual(row["first_seen_commit"], "a")
        self.assertEqual(row["latest_commit"], "c")
        self.assertEqual(row["last_seen_commit"], "c")
        self.assertIn('"xG":"0.2"', row["first_value_signature"])
        self.assertIn('"xG":"0.3"', row["latest_value_signature"])


    def test_raw_content_request_never_receives_github_api_token(self):
        class Response:
            content = b"ok"
            def raise_for_status(self):
                return None

        class Session:
            kwargs = None
            def get(self, url, **kwargs):
                self.kwargs = kwargs
                return Response()

        session = Session()
        with patch.dict("os.environ", {"GITHUB_TOKEN": "test-secret"}):
            self.assertEqual(_get_text(session, "https://raw.githubusercontent.com/o/r/p"), b"ok")
        self.assertNotIn("Authorization", session.kwargs["headers"])

    def test_duplicate_revision_is_rejected_without_mutating_row_history(self):
        commits = [
            {"sha": "b", "commit": {"committer": {"date": "2024-01-02T00:00:00Z"}}},
            {"sha": "a", "commit": {"committer": {"date": "2024-01-01T00:00:00Z"}}},
        ]
        nl = bytes([10])
        payloads = {
            "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/a/data/player_987.csv":
                b"date,season,xG" + nl + b"2024-01-01,2023,0.2" + nl,
            "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/b/data/player_987.csv":
                b"date,season,xG" + nl + b"2024-01-01,2023,0.3" + nl
                + b"2024-01-01,2023,0.4" + nl,
        }
        with patch("audit_2pm_understat_git_history.list_path_commits", return_value=commits):
            with patch("audit_2pm_understat_git_history._get_text",
                       side_effect=lambda session, url: payloads[url]):
                result = audit_file(
                    object(), "vaastav/Fantasy-Premier-League", "b",
                    "data/player_987.csv", "player", 10, 987,
                )
        self.assertEqual(len(result["commit_rows"]), 1)
        self.assertEqual(len(result["errors"]), 1)
        row = result["row_history"]["987|2024-01-01"]
        self.assertEqual(row["first_seen_commit"], "a")
        self.assertEqual(row["latest_commit"], "a")
        self.assertEqual(row["value_revision_count"], 0)
        self.assertEqual(row["last_seen_commit"], "a")

    def test_team_row_key_matches_pinned_dastan_team_file_contract(self):
        source_path = "data/2024-25/understat/understat_Arsenal.csv"
        self.assertEqual(
            _row_key({"date": "2024-08-17 14:00:00", "h_a": "h",
                      "xG": 1.6, "xGA": 0.5}, "team", source_path=source_path),
            "2024-25|Arsenal|2024-08-17 14:00:00|h",
        )
        # The same kickoff date in another team's file remains a different row.
        self.assertNotEqual(
            _row_key({"date": "2024-08-17 14:00:00", "h_a": "a"},
                     "team", source_path="data/2024-25/understat/understat_Chelsea.csv"),
            "2024-25|Arsenal|2024-08-17 14:00:00|h",
        )

    def test_team_row_key_rejects_missing_team_source_identity(self):
        with self.assertRaises(ValueError):
            _row_key({"date": "2024-08-17 14:00:00", "h_a": "h"}, "team")


if __name__ == "__main__":
    unittest.main()
