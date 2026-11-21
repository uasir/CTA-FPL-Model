"""Compare explicit joint-scenario marginal means with the M3 xP anchor.

The M3 anchor supplies conventional player-level expected points only.
Scenario outcomes and probabilities must be supplied explicitly by a separate
source. This module never constructs scenarios or infers probabilities.
"""
from __future__ import annotations

import json
import math
from typing import Any, Mapping, Sequence

from m3_covar_forecast_anchor_acceptance import accept_m3_forecast_anchor


class M3JointScenarioAlignmentError(ValueError):
    """Invalid anchor or explicit joint-scenario alignment input."""


def align_m3_anchor_to_joint_scenarios(
    *,
    forecast_bundle_bytes: bytes,
    archive_manifest: Mapping[str, Any],
    joint_scenarios: Sequence[Mapping[str, Any]],
    scenario_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Measure marginal-mean agreement without deriving any joint probabilities."""
    accepted = accept_m3_forecast_anchor(forecast_bundle_bytes, archive_manifest)
    bundle = json.loads(forecast_bundle_bytes.decode("utf-8"))
    anchor_rows = bundle["player_forecasts"]
    anchor = {str(row["fpl_element_id"]): float(row["expected_points"]) for row in anchor_rows}
    if not isinstance(scenario_provenance, Mapping):
        raise M3JointScenarioAlignmentError("scenario_provenance must be an object")
    for field in ("source_id", "method", "captured_at_utc"):
        if not isinstance(scenario_provenance.get(field), str) or not scenario_provenance[field].strip():
            raise M3JointScenarioAlignmentError(f"scenario_provenance.{field} is required")
    if scenario_provenance.get("probability_basis") != "EXPLICIT":
        raise M3JointScenarioAlignmentError("joint-scenario probabilities must be explicitly supplied")
    if not isinstance(joint_scenarios, Sequence) or isinstance(joint_scenarios, (str, bytes)) or not joint_scenarios:
        raise M3JointScenarioAlignmentError("joint_scenarios must be a non-empty sequence")

    from datetime import datetime
    try:
        captured = datetime.fromisoformat(scenario_provenance["captured_at_utc"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise M3JointScenarioAlignmentError("scenario capture timestamp must be ISO-8601") from exc
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise M3JointScenarioAlignmentError("scenario capture timestamp must include a timezone")
    as_of = datetime.fromisoformat(bundle["as_of_utc"].replace("Z", "+00:00"))
    if captured > as_of:
        raise M3JointScenarioAlignmentError("joint scenarios were captured after the M3 forecast as-of")

    total_probability = 0.0
    seen_scenarios: set[str] = set()
    weighted_points = {player_id: 0.0 for player_id in anchor}
    for scenario in joint_scenarios:
        if not isinstance(scenario, Mapping):
            raise M3JointScenarioAlignmentError("joint scenario rows must be objects")
        scenario_id = scenario.get("scenario_id")
        if not isinstance(scenario_id, str) or not scenario_id.strip() or scenario_id in seen_scenarios:
            raise M3JointScenarioAlignmentError("scenario IDs must be unique and non-empty")
        seen_scenarios.add(scenario_id)
        probability = scenario.get("probability")
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            raise M3JointScenarioAlignmentError(f"{scenario_id}.probability must be numeric")
        probability = float(probability)
        if not math.isfinite(probability) or probability <= 0:
            raise M3JointScenarioAlignmentError(f"{scenario_id}.probability must be finite and > 0")
        total_probability += probability
        points = scenario.get("player_points")
        if not isinstance(points, Mapping) or set(map(str, points.keys())) != set(anchor):
            raise M3JointScenarioAlignmentError(
                f"{scenario_id}.player_points must cover exactly the M3 anchor player universe"
            )
        for raw_id, raw_points in points.items():
            player_id = str(raw_id)
            if isinstance(raw_points, bool) or not isinstance(raw_points, (int, float)):
                raise M3JointScenarioAlignmentError(f"{scenario_id}.{player_id} points must be numeric")
            value = float(raw_points)
            if not math.isfinite(value):
                raise M3JointScenarioAlignmentError(f"{scenario_id}.{player_id} points must be finite")
            weighted_points[player_id] += probability * value

    if not math.isclose(total_probability, 1.0, rel_tol=0, abs_tol=1e-9):
        raise M3JointScenarioAlignmentError("explicit joint-scenario probabilities must sum to 1")
    errors = []
    player_rows = []
    for player_id, anchor_xp in anchor.items():
        scenario_mean = weighted_points[player_id]
        error = scenario_mean - anchor_xp
        errors.append(error)
        player_rows.append({
            "fpl_element_id": int(player_id),
            "m3_expected_points": anchor_xp,
            "scenario_marginal_mean": scenario_mean,
            "mean_error_scenario_minus_m3": error,
            "absolute_error": abs(error),
        })
    absolute = [abs(value) for value in errors]
    return {
        "schema_version": "1.0.0",
        "alignment_status": "PASS_EXPLICIT_SCENARIO_MARGINAL_ALIGNMENT_COMPUTED",
        "forecast_snapshot_id": accepted["forecast_snapshot_id"],
        "season": accepted["season"],
        "target_gameweek": accepted["target_gameweek"],
        "scenario_source_id": scenario_provenance["source_id"],
        "scenario_method": scenario_provenance["method"],
        "scenario_capture_as_of_utc": scenario_provenance["captured_at_utc"],
        "scenario_probability_basis": "EXPLICIT",
        "scenario_count": len(joint_scenarios),
        "player_count": len(player_rows),
        "mean_absolute_error": sum(absolute) / len(absolute),
        "root_mean_squared_error": math.sqrt(sum(value * value for value in errors) / len(errors)),
        "mean_bias_scenario_minus_m3": sum(errors) / len(errors),
        "maximum_absolute_error": max(absolute),
        "player_alignment": player_rows,
        "joint_distribution_was_inferred": False,
        "fixture_independence_assumed": False,
        "calibration_established": False,
        "decision_weight": 0.0,
        "production_eligible": False,
        "limitations": [
            "This is a marginal-mean consistency diagnostic, not a calibration test.",
            "Agreement with M3 xP does not validate joint dependence, tails, or portfolio outcome probabilities.",
            "The explicit joint-scenario source remains responsible for the validity of its outcomes and probabilities.",
        ],
    }
