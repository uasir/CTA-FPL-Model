"""Combined chronological and provenance acceptance for historical forecasts."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from m4_covar_joint_forecast_dataset import (
    JointForecastDatasetError, validate_joint_forecast_dataset,
)
from m4_covar_joint_forecast_provenance import (
    JointForecastProvenanceError, validate_joint_forecast_provenance,
)


class JointForecastAcceptanceError(ValueError):
    """A forecast dataset failed temporal or provenance acceptance."""


def validate_joint_forecast_acceptance(
    forecasts: Sequence[Mapping[str, Any]],
    split_gameweeks: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """Run both validators; return acceptance only when both pass.

    This combined structural gate does not authenticate declared hashes or
    certify historical source availability. It never upgrades research output
    to production eligibility.
    """
    try:
        temporal = validate_joint_forecast_dataset(forecasts, split_gameweeks)
    except JointForecastDatasetError as exc:
        raise JointForecastAcceptanceError(f"temporal validation failed: {exc}") from exc
    try:
        provenance = validate_joint_forecast_provenance(forecasts)
    except JointForecastProvenanceError as exc:
        raise JointForecastAcceptanceError(f"provenance validation failed: {exc}") from exc

    return {
        "schema_version": "1.0.0",
        "acceptance_status": "STRUCTURAL_DATASET_ACCEPTED",
        "temporal_validation": temporal,
        "provenance_validation": provenance,
        "acceptance_scope": "STRUCTURAL_METADATA_ONLY",
        "authenticity_verified": False,
        "source_bytes_rehashed": False,
        "historical_dataset_certified": False,
        "decision_weight": 0.0,
        "production_eligible": False,
    }
