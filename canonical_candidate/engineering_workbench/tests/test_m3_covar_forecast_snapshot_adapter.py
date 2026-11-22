from __future__ import annotations

import base64
import hashlib
import unittest

import m3_covar_forecast_snapshot_adapter as adapter


def _raw(value):
    raw = value.encode()
    return raw, hashlib.sha256(raw).hexdigest()


def _bundle():
    provider_raw = b'{"gameweek":11,"deadline":"2026-11-21T11:00:00Z","computed_at":"2026-11-20T08:30:00Z","players":[{"id":10,"xp":5.2,"expected_minutes":80}]}'
    provider_hash = hashlib.sha256(provider_raw).hexdigest()
    metadata_raw = b'{"events":[{"id":11,"deadline_time":"2026-11-21T11:00:00Z"}],"element_types":[{"id":3,"singular_name_short":"MID"}],"elements":[{"id":10,"now_cost":50,"element_type":3,"team":1}]}'
    metadata_hash = hashlib.sha256(metadata_raw).hexdigest()
    provider = {
        "snapshot_id": "snapshot-gw11",
        "season": "2026-27",
        "target_gameweek": 11,
        "provider": {"name": "Provider", "product": "xP", "variant": "published"},
        "timing": {
            "generated_at_utc": "2026-11-20T08:30:00Z",
            "captured_at_utc": "2026-11-20T09:00:00Z",
            "deadline_utc": "2026-11-21T11:00:00Z",
        },
        "source": {
            "url": "https://provider.example/forecast",
            "raw_snapshot_id": "provider-raw-11",
            "raw_sha256": provider_hash,
        },
        "grain": "player_gameweek",
        "records": [{"fpl_element_id": 10, "expected_points": 5.2, "expected_minutes": 80}],
        "coverage": {"row_count": 1, "expected_player_universe": 1, "identity_mapped_count": 1},
    }
    metadata = [{"fpl_element_id": 10, "price": 5.0, "position": "MID", "team_id": 1}]
    metadata_provenance = {
        "source_url": "https://fantasy.premierleague.com/api/bootstrap-static/",
        "raw_snapshot_id": "metadata-raw-11",
        "raw_sha256": metadata_hash,
        "captured_at_utc": "2026-11-20T09:05:00Z",
        "row_count": 1,
    }
    sources = [
        {
            "source_type": "provider_forecast", "source_url": "https://provider.example/forecast",
            "raw_snapshot_id": "provider-raw-11", "raw_sha256": provider_hash,
            "captured_at_utc": "2026-11-20T09:00:00Z",
            "generated_at_utc": "2026-11-20T08:30:00Z",
            "raw_payload_base64": base64.b64encode(provider_raw).decode(),
        },
        {
            "source_type": "player_metadata", "source_url": metadata_provenance["source_url"],
            "raw_snapshot_id": "metadata-raw-11", "raw_sha256": metadata_hash,
            "captured_at_utc": metadata_provenance["captured_at_utc"],
            "raw_payload_base64": base64.b64encode(metadata_raw).decode(),
        },
        {
            "source_type": "manager_deadline_state", "source_url": "https://fantasy.premierleague.com/entry/private",
            "raw_snapshot_id": "manager-private", "raw_sha256": "b" * 64,
            "captured_at_utc": "2026-11-20T09:10:00Z",
            "raw_payload_base64": base64.b64encode(b"private manager data").decode(),
        },
    ]
    evidence = {"11": {
        "target_gameweek": 11, "season": "2026-27",
        "provider_snapshot": provider, "player_metadata": metadata,
        "player_metadata_provenance": metadata_provenance,
        "decision_as_of_utc": "2026-11-20T10:00:00Z",
        "deadline_utc": "2026-11-21T11:00:00Z",
        "sources": sources,
        "manager_team_id": 123456, "manager_state": {"squad_15": [10]},
    }}
    m3_result = {
        "run_type": "M3_CONVENTIONAL_PERSONAL_SQUAD_RECOMMENDATION",
        "target_gameweek": 11, "provider_snapshot_id": "snapshot-gw11",
        "decision_as_of_utc": "2026-11-20T10:00:00Z",
        "deadline_utc": "2026-11-21T11:00:00Z",
        "recommendation": {
            "forecast_snapshot_id": "snapshot-gw11",
            "model_version": "external:Provider:xP:published:version-unreported",
        },
        "evaluation_candidate": {"manager_team_id": 123456, "manager_state": {"squad_snapshot": [10]}},
        "frozen_decision": {"transfer_in_id": 10},
    }
    return evidence, m3_result


class TestM3CoVarForecastSnapshotAdapter(unittest.TestCase):
    def setUp(self):
        self.original_normalize = adapter.normalize_provider_snapshot
        self.original_build = adapter.build_recommendation_forecast_payload
        adapter.normalize_provider_snapshot = lambda value: {
            **value, "decision_eligible": True,
            "timing": {**value["timing"], "point_in_time_status": "VERIFIED_PRE_DEADLINE"},
        }
        adapter.build_recommendation_forecast_payload = lambda snapshot, metadata, **kwargs: {
            "forecast_snapshot_id": snapshot["snapshot_id"],
            "model_version": "external:Provider:xP:published:version-unreported",
            "player_forecasts": [{"fpl_element_id": 10, "expected_points": 5.2, "expected_minutes": 80}],
            "forecast_quality": {"validation_status": "EXPLORATORY_ONLY"},
        }

    def tearDown(self):
        adapter.normalize_provider_snapshot = self.original_normalize
        adapter.build_recommendation_forecast_payload = self.original_build

    def test_extracts_exact_m3_forecast_and_excludes_manager_state(self):
        evidence, result = _bundle()
        output = adapter.extract_m3_covar_forecast_bundle(evidence, result)
        self.assertEqual(output["forecast_snapshot_id"], "snapshot-gw11")
        self.assertEqual(output["model_version"], result["recommendation"]["model_version"])
        self.assertEqual(len(output["source_archives"]), 2)
        self.assertFalse(output["privacy"]["manager_identity_included"])
        self.assertFalse(output["privacy"]["manager_squad_included"])
        self.assertNotIn("manager_team_id", output)
        self.assertNotIn("manager_state", output)
        self.assertNotIn("frozen_decision", output)
        self.assertNotIn("evaluation_candidate", output)
        self.assertEqual([x["source_type"] for x in output["source_archives"]],
                         ["provider_forecast", "player_metadata"])

    def test_rejects_provider_hash_mismatch(self):
        evidence, result = _bundle()
        evidence["11"]["sources"][0]["raw_sha256"] = "c" * 64
        with self.assertRaisesRegex(adapter.M3CoVarForecastAdapterError, "SHA-256 mismatch"):
            adapter.extract_m3_covar_forecast_bundle(evidence, result)

    def test_rejects_provider_snapshot_id_mismatch(self):
        evidence, result = _bundle()
        result["provider_snapshot_id"] = "different"
        with self.assertRaisesRegex(adapter.M3CoVarForecastAdapterError, "snapshot ID"):
            adapter.extract_m3_covar_forecast_bundle(evidence, result)

    def test_rejects_metadata_capture_after_decision_as_of(self):
        evidence, result = _bundle()
        evidence["11"]["sources"][1]["captured_at_utc"] = "2026-11-20T10:30:00Z"
        evidence["11"]["player_metadata_provenance"]["captured_at_utc"] = "2026-11-20T10:30:00Z"
        with self.assertRaisesRegex(adapter.M3CoVarForecastAdapterError, "after M3 decision"):
            adapter.extract_m3_covar_forecast_bundle(evidence, result)

    def test_rejects_multiple_gameweeks(self):
        evidence, result = _bundle()
        evidence["12"] = evidence["11"]
        with self.assertRaisesRegex(adapter.M3CoVarForecastAdapterError, "exactly one"):
            adapter.extract_m3_covar_forecast_bundle(evidence, result)


if __name__ == "__main__":
    unittest.main()
