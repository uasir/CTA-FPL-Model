from __future__ import annotations

import base64
import hashlib
import json
import unittest

import m4_covar_conventional_forecast_capture as capture


class TestConventionalForecastCapture(unittest.TestCase):
    def setUp(self):
        self.provider_raw = json.dumps({
            "gameweek": 12,
            "deadline": "2026-11-28T11:00:00Z",
            "computed_at": "2026-11-27T08:00:00Z",
            "players": [{"id": 10, "xp": 4.7, "expected_minutes": 75}],
        }).encode()
        self.bootstrap_raw = json.dumps({
            "events": [{"id": 12, "deadline_time": "2026-11-28T11:00:00Z"}],
            "element_types": [{"id": 3, "singular_name_short": "MID"}],
            "elements": [{"id": 10, "now_cost": 50, "element_type": 3, "team": 1}],
        }).encode()
        self.provider_hash = hashlib.sha256(self.provider_raw).hexdigest()
        self.bootstrap_hash = hashlib.sha256(self.bootstrap_raw).hexdigest()
        self.captured = {
            "provider_snapshot": {
                "snapshot_id": "fplcat-gw12-test",
                "season": "2026-27",
                "target_gameweek": 12,
                "provider": {"name": "FPL Cat", "product": "published xP", "variant": "public next-gameweek JSON API", "version": "api/v1"},
                "timing": {
                    "generated_at_utc": "2026-11-27T08:00:00Z",
                    "captured_at_utc": "2026-11-27T08:05:00Z",
                    "deadline_utc": "2026-11-28T11:00:00Z",
                },
                "source": {"url": "https://fplcat.com/api/v1/projections", "raw_snapshot_id": f"sha256:{self.provider_hash}", "raw_sha256": self.provider_hash},
                "grain": "player_gameweek",
                "records": [{"fpl_element_id": 10, "expected_points": 4.7, "expected_minutes": 75}],
                "coverage": {"row_count": 1, "expected_player_universe": 1, "identity_mapped_count": 1},
            },
            "player_metadata": [{"fpl_element_id": 10, "price": 5.0, "position": "MID", "team_id": 1}],
            "raw_archives": {
                "provider_response_base64": base64.b64encode(self.provider_raw).decode(),
                "fpl_bootstrap_response_base64": base64.b64encode(self.bootstrap_raw).decode(),
            },
            "player_metadata_provenance": {
                "source_url": "https://fantasy.premierleague.com/api/bootstrap-static/",
                "raw_snapshot_id": f"sha256:{self.bootstrap_hash}",
                "raw_sha256": self.bootstrap_hash,
                "captured_at_utc": "2026-11-27T08:06:00Z",
                "row_count": 1,
            },
        }

    def test_captures_exact_m3_compatible_forecast_without_manager_data(self):
        result = capture.capture_conventional_forecast(
            season="2026-27",
            capture=lambda **kwargs: self.captured,
            clock=lambda: "2026-11-27T08:10:00Z",
        )
        self.assertEqual(result["bundle_type"], "M3_CONVENTIONAL_FORECAST_ONLY_COVAR_INPUT")
        self.assertEqual(result["forecast_snapshot_id"], "fplcat-gw12-test")
        self.assertEqual(result["player_forecasts"][0]["expected_points"], 4.7)
        self.assertFalse(result["privacy"]["manager_identity_included"])
        self.assertNotIn("manager_team_id", result)
        self.assertNotIn("manager_state", result)
        self.assertEqual(len(result["source_archives"]), 2)
        self.assertEqual(result["decision_weight"], 0.0)
        self.assertFalse(result["production_eligible"])

    def test_rejects_provider_hash_mismatch(self):
        self.captured["provider_snapshot"]["source"]["raw_sha256"] = "a" * 64
        with self.assertRaisesRegex(capture.ConventionalForecastCaptureError, "provider source hash"):
            capture.capture_conventional_forecast(
                season="2026-27", capture=lambda **kwargs: self.captured,
                clock=lambda: "2026-11-27T08:10:00Z",
            )

    def test_rejects_undisclosed_provider_generation_time(self):
        self.captured["provider_snapshot"]["timing"]["generated_at_utc"] = None
        with self.assertRaisesRegex(capture.ConventionalForecastCaptureError, "generation time is undisclosed"):
            capture.capture_conventional_forecast(
                season="2026-27", capture=lambda **kwargs: self.captured,
                clock=lambda: "2026-11-27T08:10:00Z",
            )


if __name__ == "__main__":
    unittest.main()
