from __future__ import annotations
import copy
import hashlib
import pytest

from m4_covar_joint_forecast_acceptance import (
    JointForecastAcceptanceError, validate_joint_forecast_acceptance,
)

HASH = "a" * 64

def row(fid, gw, day):
    return {
        "forecast_id": fid, "gameweek_id": gw,
        "as_of_utc": f"2025-08-{day:02d}T10:00:00Z",
        "first_kickoff_utc": f"2025-08-{day:02d}T12:00:00Z",
        "training_cutoff_utc": f"2025-08-{day-1:02d}T23:00:00Z",
        "provenance": {
            "model_artifact_sha256": HASH, "model_version": "m1",
            "model_training_cutoff_utc": f"2025-08-{day-1:02d}T22:00:00Z",
            "config_sha256": "b"*64, "config_version": "c1",
            "state_catalogue_version": "states-v1",
            "forecast_payload_sha256": "c"*64,
            "generated_at_utc": f"2025-08-{day:02d}T09:59:00Z",
            "source_snapshots": [{
                "source_id": "source-a", "source_version": "v1",
                "content_sha256": "d"*64,
                "available_at_utc": f"2025-08-{day:02d}T08:00:00Z",
                "retrieved_at_utc": f"2025-08-{day:02d}T09:00:00Z",
            }],
        },
    }

def data():
    return [row("f-tr", "gw1", 2), row("f-va", "gw2", 9), row("f-te", "gw3", 16)]

def manifest():
    return {"train": ["gw1"], "validation": ["gw2"], "test": ["gw3"]}

def test_combines_temporal_and_provenance_validation():
    report = validate_joint_forecast_acceptance(data(), manifest())
    assert report["acceptance_status"] == "STRUCTURAL_DATASET_ACCEPTED"
    assert report["temporal_validation"]["validation_status"] == "CHRONOLOGICAL_SPLITS_VALIDATED"
    assert report["provenance_validation"]["validation_status"] == "PROVENANCE_METADATA_VALIDATED"
    assert report["historical_dataset_certified"] is False
    assert report["production_eligible"] is False

def test_fails_closed_when_temporal_validation_fails():
    bad = data()
    bad[2]["as_of_utc"] = "2025-08-15T12:01:00Z"
    with pytest.raises(JointForecastAcceptanceError, match="temporal validation failed"):
        validate_joint_forecast_acceptance(bad, manifest())

def test_fails_closed_when_provenance_is_missing():
    bad = data()
    del bad[1]["provenance"]
    with pytest.raises(JointForecastAcceptanceError, match="provenance validation failed"):
        validate_joint_forecast_acceptance(bad, manifest())

def test_fails_closed_when_source_is_not_point_in_time():
    bad = data()
    bad[0]["provenance"]["source_snapshots"][0]["retrieved_at_utc"] = "2025-08-01T10:01:00Z"
    with pytest.raises(JointForecastAcceptanceError, match="provenance validation failed"):
        validate_joint_forecast_acceptance(bad, manifest())

def test_preserves_repeated_forecasts_as_gameweek_cluster():
    repeated = data()
    extra = copy.deepcopy(repeated[0])
    extra["forecast_id"] = "f-tr-2"
    extra["as_of_utc"] = "2025-08-02T10:30:00Z"
    extra["provenance"]["generated_at_utc"] = "2025-08-02T10:29:00Z"
    extra["provenance"]["source_snapshots"][0]["retrieved_at_utc"] = "2025-08-02T09:30:00Z"
    report = validate_joint_forecast_acceptance(repeated + [extra], manifest())
    assert report["temporal_validation"]["split_forecast_row_counts"]["train"] == 2
    assert report["temporal_validation"]["repeated_forecasts_are_independent"] is False


def test_archive_verification_is_integrated_as_an_optional_third_stage(tmp_path):
    forecasts = data()
    entries = []
    for index, forecast in enumerate(forecasts):
        provenance = forecast["provenance"]
        artifacts = [
            ("source_snapshot", "source-a", f"source-{index}.bin", b"source-" + str(index).encode()),
            ("model_artifact", None, f"model-{index}.bin", b"model-" + str(index).encode()),
            ("config", None, f"config-{index}.bin", b"config-" + str(index).encode()),
            ("forecast_payload", None, f"payload-{index}.bin", b"payload-" + str(index).encode()),
        ]
        for kind, artifact_id, filename, payload in artifacts:
            (tmp_path / filename).write_bytes(payload)
            if kind == "source_snapshot":
                provenance["source_snapshots"][0]["content_sha256"] = hashlib.sha256(payload).hexdigest()
            elif kind == "model_artifact":
                provenance["model_artifact_sha256"] = hashlib.sha256(payload).hexdigest()
            elif kind == "config":
                provenance["config_sha256"] = hashlib.sha256(payload).hexdigest()
            else:
                provenance["forecast_payload_sha256"] = hashlib.sha256(payload).hexdigest()
            entry = {"forecast_id": forecast["forecast_id"], "artifact_type": kind, "archive_path": filename}
            if artifact_id:
                entry["source_id"] = artifact_id
            entries.append(entry)
    report = validate_joint_forecast_acceptance(
        forecasts, manifest(), archive_root=tmp_path, archive_manifest=entries,
    )
    assert report["acceptance_status"] == "STRUCTURAL_AND_COMPLETE_PROVENANCE_BYTES_VERIFIED"
    assert report["archive_validation"]["verified_artifact_count"] == 12
    assert report["source_bytes_rehashed"] is True
    assert report["model_artifact_bytes_verified"] is True
    assert report["config_bytes_verified"] is True
    assert report["forecast_payload_bytes_verified"] is True
    assert report["complete_provenance_chain_verified"] is True
    assert report["authenticity_verified"] is False
    assert report["historical_dataset_certified"] is False
    assert report["production_eligible"] is False


def test_archive_verification_fails_closed_on_digest_mismatch(tmp_path):
    forecasts = data()
    entries = []
    for index, forecast in enumerate(forecasts):
        for kind, field, payload in [
            ("source_snapshot", "content_sha256", b"source"),
            ("model_artifact", "model_artifact_sha256", b"model"),
            ("config", "config_sha256", b"config"),
            ("forecast_payload", "forecast_payload_sha256", b"payload"),
        ]:
            filename = f"{forecast['forecast_id']}-{kind}.bin"
            (tmp_path / filename).write_bytes(payload)
            if kind == "source_snapshot":
                forecast["provenance"]["source_snapshots"][0][field] = hashlib.sha256(payload).hexdigest()
            else:
                forecast["provenance"][field] = hashlib.sha256(payload).hexdigest()
            entry = {"forecast_id": forecast["forecast_id"], "artifact_type": kind, "archive_path": filename}
            if kind == "source_snapshot":
                entry["source_id"] = "source-a"
            entries.append(entry)
    (tmp_path / "f-tr-model_artifact.bin").write_bytes(b"tampered")
    with pytest.raises(JointForecastAcceptanceError, match="archive verification failed"):
        validate_joint_forecast_acceptance(forecasts, manifest(), tmp_path, entries)

def test_archive_verification_requires_both_arguments():
    with pytest.raises(JointForecastAcceptanceError, match="requires both"):
        validate_joint_forecast_acceptance(data(), manifest(), archive_root="/tmp/archive")
