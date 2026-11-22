#!/usr/bin/env python3
"""Build a research-only joint Gameweek scenario set from matched forecast residual blocks.

This producer preserves cross-player dependence by resampling complete historical
Gameweek residual vectors. It does not infer fixture states, assume independence,
fit a parametric distribution, or claim calibrated probabilities.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
from datetime import datetime
from typing import Any, Mapping


class ResidualBootstrapError(ValueError):
    """Input evidence cannot support a leakage-safe residual bootstrap."""


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ResidualBootstrapError(f"{label} must be an ISO-8601 timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResidualBootstrapError(f"{label} must be an ISO-8601 timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ResidualBootstrapError(f"{label} must include a timezone")
    return result


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ResidualBootstrapError(f"{label} must be finite numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ResidualBootstrapError(f"{label} must be finite numeric") from exc
    if not math.isfinite(result):
        raise ResidualBootstrapError(f"{label} must be finite numeric")
    return result


def build_residual_bootstrap_scenarios(
    target_forecast: Mapping[str, Any],
    matched_panel: Mapping[str, Any],
    *,
    training_cutoff_utc: str,
    minimum_gameweeks: int = 5,
) -> dict[str, Any]:
    """Create equal-weight joint scenarios from complete, prior-GW residual blocks.

    Every selected historical Gameweek must contain an observed matched row for
    every target player. Missing player-GW observations are never zero-filled.
    Residuals are centered player-wise so supplied target expected-points means
    remain the scenario means. Whole Gameweek vectors preserve observed
    cross-player residual dependence.
    """
    if not isinstance(target_forecast, Mapping) or not isinstance(matched_panel, Mapping):
        raise ResidualBootstrapError("target_forecast and matched_panel must be objects")
    if target_forecast.get("bundle_type") != "M3_CONVENTIONAL_FORECAST_ONLY_COVAR_INPUT":
        raise ResidualBootstrapError("target must be the manager-free conventional M3 forecast bundle")
    if target_forecast.get("decision_weight") != 0.0 or target_forecast.get("production_eligible") is not False:
        raise ResidualBootstrapError("target forecast must remain research-only")
    privacy = target_forecast.get("privacy")
    if not isinstance(privacy, Mapping) or any(privacy.get(key) is not False for key in (
        "manager_identity_included", "manager_squad_included",
        "bank_or_transfer_state_included", "frozen_decision_included",
    )):
        raise ResidualBootstrapError("target forecast must explicitly exclude all manager-specific data")
    if target_forecast.get("point_in_time_status") != "M3_SOURCE_TIMESTAMPS_VALIDATED":
        raise ResidualBootstrapError("target M3 source timestamps must be validated")
    if matched_panel.get("dataset_type") != "MULTI_GAMEWEEK_PROSPECTIVE_CONVENTIONAL_FORECAST_OUTCOME_PANEL":
        raise ResidualBootstrapError("unsupported matched outcome panel")
    if matched_panel.get("cluster_unit") != "GAMEWEEK" or matched_panel.get("missing_observations_zero_filled") != 0:
        raise ResidualBootstrapError("panel must be Gameweek-clustered and contain no zero-filled missing observations")
    if matched_panel.get("joint_dependence_inferred_from_marginal_player_rows") is not False:
        raise ResidualBootstrapError("panel must not infer dependence from marginal rows")
    if target_forecast.get("season") != matched_panel.get("season"):
        raise ResidualBootstrapError("target and historical panel seasons must match")

    target_gw = target_forecast.get("target_gameweek")
    if isinstance(target_gw, bool) or not isinstance(target_gw, int) or target_gw < 1:
        raise ResidualBootstrapError("target_gameweek must be a positive integer")
    if isinstance(minimum_gameweeks, bool) or not isinstance(minimum_gameweeks, int) or minimum_gameweeks < 2:
        raise ResidualBootstrapError("minimum_gameweeks must be an integer >= 2")

    as_of = _time(target_forecast.get("as_of_utc"), "target as_of_utc")
    cutoff = _time(training_cutoff_utc, "training_cutoff_utc")
    deadline = _time(target_forecast.get("deadline_utc"), "target deadline_utc")
    if cutoff > as_of or as_of >= deadline:
        raise ResidualBootstrapError("training cutoff <= forecast as-of < deadline is required")

    source_archives = target_forecast.get("source_archives")
    if not isinstance(source_archives, list) or len(source_archives) < 2:
        raise ResidualBootstrapError("target M3 source archives are required")
    source_types = set()
    for source in source_archives:
        if not isinstance(source, Mapping):
            raise ResidualBootstrapError("target source archive rows must be objects")
        source_type = source.get("source_type")
        if source_type not in {"provider_forecast", "player_metadata"} or source_type in source_types:
            raise ResidualBootstrapError("target requires unique provider_forecast and player_metadata archives")
        source_types.add(source_type)
        captured = _time(source.get("captured_at_utc"), f"{source_type}.captured_at_utc")
        if captured > as_of:
            raise ResidualBootstrapError(f"{source_type} source was captured after target as-of")
        raw_b64 = source.get("raw_payload_base64")
        if not isinstance(raw_b64, str) or not raw_b64:
            raise ResidualBootstrapError(f"{source_type} raw source bytes are missing")
        try:
            raw = base64.b64decode(raw_b64, validate=True)
        except (ValueError, TypeError) as exc:
            raise ResidualBootstrapError(f"{source_type} raw source bytes are invalid base64") from exc
        digest = hashlib.sha256(raw).hexdigest()
        if digest != source.get("raw_sha256"):
            raise ResidualBootstrapError(f"{source_type} source SHA-256 mismatch")
        if source_type == "provider_forecast":
            generated = _time(source.get("generated_at_utc"), "provider_forecast.generated_at_utc")
            if generated > as_of:
                raise ResidualBootstrapError("provider forecast was generated after target as-of")
    if source_types != {"provider_forecast", "player_metadata"}:
        raise ResidualBootstrapError("provider_forecast and player_metadata source archives are required")

    snapshot_id = str(target_forecast.get("forecast_snapshot_id", "")).strip()
    model_version = str(target_forecast.get("model_version", "")).strip()
    if not snapshot_id or not model_version:
        raise ResidualBootstrapError("target forecast snapshot ID and model version are required")
    forecasts = target_forecast.get("player_forecasts")
    if not isinstance(forecasts, list) or not forecasts:
        raise ResidualBootstrapError("target player_forecasts must be non-empty")
    target_by_id: dict[str, dict[str, float]] = {}
    for row in forecasts:
        if not isinstance(row, Mapping):
            raise ResidualBootstrapError("target player forecast rows must be objects")
        pid = str(row.get("fpl_element_id", "")).strip()
        if not pid.isdigit() or int(pid) < 1 or pid in target_by_id:
            raise ResidualBootstrapError("target player IDs must be unique positive FPL element IDs")
        ep = _finite(row.get("expected_points"), f"target player {pid} expected_points")
        mins = _finite(row.get("expected_minutes"), f"target player {pid} expected_minutes")
        if not 0 <= mins <= 90:
            raise ResidualBootstrapError(f"target player {pid} expected_minutes must be in [0, 90]")
        target_by_id[pid] = {"expected_points": ep, "expected_minutes": mins}

    clusters = matched_panel.get("gameweek_clusters")
    rows = matched_panel.get("matched_rows")
    if not isinstance(clusters, list) or not isinstance(rows, list) or not clusters or not rows:
        raise ResidualBootstrapError("matched panel requires gameweek_clusters and matched_rows")
    declared_gws = set()
    for cluster in clusters:
        if not isinstance(cluster, Mapping):
            raise ResidualBootstrapError("gameweek cluster rows must be objects")
        gw = cluster.get("gameweek")
        if isinstance(gw, bool) or not isinstance(gw, int) or gw < 1 or gw in declared_gws:
            raise ResidualBootstrapError("historical Gameweek IDs must be unique positive integers")
        if gw == target_gw:
            raise ResidualBootstrapError("target Gameweek cannot appear in historical residuals")
        if not cluster.get("outcome_available_at_utc"):
            raise ResidualBootstrapError("each historical cluster requires outcome_available_at_utc; finality alone does not prove availability time")
        available = _time(cluster["outcome_available_at_utc"], f"GW{gw} outcome_available_at_utc")
        if available >= cutoff:
            raise ResidualBootstrapError(f"GW{gw} outcome was not available strictly before training cutoff")
        if cluster.get("finality_status") != "PASS_EXACT_MATCH":
            raise ResidualBootstrapError(f"GW{gw} lacks exact finality reconciliation")
        declared_gws.add(gw)

    by_gw: dict[int, dict[str, float]] = {gw: {} for gw in declared_gws}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ResidualBootstrapError("matched rows must be objects")
        try:
            gw = int(row.get("gameweek"))
        except (TypeError, ValueError) as exc:
            raise ResidualBootstrapError("matched row Gameweek must be an integer") from exc
        pid = str(row.get("fpl_element_id", "")).strip()
        if gw not in by_gw or not pid.isdigit() or int(pid) < 1:
            raise ResidualBootstrapError("matched row references an undeclared Gameweek or invalid FPL element ID")
        if pid in by_gw[gw]:
            raise ResidualBootstrapError(f"duplicate matched player row for GW{gw}, player {pid}")
        if row.get("finality_status") != "PASS_EXACT_MATCH":
            raise ResidualBootstrapError(f"GW{gw} player row lacks exact finality reconciliation")
        if row.get("model_version") != model_version:
            raise ResidualBootstrapError("historical and target conventional model versions must match")
        by_gw[gw][pid] = _finite(
            row.get("points_error_actual_minus_expected"),
            f"GW{gw} player {pid} points residual",
        )

    target_ids = set(target_by_id)
    complete_blocks, excluded_gws = [], []
    for gw in sorted(by_gw):
        missing = target_ids - set(by_gw[gw])
        if not missing:
            complete_blocks.append(gw)
        else:
            excluded_gws.append({"gameweek": gw, "missing_target_player_ids": sorted(missing, key=int)})
    if len(complete_blocks) < minimum_gameweeks:
        raise ResidualBootstrapError(
            f"only {len(complete_blocks)} complete Gameweek residual blocks; minimum required is {minimum_gameweeks}"
        )

    mean_residual = {
        pid: sum(by_gw[gw][pid] for gw in complete_blocks) / len(complete_blocks)
        for pid in target_by_id
    }
    scenarios = []
    for gw in complete_blocks:
        outcomes = []
        for pid in sorted(target_by_id, key=int):
            centered = by_gw[gw][pid] - mean_residual[pid]
            outcomes.append({
                "player_id": pid,
                "fpl_points": target_by_id[pid]["expected_points"] + centered,
                "residual_source_gameweek": gw,
            })
        scenarios.append({
            "scenario_id": f"residual-gw-{gw}",
            "source_gameweek": gw,
            "probability": 1.0 / len(complete_blocks),
            "player_outcomes": outcomes,
        })

    payload = {
        "schema_version": "1.0.0",
        "dataset_type": "M4_COVAR_PLAYER_GAMEWEEK_RESIDUAL_BOOTSTRAP_RESEARCH_ONLY",
        "season": target_forecast["season"],
        "target_gameweek": target_gw,
        "forecast_snapshot_id": snapshot_id,
        "model_version": model_version,
        "training_cutoff_utc": cutoff.isoformat(),
        "as_of_utc": as_of.isoformat(),
        "player_count": len(target_by_id),
        "scenario_count": len(scenarios),
        "complete_historical_gameweeks": complete_blocks,
        "excluded_historical_gameweeks": excluded_gws,
        "scenarios": scenarios,
        "marginal_expected_points_preserved": True,
        "dependence_method": "CENTERED_WHOLE_GAMEWEEK_PLAYER_POINT_RESIDUAL_BLOCK_BOOTSTRAP",
        "scenario_probability_method": "EQUAL_WEIGHT_EMPIRICAL_COMPLETE_GAMEWEEK_BLOCKS",
        "probability_calibrated": False,
        "decision_weight": 0.0,
        "production_eligible": False,
        "covar_used": False,
        "limitations": [
            "Research baseline only; empirical probabilities are not calibrated forecasts.",
            "Only complete historical Gameweek residual vectors covering every target player are used.",
            "Residual dependence is conditional only through the fixed target forecast and is not a fixture-event model.",
            "At least five clusters is a prototype floor, not evidence of statistical adequacy.",
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    payload["payload_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload
