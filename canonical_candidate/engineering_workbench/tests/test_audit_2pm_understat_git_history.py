from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from audit_2pm_understat_git_history import _get_text, _row_key, audit_file, list_path_commits


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


    def test_commit_page_cache_avoids_repeating_github_api_request(self):
        commits = [{"sha": "a", "commit": {"committer": {"date": "2024-01-01T00:00:00Z"}}}]
        with tempfile.TemporaryDirectory() as directory:
            with patch("audit_2pm_understat_git_history._get_json",
                       return_value=commits) as get_json:
                first = list_path_commits(
                    object(), "vaastav/Fantasy-Premier-League", "data/player.csv",
                    "pinned", 25, Path(directory),
                )
                second = list_path_commits(
                    object(), "vaastav/Fantasy-Premier-League", "data/player.csv",
                    "pinned", 25, Path(directory),
                )
        self.assertEqual(first, commits)
        self.assertEqual(second, commits)
        self.assertEqual(get_json.call_count, 1)

    def test_raw_revision_cache_reuses_verified_exact_bytes(self):
        commits = [{"sha": "a", "commit": {"committer": {"date": "2024-01-01T00:00:00Z"}}}]
        payload = b"date,season,xG\\n2024-01-01,2023,0.2\\n"
        url = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/a/data/player_987.csv"
        with tempfile.TemporaryDirectory() as directory:
            with patch("audit_2pm_understat_git_history.list_path_commits",
                       return_value=commits):
                with patch("audit_2pm_understat_git_history._get_text",
                           return_value=payload) as get_text:
                    first = audit_file(
                        object(), "vaastav/Fantasy-Premier-League", "a",
                        "data/player_987.csv", "player", 10, 987, Path(directory),
                    )
                    second = audit_file(
                        object(), "vaastav/Fantasy-Premier-League", "a",
                        "data/player_987.csv", "player", 10, 987, Path(directory),
                    )
        self.assertEqual(first["errors"], [])
        self.assertEqual(second["errors"], [])
        self.assertEqual(get_text.call_count, 1)
        self.assertEqual(first["commit_rows"], second["commit_rows"])

    def test_team_row_key_matches_pinned_dastan_team_file_contract(self):
        source_path = "data/2024-25/understat/understat_Arsenal.csv"
        self.assertEqual(
            _row_key({"date": "2024-08-17 14:00:00", "h_a": "h",
                      "xG": 1.6, "xGA": 0.5}, "team", source_path=source_path),
            "2024-25|Arsenal|2024-08-17 14:00:00",
        )
        # Home/away is not part of the identity; a duplicate cannot evade detection.
        self.assertEqual(
            _row_key({"date": "2024-08-17 14:00:00", "h_a": "a"},
                     "team", source_path=source_path),
            "2024-25|Arsenal|2024-08-17 14:00:00",
        )
        # The same kickoff in another team's source file remains a different row.
        self.assertNotEqual(
            _row_key({"date": "2024-08-17 14:00:00", "h_a": "a"},
                     "team", source_path="data/2024-25/understat/understat_Chelsea.csv"),
            "2024-25|Arsenal|2024-08-17 14:00:00",
        )


    def test_team_row_key_excludes_previous_season_rows_like_dastan(self):
        source_path = "data/2024-25/understat/understat_Arsenal.csv"
        self.assertEqual(
            _row_key({"date": "2024-05-19 15:00:00", "h_a": "h"},
                     "team", source_path=source_path),
            "",
        )
        self.assertEqual(
            _row_key({"date": "2024-07-01 00:00:00", "h_a": "h"},
                     "team", source_path=source_path),
            "2024-25|Arsenal|2024-07-01 00:00:00",
        )
        self.assertEqual(
            _row_key({"date": "2025-06-30 23:59:59", "h_a": "a"},
                     "team", source_path=source_path),
            "2024-25|Arsenal|2025-06-30 23:59:59",
        )
        self.assertEqual(
            _row_key({"date": "2025-07-01 00:00:00", "h_a": "a"},
                     "team", source_path=source_path),
            "",
        )

    def test_team_row_key_rejects_missing_team_source_identity(self):
        with self.assertRaises(ValueError):
            _row_key({"date": "2024-08-17 14:00:00", "h_a": "h"}, "team")


if __name__ == "__main__":
    unittest.main()
