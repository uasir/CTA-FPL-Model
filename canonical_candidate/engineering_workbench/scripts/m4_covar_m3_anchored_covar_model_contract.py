"""Leakage-aware input contract for the M3-anchored CoVar scenario model.

This contract does not generate scenarios or probabilities. It verifies that a
conventional M3 player forecast and historical official FPL outcomes can be
paired without using target/future Gameweeks or outcomes unavailable by the
declared training cutoff.
"""
from __future__ import annotations
import math
import re
from datetime import datetime
from typing import Any, Mapping, Sequence

class M3AnchoredCovarModelInputError(ValueError):
    """M3 anchor or historical training inputs are incomplete or contaminated."""

_SHA256 = re.compile(r"^[0-9a-f]{64}$")

def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise M3AnchoredCovarModelInputError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise M3AnchoredCovarModelInputError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise M3AnchoredCovarModelInputError(f"{field} must include a timezone")
    return parsed

def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value.lower()):
        raise M3AnchoredCovarModelInputError(f"{field} must be a SHA-256 digest")
    return value.lower()

def validate_m3_anchored_covar_model_inputs(*, m3_forecast_anchor: Mapping[str, Any],
        historical_gameweeks: Sequence[Mapping[str, Any]], target_first_kickoff_utc: str,
        training_cutoff_utc: str) -> dict[str, Any]:
    """Validate the M3 xP anchor and leakage-safe, reconciled historical outcomes.

    Each historical Gameweek row requires gameweek, first_kickoff_utc,
    outcome_available_at_utc, finality_audit_status, outcome_dataset_sha256,
    availability_evidence_type and non-empty player_fixture_outcomes.
    This is a structural/chronological gate only: declared historical
    availability is not independently authenticated by this function.
    """
    if not isinstance(m3_forecast_anchor, Mapping):
        raise M3AnchoredCovarModelInputError("m3_forecast_anchor must be an object")
    if m3_forecast_anchor.get("bundle_type") != "M3_CONVENTIONAL_FORECAST_ONLY_COVAR_INPUT":
        raise M3AnchoredCovarModelInputError("forecast anchor must be the conventional M3 CoVar bundle")
    if m3_forecast_anchor.get("mode") != "REGULAR_GW":
        raise M3AnchoredCovarModelInputError("initial CoVar model contract accepts regular Gameweeks only")
    if m3_forecast_anchor.get("decision_weight") != 0 or m3_forecast_anchor.get("production_eligible") is not False:
        raise M3AnchoredCovarModelInputError("M3 CoVar anchor must remain research-only")
    season = m3_forecast_anchor.get("season")
    if not isinstance(season, str) or not season.strip():
        raise M3AnchoredCovarModelInputError("M3 anchor season is required")
    try:
        target_gw = int(m3_forecast_anchor.get("target_gameweek"))
    except (TypeError, ValueError) as exc:
        raise M3AnchoredCovarModelInputError("M3 anchor target_gameweek must be a positive integer") from exc
    if isinstance(m3_forecast_anchor.get("target_gameweek"), bool) or target_gw < 1:
        raise M3AnchoredCovarModelInputError("M3 anchor target_gameweek must be a positive integer")
    as_of = _time(m3_forecast_anchor.get("as_of_utc"), "m3_forecast_anchor.as_of_utc")
    deadline = _time(m3_forecast_anchor.get("deadline_utc"), "m3_forecast_anchor.deadline_utc")
    kickoff = _time(target_first_kickoff_utc, "target_first_kickoff_utc")
    cutoff = _time(training_cutoff_utc, "training_cutoff_utc")
    if not cutoff <= as_of < deadline or as_of >= kickoff:
        raise M3AnchoredCovarModelInputError("require training cutoff <= M3 as-of < deadline and first kickoff")
    forecasts = m3_forecast_anchor.get("player_forecasts")
    if not isinstance(forecasts, list) or not forecasts:
        raise M3AnchoredCovarModelInputError("M3 anchor player_forecasts must be non-empty")
    forecast_ids: set[int] = set()
    for row in forecasts:
        if not isinstance(row, Mapping):
            raise M3AnchoredCovarModelInputError("M3 forecast player rows must be objects")
        pid = row.get("fpl_element_id")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1 or pid in forecast_ids:
            raise M3AnchoredCovarModelInputError("M3 forecast player IDs must be unique positive integers")
        forecast_ids.add(pid)
        for field in ("expected_points", "expected_minutes"):
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise M3AnchoredCovarModelInputError(f"M3 player {pid} {field} must be finite numeric")
        if row["expected_minutes"] < 0 or row["expected_minutes"] > 180:
            raise M3AnchoredCovarModelInputError(f"M3 player {pid} expected_minutes outside [0,180]")
    if not isinstance(historical_gameweeks, Sequence) or isinstance(historical_gameweeks, (str, bytes)) or not historical_gameweeks:
        raise M3AnchoredCovarModelInputError("historical_gameweeks must be a non-empty sequence")
    seen_gws: set[int] = set()
    used_rows = 0
    for history in historical_gameweeks:
        if not isinstance(history, Mapping):
            raise M3AnchoredCovarModelInputError("historical Gameweek rows must be objects")
        try:
            gw = int(history.get("gameweek"))
        except (TypeError, ValueError) as exc:
            raise M3AnchoredCovarModelInputError("historical gameweek must be a positive integer") from exc
        if isinstance(history.get("gameweek"), bool) or gw < 1 or gw >= target_gw or gw in seen_gws:
            raise M3AnchoredCovarModelInputError("historical Gameweeks must be unique and strictly before target Gameweek")
        seen_gws.add(gw)
        first_kickoff = _time(history.get("first_kickoff_utc"), f"GW{gw}.first_kickoff_utc")
        available = _time(history.get("outcome_available_at_utc"), f"GW{gw}.outcome_available_at_utc")
        if first_kickoff >= kickoff or available >= cutoff:
            raise M3AnchoredCovarModelInputError(f"GW{gw} outcome was not available strictly before training cutoff")
        if available < first_kickoff:
            raise M3AnchoredCovarModelInputError(f"GW{gw} outcome availability precedes its first kickoff")
        if history.get("finality_audit_status") != "PASS_EXACT_MATCH":
            raise M3AnchoredCovarModelInputError(f"GW{gw} lacks a passing official FPL finality audit")
        _digest(history.get("outcome_dataset_sha256"), f"GW{gw}.outcome_dataset_sha256")
        if history.get("availability_evidence_type") not in {"OFFICIAL_EVENT_LIVE_CAPTURE", "OFFICIAL_FINISHED_FIXTURE_TIMESTAMPS"}:
            raise M3AnchoredCovarModelInputError(f"GW{gw} availability evidence type is unsupported")
        outcomes = history.get("player_fixture_outcomes")
        if not isinstance(outcomes, list) or not outcomes:
            raise M3AnchoredCovarModelInputError(f"GW{gw} player_fixture_outcomes must be non-empty")
        seen_keys = set()
        for outcome in outcomes:
            if not isinstance(outcome, Mapping):
                raise M3AnchoredCovarModelInputError(f"GW{gw} player-fixture outcomes must be objects")
            pid, fixture_id = outcome.get("fpl_element_id"), outcome.get("fixture_id")
            if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1:
                raise M3AnchoredCovarModelInputError(f"GW{gw} player outcome has invalid FPL player ID")
            if isinstance(fixture_id, bool) or not isinstance(fixture_id, int) or fixture_id < 1:
                raise M3AnchoredCovarModelInputError(f"GW{gw} player outcome has invalid fixture ID")
            key = (pid, fixture_id)
            if key in seen_keys:
                raise M3AnchoredCovarModelInputError(f"GW{gw} has duplicate player-fixture outcome {key}")
            seen_keys.add(key)
            for field in ("minutes", "total_points"):
                value = outcome.get(field)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                    raise M3AnchoredCovarModelInputError(f"GW{gw} {key}.{field} must be finite numeric")
            if outcome["minutes"] < 0 or outcome["minutes"] > 120:
                raise M3AnchoredCovarModelInputError(f"GW{gw} {key}.minutes outside [0,120]")
        used_rows += len(outcomes)
    return {
        "schema_version": "1.0.0",
        "validation_status": "M3_ANCHORED_COVAR_MODEL_INPUTS_ACCEPTED",
        "season": season,
        "target_gameweek": target_gw,
        "forecast_snapshot_id": m3_forecast_anchor.get("forecast_snapshot_id"),
        "model_version": m3_forecast_anchor.get("model_version"),
        "player_anchor_count": len(forecast_ids),
        "historical_gameweek_count": len(seen_gws),
        "historical_gameweeks": sorted(seen_gws),
        "historical_player_fixture_row_count": used_rows,
        "training_cutoff_utc": cutoff.isoformat(),
        "m3_as_of_utc": as_of.isoformat(),
        "target_first_kickoff_utc": kickoff.isoformat(),
        "historical_finality_required": "PASS_EXACT_MATCH",
        "historical_availability_chronology_checked": True,
        "historical_availability_authentication_verified": False,
        "uses_m3_player_expected_points_as_mean_anchor": True,
        "joint_probabilities_generated": False,
        "decision_weight": 0.0,
        "production_eligible": False,
        "limitations": [
            "This contract validates inputs only; it does not generate scenarios or probabilities.",
            "Historical availability timestamps are checked structurally but are not independently authenticated.",
            "M3 xP is a player-level expectation and does not itself define marginal distributions or joint dependence.",
            "No CTA forecast model is used as the CoVar probability source.",
        ],
    }
