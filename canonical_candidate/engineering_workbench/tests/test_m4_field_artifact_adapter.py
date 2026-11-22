from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from m4_field_artifact_adapter import (
    FieldArtifactAdapterError,
    load_post_lock_field_artifact,
)


class TestM4FieldArtifactAdapter(unittest.TestCase):
    def _write_fixture(self, root: Path, *, picks_at="2026-11-21T11:02:00Z",
                       cohort_at="2026-11-21T10:30:00Z", status="CAPTURED_POST_DEADLINE_PICKS",
                       lock_verified=True):
        csv_path = root / "eo.csv"
        report_path = root / "report.json"
        fields = [
            "gameweek", "fpl_element_id", "sample_managers", "sample_weight",
            "owned_by_pct", "starting_pct", "captain_pct", "triple_captain_pct",
            "effective_ownership_pct", "scoring_exposure_pct",
            "effective_ownership_pct_ci95_low", "effective_ownership_pct_ci95_high",
        ]
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerow({
                "gameweek": 11, "fpl_element_id": 1, "sample_managers": 400,
                "sample_weight": 25, "owned_by_pct": 50, "starting_pct": 45,
                "captain_pct": 10, "triple_captain_pct": 0,
                "effective_ownership_pct": 60, "scoring_exposure_pct": 55,
                "effective_ownership_pct_ci95_low": 50,
                "effective_ownership_pct_ci95_high": 70,
            })
        report = {
            "status": status, "picks_lock_verified": lock_verified,
            "deadline_time_utc": "2026-11-21T11:00:00Z",
            "rank_cohort_captured_at_utc": cohort_at,
            "picks_captured_at_utc": picks_at,
            "lock_grace_seconds": 60, "gameweek": 11,
            "sample_size_captured": 400, "effective_sample_size": 392.4,
            "rank_limit": 10000, "rank_min": 1, "rank_max": 9999,
            "rank_strata_count": 200, "cohort": "overall global league rank",
            "sample_weight": 25,
        }
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return csv_path, report_path

    def test_adapts_real_capture_schema_as_retrospective_only(self):
        with tempfile.TemporaryDirectory() as temp:
            csv_path, report_path = self._write_fixture(Path(temp))
            result = load_post_lock_field_artifact(
                csv_path, report_path, season="2026-27",
                source_url="https://github.com/uasir/CTA-FPL-Model/actions/runs/123",
            )
        self.assertEqual(result["evidence_role"], "RETROSPECTIVE_POST_LOCK")
        self.assertEqual(result["comparison_admission"], "NOT_VALID_FOR_PREDEADLINE_DECISION")
        self.assertEqual(result["snapshot"]["sample"]["manager_count"], 400)
        self.assertEqual(result["snapshot"]["field_eo_rows"][0]["effective_ownership_pct"], 60.0)
        self.assertEqual(len(result["snapshot"]["source"]["artifact_sha256"]), 64)
        self.assertFalse(result["release_eligible"])

    def test_rejects_picks_before_lock_grace(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = self._write_fixture(Path(temp), picks_at="2026-11-21T11:00:30Z")
            with self.assertRaisesRegex(FieldArtifactAdapterError, "lock grace"):
                load_post_lock_field_artifact(*paths, season="2026-27", source_url="https://example.test/run")

    def test_rejects_rank_cohort_after_deadline(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = self._write_fixture(Path(temp), cohort_at="2026-11-21T11:00:01Z")
            with self.assertRaisesRegex(FieldArtifactAdapterError, "cohort"):
                load_post_lock_field_artifact(*paths, season="2026-27", source_url="https://example.test/run")

    def test_rejects_unverified_capture(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = self._write_fixture(Path(temp), lock_verified=False)
            with self.assertRaisesRegex(FieldArtifactAdapterError, "verified"):
                load_post_lock_field_artifact(*paths, season="2026-27", source_url="https://example.test/run")

    def test_rejects_duplicate_player_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            csv_path, report_path = self._write_fixture(Path(temp))
            with csv_path.open("a", encoding="utf-8") as handle:
                handle.write("11,1,400,25,50,45,10,0,60,55,50,70\\n")
            with self.assertRaisesRegex(FieldArtifactAdapterError, "duplicate"):
                load_post_lock_field_artifact(csv_path, report_path, season="2026-27", source_url="https://example.test/run")


if __name__ == "__main__":
    unittest.main()
