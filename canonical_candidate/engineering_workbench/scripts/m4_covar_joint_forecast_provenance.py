"""Fail-closed provenance checks for historical joint Gameweek forecasts.

Checks traceability and point-in-time metadata; it cannot authenticate hashes or
prove that archived source bytes match the declared digests.
"""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Mapping, Sequence


class JointForecastProvenanceError(ValueError):
    """Missing, malformed, or temporally invalid forecast provenance."""


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise JointForecastProvenanceError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise JointForecastProvenanceError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise JointForecastProvenanceError(f"{field} must include a timezone")
    return parsed


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise JointForecastProvenanceError(f"{field} must be a non-empty string")
    return value.strip()


def _digest(value: Any, field: str) -> str:
    digest = _text(value, field).lower()
    if not _SHA256.fullmatch(digest):
        raise JointForecastProvenanceError(f"{field} must be a 64-character SHA-256 hex digest")
    return digest


def validate_joint_forecast_provenance(
    forecasts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate source/model/config traceability and point-in-time availability.

    Every forecast must carry a provenance object with model/config hashes and
    versions, a state-catalogue version, generation timestamp, model training
    cutoff, forecast-payload hash, and at least one versioned source snapshot.
    Source availability and retrieval timestamps must both be no later than the
    forecast as-of timestamp. This is structural validation, not authentication.
    """
    if not isinstance(forecasts, Sequence) or isinstance(forecasts, (str, bytes)) or not forecasts:
        raise JointForecastProvenanceError("forecasts must be a non-empty sequence")

    seen = set()
    source_count = 0
    source_ids = set()
    for row in forecasts:
        if not isinstance(row, Mapping):
            raise JointForecastProvenanceError("each forecast must be an object")
        forecast_id = _text(row.get("forecast_id"), "forecast_id")
        if forecast_id in seen:
            raise JointForecastProvenanceError("forecast IDs must be unique")
        seen.add(forecast_id)
        as_of = _time(row.get("as_of_utc"), "as_of_utc")
        cutoff = _time(row.get("training_cutoff_utc"), "training_cutoff_utc")
        provenance = row.get("provenance")
        if not isinstance(provenance, Mapping):
            raise JointForecastProvenanceError(f"{forecast_id}: provenance must be an object")

        _digest(provenance.get("model_artifact_sha256"), "model_artifact_sha256")
        _digest(provenance.get("config_sha256"), "config_sha256")
        _digest(provenance.get("forecast_payload_sha256"), "forecast_payload_sha256")
        _text(provenance.get("model_version"), "model_version")
        _text(provenance.get("config_version"), "config_version")
        _text(provenance.get("state_catalogue_version"), "state_catalogue_version")

        generated = _time(provenance.get("generated_at_utc"), "generated_at_utc")
        model_cutoff = _time(provenance.get("model_training_cutoff_utc"), "model_training_cutoff_utc")
        if generated > as_of:
            raise JointForecastProvenanceError(f"{forecast_id}: forecast generation is after forecast as-of")
        if model_cutoff > cutoff:
            raise JointForecastProvenanceError(f"{forecast_id}: model training cutoff exceeds declared training cutoff")
        if generated < model_cutoff:
            raise JointForecastProvenanceError(f"{forecast_id}: forecast generation precedes model training cutoff")

        sources = provenance.get("source_snapshots")
        if not isinstance(sources, Sequence) or isinstance(sources, (str, bytes)) or not sources:
            raise JointForecastProvenanceError(f"{forecast_id}: source_snapshots must be a non-empty list")
        local_ids = set()
        for source in sources:
            if not isinstance(source, Mapping):
                raise JointForecastProvenanceError("each source snapshot must be an object")
            source_id = _text(source.get("source_id"), "source_id")
            version = _text(source.get("source_version"), "source_version")
            if source_id in local_ids:
                raise JointForecastProvenanceError(f"{forecast_id}: duplicate source_id {source_id}")
            local_ids.add(source_id)
            _digest(source.get("content_sha256"), "source content_sha256")
            available = _time(source.get("available_at_utc"), "source available_at_utc")
            retrieved = _time(source.get("retrieved_at_utc"), "source retrieved_at_utc")
            if available > as_of:
                raise JointForecastProvenanceError(
                    f"{forecast_id}: source {source_id} was not available by forecast as-of"
                )
            if retrieved > as_of:
                raise JointForecastProvenanceError(
                    f"{forecast_id}: source {source_id} was retrieved after forecast as-of"
                )
            if retrieved < available:
                raise JointForecastProvenanceError(
                    f"{forecast_id}: source {source_id} retrieval precedes source availability"
                )
            source_count += 1
            source_ids.add((source_id, version))

    return {
        "schema_version": "1.0.0",
        "validation_status": "PROVENANCE_METADATA_VALIDATED",
        "forecast_count": len(seen),
        "source_snapshot_count": source_count,
        "distinct_source_versions": len(source_ids),
        "point_in_time_rule": "SOURCE_AVAILABLE_AND_RETRIEVED_NO_LATER_THAN_FORECAST_AS_OF",
        "hash_algorithm": "SHA256_DECLARATION_ONLY",
        "authenticity_verified": False,
        "source_bytes_rehashed": False,
        "decision_weight": 0.0,
        "production_eligible": False,
    }
