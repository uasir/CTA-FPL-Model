from __future__ import annotations

import unittest

from audit_2pm_understat_git_history import _row_key


class UnderstatGitHistoryTests(unittest.TestCase):
    def test_player_row_key_uses_mapped_understat_id(self):
        self.assertEqual(
            _row_key({"date": "2024-01-01", "id": 1234}, "player", 987),
            "987|2024-01-01",
        )

    def test_team_row_key_uses_date_match_and_home_away_identity(self):
        self.assertEqual(
            _row_key({"date": "2024-01-01", "id": 1234, "h": "Arsenal", "a": "Chelsea"},
                     "team"),
            "2024-01-01|Arsenal|Chelsea",
        )


if __name__ == "__main__":
    unittest.main()
