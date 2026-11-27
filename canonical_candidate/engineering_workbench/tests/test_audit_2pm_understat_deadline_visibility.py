from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

import pandas as pd

from audit_2pm_understat_deadline_visibility import (
    _evaluate_deadline,
    _fixture_match,
    _latest_state_before_deadline,
    _metric_signature,
)


class UnderstatDeadlineVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.calendars = {
            "2022-23": pd.DataFrame([{
                "season": "2022-23",
                "fixture_id": 61,
                "event": 25,
                "kickoff_time": pd.Timestamp("2023-03-01T19:45:00Z"),
                "home_team": "Arsenal",
                "away_team": "Everton",
            }])
        }

    def test_player_row_maps_to_canonical_fixture_by_date_and_home_away(self):
        fixture, status = _fixture_match({
            "date": "2023-03-01",
            "season": "2022",
            "h_team": "Arsenal",
            "a_team": "Everton",
        }, "player", "data/2024-25/understat/Player_1250.csv", self.calendars)
        self.assertEqual(status, "matched")
        self.assertEqual(fixture["fixture_id"], 61)
        self.assertEqual(fixture["event"], 25)

    def test_team_row_one_day_date_shift_maps_to_same_fixture(self):
        fixture, status = _fixture_match({
            "date": "2023-03-02 20:00:00",
            "h_a": "h",
            "xG": 3.06919,
        }, "team", "data/2022-23/understat/understat_Arsenal.csv", self.calendars)
        self.assertEqual(status, "matched")
        self.assertEqual(fixture["fixture_id"], 61)

    def test_date_is_excluded_from_metric_signature_but_values_are_not(self):
        old = json.dumps({"date": "2023-03-02", "xG": "3.06919", "xGA": "1.604"})
        corrected_date = json.dumps({"date": "2023-03-01", "xG": "3.06919", "xGA": "1.604"})
        changed_value = json.dumps({"date": "2023-03-01", "xG": "3.0", "xGA": "1.604"})
        self.assertEqual(_metric_signature(old), _metric_signature(corrected_date))
        self.assertNotEqual(_metric_signature(old), _metric_signature(changed_value))

    def test_strict_five_minute_cutoff_excludes_equal_or_later_commit(self):
        events = [
            {"commit": "a", "committed_at": "2023-03-04T10:54:59Z", "status": "present"},
            {"commit": "b", "committed_at": "2023-03-04T10:55:00Z", "status": "present"},
        ]
        deadline = datetime(2023, 3, 4, 11, 0, tzinfo=timezone.utc)
        state = _latest_state_before_deadline(events, deadline)
        self.assertEqual(state["commit"], "a")

    def test_same_commit_date_correction_prefers_new_present_row_over_old_missing(self):
        events = [
            {"commit": "a", "committed_at": "2023-03-02T12:40:22Z",
             "status": "present", "source_row_key": "old"},
            {"commit": "b", "committed_at": "2023-03-27T11:00:02Z",
             "status": "missing", "source_row_key": "old"},
            {"commit": "b", "committed_at": "2023-03-27T11:00:02Z",
             "status": "present", "source_row_key": "new"},
        ]
        events.sort(key=lambda event: (
            pd.to_datetime(event["committed_at"], utc=True),
            1 if event["status"] == "present" else 0,
        ))
        deadline = datetime(2023, 4, 1, 10, 0, tzinfo=timezone.utc)
        state = _latest_state_before_deadline(events, deadline)
        self.assertEqual(state["status"], "present")
        self.assertEqual(state["source_row_key"], "new")

    def test_value_revision_is_selected_as_of_deadline_not_from_final_file(self):
        old_metric = _metric_signature(json.dumps({"date": "2020-09-20", "xG": "2.69491"}))
        final_metric = _metric_signature(json.dumps({"date": "2020-09-20", "xG": "2.25211"}))
        item = {
            "season": "2020-21", "entity": "team:Liverpool",
            "source_kind": "pinned_team_csv", "source_path": "understat_Liverpool.csv",
            "fixture_id": 2, "fixture_event": 2,
            "kickoff_time": "2020-09-20T15:30:00+00:00",
            "home_team": "Chelsea", "away_team": "Liverpool",
            "first_seen_at": "2020-09-22T07:05:27Z",
            "value_revision_events": 1, "source_row_keys": ["old"],
            "events": [
                {"commit": "a", "committed_at": "2020-09-22T07:05:27Z",
                 "status": "present", "value_signature": old_metric,
                 "metric_signature": old_metric, "source_row_key": "old"},
                {"commit": "b", "committed_at": "2020-11-10T13:36:37Z",
                 "status": "present", "value_signature": final_metric,
                 "metric_signature": final_metric, "source_row_key": "old"},
            ],
            "final_metric_signature": final_metric,
        }
        early = _evaluate_deadline(item, {
            "gameweek": 3,
            "deadline": datetime(2020, 9, 26, 10, 0, tzinfo=timezone.utc),
            "deadline_status": "pre_deadline_snapshot_verified",
            "deadline_verified": True,
        })
        self.assertEqual(early["visibility_status"], "repository_proven_prior_row")
        self.assertFalse(early["value_matches_final"])
        later = _evaluate_deadline(item, {
            "gameweek": 9,
            "deadline": datetime(2020, 11, 21, 10, 0, tzinfo=timezone.utc),
            "deadline_status": "pre_deadline_snapshot_verified",
            "deadline_verified": True,
        })
        self.assertTrue(later["value_matches_final"])

    def test_unverified_deadline_never_becomes_an_eligibility_claim(self):
        item = {
            "season": "2020-21", "entity": "team:Liverpool",
            "source_kind": "pinned_team_csv", "source_path": "x",
            "fixture_id": 2, "fixture_event": 2,
            "kickoff_time": "2020-09-20T15:30:00+00:00",
            "home_team": "Chelsea", "away_team": "Liverpool",
            "first_seen_at": "2020-09-22T07:05:27Z",
            "value_revision_events": 0, "source_row_keys": ["old"],
            "events": [{"commit": "a", "committed_at": "2020-09-22T07:05:27Z",
                        "status": "present", "value_signature": "{}", 
                        "metric_signature": "old", "source_row_key": "old"}],
            "final_metric_signature": "final",
        }
        result = _evaluate_deadline(item, {
            "gameweek": 3,
            "deadline": datetime(2020, 9, 26, 10, 0, tzinfo=timezone.utc),
            "deadline_status": "no_pre_deadline_snapshot",
            "deadline_verified": False,
        })
        self.assertEqual(result["visibility_status"], "deadline_unverified")
        self.assertFalse(result["deadline_verified"])
        self.assertEqual(result["provisional_visibility_status"], "repository_proven_prior_row")
        self.assertFalse(result["provisional_value_matches_final"])


if __name__ == "__main__":
    unittest.main()
