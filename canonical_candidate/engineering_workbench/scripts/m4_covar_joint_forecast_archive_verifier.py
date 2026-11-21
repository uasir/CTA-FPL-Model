"""Verify archived source and forecast-artifact bytes against provenance SHA-256 declarations."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence


class JointForecastArchiveVerificationError(ValueError):
    """Archived bytes are missing, unsafe, or fail digest verification."""


def verify_joint_forecast_archive(
    forecasts: Sequence[Mapping[str, Any]],
    archive_root: str | Path,
    archive_manifest: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Rehash every declared source, model, config and forecast-payload artifact.

    Manifest rows use forecast_id, artifact_type, archive_path and, only for
    source_snapshot rows, source_id. Expected hashes always come from forecast
    provenance. Exactly one row is required for each declared artifact.
    """
    if not isinstance(forecasts, Sequence) or isinstance(forecasts, (str, bytes)) or not forecasts:
        raise JointForecastArchiveVerificationError("forecasts must be a non-empty sequence")
    if not isinstance(archive_manifest, Sequence) or isinstance(archive_manifest, (str, bytes)):
        raise JointForecastArchiveVerificationError("archive_manifest must be a sequence")

    root = Path(archive_root).resolve()
    if not root.exists() or not root.is_dir():
        raise JointForecastArchiveVerificationError("archive_root must be an existing directory")

    expected: dict[tuple[str, str, str], str] = {}
    for row in forecasts:
        if not isinstance(row, Mapping):
            raise JointForecastArchiveVerificationError("each forecast must be an object")
        fid, provenance = row.get("forecast_id"), row.get("provenance")
        if not isinstance(fid, str) or not fid.strip() or not isinstance(provenance, Mapping):
            raise JointForecastArchiveVerificationError("forecast ID and provenance are required")
        declarations = (
            ("model_artifact", "model_artifact_sha256"),
            ("config", "config_sha256"),
            ("forecast_payload", "forecast_payload_sha256"),
        )
        for artifact_type, field in declarations:
            digest = provenance.get(field)
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdefABCDEF" for c in digest):
                raise JointForecastArchiveVerificationError(f"{fid}/{artifact_type}: invalid declared SHA-256")
            expected[(fid, artifact_type, "")] = digest.lower()

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
            key = (fid, "source_snapshot", sid)
            if key in expected:
                raise JointForecastArchiveVerificationError(f"duplicate provenance source {fid}/{sid}")
            expected[key] = digest.lower()

    supplied: dict[tuple[str, str, str], str] = {}
    allowed = {"source_snapshot", "model_artifact", "config", "forecast_payload"}
    for entry in archive_manifest:
        if not isinstance(entry, Mapping):
            raise JointForecastArchiveVerificationError("each archive manifest entry must be an object")
        fid, artifact_type, relative = entry.get("forecast_id"), entry.get("artifact_type"), entry.get("archive_path")
        if artifact_type is None:
            artifact_type = "source_snapshot"  # backward-compatible source manifest shape
        sid = entry.get("source_id", "") if artifact_type == "source_snapshot" else ""
        if artifact_type not in allowed:
            raise JointForecastArchiveVerificationError(f"unknown artifact_type: {artifact_type}")
        if not isinstance(fid, str) or not isinstance(relative, str) or not relative.strip():
            raise JointForecastArchiveVerificationError("manifest requires forecast_id and archive_path")
        if artifact_type == "source_snapshot" and (not isinstance(sid, str) or not sid.strip()):
            raise JointForecastArchiveVerificationError("source_snapshot manifest rows require source_id")
        key = (fid, artifact_type, sid)
        if key in supplied:
            raise JointForecastArchiveVerificationError(f"duplicate archive manifest entry {key}")
        if key not in expected:
            raise JointForecastArchiveVerificationError(f"archive manifest contains unknown artifact {key}")
        supplied[key] = relative

    missing = set(expected) - set(supplied)
    if missing:
        raise JointForecastArchiveVerificationError(f"archive is missing {len(missing)} declared artifact file(s)")

    verified = []
    for key, relative in supplied.items():
        rel = Path(relative)
        label = "/".join(part for part in key if part)
        if rel.is_absolute() or ".." in rel.parts:
            raise JointForecastArchiveVerificationError(f"{label}: unsafe archive path")
        candidate = root / rel
        current = root
        for part in rel.parts:
            current = current / part
            if current.is_symlink():
                raise JointForecastArchiveVerificationError(f"{label}: symlink archive paths are not allowed")
        resolved = candidate.resolve()
        if root not in resolved.parents:
            raise JointForecastArchiveVerificationError(f"{label}: archive path escapes archive_root")
        if not resolved.exists() or not resolved.is_file():
            raise JointForecastArchiveVerificationError(f"{label}: archived file is missing or not regular")
        digest = hashlib.sha256()
        with resolved.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        actual = digest.hexdigest()
        if actual != expected[key]:
            raise JointForecastArchiveVerificationError(
                f"{label}: SHA-256 mismatch (expected {expected[key]}, got {actual})"
            )
        verified.append({
            "forecast_id": key[0], "artifact_type": key[1],
            "artifact_id": key[2] or None, "sha256": actual,
        })

    counts = {kind: sum(item["artifact_type"] == kind for item in verified) for kind in sorted(allowed)}
    return {
        "schema_version": "2.0.0",
        "verification_status": "COMPLETE_PROVENANCE_CHAIN_BYTES_VERIFIED",
        "verified_artifact_count": len(verified),
        "verified_source_count": counts["source_snapshot"],
        "verified_model_artifact_count": counts["model_artifact"],
        "verified_config_count": counts["config"],
        "verified_forecast_payload_count": counts["forecast_payload"],
        "verified_artifacts": verified,
        "hash_algorithm": "SHA256",
        "complete_provenance_chain_verified": True,
        "source_bytes_rehashed": True,
        "model_artifact_bytes_verified": True,
        "config_bytes_verified": True,
        "forecast_payload_bytes_verified": True,
        "provider_availability_authenticated": False,
        "historical_capture_time_authenticated": False,
        "decision_weight": 0.0,
        "production_eligible": False,
    }
