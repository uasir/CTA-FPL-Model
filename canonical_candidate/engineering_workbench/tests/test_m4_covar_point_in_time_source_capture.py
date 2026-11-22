from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from m4_covar_point_in_time_source_capture import (
    SourceCaptureError,
    capture_public_sources,
    fetch_source_bytes,
)


def test_capture_archives_exact_public_bytes_with_conservative_retrieval_timestamps(tmp_path):
    responses = [
        b'{"events":[]}',
        b'[]',
        b'{"elements":[]}',
    ]
    calls = []
    clock_values = iter([
        "2026-11-21T05:00:01Z",
        "2026-11-21T05:00:02Z",
        "2026-11-21T05:00:03Z",
    ])

    def fetch(url):
        calls.append(url)
        return responses[len(calls) - 1]

    result = capture_public_sources(
        12, (tmp_path / "private_archive").resolve(),
        fetch=fetch, clock=lambda: next(clock_values), sleep=lambda _: None,
    )
    archive = Path(result["archive_directory"])
    manifest = json.loads(Path(result["manifest_path"]).read_text())
    assert result["status"] == "PUBLIC_SOURCE_BYTES_CAPTURED"
    assert len(calls) == 3
    assert manifest["point_in_time_policy"]["historical_reconstruction"] is False
    assert manifest["manager_data_included"] is False
    assert [row["retrieved_at_utc"] for row in manifest["source_snapshots"]] == [
        "2026-11-21T05:00:01Z",
        "2026-11-21T05:00:02Z",
        "2026-11-21T05:00:03Z",
    ]
    for row, expected in zip(manifest["source_snapshots"], responses):
        archived = (archive / row["archive_path"]).read_bytes()
        assert archived == expected
        assert row["content_sha256"] == hashlib.sha256(expected).hexdigest()
        assert row["available_at_utc"] == row["retrieved_at_utc"]
    assert (archive.stat().st_mode & 0o777) == 0o700
    assert (archive / "capture_manifest.json").stat().st_mode & 0o777 == 0o600


def test_rejects_relative_output_and_existing_directory(tmp_path):
    with pytest.raises(ValueError, match="absolute"):
        capture_public_sources(1, Path("relative"))
    existing = tmp_path / "exists"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        capture_public_sources(1, existing.resolve())


def test_rejects_nonpositive_event_and_nonofficial_urls():
    with pytest.raises(ValueError, match="positive"):
        capture_public_sources(0, Path("/tmp/not-created"))
    with pytest.raises(SourceCaptureError, match="only official"):
        fetch_source_bytes("https://example.com/api/bootstrap-static/")


def test_failed_capture_is_marked_incomplete_and_not_presented_as_complete(tmp_path):
    calls = 0

    def fetch(_url):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise SourceCaptureError("simulated failure")
        return b'{}'

    target = (tmp_path / "partial").resolve()
    with pytest.raises(SourceCaptureError):
        capture_public_sources(5, target, fetch=fetch, clock=lambda: "2026-11-21T05:00:00Z", sleep=lambda _: None)
    assert (target / "CAPTURE_INCOMPLETE").exists()
    assert not (target / "capture_manifest.json").exists()



def test_manifest_records_github_actions_run_identity_without_credentials(tmp_path, monkeypatch):
    values = {
        "GITHUB_REPOSITORY": "uasir/CTA-FPL-Model",
        "GITHUB_WORKFLOW": "CTA FPL point-in-time public source capture",
        "GITHUB_WORKFLOW_REF": "uasir/CTA-FPL-Model/.github/workflows/cta-fpl-point-in-time-source-capture.yml@refs/heads/main",
        "GITHUB_SHA": "a" * 40,
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_RUN_ID": "123456",
        "GITHUB_RUN_ATTEMPT": "2",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    responses = iter([b'{}', b'[]', b'{}'])
    result = capture_public_sources(
        14, (tmp_path / "run_context").resolve(),
        fetch=lambda _: next(responses),
        clock=lambda: "2026-11-21T05:00:00Z",
        sleep=lambda _: None,
    )
    manifest = json.loads(Path(result["manifest_path"]).read_text())
    assert manifest["capture_context"] == {
        "repository": values["GITHUB_REPOSITORY"],
        "workflow": values["GITHUB_WORKFLOW"],
        "workflow_ref": values["GITHUB_WORKFLOW_REF"],
        "git_commit_sha": values["GITHUB_SHA"],
        "git_ref": values["GITHUB_REF"],
        "actions_run_id": values["GITHUB_RUN_ID"],
        "actions_run_attempt": values["GITHUB_RUN_ATTEMPT"],
    }
