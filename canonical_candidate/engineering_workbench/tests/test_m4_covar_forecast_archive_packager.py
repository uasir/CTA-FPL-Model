from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from m4_covar_forecast_archive_packager import (
    ForecastArchivePackagingError,
    package_forecast_archive,
)
from m4_covar_point_in_time_source_capture import capture_public_sources


def sha(data):
    return hashlib.sha256(data).hexdigest()


def make_capture(tmp_path):
    bodies = [b'{"events":[]}', b'[]', b'{"elements":[]}']
    index = 0

    def fetch(_url):
        nonlocal index
        body = bodies[index]
        index += 1
        return body

    result = capture_public_sources(
        12, (tmp_path / "capture").resolve(),
        fetch=fetch,
        clock=lambda: "2026-11-21T05:00:00Z",
        sleep=lambda _: None,
    )
    return Path(result["manifest_path"]), bodies


def make_forecast(tmp_path):
    model = tmp_path / "model.bin"
    config = tmp_path / "config.json"
    payload = tmp_path / "forecast.json"
    model.write_bytes(b"model-v1")
    config.write_bytes(b'{"temperature":0.2}')
    payload.write_bytes(b'{"joint_probabilities":{"A":0.7,"B":0.3}}')
    forecast = {
        "forecast_id": "forecast-gw12-001",
        "gameweek_id": "gw12",
        "as_of_utc": "2026-11-21T05:40:00Z",
        "training_cutoff_utc": "2026-11-21T05:10:00Z",
        "first_kickoff_utc": "2026-11-21T18:00:00Z",
        "provenance": {
            "model_artifact_sha256": sha(model.read_bytes()),
            "config_sha256": sha(config.read_bytes()),
            "forecast_payload_sha256": sha(payload.read_bytes()),
            "model_version": "model-v1",
            "config_version": "config-v1",
            "state_catalogue_version": "states-v1",
            "generated_at_utc": "2026-11-21T05:30:00Z",
            "model_training_cutoff_utc": "2026-11-21T05:10:00Z",
        },
    }
    return forecast, model, config, payload


def test_packages_and_rehashes_sources_model_config_and_forecast_payload(tmp_path):
    capture_manifest, bodies = make_capture(tmp_path)
    capture_doc = json.loads(capture_manifest.read_text())
    capture_doc["capture_context"] = {"actions_run_id": "987654", "git_commit_sha": "b" * 40}
    capture_manifest.write_text(json.dumps(capture_doc))
    forecast, model, config, payload = make_forecast(tmp_path)
    result = package_forecast_archive(
        forecast, capture_manifest, model, config, payload,
        (tmp_path / "complete_archive").resolve(),
    )
    assert result["status"] == "COMPLETE_FORECAST_ARCHIVE_VERIFIED"
    assert result["source_bytes_rehashed"] is True
    assert result["artifact_count"] == 6
    package = json.loads((Path(result["archive_directory"]) / "package_manifest.json").read_text())
    assert package["provenance_validation"]["authenticity_verified"] is False
    assert package["archive_verification"]["source_bytes_rehashed"] is True
    assert package["forecast"]["provenance"]["source_snapshots"][0]["retrieved_at_utc"] == "2026-11-21T05:00:00Z"
    assert package["source_capture_context"] == {"actions_run_id": "987654", "git_commit_sha": "b" * 40}
    assert package["forecast"]["provenance"]["source_capture_context"]["actions_run_id"] == "987654"
    assert package["decision_weight"] == 0
    assert package["production_eligible"] is False
    for row in package["archive_manifest"]:
        if row["artifact_type"] == "source_snapshot":
            archived = (Path(result["archive_directory"]) / row["archive_path"]).read_bytes()
            assert archived in bodies


def test_rejects_forecast_as_of_before_any_source_was_retrieved(tmp_path):
    capture_manifest, _ = make_capture(tmp_path)
    forecast, model, config, payload = make_forecast(tmp_path)
    forecast["as_of_utc"] = "2026-11-21T04:59:59Z"
    forecast["provenance"]["generated_at_utc"] = "2026-11-21T04:59:00Z"
    with pytest.raises(ForecastArchivePackagingError, match="not available by forecast generation time"):
        package_forecast_archive(
            forecast, capture_manifest, model, config, payload,
            (tmp_path / "too_early").resolve(),
        )


def test_rejects_artifact_hash_mismatch_and_marks_incomplete(tmp_path):
    capture_manifest, _ = make_capture(tmp_path)
    forecast, model, config, payload = make_forecast(tmp_path)
    config.write_bytes(b'{"tampered":true}')
    target = (tmp_path / "tampered_archive").resolve()
    with pytest.raises(ForecastArchivePackagingError, match="SHA-256 mismatch"):
        package_forecast_archive(forecast, capture_manifest, model, config, payload, target)
    assert (target / "PACKAGING_INCOMPLETE").exists()
    assert not (target / "package_manifest.json").exists()


def test_rejects_capture_manifest_with_incomplete_marker_status(tmp_path):
    capture_manifest, _ = make_capture(tmp_path)
    document = json.loads(capture_manifest.read_text())
    document["capture_status"] = "INCOMPLETE"
    capture_manifest.write_text(json.dumps(document))
    forecast, model, config, payload = make_forecast(tmp_path)
    with pytest.raises(ForecastArchivePackagingError, match="not marked complete"):
        package_forecast_archive(
            forecast, capture_manifest, model, config, payload,
            (tmp_path / "invalid_capture").resolve(),
        )



def test_rejects_source_manifest_that_backdates_availability_before_retrieval(tmp_path):
    capture_manifest, _ = make_capture(tmp_path)
    document = json.loads(capture_manifest.read_text())
    document["source_snapshots"][0]["available_at_utc"] = "2026-11-21T04:00:00Z"
    capture_manifest.write_text(json.dumps(document))
    forecast, model, config, payload = make_forecast(tmp_path)
    with pytest.raises(ForecastArchivePackagingError, match="availability must equal"):
        package_forecast_archive(
            forecast, capture_manifest, model, config, payload,
            (tmp_path / "backdated_source").resolve(),
        )


def test_rejects_source_retrieved_after_forecast_generation_even_if_before_as_of(tmp_path):
    capture_manifest, _ = make_capture(tmp_path)
    document = json.loads(capture_manifest.read_text())
    document["source_snapshots"][0]["retrieved_at_utc"] = "2026-11-21T05:35:00Z"
    document["source_snapshots"][0]["available_at_utc"] = "2026-11-21T05:35:00Z"
    capture_manifest.write_text(json.dumps(document))
    forecast, model, config, payload = make_forecast(tmp_path)
    with pytest.raises(ForecastArchivePackagingError, match="not available by forecast generation time"):
        package_forecast_archive(
            forecast, capture_manifest, model, config, payload,
            (tmp_path / "after_generation").resolve(),
        )
