from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

import pytest

import m3_covar_forecast_archive_packager as packager


def _sanitized_bundle():
    provider_raw = b'{"players":[{"id":10,"xp":4.5}]}'
    metadata_raw = b'{"elements":[{"id":10}]}'
    return {
        "schema_version": "1.0.0",
        "bundle_type": "M3_CONVENTIONAL_FORECAST_ONLY_COVAR_INPUT",
        "season": "2026-27",
        "target_gameweek": 12,
        "mode": "REGULAR_GW",
        "player_forecasts": [{"fpl_element_id": 10, "expected_points": 4.5, "expected_minutes": 75}],
        "as_of_utc": "2026-11-21T10:00:00+00:00",
        "deadline_utc": "2026-11-21T11:00:00+00:00",
        "forecast_snapshot_id": "provider-snapshot-12",
        "model_version": "m3-conventional-v1",
        "source_archives": [
            {
                "source_type": "provider_forecast",
                "raw_snapshot_id": "provider-raw-12",
                "raw_sha256": hashlib.sha256(provider_raw).hexdigest(),
                "captured_at_utc": "2026-11-21T09:50:00+00:00",
                "source_url": "https://provider.example/forecast",
                "raw_payload_base64": base64.b64encode(provider_raw).decode(),
            },
            {
                "source_type": "player_metadata",
                "raw_snapshot_id": "bootstrap-12",
                "raw_sha256": hashlib.sha256(metadata_raw).hexdigest(),
                "captured_at_utc": "2026-11-21T09:51:00+00:00",
                "source_url": "https://fantasy.premierleague.com/api/bootstrap-static/",
                "raw_payload_base64": base64.b64encode(metadata_raw).decode(),
            },
        ],
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


def _inputs(tmp_path: Path):
    evidence = tmp_path / "evidence.json"
    result = tmp_path / "result.json"
    evidence.write_text(json.dumps({"12": {"manager_team_id": 999}}), encoding="utf-8")
    result.write_text(json.dumps({"manager_team_id": 999, "frozen_decision": {"private": True}}), encoding="utf-8")
    return evidence, result


def test_packager_writes_private_manager_free_bundle_and_hash_manifest(tmp_path, monkeypatch):
    evidence, result = _inputs(tmp_path)
    output = tmp_path / "private-archive"
    monkeypatch.setattr(
        packager, "extract_m3_covar_forecast_bundle",
        lambda _evidence, _result: _sanitized_bundle(),
    )

    report = packager.package_m3_covar_forecast_archive(
        evidence_path=evidence, result_path=result, output_dir=output
    )

    bundle_path = output / "m3_covar_forecast_gw12.json"
    manifest_path = output / "archive_manifest.json"
    bundle_bytes = bundle_path.read_bytes()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bundle = json.loads(bundle_bytes)

    assert report["status"] == "PASS_MANAGER_FREE_ARCHIVE_CREATED"
    assert report["private_destination_configured"] is False
    assert manifest["bundle_sha256"] == hashlib.sha256(bundle_bytes).hexdigest()
    assert manifest["anchor_acceptance"]["acceptance_status"] == "ACCEPTED_PLAYER_LEVEL_FORECAST_ANCHOR_ONLY"
    assert report["anchor_acceptance_status"] == "ACCEPTED_PLAYER_LEVEL_FORECAST_ANCHOR_ONLY"
    assert report["joint_distribution_available"] is False
    assert bundle["forecast_snapshot_id"] == "provider-snapshot-12"
    assert "manager_team_id" not in bundle
    assert "frozen_decision" not in bundle
    assert (output.stat().st_mode & 0o777) == 0o700
    assert (bundle_path.stat().st_mode & 0o777) == 0o600
    assert (manifest_path.stat().st_mode & 0o777) == 0o600


def test_packager_refuses_existing_output_directory(tmp_path, monkeypatch):
    evidence, result = _inputs(tmp_path)
    output = tmp_path / "already-exists"
    output.mkdir()
    monkeypatch.setattr(
        packager, "extract_m3_covar_forecast_bundle",
        lambda _evidence, _result: _sanitized_bundle(),
    )

    with pytest.raises(packager.M3CoVarArchivePackagingError, match="already exists"):
        packager.package_m3_covar_forecast_archive(
            evidence_path=evidence, result_path=result, output_dir=output
        )


def test_packager_refuses_repository_output(tmp_path, monkeypatch):
    evidence, result = _inputs(tmp_path)
    monkeypatch.setattr(packager, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        packager, "extract_m3_covar_forecast_bundle",
        lambda _evidence, _result: _sanitized_bundle(),
    )

    with pytest.raises(packager.M3CoVarArchivePackagingError, match="outside the repository"):
        packager.package_m3_covar_forecast_archive(
            evidence_path=evidence, result_path=result, output_dir=tmp_path / "repo" / "archive"
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("decision_weight", 1.0),
        ("production_eligible", True),
        ("privacy", {"manager_identity_included": True}),
    ],
)
def test_packager_fails_closed_on_privacy_or_research_only_contract(tmp_path, monkeypatch, field, value):
    evidence, result = _inputs(tmp_path)
    output = tmp_path / "bad-archive"
    bundle = _sanitized_bundle()
    bundle[field] = value
    monkeypatch.setattr(
        packager, "extract_m3_covar_forecast_bundle",
        lambda _evidence, _result: bundle,
    )

    with pytest.raises(packager.M3CoVarArchivePackagingError):
        packager.package_m3_covar_forecast_archive(
            evidence_path=evidence, result_path=result, output_dir=output
        )
    assert not output.exists()
