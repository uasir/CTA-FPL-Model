from __future__ import annotations
import hashlib
import pytest

from m4_covar_joint_forecast_archive_verifier import (
    JointForecastArchiveVerificationError, verify_joint_forecast_archive,
)

def make_forecast(payload):
    return {
        "forecast_id": "f1",
        "provenance": {"source_snapshots": [{
            "source_id": "api-static", "content_sha256": hashlib.sha256(payload).hexdigest(),
        }]},
    }

def test_rehashes_and_verifies_archived_source_bytes(tmp_path):
    payload = b"immutable point-in-time source snapshot"
    (tmp_path / "source.bin").write_bytes(payload)
    report = verify_joint_forecast_archive(
        [make_forecast(payload)], tmp_path,
        [{"forecast_id": "f1", "source_id": "api-static", "archive_path": "source.bin"}],
    )
    assert report["verification_status"] == "ARCHIVED_SOURCE_BYTES_VERIFIED"
    assert report["verified_source_count"] == 1
    assert report["source_bytes_rehashed"] is True
    assert report["provider_availability_authenticated"] is False

def test_rejects_digest_mismatch(tmp_path):
    (tmp_path / "source.bin").write_bytes(b"changed bytes")
    with pytest.raises(JointForecastArchiveVerificationError, match="SHA-256 mismatch"):
        verify_joint_forecast_archive(
            [make_forecast(b"original bytes")], tmp_path,
            [{"forecast_id": "f1", "source_id": "api-static", "archive_path": "source.bin"}],
        )

def test_rejects_missing_archive_entry(tmp_path):
    with pytest.raises(JointForecastArchiveVerificationError, match="missing 1"):
        verify_joint_forecast_archive(
            [make_forecast(b"x")], tmp_path, [],
        )

def test_rejects_unknown_archive_entry(tmp_path):
    with pytest.raises(JointForecastArchiveVerificationError, match="unknown source"):
        verify_joint_forecast_archive(
            [make_forecast(b"x")], tmp_path,
            [{"forecast_id": "f1", "source_id": "unknown", "archive_path": "x"}],
        )

@pytest.mark.parametrize("path", ["../outside.bin", "/tmp/outside.bin"])
def test_rejects_path_traversal_and_absolute_paths(tmp_path, path):
    payload = b"x"
    with pytest.raises(JointForecastArchiveVerificationError, match="unsafe archive path"):
        verify_joint_forecast_archive(
            [make_forecast(payload)], tmp_path,
            [{"forecast_id": "f1", "source_id": "api-static", "archive_path": path}],
        )

def test_rejects_symlink_archive_file(tmp_path):
    payload = b"x"
    target = tmp_path / "target.bin"
    target.write_bytes(payload)
    link = tmp_path / "link.bin"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this platform")
    with pytest.raises(JointForecastArchiveVerificationError, match="symlink"):
        verify_joint_forecast_archive(
            [make_forecast(payload)], tmp_path,
            [{"forecast_id": "f1", "source_id": "api-static", "archive_path": "link.bin"}],
        )

def test_rejects_duplicate_manifest_entries(tmp_path):
    payload = b"x"
    (tmp_path / "source.bin").write_bytes(payload)
    item = {"forecast_id": "f1", "source_id": "api-static", "archive_path": "source.bin"}
    with pytest.raises(JointForecastArchiveVerificationError, match="duplicate archive"):
        verify_joint_forecast_archive([make_forecast(payload)], tmp_path, [item, item])
