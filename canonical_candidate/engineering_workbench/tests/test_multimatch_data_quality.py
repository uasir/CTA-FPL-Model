import json
import tempfile
import unittest
from pathlib import Path
from scripts.audit_multimatch_data_quality import audit_quality


class MultiMatchDataQualityTests(unittest.TestCase):
    def _audit(self, manifest_rows, audit_rows):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "python"
            root.mkdir()
            for match_id, payload in audit_rows.items():
                out = root / str(match_id)
                out.mkdir()
                (out / "audit.json").write_text(json.dumps({
                    "events_processed": 100,
                    "statsbomb_360_audit": payload,
                }))
            return audit_quality({"source": {"commit_sha": "a" * 40}, "matches": manifest_rows}, root)

    def test_passes_usable_360_and_preserves_unavailable_and_excluded_statuses(self):
        rows = [
            {"match_id": 1, "has_360": True, "has_360_source": True},
            {"match_id": 2, "has_360": False, "has_360_source": False},
            {"match_id": 3, "has_360": False, "has_360_source": True,
             "three_sixty_exclusion_reason": "Bad UUID linkage."},
        ]
        audits = {
            "1": {"frames": 10, "frames_with_event_uuid": 10, "matched_frame_uuids": 10,
                  "unmatched_frame_uuids": 0, "duplicate_frame_event_uuids": 0,
                  "frame_to_event_join_rate": 1.0},
            "2": {"frames": 0, "frames_with_event_uuid": 0, "matched_frame_uuids": 0,
                  "unmatched_frame_uuids": 0, "duplicate_frame_event_uuids": 0,
                  "frame_to_event_join_rate": None},
            "3": {"frames": 0, "frames_with_event_uuid": 0, "matched_frame_uuids": 0,
                  "unmatched_frame_uuids": 0, "duplicate_frame_event_uuids": 0,
                  "frame_to_event_join_rate": None},
        }
        result = self._audit(rows, audits)
        self.assertEqual(result["status"], "PASS_WITH_EXPLICIT_EXCLUSIONS")
        self.assertEqual(result["counts"]["PASS"], 1)
        self.assertEqual(result["counts"]["NOT_AVAILABLE"], 1)
        self.assertEqual(result["counts"]["EXCLUDED_INVALID_SOURCE"], 1)

    def test_fails_present_360_with_unmatched_frame_uuids(self):
        rows = [{"match_id": 1, "has_360": True, "has_360_source": True}]
        audits = {"1": {"frames": 5, "frames_with_event_uuid": 5, "matched_frame_uuids": 0,
                        "unmatched_frame_uuids": 5, "duplicate_frame_event_uuids": 0,
                        "frame_to_event_join_rate": 0.0}}
        result = self._audit(rows, audits)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("1", result["failures"])

    def test_fails_if_excluded_or_unavailable_360_is_processed(self):
        rows = [{"match_id": 1, "has_360": False, "has_360_source": True,
                 "three_sixty_exclusion_reason": "Invalid source."}]
        audits = {"1": {"frames": 1, "frames_with_event_uuid": 1, "matched_frame_uuids": 1,
                        "unmatched_frame_uuids": 0, "duplicate_frame_event_uuids": 0,
                        "frame_to_event_join_rate": 1.0}}
        result = self._audit(rows, audits)
        self.assertEqual(result["status"], "FAIL")

    def test_fails_when_expected_match_audit_is_missing(self):
        rows = [{"match_id": 1, "has_360": False, "has_360_source": False}]
        result = self._audit(rows, {})
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["missing_match_audits"], ["1"])

    def test_fails_when_event_processing_is_empty(self):
        rows = [{"match_id": 1, "has_360": False, "has_360_source": False}]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "python"
            match = root / "1"
            match.mkdir(parents=True)
            (match / "audit.json").write_text(json.dumps({
                "events_processed": 0,
                "statsbomb_360_audit": {"frames": 0},
            }))
            result = audit_quality({"matches": rows}, root)
        self.assertEqual(result["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
