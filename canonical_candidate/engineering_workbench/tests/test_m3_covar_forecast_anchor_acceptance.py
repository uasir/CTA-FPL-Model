from __future__ import annotations

import base64
import hashlib
import json
import unittest

from m3_covar_forecast_anchor_acceptance import (
    M3ForecastAnchorAcceptanceError,
    accept_m3_forecast_anchor,
)


def _fixture():
    provider_raw = b'{"players":[{"id":10,"xp":5.2}]}'
    metadata_raw = b'{"elements":[{"id":10}]}'
    sources = [
        {
            "source_type": "provider_forecast",
            "source_url": "https://provider.example/forecast",
            "raw_snapshot_id": "provider-raw",
            "raw_sha256": hashlib.sha256(provider_raw).hexdigest(),
            "captured_at_utc": "2026-11-20T08:00:00+00:00",
            "raw_payload_base64": base64.b64encode(provider_raw).decode(),
        },
        {
            "source_type": "player_metadata",
            "source_url": "https://fantasy.premierleague.com/api/bootstrap-static/",
            "raw_snapshot_id": "fpl-bootstrap",
            "raw_sha256": hashlib.sha256(metadata_raw).hexdigest(),
            "captured_at_utc": "2026-11-20T08:05:00+00:00",
            "raw_payload_base64": base64.b64encode(metadata_raw).decode(),
        },
    ]
    bundle = {
        "schema_version": "1.0.0",
        "bundle_type": "M3_CONVENTIONAL_FORECAST_ONLY_COVAR_INPUT",
        "season": "2026-27",
        "target_gameweek": 11,
        "mode": "REGULAR_GW",
        "as_of_utc": "2026-11-20T09:00:00+00:00",
        "deadline_utc": "2026-11-21T11:00:00+00:00",
        "forecast_snapshot_id": "fplcat-gw11-snapshot",
        "model_version": "external:FPL Cat:published xP:api/v1",
        "player_forecasts": [
            {"fpl_element_id": 10, "expected_points": 5.2, "expected_minutes": 80}
        ],
        "source_archives": sources,
        "privacy": {
            "manager_identity_included": False,
            "manager_squad_included": False,
            "bank_or_transfer_state_included": False,
            "frozen_decision_included": False,
        },
        "point_in_time_status": "M3_SOURCE_TIMESTAMPS_VALIDATED",
        "decision_weight": 0.0,
        "production_eligible": False,
    }
    raw = json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode()
    manifest = {
        "archive_type": "PRIVATE_MANAGER_FREE_M3_COVAR_FORECAST_ARCHIVE",
        "schema_version": "1.0.0",
        "season": "2026-27",
        "target_gameweek": 11,
        "as_of_utc": bundle["as_of_utc"],
        "deadline_utc": bundle["deadline_utc"],
        "forecast_snapshot_id": bundle["forecast_snapshot_id"],
        "model_version": bundle["model_version"],
        "bundle_sha256": hashlib.sha256(raw).hexdigest(),
        "bundle_bytes": len(raw),
        "source_archives": [
            {key: value for key, value in source.items() if key != "raw_payload_base64"}
            for source in sources
        ],
        "decision_weight": 0.0,
        "production_eligible": False,
    }
    return raw, manifest, bundle


class TestM3CoVarForecastAnchorAcceptance(unittest.TestCase):
    def test_accepts_only_as_player_level_anchor(self):
        raw, manifest, _ = _fixture()
        result = accept_m3_forecast_anchor(raw, manifest)
        self.assertEqual(result["acceptance_status"], "ACCEPTED_PLAYER_LEVEL_FORECAST_ANCHOR_ONLY")
        self.assertEqual(result["player_forecast_count"], 1)
        self.assertFalse(result["joint_distribution_available"])
        self.assertFalse(result["joint_probabilities_inferred"])
        self.assertEqual(result["decision_weight"], 0.0)
        self.assertFalse(result["production_eligible"])

    def test_rejects_bundle_hash_mismatch(self):
        raw, manifest, _ = _fixture()
        manifest["bundle_sha256"] = "0" * 64
        with self.assertRaisesRegex(M3ForecastAnchorAcceptanceError, "SHA-256"):
            accept_m3_forecast_anchor(raw, manifest)

    def test_rejects_manager_data_flag(self):
        raw, manifest, bundle = _fixture()
        bundle["privacy"]["manager_squad_included"] = True
        raw = json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode()
        manifest["bundle_sha256"] = hashlib.sha256(raw).hexdigest()
        manifest["bundle_bytes"] = len(raw)
        with self.assertRaisesRegex(M3ForecastAnchorAcceptanceError, "privacy flags"):
            accept_m3_forecast_anchor(raw, manifest)

    def test_rejects_late_source_capture(self):
        raw, manifest, bundle = _fixture()
        bundle["source_archives"][0]["captured_at_utc"] = "2026-11-20T09:01:00+00:00"
        raw = json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode()
        manifest["bundle_sha256"] = hashlib.sha256(raw).hexdigest()
        manifest["bundle_bytes"] = len(raw)
        manifest["source_archives"][0]["captured_at_utc"] = bundle["source_archives"][0]["captured_at_utc"]
        with self.assertRaisesRegex(M3ForecastAnchorAcceptanceError, "after forecast as-of"):
            accept_m3_forecast_anchor(raw, manifest)

    def test_rejects_joint_probability_field_in_place_of_player_xp(self):
        raw, manifest, bundle = _fixture()
        bundle["joint_probabilities"] = {"state-a": 1.0}
        raw = json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode()
        manifest["bundle_sha256"] = hashlib.sha256(raw).hexdigest()
        manifest["bundle_bytes"] = len(raw)
        # Extra joint data is not accepted as a CoVar probability model.
        result = accept_m3_forecast_anchor(raw, manifest)
        self.assertFalse(result["joint_distribution_available"])
        self.assertFalse(result["joint_probabilities_inferred"])

    def test_rejects_source_bytes_hash_mismatch_even_when_bundle_hash_matches(self):
        raw, manifest, bundle = _fixture()
        bundle["source_archives"][0]["raw_payload_base64"] = base64.b64encode(b"tampered").decode()
        raw = json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode()
        manifest["bundle_sha256"] = hashlib.sha256(raw).hexdigest()
        manifest["bundle_bytes"] = len(raw)
        with self.assertRaisesRegex(M3ForecastAnchorAcceptanceError, "raw source SHA-256 mismatch"):
            accept_m3_forecast_anchor(raw, manifest)

    def test_rejects_duplicate_player_ids(self):
        raw, manifest, bundle = _fixture()
        bundle["player_forecasts"].append(dict(bundle["player_forecasts"][0]))
        raw = json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode()
        manifest["bundle_sha256"] = hashlib.sha256(raw).hexdigest()
        manifest["bundle_bytes"] = len(raw)
        with self.assertRaisesRegex(M3ForecastAnchorAcceptanceError, "unique positive integers"):
            accept_m3_forecast_anchor(raw, manifest)


if __name__ == "__main__":
    unittest.main()
