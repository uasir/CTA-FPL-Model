from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from m4_covar_realized_fpl_finality_batch import (
    FinalityBatchError,
    run_finality_batch,
)


def _write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


class TestRealizedFplFinalityBatch(unittest.TestCase):
    def _fixture(self, root):
        dataset = root / "dataset" / "fpl_realized_player_gameweek.csv"
        dataset.parent.mkdir(parents=True)
        fields = ["season", "gameweek", "fpl_element_id", "minutes", "total_points",
                  "goals_scored", "assists", "clean_sheets", "goals_conceded",
                  "own_goals", "penalties_saved", "penalties_missed", "yellow_cards",
                  "red_cards", "saves", "bonus", "bps"]
        values = {key: 0 for key in fields}
        values.update({"season": "2026-27", "gameweek": 1, "fpl_element_id": 10,
                       "minutes": 90, "total_points": 6, "goals_scored": 1})
        with dataset.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerow(values)
        archive = root / "captures" / "event_1"
        live = {"elements": [{"id": 10, "stats": {
            key: values[key] for key in fields if key not in {"season", "gameweek", "fpl_element_id"}
        }}]}
        fixtures = [{"event": 1, "finished": True, "finished_provisional": False}]
        live_raw = json.dumps(live, separators=(",", ":")).encode()
        fixture_raw = json.dumps(fixtures, separators=(",", ":")).encode()
        _write(archive / "event_live.json", live_raw)
        _write(archive / "fixtures.json", fixture_raw)
        manifest = {
            "capture_status": "PUBLIC_SOURCE_BYTES_CAPTURED",
            "event_id": 1,
            "source_snapshots": [
                {"source_id": "event_live",
                 "source_url": "https://fantasy.premierleague.com/api/event/1/live/",
                 "retrieved_at_utc": "2026-11-21T12:00:00Z",
                 "archive_path": "event_live.json",
                 "content_sha256": hashlib.sha256(live_raw).hexdigest()},
                {"source_id": "fixtures",
                 "source_url": "https://fantasy.premierleague.com/api/fixtures/",
                 "retrieved_at_utc": "2026-11-21T12:00:00Z",
                 "archive_path": "fixtures.json",
                 "content_sha256": hashlib.sha256(fixture_raw).hexdigest()},
            ],
        }
        _write(archive / "capture_manifest.json", json.dumps(manifest).encode())
        return dataset, root / "captures", root / "output"

    def test_batch_reconciles_exact_official_captures(self):
        with tempfile.TemporaryDirectory() as temp:
            dataset, captures, output = self._fixture(Path(temp))
            result = run_finality_batch(dataset, captures, output)
            self.assertEqual(result["status"], "PASS_ALL_EVENTS")
            self.assertTrue(result["all_event_finality_reconciled"])
            self.assertTrue((output / "finality_batch_report.json").is_file())

    def test_rejects_provisional_fixture_before_scoring_audit(self):
        with tempfile.TemporaryDirectory() as temp:
            dataset, captures, output = self._fixture(Path(temp))
            fixture_path = captures / "event_1" / "fixtures.json"
            fixtures = json.loads(fixture_path.read_text())
            fixtures[0]["finished_provisional"] = True
            raw = json.dumps(fixtures, separators=(",", ":")).encode()
            fixture_path.write_bytes(raw)
            manifest_path = captures / "event_1" / "capture_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            next(x for x in manifest["source_snapshots"] if x["source_id"] == "fixtures")["content_sha256"] = hashlib.sha256(raw).hexdigest()
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(FinalityBatchError, "non-provisional"):
                run_finality_batch(dataset, captures, output)

    def test_rejects_capture_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            dataset, captures, output = self._fixture(Path(temp))
            path = captures / "event_1" / "event_live.json"
            path.write_bytes(path.read_bytes() + b"tampered")
            with self.assertRaisesRegex(FinalityBatchError, "hash mismatch"):
                run_finality_batch(dataset, captures, output)


if __name__ == "__main__":
    unittest.main()
