from __future__ import annotations
import copy
import pytest

from m4_covar_joint_forecast_provenance import (
    JointForecastProvenanceError, validate_joint_forecast_provenance,
)

HASH = "a" * 64

def forecast(fid="f1"):
    return {
        "forecast_id": fid,
        "as_of_utc": "2025-08-01T10:00:00Z",
        "training_cutoff_utc": "2025-07-31T23:00:00Z",
        "provenance": {
            "model_artifact_sha256": HASH,
            "model_version": "joint-model-1.2",
            "model_training_cutoff_utc": "2025-07-31T22:00:00Z",
            "config_sha256": "b" * 64,
            "config_version": "config-3",
            "state_catalogue_version": "gw-state-v1",
            "forecast_payload_sha256": "c" * 64,
            "generated_at_utc": "2025-08-01T09:59:00Z",
            "source_snapshots": [{
                "source_id": "bootstrap-static",
                "source_version": "2025-08-01T09:00Z",
                "content_sha256": "d" * 64,
                "available_at_utc": "2025-08-01T08:00:00Z",
                "retrieved_at_utc": "2025-08-01T09:00:00Z",
            }],
        },
    }

def test_validates_complete_point_in_time_provenance():
    report = validate_joint_forecast_provenance([forecast()])
    assert report["validation_status"] == "PROVENANCE_METADATA_VALIDATED"
    assert report["source_snapshot_count"] == 1
    assert report["authenticity_verified"] is False
    assert report["production_eligible"] is False

def test_rejects_missing_provenance():
    row = forecast(); del row["provenance"]
    with pytest.raises(JointForecastProvenanceError, match="provenance must be an object"):
        validate_joint_forecast_provenance([row])

@pytest.mark.parametrize("field", ["model_artifact_sha256", "config_sha256", "forecast_payload_sha256"])
def test_rejects_invalid_hash(field):
    row = forecast(); row["provenance"][field] = "not-a-hash"
    with pytest.raises(JointForecastProvenanceError, match="SHA-256"):
        validate_joint_forecast_provenance([row])

def test_rejects_source_available_after_as_of():
    row = forecast()
    row["provenance"]["source_snapshots"][0]["available_at_utc"] = "2025-08-01T10:01:00Z"
    with pytest.raises(JointForecastProvenanceError, match="not available by forecast as-of"):
        validate_joint_forecast_provenance([row])

def test_rejects_source_retrieved_after_as_of():
    row = forecast()
    row["provenance"]["source_snapshots"][0]["retrieved_at_utc"] = "2025-08-01T10:01:00Z"
    with pytest.raises(JointForecastProvenanceError, match="retrieved after forecast as-of"):
        validate_joint_forecast_provenance([row])

def test_rejects_model_training_cutoff_after_declared_cutoff():
    row = forecast()
    row["provenance"]["model_training_cutoff_utc"] = "2025-08-01T00:00:00Z"
    with pytest.raises(JointForecastProvenanceError, match="exceeds declared training cutoff"):
        validate_joint_forecast_provenance([row])

def test_rejects_generation_after_as_of():
    row = forecast()
    row["provenance"]["generated_at_utc"] = "2025-08-01T10:01:00Z"
    with pytest.raises(JointForecastProvenanceError, match="generation is after"):
        validate_joint_forecast_provenance([row])

def test_rejects_duplicate_source_id_within_forecast():
    row = forecast()
    row["provenance"]["source_snapshots"].append(copy.deepcopy(row["provenance"]["source_snapshots"][0]))
    with pytest.raises(JointForecastProvenanceError, match="duplicate source_id"):
        validate_joint_forecast_provenance([row])

def test_rejects_timezone_naive_source_timestamp():
    row = forecast()
    row["provenance"]["source_snapshots"][0]["available_at_utc"] = "2025-08-01T08:00:00"
    with pytest.raises(JointForecastProvenanceError, match="timezone"):
        validate_joint_forecast_provenance([row])

def test_rejects_duplicate_forecast_ids():
    with pytest.raises(JointForecastProvenanceError, match="unique"):
        validate_joint_forecast_provenance([forecast(), forecast()])
