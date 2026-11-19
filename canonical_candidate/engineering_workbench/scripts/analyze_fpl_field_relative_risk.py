#!/usr/bin/env python3
"""Research-only field-relative portfolio risk (CoVar) analysis for a personal FPL XI.

The report decomposes own-team variance, field variance, own/field covariance and
variance of the score difference. It never changes a recommendation. A complete
player universe, deadline-matched LiveFPL EO and a complete shrunk covariance
matrix are mandatory; missing EO/covariance is not treated as zero.
"""
from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np


class FieldRiskInputError(ValueError):
    """Raised when the field-relative risk inputs are malformed."""


def _finite(value, name):
    if isinstance(value, bool) or value is None or value == "":
        raise FieldRiskInputError(f"{name} must be a finite number")
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        raise FieldRiskInputError(f"{name} must be a finite number")
    if not math.isfinite(numeric):
        raise FieldRiskInputError(f"{name} must be a finite number")
    return numeric


def _pair_key(left, right):
    return tuple(sorted((str(left), str(right)), key=lambda value: (0, int(value)) if value.isdigit() else (1, value)))


def analyze_field_relative_risk(
    player_forecasts: Sequence[Mapping],
    starting_xi: Sequence[int],
    captain_id: int,
    field_eo_by_player: Mapping[str | int, float],
    covariance_pairs: Sequence[Mapping],
    metadata: Mapping,
) -> dict:
    """Estimate the variance of own XI score minus field score for one GW.

    Own exposure is one unit for each starter plus one additional captain unit.
    Field exposure is standard effective ownership (EO percent / 100). Bench
    auto-substitution, chips and manager-specific field lineups are outside this
    first research diagnostic and are explicitly not inferred.
    """
    if len(starting_xi) != 11 or len(set(starting_xi)) != 11:
        raise FieldRiskInputError("starting_xi must contain 11 unique player IDs")
    if captain_id not in starting_xi:
        raise FieldRiskInputError("captain_id must be in starting_xi")
    forecasts = {}
    for row in player_forecasts:
        player_id = row.get("fpl_element_id")
        if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id < 1 or player_id in forecasts:
            raise FieldRiskInputError("player forecasts require unique positive integer FPL IDs")
        forecasts[player_id] = _finite(row.get("expected_points"), f"expected_points[{player_id}]")
    if any(player_id not in forecasts for player_id in starting_xi):
        raise FieldRiskInputError("every starting XI player must have a point forecast")

    if not isinstance(metadata, Mapping):
        raise FieldRiskInputError("metadata must be a mapping")
    required_meta = ("target_deadline", "eo_deadline", "picks_lock_verified", "eo_cohort", "eo_sample_size", "eo_captured_at")
    missing_meta = [key for key in required_meta if key not in metadata or metadata[key] in (None, "")]
    if missing_meta:
        return {"status": "INSUFFICIENT_FIELD_PROVENANCE", "missing_metadata": missing_meta,
                "decision_weight": 0.0, "used_for_recommendation": False}
    if metadata["target_deadline"] != metadata["eo_deadline"] or metadata["picks_lock_verified"] is not True:
        return {"status": "EO_NOT_DEADLINE_MATCHED_OR_LOCK_VERIFIED", "decision_weight": 0.0,
                "used_for_recommendation": False}

    universe = sorted(forecasts, key=lambda value: (0, value) if isinstance(value, int) else (1, str(value)))
    try:
        sample_size = int(metadata["eo_sample_size"])
    except (TypeError, ValueError):
        raise FieldRiskInputError("eo_sample_size must be a positive integer")
    if sample_size < 1 or isinstance(metadata["eo_sample_size"], bool):
        raise FieldRiskInputError("eo_sample_size must be a positive integer")
    eo = {}
    for player_id in universe:
        raw = field_eo_by_player.get(player_id, field_eo_by_player.get(str(player_id)))
        if raw is None:
            return {"status": "INCOMPLETE_FIELD_EO_UNIVERSE", "missing_player_ids": [player_id],
                    "decision_weight": 0.0, "used_for_recommendation": False}
        value = _finite(raw, f"field_eo[{player_id}]")
        if value < 0:
            raise FieldRiskInputError("field EO percentages cannot be negative")
        eo[player_id] = value / 100.0

    own = {player_id: 0.0 for player_id in universe}
    for player_id in starting_xi:
        own[player_id] = 1.0
    own[captain_id] += 1.0
    differential = {player_id: own[player_id] - eo[player_id] for player_id in universe}

    covariance = {}
    for row in covariance_pairs:
        left, right = row.get("player1_id"), row.get("player2_id")
        if left is None or right is None:
            raise FieldRiskInputError("covariance rows require player1_id and player2_id")
        value = _finite(row.get("shrunk_covariance"), f"shrunk_covariance[{left},{right}]")
        key = _pair_key(left, right)
        if key in covariance:
            raise FieldRiskInputError(f"duplicate covariance pair {key}")
        covariance[key] = value

    # Players with both zero own exposure and zero field EO cannot affect any
    # of the three portfolio moments, so no covariance estimate is required.
    active_universe = [player_id for player_id in universe
                       if abs(own[player_id]) > 1e-12 or abs(eo[player_id]) > 1e-12]
    missing_pairs = []
    for i, left in enumerate(active_universe):
        for right in active_universe[i:]:
            if _pair_key(left, right) not in covariance:
                missing_pairs.append([left, right])
                if len(missing_pairs) >= 20:
                    break
        if len(missing_pairs) >= 20:
            break
    if missing_pairs:
        return {"status": "INCOMPLETE_COVARIANCE_MATRIX", "missing_pair_examples": missing_pairs,
                "decision_weight": 0.0, "used_for_recommendation": False}

    matrix = np.empty((len(active_universe), len(active_universe)), dtype=float)
    for i, left in enumerate(active_universe):
        for j in range(i, len(active_universe)):
            value = covariance[_pair_key(left, active_universe[j])]
            matrix[i, j] = value
            matrix[j, i] = value
    eigen_min = float(np.linalg.eigvalsh(matrix).min())
    scale = max(1.0, float(np.max(np.abs(matrix))))
    if eigen_min < -1e-8 * scale:
        return {"status": "NON_PSD_COVARIANCE_MATRIX", "minimum_eigenvalue": eigen_min,
                "decision_weight": 0.0, "used_for_recommendation": False}

    own_vector = np.array([own[player_id] for player_id in active_universe], dtype=float)
    field_vector = np.array([eo[player_id] for player_id in active_universe], dtype=float)
    diff_vector = own_vector - field_vector
    points_vector = np.array([forecasts[player_id] for player_id in universe], dtype=float)
    own_variance = float(own_vector @ matrix @ own_vector)
    field_variance = float(field_vector @ matrix @ field_vector)
    own_field_covariance = float(own_vector @ matrix @ field_vector)
    relative_variance = float(diff_vector @ matrix @ diff_vector)
    if relative_variance < -1e-8 * scale:
        return {"status": "INVALID_NEGATIVE_RELATIVE_VARIANCE", "relative_variance": relative_variance,
                "decision_weight": 0.0, "used_for_recommendation": False}
    relative_variance = max(0.0, relative_variance)

    contributions = []
    for i, player_id in enumerate(active_universe):
        contribution = float(diff_vector[i] * (matrix[i, :] @ diff_vector))
        if abs(contribution) > 1e-12:
            contributions.append({"fpl_element_id": player_id, "variance_contribution": contribution,
                                  "own_exposure": own[player_id], "field_eo_exposure": eo[player_id],
                                  "exposure_difference": differential[player_id]})
    contributions.sort(key=lambda row: abs(row["variance_contribution"]), reverse=True)

    return {
        "status": "RESEARCH_ONLY_FIELD_RELATIVE_RISK_ESTIMATE",
        "target_deadline": metadata["target_deadline"],
        "eo_deadline": metadata["eo_deadline"],
        "eo_cohort": metadata["eo_cohort"],
        "eo_sample_size": sample_size,
        "eo_captured_at": metadata["eo_captured_at"],
        "player_universe_size": len(universe),
        "covariance_active_player_count": len(active_universe),
        "eo_universe_coverage": 1.0,
        "covariance_window_gameweeks": metadata.get("covariance_window_gameweeks"),
        "covariance_source": metadata.get("covariance_source", "historical_realised_fpl_points"),
        "minimum_covariance_eigenvalue": eigen_min,
        "expected_points_difference_vs_field": float(diff_vector @ points_vector),
        "own_xi_variance": own_variance,
        "field_variance": field_variance,
        "own_field_covariance": own_field_covariance,
        "relative_score_variance": relative_variance,
        "relative_score_standard_deviation": math.sqrt(relative_variance),
        "top_absolute_variance_contributors": contributions[:10],
        "exposure_definition": "own XI starters=1 plus captain extra=1; field exposure=deadline-matched standard EO percent / 100",
        "limitations": [
            "Research diagnostic only; does not change transfer, XI or captain recommendations.",
            "Covariance is estimated from historical realised FPL points and requires separate out-of-sample stability validation.",
            "LiveFPL EO must cover the complete player universe and match the target deadline with verified post-lock picks.",
            "Bench auto-substitution, chips and field-manager lineup/bench interactions are not modelled.",
            "The reported expected points difference uses the supplied player forecasts and is not a probability of rank gain.",
        ],
        "decision_weight": 0.0,
        "used_for_recommendation": False,
    }
