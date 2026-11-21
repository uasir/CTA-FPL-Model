from __future__ import annotations

import copy
import pytest

from m4_covar_joint_forecast_intake import (
    JointForecastIntakeError,
    validate_joint_forecast_intake,
)

HASH = "a" * 64

def document():
    return {
        "schema_version": "1.0.0",
        "forecast_kind": "EXPLICIT_JOINT_GAMEWEEK_DISTRIBUTION",
        "forecast_id": "season-gw11-source-001",
        "season": "2026-27",
        "target_gameweek": 11,
        "deadline_utc": "2026-11-21T11:00:00Z",
        "as_of_utc": "2026-11-21T10:30:00Z",
        "training_cutoff_utc": "2026-11-20T23:00:00Z",
        "player_universe": [
            {"player_id": 101, "team_id": "A"},
            {"player_id": 202, "team_id": "B"},
        ],
        "fixtures": [
            {"fixture_id": 9001, "home_team_id": "A", "away_team_id": "B"}
        ],
        "scenarios": [
            {
                "scenario_id": "low",
                "probability": 0.4,
                "probability_basis": "EXPLICIT_SOURCE_SUPPLIED",
                "fixture_states": [
                    {"fixture_id": 9001, "home_goals": 0, "away_goals": 0}
                ],
                "player_outcomes": [
                    {"player_id": 101, "minutes": 90, "played": True, "fpl_points": 2},
                    {"player_id": 202, "minutes": 0, "played": False, "fpl_points": 0},
                ],
            },
            {
                "scenario_id": "high",
                "probability": 0.6,
                "probability_basis": "EXPLICIT_SOURCE_SUPPLIED",
                "fixture_states": [
                    {"fixture_id": 9001, "home_goals": 2, "away_goals": 1}
                ],
                "player_outcomes": [
                    {"player_id": 101, "minutes": 90, "played": True, "fpl_points": 12},
                    {"player_id": 202, "minutes": 90, "played": True, "fpl_points": 5},
                ],
            },
        ],
        "provenance": {
            "model_artifact_sha256": HASH,
            "model_version": "provider-joint-model-1",
            "model_training_cutoff_utc": "2026-11-20T22:00:00Z",
            "config_sha256": "b" * 64,
            "config_version": "v1",
            "state_catalogue_version": "gw-state-v1",
            "forecast_payload_sha256": "c" * 64,
            "generated_at_utc": "2026-11-21T10:29:00Z",
            "source_snapshots": [
                {
                    "source_id": "fpl-bootstrap",
                    "source_version": "2026-11-21",
                    "content_sha256": "d" * 64,
                    "available_at_utc": "2026-11-21T09:00:00Z",
                    "retrieved_at_utc": "2026-11-21T09:05:00Z",
                }
            ],
        },
    }

def test_accepts_complete_explicit_joint_forecast():
    report = validate_joint_forecast_intake(document())
    assert report["validation_status"] == "EXPLICIT_JOINT_FORECAST_INTAKE_ACCEPTED"
    assert report["scenario_count"] == 2
    assert report["probability_total"] == pytest.approx(1.0)
    assert report["joint_distribution_inferred"] is False
    assert report["production_eligible"] is False

@pytest.mark.parametrize("field,value", [
    ("forecast_kind", "MARGINAL_PLAYER_EXPECTED_POINTS"),
    ("schema_version", "2.0.0"),
    ("as_of_utc", "2026-11-21T11:00:00Z"),
])
def test_rejects_wrong_kind_version_or_postdeadline_asof(field, value):
    doc = document()
    doc[field] = value
    with pytest.raises(JointForecastIntakeError):
        validate_joint_forecast_intake(doc)

def test_rejects_probabilities_that_do_not_sum_to_one():
    doc = document()
    doc["scenarios"][0]["probability"] = 0.2
    with pytest.raises(JointForecastIntakeError, match="sum to 1"):
        validate_joint_forecast_intake(doc)

def test_rejects_inferred_probability_basis():
    doc = document()
    doc["scenarios"][0]["probability_basis"] = "MULTIPLIED_MARGINALS"
    with pytest.raises(JointForecastIntakeError, match="EXPLICIT_SOURCE_SUPPLIED"):
        validate_joint_forecast_intake(doc)

def test_rejects_incomplete_player_universe():
    doc = document()
    doc["scenarios"][0]["player_outcomes"].pop()
    with pytest.raises(JointForecastIntakeError, match="every player outcome"):
        validate_joint_forecast_intake(doc)

def test_rejects_incomplete_fixture_coverage():
    doc = document()
    doc["scenarios"][1]["fixture_states"].clear()
    with pytest.raises(JointForecastIntakeError, match="every fixture state"):
        validate_joint_forecast_intake(doc)

def test_rejects_duplicate_scenario_ids():
    doc = document()
    doc["scenarios"][1]["scenario_id"] = doc["scenarios"][0]["scenario_id"]
    with pytest.raises(JointForecastIntakeError, match="unique"):
        validate_joint_forecast_intake(doc)

def test_rejects_played_minutes_mismatch():
    doc = document()
    doc["scenarios"][0]["player_outcomes"][0]["played"] = False
    with pytest.raises(JointForecastIntakeError, match="played must agree"):
        validate_joint_forecast_intake(doc)

def test_rejects_missing_provenance_hash():
    doc = document()
    doc["provenance"]["model_artifact_sha256"] = "missing"
    with pytest.raises(JointForecastIntakeError, match="provenance validation failed"):
        validate_joint_forecast_intake(doc)

def test_preserves_negative_fpl_points():
    doc = document()
    doc["scenarios"][0]["player_outcomes"][0]["fpl_points"] = -2
    assert validate_joint_forecast_intake(doc)["validation_status"] == "EXPLICIT_JOINT_FORECAST_INTAKE_ACCEPTED"

def test_accepts_model_generated_explicit_probabilities_with_reproducibility_metadata():
    doc = document()
    for scenario in doc["scenarios"]:
        scenario["probability_basis"] = "MODEL_GENERATED_EXPLICIT"
    doc["probability_generation"] = {
        "method": "M3_ANCHORED_HISTORICAL_BLOCK_BOOTSTRAP",
        "method_version": "0.1.0",
        "algorithm": "FIXTURE_BLOCK_RESIDUAL_RESAMPLING",
        "random_generator": "PCG64",
        "random_seed": 42,
        "draw_count": 10000,
        "scenario_reduction": "UNIQUE_JOINT_OUTCOME_FREQUENCIES",
        "probability_semantics": "EMPIRICAL_DRAW_FREQUENCY",
    }
    report = validate_joint_forecast_intake(doc)
    assert report["probability_basis"] == "MODEL_GENERATED_EXPLICIT"
    assert report["probability_generation_validated"] is True
    assert report["probability_generation"]["draw_count"] == 10000
    assert report["production_eligible"] is False


@pytest.mark.parametrize("field,value", [
    ("random_seed", None),
    ("draw_count", 1),
    ("random_generator", ""),
    ("probability_semantics", "NORMALIZED_GUESSES"),
])
def test_rejects_incomplete_model_probability_generation_metadata(field, value):
    doc = document()
    for scenario in doc["scenarios"]:
        scenario["probability_basis"] = "MODEL_GENERATED_EXPLICIT"
    doc["probability_generation"] = {
        "method": "M3_ANCHORED_HISTORICAL_BLOCK_BOOTSTRAP",
        "method_version": "0.1.0",
        "algorithm": "FIXTURE_BLOCK_RESIDUAL_RESAMPLING",
        "random_generator": "PCG64",
        "random_seed": 42,
        "draw_count": 10000,
        "scenario_reduction": "UNIQUE_JOINT_OUTCOME_FREQUENCIES",
        "probability_semantics": "EMPIRICAL_DRAW_FREQUENCY",
    }
    doc["probability_generation"][field] = value
    with pytest.raises(JointForecastIntakeError):
        validate_joint_forecast_intake(doc)


def test_rejects_mixed_probability_bases():
    doc = document()
    doc["scenarios"][1]["probability_basis"] = "MODEL_GENERATED_EXPLICIT"
    with pytest.raises(JointForecastIntakeError, match="same probability_basis"):
        validate_joint_forecast_intake(doc)


def test_rejects_model_generation_metadata_for_source_supplied_probabilities():
    doc = document()
    doc["probability_generation"] = {"method": "not-applicable"}
    with pytest.raises(JointForecastIntakeError, match="only valid"):
        validate_joint_forecast_intake(doc)
