import json
import tempfile
import unittest
from pathlib import Path

from src.cta_engine import audit_360, build_player_rows


class CTARegressionTests(unittest.TestCase):
    def test_player_rows_zero_fill_counts_but_keep_unestimable_means_blank(self):
        rows = build_player_rows({"Player A": {"passes": 1}}, minutes={}, aliases={})
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["passes"], 1)
        for field in (
            "event_involvements", "completed_passes", "carries", "shots",
            "receipts", "pressured_events", "pressured_receipts", "box_entries",
            "final_third_entries", "progressive_actions", "action_xt_gain_sum",
            "action_xt_gain_n", "passes_received", "pressured_passes_received",
            "sequences_involved", "shot_linked_sequences", "non_shot_candidate_sequences",
        ):
            self.assertEqual(row[field], 0, field)
        self.assertEqual(row["shot_xg_reference_only"], 0.0)
        self.assertEqual(row["mean_action_xt_gain"], "")
        self.assertEqual(row["action_xt_gain_per90"], "")
        self.assertEqual(row["minutes"], 0.0)

    def test_360_join_does_not_cross_match_on_a_reused_uuid(self):
        events = [{"_match_id": "other-match", "id": "shared-uuid"}]
        with tempfile.TemporaryDirectory() as tmp:
            frame_dir = Path(tmp)
            (frame_dir / "target-match.json").write_text(
                json.dumps([{"event_uuid": "shared-uuid"}]), encoding="utf-8"
            )
            result = audit_360(events, frame_dir)
        self.assertEqual(result["matched_frame_uuids"], 0)
        self.assertEqual(result["unmatched_frame_uuids"], 1)
        self.assertEqual(result["frame_to_event_join_rate"], 0.0)

    def test_360_duplicate_uuid_count_is_scoped_to_match(self):
        events = [
            {"_match_id": "match-1", "id": "shared-uuid"},
            {"_match_id": "match-2", "id": "shared-uuid"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            frame_dir = Path(tmp)
            (frame_dir / "match-1.json").write_text(
                json.dumps([{"event_uuid": "shared-uuid"}]), encoding="utf-8"
            )
            (frame_dir / "match-2.json").write_text(
                json.dumps([{"event_uuid": "shared-uuid"}]), encoding="utf-8"
            )
            result = audit_360(events, frame_dir)
        self.assertEqual(result["matched_frame_uuids"], 2)
        self.assertEqual(result["unique_event_uuids"], 1)
        self.assertEqual(result["unique_match_event_keys"], 2)
        self.assertEqual(result["duplicate_frame_event_uuids"], 0)


if __name__ == "__main__":
    unittest.main()
