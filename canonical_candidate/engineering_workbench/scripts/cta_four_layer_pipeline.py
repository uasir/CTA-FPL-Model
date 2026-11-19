#!/usr/bin/env python3
"""Typed-by-contract integration for CTA-FPL's four research layers.

A/B/C are feature-intelligence layers. D is the temporal two-part model.
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
    ),
    "B_risk_defensive_intelligence": (
        "pressure_events", "pressure_success_rate", "duel_success_rate",
        "defensive_actions", "turnovers_under_pressure", "opponent_threat_allowed",
        "defensive_exposure",
    ),
    "C_player_intelligence": (
        "role_stability", "minutes_trend", "attacking_involvement",
        "threat_creation_rate", "threat_reception_rate", "threat_realisation_rate",
        "contextual_threat_score",
    ),
}
LAYER_DEPENDENCIES = {
    "A_temporal_football_value": (),
    "B_risk_defensive_intelligence": (),
    "C_player_intelligence": ("A_temporal_football_value", "B_risk_defensive_intelligence"),
    "D_2PM_transformer": ("A_temporal_football_value", "B_risk_defensive_intelligence",
                          "C_player_intelligence"),
}


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
        raise ValueError("Cannot train integrated model with missing A/B/C layers")
    if sequence.get("status") != "VALIDATED":
        raise ValueError("Research-only layer features cannot enter promoted training")
