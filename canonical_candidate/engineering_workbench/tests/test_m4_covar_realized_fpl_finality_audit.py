from __future__ import annotations

import hashlib
import json
import unittest

from m4_covar_realized_fpl_finality_audit import (
    RealizedFplFinalityAuditError,
    audit_player_gameweek_finality,
)


FIELDS = (
    "minutes", "total_points", "goals_scored", "assists", "clean_sheets",
    "goals_conceded", "own_goals", "penalties_saved", "penalties_missed",
    "yellow_cards", "red_cards", "saves", "bonus", "bps",
)


def _fixture():
    row = {"season": "2026-27", "gameweek": 1, "fpl_element_id": 10}
    stats = {}
    for field in FIELDS:
        row[field] = 0
        stats[field] = 0
    row.update({"minutes": 90, "total_points": 6, "goals_scored": 1})
    stats.update({"minutes": 90, "total_points": 6, "goals_scored": 1})
    live = {"elements": [{"id": 10, "stats": stats}]}
    raw = json.dumps(live, separators=(",", ":")).encode()
    return [row], live, {
        "source_url": "https://fantasy.premierleague.com/api/event/1/live/",
        "captured_at_utc": "2026-11-21T12:00:00Z",
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
    }, raw


class TestRealizedFplFinalityAudit(unittest.TestCase):
    def test_exact_match_passes_but_is_not_point_in_time_verified(self):
        rows, live, provenance, raw = _fixture()
        report = audit_player_gameweek_finality(
            rows, live, season="2026-27", event_id=1, source_provenance=provenance,
            raw_source_bytes=raw,
        )
        self.assertEqual(report["status"], "PASS_EXACT_MATCH")
        self.assertTrue(report["finality_reconciled"])
        self.assertFalse(report["point_in_time_status"] == "VERIFIED")
        self.assertEqual(report["stat_values_compared"], len(FIELDS))

    def test_any_stat_mismatch_fails(self):
        rows, live, provenance, raw = _fixture()
        live["elements"][0]["stats"]["total_points"] = 5
        raw = json.dumps(live, separators=(",", ":")).encode()
        provenance["raw_sha256"] = hashlib.sha256(raw).hexdigest()
        report = audit_player_gameweek_finality(
            rows, live, season="2026-27", event_id=1, source_provenance=provenance,
            raw_source_bytes=raw,
        )
        self.assertEqual(report["status"], "FAIL_MISMATCH")
        self.assertEqual(report["mismatch_count"], 1)

    def test_missing_player_is_not_zero_filled(self):
        rows, live, provenance, raw = _fixture()
        live["elements"] = []
        raw = json.dumps(live, separators=(",", ":")).encode()
        provenance["raw_sha256"] = hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(RealizedFplFinalityAuditError, "non-empty"):
            audit_player_gameweek_finality(
                rows, live, season="2026-27", event_id=1, source_provenance=provenance,
                raw_source_bytes=raw,
            )

    def test_wrong_gameweek_rejected(self):
        rows, live, provenance, raw = _fixture()
        with self.assertRaisesRegex(RealizedFplFinalityAuditError, "requested season and event"):
            audit_player_gameweek_finality(
                rows, live, season="2026-27", event_id=2, source_provenance=provenance,
                raw_source_bytes=raw,
            )

    def test_duplicate_player_gw_rejected(self):
        rows, live, provenance, raw = _fixture()
        with self.assertRaisesRegex(RealizedFplFinalityAuditError, "duplicate"):
            audit_player_gameweek_finality(
                rows + rows, live, season="2026-27", event_id=1, source_provenance=provenance,
                raw_source_bytes=raw,
            )

    def test_source_must_be_official_requested_event_live(self):
        rows, live, provenance, raw = _fixture()
        provenance["source_url"] = "https://example.com/event/1/live"
        with self.assertRaisesRegex(RealizedFplFinalityAuditError, "official"):
            audit_player_gameweek_finality(
                rows, live, season="2026-27", event_id=1, source_provenance=provenance,
                raw_source_bytes=raw,
            )


    def test_rejects_raw_bytes_that_do_not_match_declared_hash(self):
        rows, live, provenance, raw = _fixture()
        with self.assertRaisesRegex(RealizedFplFinalityAuditError, "SHA-256"):
            audit_player_gameweek_finality(
                rows, live, season="2026-27", event_id=1, source_provenance=provenance,
                raw_source_bytes=raw + b"tampered",
            )


if __name__ == "__main__":
    unittest.main()
