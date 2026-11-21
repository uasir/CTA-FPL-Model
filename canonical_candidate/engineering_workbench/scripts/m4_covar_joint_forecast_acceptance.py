"""Combined chronological and provenance acceptance for historical forecasts."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from m4_covar_joint_forecast_dataset import (
    JointForecastDatasetError, validate_joint_forecast_dataset,
)
from m4_covar_joint_forecast_archive_verifier import (
    JointForecastArchiveVerificationError, verify_joint_forecast_archive,
)
from m4_covar_joint_forecast_provenance import (
    JointForecastProvenanceError, validate_joint_forecast_provenance,
)


class JointForecastAcceptanceError(ValueError):
    """A forecast dataset failed temporal or provenance acceptance."""


def validate_joint_forecast_acceptance(
    forecasts: Sequence[Mapping[str, Any]],
    split_gameweeks: Mapping[str, Sequence[str]],
    archive_root: str | Path | None = None,
    archive_manifest: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run both validators; return acceptance only when both pass.

    This combined structural gate does not authenticate declared hashes or
    certify historical source availability. It never upgrades research output
    to production eligibility. Archive verification is optional; when either
    archive argument is supplied, both are required and every declared source
    snapshot must be matched to an archived file whose bytes rehash correctly.
    """
    try:
        temporal = validate_joint_forecast_dataset(forecasts, split_gameweeks)
    except JointForecastDatasetError as exc:
        raise JointForecastAcceptanceError(f"temporal validation failed: {exc}") from exc
    try:
        provenance = validate_joint_forecast_provenance(forecasts)
    except JointForecastProvenanceError as exc:
        raise JointForecastAcceptanceError(f"provenance validation failed: {exc}") from exc

    if (archive_root is None) != (archive_manifest is None):
        raise JointForecastAcceptanceError("archive verification requires both archive_root and archive_manifest")
    archive = None
    if archive_root is not None and archive_manifest is not None:
        try:
            archive = verify_joint_forecast_archive(forecasts, archive_root, archive_manifest)
        except JointForecastArchiveVerificationError as exc:
            raise JointForecastAcceptanceError(f"archive verification failed: {exc}") from exc

    return {
        "schema_version": "1.1.0",
        "acceptance_status": "STRUCTURAL_AND_ARCHIVE_BYTES_VERIFIED" if archive else "STRUCTURAL_DATASET_ACCEPTED",
        "temporal_validation": temporal,
        "provenance_validation": provenance,
        "archive_validation": archive,
        "acceptance_scope": "STRUCTURAL_METADATA_AND_ARCHIVED_SOURCE_BYTES" if archive else "STRUCTURAL_METADATA_ONLY",
        "authenticity_verified": False,
        "source_bytes_rehashed": bool(archive),
        "historical_dataset_certified": False,
        "decision_weight": 0.0,
        "production_eligible": False,
    }
