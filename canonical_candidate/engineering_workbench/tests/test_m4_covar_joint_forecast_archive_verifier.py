from __future__ import annotations
import hashlib
import pytest

from m4_covar_joint_forecast_archive_verifier import (
    JointForecastArchiveVerificationError, verify_joint_forecast_archive,
)


def make_forecast(payloads=None):
    payloads = payloads or {
        "source": b"source bytes", "model": b"model bytes",
        "config": b"config bytes", "forecast": b"forecast payload",
    }
    return {
        "forecast_id": "f1",
        "provenance": {
            "model_artifact_sha256": hashlib.sha256(payloads["model"]).hexdigest(),
            "config_sha256": hashlib.sha256(payloads["config"]).hexdigest(),
            "forecast_payload_sha256": hashlib.sha256(payloads["forecast"]).hexdigest(),
            "source_snapshots": [{
                "source_id": "api-static",
                "content_sha256": hashlib.sha256(payloads["source"]).hexdigest(),
            }],
        },
    }


def write_manifest(root, payloads=None):
    payloads = payloads or {
        "source": b"source bytes", "model": b"model bytes",
        "config": b"config bytes", "forecast": b"forecast payload",
    }
    mapping = [
        ("source_snapshot", "source", "source.bin", "source_id"),
        ("model_artifact", "model", "model.bin", None),
        ("config", "config", "config.bin", None),
        ("forecast_payload", "forecast", "forecast.bin", None),
    ]
    entries = []
    for kind, key, filename, id_field in mapping:
        (root / filename).write_bytes(payloads[key])
        entry = {"forecast_id": "f1", "artifact_type": kind, "archive_path": filename}
        if id_field:
            entry[id_field] = "api-static"
        entries.append(entry)
    return entries


def test_rehashes_complete_provenance_chain(tmp_path):
    report = verify_joint_forecast_archive([make_forecast()], tmp_path, write_manifest(tmp_path))
    assert report["verification_status"] == "COMPLETE_PROVENANCE_CHAIN_BYTES_VERIFIED"
    assert report["verified_artifact_count"] == 4
    assert report["verified_source_count"] == 1
    assert report["verified_model_artifact_count"] == 1
    assert report["verified_config_count"] == 1
    assert report["verified_forecast_payload_count"] == 1
    assert report["complete_provenance_chain_verified"] is True
    assert report["source_bytes_rehashed"] is True
    assert report["model_artifact_bytes_verified"] is True
    assert report["config_bytes_verified"] is True
    assert report["forecast_payload_bytes_verified"] is True
    assert report["provider_availability_authenticated"] is False
    assert report["production_eligible"] is False


@pytest.mark.parametrize("key", ["source", "model", "config", "forecast"])
def test_rejects_digest_mismatch_for_each_artifact_class(tmp_path, key):
    entries = write_manifest(tmp_path)
    (tmp_path / {"source":"source.bin","model":"model.bin","config":"config.bin","forecast":"forecast.bin"}[key]).write_bytes(b"tampered")
    with pytest.raises(JointForecastArchiveVerificationError, match="SHA-256 mismatch"):
        verify_joint_forecast_archive([make_forecast()], tmp_path, entries)


def test_rejects_missing_archive_entry(tmp_path):
    entries = write_manifest(tmp_path)
    with pytest.raises(JointForecastArchiveVerificationError, match="missing 1"):
        verify_joint_forecast_archive([make_forecast()], tmp_path, entries[:-1])


def test_rejects_unknown_archive_entry(tmp_path):
    entries = write_manifest(tmp_path)
    entries.append({"forecast_id":"f1","artifact_type":"mystery","archive_path":"x"})
    with pytest.raises(JointForecastArchiveVerificationError, match="unknown artifact_type"):
        verify_joint_forecast_archive([make_forecast()], tmp_path, entries)


def test_rejects_unknown_forecast_artifact_mapping(tmp_path):
    entries = write_manifest(tmp_path)
    entries[1]["forecast_id"] = "unknown"
    with pytest.raises(JointForecastArchiveVerificationError, match="unknown artifact"):
        verify_joint_forecast_archive([make_forecast()], tmp_path, entries)


@pytest.mark.parametrize("path", ["../outside.bin", "/tmp/outside.bin"])
def test_rejects_path_traversal_and_absolute_paths(tmp_path, path):
    entries = write_manifest(tmp_path)
    entries[0]["archive_path"] = path
    with pytest.raises(JointForecastArchiveVerificationError, match="unsafe archive path"):
        verify_joint_forecast_archive([make_forecast()], tmp_path, entries)


def test_rejects_symlink_archive_file(tmp_path):
    entries = write_manifest(tmp_path)
    target = tmp_path / "target.bin"
    target.write_bytes(b"source bytes")
    link = tmp_path / "link.bin"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this platform")
    entries[0]["archive_path"] = "link.bin"
    with pytest.raises(JointForecastArchiveVerificationError, match="symlink"):
        verify_joint_forecast_archive([make_forecast()], tmp_path, entries)


def test_rejects_duplicate_manifest_entries(tmp_path):
    entries = write_manifest(tmp_path)
    with pytest.raises(JointForecastArchiveVerificationError, match="duplicate archive"):
        verify_joint_forecast_archive([make_forecast()], tmp_path, entries + [entries[0]])
