from __future__ import annotations

import unittest
from unittest.mock import patch

from audit_2pm_understat_git_history import _row_key, audit_file


class UnderstatGitHistoryTests(unittest.TestCase):
    def test_player_row_key_uses_mapped_understat_id(self):
        self.assertEqual(
            _row_key({"date": "2024-01-01", "id": 1234}, "player", 987),
            "987|2024-01-01",
        )


    def test_row_history_tracks_removal_reappearance_and_value_revision(self):
        commits = [
            {"sha": "a", "commit": {"committer": {"date": "2024-01-01T00:00:00Z"}}},
            {"sha": "b", "commit": {"committer": {"date": "2024-01-02T00:00:00Z"}}},
            {"sha": "c", "commit": {"committer": {"date": "2024-01-03T00:00:00Z"}}},
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

    def test_team_row_key_uses_date_match_and_home_away_identity(self):
        self.assertEqual(
            _row_key({"date": "2024-01-01", "id": 1234, "h": "Arsenal", "a": "Chelsea"},
                     "team"),
            "2024-01-01|Arsenal|Chelsea",
        )


if __name__ == "__main__":
    unittest.main()
