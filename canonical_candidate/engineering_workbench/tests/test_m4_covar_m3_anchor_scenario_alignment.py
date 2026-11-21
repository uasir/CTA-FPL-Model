from __future__ import annotations

import base64
import hashlib
import json
import unittest

from m4_covar_m3_anchor_scenario_alignment import (
    M3JointScenarioAlignmentError,
    align_m3_anchor_to_joint_scenarios,
)


def _inputs():
    provider_raw = b'{"players":[{"id":10,"xp":5.0},{"id":20,"xp":3.0}]}'
    metadata_raw = b'{"elements":[{"id":10},{"id":20}]}'
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
            "raw_snapshot_id": "bootstrap-raw",
            "raw_sha256": hashlib.sha256(metadata_raw).hexdigest(),
            "captured_at_utc": "2026-11-20T08:01:00+00:00",
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
        "forecast_snapshot_id": "m3-gw11",
        "model_version": "m3-conventional",
        "player_forecasts": [
            {"fpl_element_id": 10, "expected_points": 5.0, "expected_minutes": 80},
            {"fpl_element_id": 20, "expected_points": 3.0, "expected_minutes": 70},
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
            {key: value for key, value in row.items() if key != "raw_payload_base64"}
            for row in sources
        ],
        "privacy": dict(bundle["privacy"]),
        "point_in_time_status": bundle["point_in_time_status"],
        "decision_weight": 0.0,
        "production_eligible": False,
    }
    provenance = {
        "source_id": "explicit-test-scenarios",
        "method": "explicitly authored joint outcomes for unit tests",
        "captured_at_utc": "2026-11-20T08:30:00+00:00",
        "probability_basis": "EXPLICIT",
    }
    scenarios = [
        {"scenario_id": "a", "probability": 0.25, "player_points": {"10": 8, "20": 2}},
        {"scenario_id": "b", "probability": 0.75, "player_points": {"10": 4, "20": 10/3}},
    ]
    return raw, manifest, provenance, scenarios


class TestM3AnchorScenarioAlignment(unittest.TestCase):
    def test_computes_marginal_mean_alignment_without_inference(self):
        raw, manifest, provenance, scenarios = _inputs()
        report = align_m3_anchor_to_joint_scenarios(
            forecast_bundle_bytes=raw,
            archive_manifest=manifest,
            joint_scenarios=scenarios,
            scenario_provenance=provenance,
        )
        self.assertEqual(report["alignment_status"], "PASS_EXPLICIT_SCENARIO_MARGINAL_ALIGNMENT_COMPUTED")
        self.assertAlmostEqual(report["mean_absolute_error"], 0.0, places=9)
        self.assertFalse(report["joint_distribution_was_inferred"])
        self.assertFalse(report["fixture_independence_assumed"])
        self.assertFalse(report["calibration_established"])
        self.assertEqual(report["decision_weight"], 0.0)
        self.assertFalse(report["production_eligible"])

    def test_rejects_marginal_probability_guess(self):
        raw, manifest, provenance, scenarios = _inputs()
        provenance["probability_basis"] = "INFERRED_FROM_XP"
        with self.assertRaisesRegex(M3JointScenarioAlignmentError, "explicitly supplied"):
            align_m3_anchor_to_joint_scenarios(
                forecast_bundle_bytes=raw,
                archive_manifest=manifest,
                joint_scenarios=scenarios,
                scenario_provenance=provenance,
            )

    def test_rejects_scenario_capture_after_m3_as_of(self):
        raw, manifest, provenance, scenarios = _inputs()
        provenance["captured_at_utc"] = "2026-11-20T09:01:00+00:00"
        with self.assertRaisesRegex(M3JointScenarioAlignmentError, "after the M3 forecast as-of"):
            align_m3_anchor_to_joint_scenarios(
                forecast_bundle_bytes=raw,
                archive_manifest=manifest,
                joint_scenarios=scenarios,
                scenario_provenance=provenance,
            )

    def test_rejects_incomplete_player_universe(self):
        raw, manifest, provenance, scenarios = _inputs()
        del scenarios[0]["player_points"]["20"]
        with self.assertRaisesRegex(M3JointScenarioAlignmentError, "exactly the M3 anchor player universe"):
            align_m3_anchor_to_joint_scenarios(
                forecast_bundle_bytes=raw,
                archive_manifest=manifest,
                joint_scenarios=scenarios,
                scenario_provenance=provenance,
            )

    def test_rejects_probabilities_not_summing_to_one(self):
        raw, manifest, provenance, scenarios = _inputs()
        scenarios[0]["probability"] = 0.5
        with self.assertRaisesRegex(M3JointScenarioAlignmentError, "must sum to 1"):
            align_m3_anchor_to_joint_scenarios(
                forecast_bundle_bytes=raw,
                archive_manifest=manifest,
                joint_scenarios=scenarios,
                scenario_provenance=provenance,
            )


if __name__ == "__main__":
    unittest.main()
