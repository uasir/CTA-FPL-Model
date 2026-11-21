"""Verify archived source bytes against forecast provenance SHA-256 declarations."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence


class JointForecastArchiveVerificationError(ValueError):
    """Archived source bytes are missing, unsafe, or fail digest verification."""


def verify_joint_forecast_archive(
    forecasts: Sequence[Mapping[str, Any]],
    archive_root: str | Path,
    archive_manifest: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Rehash archived source files and match them to provenance declarations.

    Each manifest row contains forecast_id, source_id and a relative archive_path.
    The expected digest is taken from the corresponding forecast provenance,
    not trusted from the archive manifest. Paths must remain inside archive_root;
    symlinks and non-regular files are rejected.
    """
    if not isinstance(forecasts, Sequence) or isinstance(forecasts, (str, bytes)) or not forecasts:
        raise JointForecastArchiveVerificationError("forecasts must be a non-empty sequence")
    if not isinstance(archive_manifest, Sequence) or isinstance(archive_manifest, (str, bytes)):
        raise JointForecastArchiveVerificationError("archive_manifest must be a sequence")

    root = Path(archive_root).resolve()
    if not root.exists() or not root.is_dir():
        raise JointForecastArchiveVerificationError("archive_root must be an existing directory")

    expected = {}
    for row in forecasts:
        if not isinstance(row, Mapping):
            raise JointForecastArchiveVerificationError("each forecast must be an object")
        fid = row.get("forecast_id")
        provenance = row.get("provenance")
        if not isinstance(fid, str) or not fid.strip() or not isinstance(provenance, Mapping):
            raise JointForecastArchiveVerificationError("forecast ID and provenance are required")
        sources = provenance.get("source_snapshots")
        if not isinstance(sources, Sequence) or isinstance(sources, (str, bytes)) or not sources:
            raise JointForecastArchiveVerificationError(f"{fid}: source_snapshots are required")
        for source in sources:
            if not isinstance(source, Mapping):
                raise JointForecastArchiveVerificationError("each source snapshot must be an object")
            sid, digest = source.get("source_id"), source.get("content_sha256")
            if not isinstance(sid, str) or not sid.strip():
                raise JointForecastArchiveVerificationError("source_id must be non-empty")
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdefABCDEF" for c in digest):
                raise JointForecastArchiveVerificationError(f"{fid}/{sid}: invalid declared SHA-256")
            key = (fid, sid)
            if key in expected:
                raise JointForecastArchiveVerificationError(f"duplicate provenance source {fid}/{sid}")
            expected[key] = digest.lower()

    supplied = {}
    for entry in archive_manifest:
        if not isinstance(entry, Mapping):
            raise JointForecastArchiveVerificationError("each archive manifest entry must be an object")
        fid, sid, relative = entry.get("forecast_id"), entry.get("source_id"), entry.get("archive_path")
        if not isinstance(fid, str) or not isinstance(sid, str) or not isinstance(relative, str) or not relative.strip():
            raise JointForecastArchiveVerificationError("manifest requires forecast_id, source_id and archive_path")
        key = (fid, sid)
        if key in supplied:
            raise JointForecastArchiveVerificationError(f"duplicate archive manifest entry {fid}/{sid}")
        if key not in expected:
            raise JointForecastArchiveVerificationError(f"archive manifest contains unknown source {fid}/{sid}")
        supplied[key] = relative

    missing = set(expected) - set(supplied)
    if missing:
        raise JointForecastArchiveVerificationError(f"archive is missing {len(missing)} declared source file(s)")

    verified = []
    for key, relative in supplied.items():
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts:
            raise JointForecastArchiveVerificationError(f"{key[0]}/{key[1]}: unsafe archive path")
        candidate = root / rel
        # Reject symlinks in every path component, including the final file.
        current = root
        for part in rel.parts:
            current = current / part
            if current.is_symlink():
                raise JointForecastArchiveVerificationError(f"{key[0]}/{key[1]}: symlink archive paths are not allowed")
        resolved = candidate.resolve()
        if root not in resolved.parents:
            raise JointForecastArchiveVerificationError(f"{key[0]}/{key[1]}: archive path escapes archive_root")
        if not resolved.exists() or not resolved.is_file():
            raise JointForecastArchiveVerificationError(f"{key[0]}/{key[1]}: archived source file is missing or not regular")
        digest = hashlib.sha256()
        with resolved.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        actual = digest.hexdigest()
        if actual != expected[key]:
            raise JointForecastArchiveVerificationError(
                f"{key[0]}/{key[1]}: SHA-256 mismatch (expected {expected[key]}, got {actual})"
            )
        verified.append({"forecast_id": key[0], "source_id": key[1], "sha256": actual})

    return {
        "schema_version": "1.0.0",
        "verification_status": "ARCHIVED_SOURCE_BYTES_VERIFIED",
        "verified_source_count": len(verified),
        "verified_sources": verified,
        "hash_algorithm": "SHA256",
        "source_bytes_rehashed": True,
        "provider_availability_authenticated": False,
        "model_artifact_bytes_verified": False,
        "decision_weight": 0.0,
        "production_eligible": False,
    }
