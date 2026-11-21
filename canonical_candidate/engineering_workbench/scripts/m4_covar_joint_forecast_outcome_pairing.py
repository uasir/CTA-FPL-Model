"""Build a calibration-ready dataset by pairing archived joint forecasts with
explicitly resolved, officially reconciled realized joint states.

This module does not infer observed states from marginal xP/EO, generate joint
probabilities, or create missing state labels. A separately versioned resolver
must provide the exact observed state and auditable coverage evidence.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from m4_covar_joint_forecast_acceptance import (
    JointForecastAcceptanceError,
    validate_joint_forecast_acceptance,
)


class JointForecastOutcomePairingError(ValueError):
    """Forecasts and realized joint outcomes cannot be safely paired."""


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise JointForecastOutcomePairingError(f"{field} must be a non-empty string")
    return value.strip()


def _digest(value: Any, field: str) -> str:
    result = _text(value, field).lower()
    if not _SHA256.fullmatch(result):
        raise JointForecastOutcomePairingError(f"{field} must be a 64-character SHA-256")
    return result


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise JointForecastOutcomePairingError(f"{field} must be a non-negative integer")
    return value


def build_joint_forecast_outcome_pairs(
    *,
    forecasts: Sequence[Mapping[str, Any]],
    realized_state_mappings: Sequence[Mapping[str, Any]],
    split_gameweeks: Mapping[str, Sequence[str]],
    archive_root: str,
    archive_manifest: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Verify archived forecast provenance and pair with explicit realized labels.

    One realized-state mapping is required per season/Gameweek. It must be
    produced by a separately versioned resolver, refer to the same complete
    joint state catalogue and exact player universe, and be backed by a
    passing official event-live finality audit. The resolver's mapping source
    bytes are identified by SHA-256; this function cannot authenticate the
    resolver implementation or source provider.
    """
    if not isinstance(realized_state_mappings, Sequence) or isinstance(realized_state_mappings, (str, bytes)) or not realized_state_mappings:
        raise JointForecastOutcomePairingError("realized_state_mappings must be a non-empty sequence")

    try:
        acceptance = validate_joint_forecast_acceptance(
            forecasts, split_gameweeks, archive_root, archive_manifest
        )
    except JointForecastAcceptanceError as exc:
        raise JointForecastOutcomePairingError(f"forecast archive acceptance failed: {exc}") from exc

    if acceptance.get("acceptance_status") != "STRUCTURAL_AND_COMPLETE_PROVENANCE_BYTES_VERIFIED":
        raise JointForecastOutcomePairingError("complete archived forecast provenance bytes must be verified")

    mapping_by_gw: dict[tuple[str, str], Mapping[str, Any]] = {}
    for mapping in realized_state_mappings:
        if not isinstance(mapping, Mapping):
            raise JointForecastOutcomePairingError("each realized state mapping must be an object")
        season = _text(mapping.get("season"), "realized mapping season")
        gameweek = _text(mapping.get("gameweek_id"), "realized mapping gameweek_id")
        key = (season, gameweek)
        if key in mapping_by_gw:
            raise JointForecastOutcomePairingError(f"duplicate realized state mapping for {season} GW{gameweek}")
        mapping_by_gw[key] = mapping

    paired = []
    forecast_gameweeks: dict[tuple[str, str], dict[str, str]] = {}
    forecast_keys = set()
    for forecast in forecasts:
        if not isinstance(forecast, Mapping):
            raise JointForecastOutcomePairingError("each forecast must be an object")
        forecast_id = _text(forecast.get("forecast_id"), "forecast_id")
        season = _text(forecast.get("season"), f"{forecast_id}.season")
        gameweek = _text(forecast.get("gameweek_id"), f"{forecast_id}.gameweek_id")
        key = (season, gameweek)
        if key not in mapping_by_gw:
            raise JointForecastOutcomePairingError(f"{forecast_id}: no reconciled realized joint state for {season} GW{gameweek}")
        if forecast_id in forecast_keys:
            raise JointForecastOutcomePairingError(f"duplicate forecast_id {forecast_id}")
        forecast_keys.add(forecast_id)

        mapping = mapping_by_gw[key]
        if mapping.get("mapping_status") != "PASS_EXACT_OBSERVED_STATE_RESOLUTION":
            raise JointForecastOutcomePairingError(f"{forecast_id}: realized state mapping has not passed exact resolution")
        if mapping.get("mapping_inferred_from_marginals") is not False:
            raise JointForecastOutcomePairingError(f"{forecast_id}: observed joint state cannot be inferred from marginal data")
        if mapping.get("finality_audit_status") != "PASS_EXACT_MATCH":
            raise JointForecastOutcomePairingError(f"{forecast_id}: official event-live finality audit is not passing")
        if mapping.get("point_in_time_status") != "NOT_VERIFIED_RETROSPECTIVE_FINAL_SCORING_AUDIT":
            raise JointForecastOutcomePairingError(f"{forecast_id}: realized scoring must retain retrospective status")

        for field in ("state_catalogue_sha256", "player_universe_sha256", "mapping_source_sha256"):
            _digest(mapping.get(field), f"{forecast_id}.{field}")
        if _digest(forecast.get("state_catalogue_sha256"), f"{forecast_id}.state_catalogue_sha256") != mapping["state_catalogue_sha256"]:
            raise JointForecastOutcomePairingError(f"{forecast_id}: forecast and observed state catalogue hashes differ")
        if _digest(forecast.get("player_universe_sha256"), f"{forecast_id}.player_universe_sha256") != mapping["player_universe_sha256"]:
            raise JointForecastOutcomePairingError(f"{forecast_id}: forecast and realized player universe hashes differ")

        resolver = _text(mapping.get("resolver_name"), f"{forecast_id}.resolver_name")
        resolver_version = _text(mapping.get("resolver_version"), f"{forecast_id}.resolver_version")
        observed_state = _text(mapping.get("observed_state_id"), f"{forecast_id}.observed_state_id")
        mapped_count = _integer(mapping.get("mapped_player_count"), f"{forecast_id}.mapped_player_count")
        missing_count = _integer(mapping.get("missing_player_count"), f"{forecast_id}.missing_player_count")
        unexpected_count = _integer(mapping.get("unexpected_player_count"), f"{forecast_id}.unexpected_player_count")
        declared_count = _integer(forecast.get("player_count"), f"{forecast_id}.player_count")
        if mapped_count != declared_count or missing_count != 0 or unexpected_count != 0:
            raise JointForecastOutcomePairingError(f"{forecast_id}: realized player coverage is not exact")
        probabilities = forecast.get("probabilities")
        reference_probabilities = forecast.get("reference_probabilities")
        if not isinstance(probabilities, Mapping) or observed_state not in probabilities:
            raise JointForecastOutcomePairingError(f"{forecast_id}: observed state must be represented in the complete forecast state catalogue")
        if not isinstance(reference_probabilities, Mapping) or set(reference_probabilities) != set(probabilities):
            raise JointForecastOutcomePairingError(f"{forecast_id}: reference forecast must use the same complete state catalogue")

        state_meta = forecast_gameweeks.setdefault(key, {
            "state_catalogue_sha256": mapping["state_catalogue_sha256"],
            "player_universe_sha256": mapping["player_universe_sha256"],
            "observed_state_id": observed_state,
            "resolver_name": resolver,
            "resolver_version": resolver_version,
            "mapping_source_sha256": mapping["mapping_source_sha256"],
        })
        for field in ("state_catalogue_sha256", "player_universe_sha256", "observed_state_id", "resolver_name", "resolver_version", "mapping_source_sha256"):
            if state_meta[field] != (mapping[field] if field.endswith("sha256") else (
                observed_state if field == "observed_state_id" else resolver if field == "resolver_name" else resolver_version
            )):
                raise JointForecastOutcomePairingError(f"{season} GW{gameweek}: forecasts do not share one consistent realized-state mapping")

        paired.append({
            "forecast_id": forecast_id,
            "gameweek_id": gameweek,
            "as_of_utc": forecast["as_of_utc"],
            "first_kickoff_utc": forecast["first_kickoff_utc"],
            "training_cutoff_utc": forecast["training_cutoff_utc"],
            "probabilities": dict(probabilities),
            "reference_probabilities": dict(reference_probabilities),
            "observed_state_id": observed_state,
        })

    expected_keys = {(str(row.get("season", "")).strip(), str(row.get("gameweek_id", "")).strip()) for row in forecasts}
    if set(mapping_by_gw) != expected_keys:
        extras = sorted(set(mapping_by_gw) - expected_keys)
        raise JointForecastOutcomePairingError(f"realized state mappings include Gameweeks without forecasts: {extras}")

    return {
        "schema_version": "1.0.0",
        "dataset_type": "M4_COVAR_PAIRED_JOINT_FORECAST_AND_REALIZED_STATE_DATASET",
        "pairing_status": "PASS_ARCHIVED_FORECASTS_PAIRED_WITH_EXPLICIT_RECONCILED_STATES",
        "forecast_acceptance": acceptance,
        "forecast_count": len(paired),
        "gameweek_count": len(forecast_gameweeks),
        "paired_gameweeks": [
            {
                "season": season,
                "gameweek_id": gameweek,
                "forecast_count": sum(1 for row in paired if row["gameweek_id"] == gameweek),
                "observed_state_id": details["observed_state_id"],
                "state_catalogue_sha256": details["state_catalogue_sha256"],
                "player_universe_sha256": details["player_universe_sha256"],
                "resolver_name": details["resolver_name"],
                "resolver_version": details["resolver_version"],
                "mapping_source_sha256": details["mapping_source_sha256"],
                "finality_audit_status": "PASS_EXACT_MATCH",
                "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_FINAL_SCORING_AUDIT",
            }
            for (season, gameweek), details in sorted(forecast_gameweeks.items())
        ],
        "calibration_forecasts": paired,
        "observed_state_mapping_inferred_from_marginals": False,
        "fixture_independence_assumed": False,
        "historical_forecast_availability_authenticated": False,
        "realized_outcomes_are_point_in_time_features": False,
        "independence_unit": "GAMEWEEK_CLUSTER",
        "decision_weight": 0.0,
        "production_eligible": False,
        "limitations": [
            "Pairing requires an independently versioned resolver to map complete realized player outcomes to the predeclared joint state catalogue.",
            "This module verifies declared hashes and exact coverage metadata but cannot authenticate resolver code, provider availability, or the historical truth of source timestamps.",
            "A retrospective event-live finality audit does not make realized outcomes point-in-time forecast inputs.",
            "The calibration dataset is only as valid as the forecast archive, state catalogue, resolver, and finality evidence supplied.",
        ],
    }
