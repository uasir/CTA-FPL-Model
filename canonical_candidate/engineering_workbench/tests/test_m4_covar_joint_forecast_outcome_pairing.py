from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from m4_covar_joint_forecast_outcome_pairing import (
    JointForecastOutcomePairingError,
    build_joint_forecast_outcome_pairs,
)


def _forecast(fid="forecast-gw1-a", as_of="2026-08-01T09:00:00Z"):
    return {
        "forecast_id": fid,
        "season": "2026-27",
        "gameweek_id": "1",
        "as_of_utc": as_of,
        "first_kickoff_utc": "2026-08-01T11:00:00Z",
        "training_cutoff_utc": "2026-07-31T23:59:00Z",
        "probabilities": {"state-a": 0.7, "state-b": 0.3},
        "reference_probabilities": {"state-a": 0.5, "state-b": 0.5},
        "state_catalogue_sha256": "a" * 64,
        "player_universe_sha256": "b" * 64,
        "player_count": 2,
        "provenance": {},
    }


def _mapping():
    return {
        "season": "2026-27",
        "gameweek_id": "1",
        "mapping_status": "PASS_EXACT_OBSERVED_STATE_RESOLUTION",
        "mapping_inferred_from_marginals": False,
        "finality_audit_status": "PASS_EXACT_MATCH",
        "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_FINAL_SCORING_AUDIT",
        "state_catalogue_sha256": "a" * 64,
        "player_universe_sha256": "b" * 64,
        "mapping_source_sha256": "c" * 64,
        "resolver_name": "official-outcome-state-resolver",
        "resolver_version": "1.0.0",
        "observed_state_id": "state-a",
        "mapped_player_count": 2,
        "missing_player_count": 0,
        "unexpected_player_count": 0,
    }


class TestJointForecastOutcomePairing(unittest.TestCase):
    def _build(self, forecasts=None, mappings=None):
        forecasts = forecasts or [_forecast()]
        mappings = mappings or [_mapping()]
        with patch(
            "m4_covar_joint_forecast_outcome_pairing.validate_joint_forecast_acceptance",
            return_value={
                "acceptance_status": "STRUCTURAL_AND_COMPLETE_PROVENANCE_BYTES_VERIFIED",
                "complete_provenance_chain_verified": True,
                "source_bytes_rehashed": True,
                "forecast_payload_bytes_verified": True,
            },
        ) as accept:
            result = build_joint_forecast_outcome_pairs(
                forecasts=forecasts,
                realized_state_mappings=mappings,
                split_gameweeks={"train": ["1"], "validation": ["2"], "test": ["3"]},
                archive_root="/private/archive",
                archive_manifest=[],
            )
            accept.assert_called_once()
            return result

    def test_builds_calibration_rows_only_after_archive_acceptance(self):
        result = self._build()
        self.assertEqual(result["pairing_status"], "PASS_ARCHIVED_FORECASTS_PAIRED_WITH_EXPLICIT_RECONCILED_STATES")
        self.assertEqual(result["forecast_count"], 1)
        self.assertEqual(result["gameweek_count"], 1)
        self.assertEqual(result["calibration_forecasts"][0]["observed_state_id"], "state-a")
        self.assertFalse(result["observed_state_mapping_inferred_from_marginals"])
        self.assertFalse(result["historical_forecast_availability_authenticated"])
        self.assertFalse(result["production_eligible"])
        self.assertEqual(result["decision_weight"], 0.0)

    def test_allows_multiple_forecasts_in_same_gameweek_with_same_mapping(self):
        result = self._build([
            _forecast("forecast-gw1-a"),
            _forecast("forecast-gw1-b", "2026-08-01T09:30:00Z"),
        ])
        self.assertEqual(result["forecast_count"], 2)
        self.assertEqual(result["gameweek_count"], 1)
        self.assertEqual(result["paired_gameweeks"][0]["forecast_count"], 2)

    def test_rejects_unaccepted_archive(self):
        with patch(
            "m4_covar_joint_forecast_outcome_pairing.validate_joint_forecast_acceptance",
            return_value={"acceptance_status": "STRUCTURAL_DATASET_ACCEPTED"},
        ):
            with self.assertRaisesRegex(JointForecastOutcomePairingError, "complete archived"):
                build_joint_forecast_outcome_pairs(
                    forecasts=[_forecast()],
                    realized_state_mappings=[_mapping()],
                    split_gameweeks={"train": ["1"], "validation": ["2"], "test": ["3"]},
                    archive_root="/private/archive",
                    archive_manifest=[],
                )

    def test_rejects_missing_or_inferred_observed_state_mapping(self):
        mapping = _mapping()
        mapping["mapping_inferred_from_marginals"] = True
        with self.assertRaisesRegex(JointForecastOutcomePairingError, "cannot be inferred"):
            self._build(mappings=[mapping])

    def test_rejects_failed_finality_audit(self):
        mapping = _mapping()
        mapping["finality_audit_status"] = "FAIL_MISMATCH"
        with self.assertRaisesRegex(JointForecastOutcomePairingError, "finality audit"):
            self._build(mappings=[mapping])

    def test_rejects_catalogue_or_player_universe_mismatch(self):
        forecast = _forecast()
        forecast["state_catalogue_sha256"] = "d" * 64
        with self.assertRaisesRegex(JointForecastOutcomePairingError, "catalogue hashes differ"):
            self._build(forecasts=[forecast])
        forecast = _forecast()
        forecast["player_universe_sha256"] = "d" * 64
        with self.assertRaisesRegex(JointForecastOutcomePairingError, "player universe hashes differ"):
            self._build(forecasts=[forecast])

    def test_rejects_incomplete_player_coverage(self):
        mapping = _mapping()
        mapping["missing_player_count"] = 1
        with self.assertRaisesRegex(JointForecastOutcomePairingError, "coverage is not exact"):
            self._build(mappings=[mapping])

    def test_rejects_observed_state_outside_declared_catalogue(self):
        mapping = _mapping()
        mapping["observed_state_id"] = "not-in-catalogue"
        with self.assertRaisesRegex(JointForecastOutcomePairingError, "complete forecast state catalogue"):
            self._build(mappings=[mapping])

    def test_rejects_inconsistent_realized_state_for_snapshots_in_same_gameweek(self):
        mappings = [_mapping()]
        forecasts = [_forecast(), _forecast("forecast-gw1-b", "2026-08-01T09:30:00Z")]
        mapping = _mapping()
        mapping["observed_state_id"] = "state-b"
        # Duplicate mapping keys are rejected before forecasts are processed.
        with self.assertRaisesRegex(JointForecastOutcomePairingError, "duplicate realized state mapping"):
            self._build(forecasts=forecasts, mappings=mappings + [mapping])

    def test_rejects_mapping_for_gameweek_without_forecast(self):
        mapping = _mapping()
        extra = _mapping()
        extra["gameweek_id"] = "9"
        with self.assertRaisesRegex(JointForecastOutcomePairingError, "without forecasts"):
            self._build(mappings=[mapping, extra])

    def test_rejects_non_retroactive_label_claim(self):
        mapping = _mapping()
        mapping["point_in_time_status"] = "POINT_IN_TIME"
        with self.assertRaisesRegex(JointForecastOutcomePairingError, "retain retrospective status"):
            self._build(mappings=[mapping])


if __name__ == "__main__":
    unittest.main()
