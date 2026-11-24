#!/usr/bin/env python3
"""Typed-by-contract integration for CTA-FPL's independent research tracks.

A/B/C form an integrated contextual predictor. The conventional FPL 2PM
Transformer is a separate track and does not depend on CTA. A+B+C may be
added to a later Transformer ablation, but that is an optional experiment.
Missing provider evidence stays missing; no layer may silently convert absent
features to zero or use target-fixture outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

LAYER_FEATURES = {
    "A_temporal_football_value": (
        "progressive_passes", "progressive_carries", "final_third_entries",
        "dangerous_receipts", "sequence_value", "recent_action_trend",
        "team_final_third_entries", "team_successful_dribbles",
        "player_key_pass_rate", "player_tracked_xg_rate",
        "recent_key_pass_trend", "recent_xg_trend",
    ),
    "B_risk_defensive_intelligence": (
        "pressure_events", "pressure_success_rate", "duel_success_rate",
        "defensive_actions", "turnovers_under_pressure", "opponent_threat_allowed",
        "defensive_exposure", "team_interceptions", "team_tackles_won",
        "team_ball_recoveries", "team_recoveries", "team_duels_won",
        "opponent_box_attempts_allowed", "player_fouls_committed_rate",
    ),
    "C_player_intelligence": (
        "role_stability", "minutes_trend", "attacking_involvement",
        "threat_creation_rate", "threat_reception_rate", "threat_realisation_rate",
        "contextual_threat_score", "attacking_involvement_rate",
    ),
}

# Dependencies describe the conceptual CTA feature layers only. D is deliberately
# not a required fourth layer: the standalone 2PM model is a separate predictor.
LAYER_DEPENDENCIES = {
    "A_temporal_football_value": (),
    "B_risk_defensive_intelligence": (),
    "C_player_intelligence": ("A_temporal_football_value", "B_risk_defensive_intelligence"),
}

MODEL_TRACKS = {
    "integrated_abc": {
        "required_layers": tuple(LAYER_FEATURES),
        "input_family": "CTA_A_B_C",
        "depends_on_2pm_transformer": False,
    },
    "standalone_2pm": {
        "required_layers": (),
        "input_family": "CONVENTIONAL_FPL",
        "depends_on_abc": False,
    },
    "abc_augmented_2pm": {
        "required_layers": tuple(LAYER_FEATURES),
        "input_family": "CONVENTIONAL_FPL_PLUS_CTA_A_B_C",
        "optional_ablation": True,
    },
}

# Features available to the conventional track. These are pre-deadline
# historical FPL aggregates and fixture context, never target-fixture outcomes.
CONVENTIONAL_FPL_FEATURES = (
    "prior_gw_points", "prior3_gw_points_avg", "prior5_gw_points_avg",
    "prior_gw_minutes", "prior3_gw_minutes_avg", "prior5_gw_minutes_avg",
    "prior3_gw_xg_avg", "prior3_gw_xa_avg",
    "prior5_appearance_rate", "season_appearance_rate",
    "season_to_date_minutes", "season_to_date_points_per90", "was_home",
)


@dataclass(frozen=True)
class LayerResult:
    layer: str
    status: str
    features: Mapping[str, float | None]
    source_coverage: Mapping[str, str]
    as_of: str
    provenance: str


def validate_layer_result(result: LayerResult, target_deadline: str) -> None:
    if result.layer not in LAYER_FEATURES:
        raise ValueError(f"Unknown feature layer: {result.layer}")
    if result.status not in {"RESEARCH_ONLY", "VALIDATED"}:
        raise ValueError("Layer status must be explicit")
    if not result.as_of or result.as_of > target_deadline:
        raise ValueError("Layer feature snapshot is after the target deadline")
    expected = set(LAYER_FEATURES[result.layer])
    unexpected = set(result.features) - expected
    if unexpected:
        raise ValueError(f"Unexpected {result.layer} features: {sorted(unexpected)}")
    for name, value in result.features.items():
        if value is not None and not isinstance(value, (int, float)):
            raise ValueError(f"Feature {name} must be numeric or None")
        if result.source_coverage.get(name) not in {"OBSERVED", "MISSING", "PARTIAL"}:
            raise ValueError(f"Feature {name} needs explicit source coverage")
        if value is None and result.source_coverage[name] == "OBSERVED":
            raise ValueError(f"Observed feature {name} cannot be null")
        if value is not None and result.source_coverage[name] == "MISSING":
            raise ValueError(f"Missing feature {name} cannot contain a value")
    if not result.provenance:
        raise ValueError("Feature provenance is required")


def integrate_player_sequence(layer_results: Sequence[LayerResult],
                              target_deadline: str) -> dict:
    """Join A/B/C by an exact player-fixture key supplied by the caller."""
    by_layer = {}
    for result in layer_results:
        validate_layer_result(result, target_deadline)
        if result.layer in by_layer:
            raise ValueError(f"Duplicate layer result: {result.layer}")
        by_layer[result.layer] = result
    missing = [name for name in LAYER_FEATURES if name not in by_layer]
    features = {}
    statuses = {}
    coverage = {}
    provenance = {}
    for layer_name, result in by_layer.items():
        statuses[layer_name] = result.status
        provenance[layer_name] = result.provenance
        for name, value in result.features.items():
            features[name] = value
            coverage[name] = result.source_coverage[name]
    return {
        "status": "RESEARCH_ONLY" if missing or any(v != "VALIDATED" for v in statuses.values()) else "VALIDATED",
        "missing_layers": missing,
        "layer_status": statuses,
        "features": features,
        "source_coverage": coverage,
        "provenance": provenance,
        "target_deadline": target_deadline,
        "promotion_blockers": ["missing_feature_layer:" + x for x in missing],
    }


def require_complete_sequence(sequence: Mapping) -> None:
    if sequence.get("missing_layers"):
        raise ValueError("Cannot train integrated A/B/C predictor with missing layers")
    if sequence.get("status") != "VALIDATED":
        raise ValueError("Research-only layer features cannot enter promoted training")


def validate_model_track_input(track: str, feature_names: Sequence[str]) -> None:
    """Fail closed when a model receives features from the wrong experiment.

    The standalone 2PM model is conventional-FPL-only. The optional augmented
    experiment is the sole track allowed to combine FPL and A/B/C features.
    """
    if track not in MODEL_TRACKS:
        raise ValueError(f"Unknown model track: {track}")
    names = set(feature_names)
    abc_names = {name for values in LAYER_FEATURES.values() for name in values}
    conventional_names = set(CONVENTIONAL_FPL_FEATURES)
    if track == "standalone_2pm":
        if names & abc_names:
            raise ValueError("Standalone 2PM input must not contain CTA A/B/C features")
        unknown = names - conventional_names
        if unknown:
            raise ValueError(f"Unknown conventional FPL features: {sorted(unknown)}")
        if not names:
            raise ValueError("Standalone 2PM input feature list cannot be empty")
    elif track == "integrated_abc":
        if names & conventional_names:
            raise ValueError("Integrated A/B/C predictor must be evaluated separately from conventional FPL features")
        unknown = names - abc_names
        if unknown:
            raise ValueError(f"Unknown A/B/C features: {sorted(unknown)}")
        if not names:
            raise ValueError("Integrated A/B/C input feature list cannot be empty")
    else:
        if not (names & conventional_names) or not (names & abc_names):
            raise ValueError("A/B/C-augmented 2PM requires both conventional FPL and A/B/C features")
        unknown = names - conventional_names - abc_names
        if unknown:
            raise ValueError(f"Unknown augmented 2PM features: {sorted(unknown)}")
