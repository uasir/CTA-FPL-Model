import base64
import hashlib
import json
from pathlib import Path

import pytest

from m3_covar_real_archive_preflight import (
    M3CoVarArchivePreflightError,
    run_preflight,
)


def write_fixture(root: Path, *, available_at: str = "2026-11-21T08:00:15Z"):
    archive = root / "private-archive" / "2026-27" / "gw11" / "source-run-44809552413"
    archive.mkdir(parents=True)
    raw_provider = b'{"players":[]}'
    raw_metadata = b'{"elements":[]}'
    bundle = {
        "bundle_type": "M3_CONVENTIONAL_FORECAST_ONLY_COVAR_INPUT",
        "season": "2026-27",
        "target_gameweek": 11,
        "forecast_snapshot_id": "fplcat-gw11-20261120T201442368955Z",
        "model_version": "external:FPL Cat:published xP:public next-gameweek JSON API:api/v1",
        "as_of_utc": "2026-11-20T20:14:42.975478Z",
        "deadline_utc": "2026-11-21T11:00:00Z",
        "point_in_time_status": "M3_SOURCE_TIMESTAMPS_VALIDATED",
        "decision_weight": 0.0,
        "production_eligible": False,
        "privacy": {
            "manager_identity_included": False,
            "manager_squad_included": False,
            "bank_or_transfer_state_included": False,
            "frozen_decision_included": False,
        },
        "source_archives": [
            {
                "source_type": "provider_forecast",
                "source_url": "https://provider.example/xp",
                "raw_snapshot_id": "sha256:" + hashlib.sha256(raw_provider).hexdigest(),
                "captured_at_utc": "2026-11-20T20:14:42Z",
                "raw_payload_base64": base64.b64encode(raw_provider).decode(),
                "raw_sha256": hashlib.sha256(raw_provider).hexdigest(),
            },
            {
                "source_type": "player_metadata",
                "source_url": "https://fpl.example/bootstrap",
                "raw_snapshot_id": "sha256:" + hashlib.sha256(raw_metadata).hexdigest(),
                "captured_at_utc": "2026-11-20T20:14:42Z",
                "raw_payload_base64": base64.b64encode(raw_metadata).decode(),
                "raw_sha256": hashlib.sha256(raw_metadata).hexdigest(),
            },
        ],
    }
    bundle_bytes = (json.dumps(bundle, sort_keys=True) + "\n").encode()
    bundle_path = archive / "m3_covar_forecast_gw11.json"
    bundle_path.write_bytes(bundle_bytes)
    manifest = {
        "archive_type": "PRIVATE_MANAGER_FREE_M3_COVAR_FORECAST_ARCHIVE",
        "season": bundle["season"],
        "target_gameweek": bundle["target_gameweek"],
        "forecast_snapshot_id": bundle["forecast_snapshot_id"],
        "model_version": bundle["model_version"],
        "as_of_utc": bundle["as_of_utc"],
        "deadline_utc": bundle["deadline_utc"],
        "point_in_time_status": bundle["point_in_time_status"],
        "bundle_sha256": hashlib.sha256(bundle_bytes).hexdigest(),
        "bundle_bytes": len(bundle_bytes),
    }
    manifest_path = archive / "archive_manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    finality = root / "finality"
    (finality / "covar-finality-result").mkdir(parents=True)
    (finality / "covar-finality-captures" / "event_1").mkdir(parents=True)
    (finality / "covar-finality-result" / "finality_batch_report.json").write_text(json.dumps({
        "status": "PASS_ALL_EVENTS",
        "season": "2026-27",
        "events_checked": [1],
        "event_count": 1,
        "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_FINAL_SCORING_AUDIT",
    }))
    (finality / "covar-finality-captures" / "event_1" / "capture_manifest.json").write_text(json.dumps({
        "source_snapshots": [{
            "source_id": "event_live",
            "available_at_utc": available_at,
            "retrieved_at_utc": available_at,
        }]
    }))
    return bundle_path, manifest_path, finality


def test_blocks_realistic_late_finality_capture_before_running_producer(tmp_path):
    bundle, manifest, finality = write_fixture(tmp_path)
    report = run_preflight(
        bundle_path=bundle,
        archive_manifest_path=manifest,
        finality_dir=finality,
    )
    assert report["archive_verified"] is True
    assert report["status"] == "BLOCKED_OUTCOME_AVAILABILITY_AFTER_TRAINING_CUTOFF"
    assert report["outcome_availability_after_training_cutoff"] is True
    assert report["producer_invoked"] is False
    assert report["scenario_count"] == 0
    assert report["decision_weight"] == 0.0
    assert report["production_eligible"] is False


def test_finality_only_archive_does_not_substitute_for_forecast_residual_panel(tmp_path):
    bundle, manifest, finality = write_fixture(
        tmp_path, available_at="2026-11-20T19:00:00Z"
    )
    report = run_preflight(
        bundle_path=bundle,
        archive_manifest_path=manifest,
        finality_dir=finality,
    )
    assert report["status"] == "BLOCKED_NO_REAL_MATCHED_FORECAST_OUTCOME_PANEL"
    assert report["matched_panel_supplied"] is False
    assert report["producer_invoked"] is False
    assert report["scenario_count"] == 0


def test_rejects_tampered_private_archive_bundle(tmp_path):
    bundle, manifest, finality = write_fixture(
        tmp_path, available_at="2026-11-20T19:00:00Z"
    )
    bundle.write_bytes(bundle.read_bytes() + b" ")
    with pytest.raises(M3CoVarArchivePreflightError, match="SHA-256"):
        run_preflight(
            bundle_path=bundle,
            archive_manifest_path=manifest,
            finality_dir=finality,
        )
