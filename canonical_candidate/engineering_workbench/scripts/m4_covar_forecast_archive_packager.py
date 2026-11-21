"""Bind a captured FPL source set and exact forecast artifacts into a private archive."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
from pathlib import Path
from typing import Any, Mapping

from m4_covar_joint_forecast_archive_verifier import verify_joint_forecast_archive
from m4_covar_joint_forecast_provenance import validate_joint_forecast_provenance


class ForecastArchivePackagingError(ValueError):
    """A point-in-time forecast archive cannot be assembled safely."""


_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _private_copy(source: Path, destination: Path, expected_digest: str) -> str:
    if source.is_symlink() or not source.is_file():
        raise ForecastArchivePackagingError(f"archive input is not a regular non-symlink file: {source.name}")
    actual = _digest(source)
    if actual != expected_digest.lower():
        raise ForecastArchivePackagingError(f"SHA-256 mismatch for {source.name}")
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    with source.open("rb") as src, os.fdopen(fd, "wb") as dst:
        shutil.copyfileobj(src, dst)
        dst.flush()
        os.fsync(dst.fileno())
    return actual


def package_forecast_archive(
    forecast: Mapping[str, Any],
    capture_manifest_path: str | Path,
    model_artifact_path: str | Path,
    config_path: str | Path,
    forecast_payload_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Create and fully verify a private archive for one as-of forecast.

    The caller must provide the exact bytes used for the model, configuration,
    and forecast payload. Captured source bytes are bound to the forecast only
    when all retrieval timestamps are <= its as-of time.
    """
    if not isinstance(forecast, Mapping):
        raise ForecastArchivePackagingError("forecast must be an object")
    forecast_id = forecast.get("forecast_id")
    if not isinstance(forecast_id, str) or not forecast_id.strip():
        raise ForecastArchivePackagingError("forecast_id must be non-empty")
    provenance = forecast.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ForecastArchivePackagingError("forecast provenance is required")
    for field in ("model_artifact_sha256", "config_sha256", "forecast_payload_sha256"):
        value = provenance.get(field)
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            raise ForecastArchivePackagingError(f"{field} must be a SHA-256 digest")

    manifest_path = Path(capture_manifest_path).resolve()
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ForecastArchivePackagingError("capture manifest must be a regular file")
    capture_root = manifest_path.parent.resolve()
    try:
        capture = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ForecastArchivePackagingError("capture manifest is unreadable or invalid JSON") from exc
    if capture.get("capture_status") != "PUBLIC_SOURCE_BYTES_CAPTURED":
        raise ForecastArchivePackagingError("capture manifest is not marked complete")
    policy = capture.get("point_in_time_policy")
    if not isinstance(policy, Mapping) or policy.get("historical_reconstruction") is not False:
        raise ForecastArchivePackagingError("capture manifest has an unsupported historical-reconstruction status")
    source_rows = capture.get("source_snapshots")
    if not isinstance(source_rows, list) or not source_rows:
        raise ForecastArchivePackagingError("capture manifest has no source snapshots")

    as_of = forecast.get("as_of_utc")
    if not isinstance(as_of, str):
        raise ForecastArchivePackagingError("forecast as_of_utc is required")
    from datetime import datetime
    try:
        as_of_dt = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ForecastArchivePackagingError("forecast as_of_utc must be ISO-8601") from exc
    if as_of_dt.tzinfo is None or as_of_dt.utcoffset() is None:
        raise ForecastArchivePackagingError("forecast as_of_utc must include a timezone")

    target = Path(output_dir)
    if not target.is_absolute():
        raise ForecastArchivePackagingError("output_dir must be absolute")
    target = target.resolve()
    repository_root = Path(__file__).resolve().parents[3]
    if target.is_relative_to(repository_root):
        raise ForecastArchivePackagingError("archive output must be outside the repository")
    if target.exists():
        raise FileExistsError("refusing to overwrite an existing archive directory")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(mode=stat.S_IRWXU)
    archive_rows = []
    enriched = dict(forecast)
    enriched_provenance = dict(provenance)
    normalized_sources = []
    try:
        for index, source in enumerate(source_rows):
            if not isinstance(source, Mapping):
                raise ForecastArchivePackagingError("each capture source row must be an object")
            source_id = source.get("source_id")
            source_version = source.get("source_version")
            digest = source.get("content_sha256")
            relative = source.get("archive_path")
            retrieved = source.get("retrieved_at_utc")
            available = source.get("available_at_utc")
            if not all(isinstance(v, str) and v.strip() for v in (source_id, source_version, relative, retrieved, available)):
                raise ForecastArchivePackagingError("capture source metadata is incomplete")
            if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
                raise ForecastArchivePackagingError("capture source SHA-256 is invalid")
            try:
                retrieved_dt = datetime.fromisoformat(retrieved.replace("Z", "+00:00"))
                available_dt = datetime.fromisoformat(available.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ForecastArchivePackagingError("capture source timestamps must be ISO-8601") from exc
            if retrieved_dt.tzinfo is None or available_dt.tzinfo is None:
                raise ForecastArchivePackagingError("capture source timestamps must include timezones")
            if retrieved_dt > as_of_dt or available_dt > as_of_dt:
                raise ForecastArchivePackagingError("captured source was not available by forecast as-of")
            source_file = (capture_root / relative).resolve()
            if not source_file.is_relative_to(capture_root):
                raise ForecastArchivePackagingError("capture source path escapes archive directory")
            archive_name = f"source_{index:02d}_{hashlib.sha256(source_id.encode()).hexdigest()[:10]}.json"
            _private_copy(source_file, target / archive_name, digest)
            normalized_sources.append({
                "source_id": source_id,
                "source_version": source_version,
                "content_sha256": digest.lower(),
                "available_at_utc": available,
                "retrieved_at_utc": retrieved,
            })
            archive_rows.append({
                "forecast_id": forecast_id,
                "artifact_type": "source_snapshot",
                "source_id": source_id,
                "archive_path": archive_name,
            })

        artifact_inputs = (
            ("model_artifact", Path(model_artifact_path).resolve(), provenance["model_artifact_sha256"], "model_artifact.bin"),
            ("config", Path(config_path).resolve(), provenance["config_sha256"], "config.bin"),
            ("forecast_payload", Path(forecast_payload_path).resolve(), provenance["forecast_payload_sha256"], "forecast_payload.bin"),
        )
        for artifact_type, source_path, digest, archive_name in artifact_inputs:
            _private_copy(source_path, target / archive_name, digest)
            archive_rows.append({
                "forecast_id": forecast_id,
                "artifact_type": artifact_type,
                "archive_path": archive_name,
            })

        enriched_provenance["source_snapshots"] = normalized_sources
        enriched["provenance"] = enriched_provenance
        provenance_report = validate_joint_forecast_provenance([enriched])
        archive_report = verify_joint_forecast_archive([enriched], target, archive_rows)
        result = {
            "schema_version": "1.0.0",
            "packaging_status": "COMPLETE_FORECAST_ARCHIVE_VERIFIED",
            "forecast": enriched,
            "archive_manifest": archive_rows,
            "provenance_validation": provenance_report,
            "archive_verification": archive_report,
            "archive_directory": str(target),
            "historical_reconstruction": False,
            "decision_weight": 0.0,
            "production_eligible": False,
        }
        manifest_output = target / "package_manifest.json"
        fd = os.open(manifest_output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return {
            "status": result["packaging_status"],
            "forecast_id": forecast_id,
            "archive_directory": str(target),
            "artifact_count": len(archive_rows),
            "source_snapshot_count": len(normalized_sources),
            "source_bytes_rehashed": True,
            "historical_reconstruction": False,
            "decision_weight": 0.0,
            "production_eligible": False,
        }
    except Exception:
        marker = target / "PACKAGING_INCOMPLETE"
        try:
            marker.write_text("Archive packaging failed; do not use as complete.\n", encoding="utf-8")
            os.chmod(marker, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        raise
