#!/usr/bin/env python3
"""Match genuine pre-deadline conventional forecasts to final official FPL outcomes.

The matcher is deliberately a join/validation layer, not a forecast estimator.
It requires an explicit PASS_ALL_EVENTS finality audit and never zero-fills
missing player-Gameweek observations.
"""
from __future__ import annotations

from datetime import datetime
import math
from typing import Any, Mapping, Sequence


class ForecastOutcomeMatchError(ValueError):
    """Forecast and realized outcomes cannot be safely matched."""


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ForecastOutcomeMatchError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ForecastOutcomeMatchError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ForecastOutcomeMatchError(f"{field} must include a timezone")
    return parsed


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ForecastOutcomeMatchError(f"{field} must be finite numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ForecastOutcomeMatchError(f"{field} must be finite numeric") from exc
    if not math.isfinite(number):
        raise ForecastOutcomeMatchError(f"{field} must be finite numeric")
    return number


def match_forecast_to_realized_outcomes(
    forecast_bundle: Mapping[str, Any],
    realized_gameweek_rows: Sequence[Mapping[str, Any]],
    realized_fixture_rows: Sequence[Mapping[str, Any]],
    finality_batch_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Create matched forecast/outcome rows for one Gameweek.

    A row is admitted only when its player ID exists in both the forecast and
    realized panel, the target Gameweek passed exact official event-live
    reconciliation, and forecast/source timestamps precede the first kickoff.
    """
    if not isinstance(forecast_bundle, Mapping):
        raise ForecastOutcomeMatchError("forecast_bundle must be an object")
    if forecast_bundle.get("bundle_type") != "M3_CONVENTIONAL_FORECAST_ONLY_COVAR_INPUT":
        raise ForecastOutcomeMatchError("unsupported forecast bundle type")
    if forecast_bundle.get("decision_weight") != 0.0 or forecast_bundle.get("production_eligible") is not False:
        raise ForecastOutcomeMatchError("forecast bundle must remain research-only")
    privacy = forecast_bundle.get("privacy")
    if not isinstance(privacy, Mapping) or any(privacy.get(key) is not False for key in (
        "manager_identity_included", "manager_squad_included",
        "bank_or_transfer_state_included", "frozen_decision_included",
    )):
        raise ForecastOutcomeMatchError("forecast bundle privacy declarations must explicitly exclude manager data")

    season = forecast_bundle.get("season")
    gw = forecast_bundle.get("target_gameweek")
    if not isinstance(season, str) or not season.strip() or isinstance(gw, bool) or not isinstance(gw, int) or gw < 1:
        raise ForecastOutcomeMatchError("forecast season and target Gameweek are required")
    if not isinstance(realized_gameweek_rows, Sequence) or not realized_gameweek_rows:
        raise ForecastOutcomeMatchError("realized_gameweek_rows must be non-empty")
    if not isinstance(realized_fixture_rows, Sequence) or not realized_fixture_rows:
        raise ForecastOutcomeMatchError("realized_fixture_rows must be non-empty")

    finality = finality_batch_report
    if not isinstance(finality, Mapping) or finality.get("status") != "PASS_ALL_EVENTS":
        raise ForecastOutcomeMatchError("finality batch must have status PASS_ALL_EVENTS")
    if finality.get("season") != season or gw not in finality.get("events_checked", []):
        raise ForecastOutcomeMatchError("finality batch does not cover the forecast season and Gameweek")
    reports = finality.get("reports")
    if not isinstance(reports, list):
        raise ForecastOutcomeMatchError("finality batch reports are required")
    matching_reports = [row for row in reports if isinstance(row, Mapping) and row.get("event_id") == gw]
    if len(matching_reports) != 1 or matching_reports[0].get("status") != "PASS_EXACT_MATCH" or matching_reports[0].get("finality_reconciled") is not True:
        raise ForecastOutcomeMatchError("target Gameweek lacks an exact official event-live finality pass")

    as_of = _time(forecast_bundle.get("as_of_utc"), "forecast as_of_utc")
    deadline = _time(forecast_bundle.get("deadline_utc"), "forecast deadline_utc")
    if as_of >= deadline:
        raise ForecastOutcomeMatchError("forecast as-of must precede deadline")
    source_archives = forecast_bundle.get("source_archives")
    if not isinstance(source_archives, list) or len(source_archives) < 2:
        raise ForecastOutcomeMatchError("forecast source archives are required")
    for source in source_archives:
        if not isinstance(source, Mapping):
            raise ForecastOutcomeMatchError("forecast source archive rows must be objects")
        captured = _time(source.get("captured_at_utc"), "source captured_at_utc")
        if captured > as_of:
            raise ForecastOutcomeMatchError("source capture occurred after forecast as-of")
        if source.get("source_type") == "provider_forecast":
            generated = _time(source.get("generated_at_utc"), "provider generated_at_utc")
            if generated > as_of:
                raise ForecastOutcomeMatchError("provider generation occurred after forecast as-of")

    fixture_rows = []
    for row in realized_fixture_rows:
        if row.get("season") == season and row.get("gameweek") == gw:
            fixture_rows.append(row)
    if not fixture_rows:
        raise ForecastOutcomeMatchError("no realized fixture rows for target Gameweek")
    kickoff_values = [_time(row.get("kickoff_time"), "fixture kickoff_time") for row in fixture_rows]
    first_kickoff = min(kickoff_values)
    if as_of >= first_kickoff:
        raise ForecastOutcomeMatchError("forecast as-of is not strictly before first fixture kickoff")
    for source in source_archives:
        if _time(source.get("captured_at_utc"), "source captured_at_utc") >= first_kickoff:
            raise ForecastOutcomeMatchError("forecast source capture is not strictly before first kickoff")

    forecasts = forecast_bundle.get("player_forecasts")
    if not isinstance(forecasts, list) or not forecasts:
        raise ForecastOutcomeMatchError("player_forecasts must be non-empty")
    forecast_by_id = {}
    for row in forecasts:
        if not isinstance(row, Mapping):
            raise ForecastOutcomeMatchError("forecast player rows must be objects")
        pid = row.get("fpl_element_id")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1 or pid in forecast_by_id:
            raise ForecastOutcomeMatchError("forecast player IDs must be unique positive integers")
        forecast_by_id[pid] = row

    realized_by_id = {}
    for row in realized_gameweek_rows:
        if row.get("season") != season or int(row.get("gameweek", -1)) != gw:
            raise ForecastOutcomeMatchError("realized player-Gameweek rows must match target season and Gameweek")
        pid = int(row.get("fpl_element_id", -1))
        if pid < 1 or pid in realized_by_id:
            raise ForecastOutcomeMatchError("realized player IDs must be unique positive integers")
        realized_by_id[pid] = row

    matched = []
    for pid in sorted(set(forecast_by_id) & set(realized_by_id)):
        forecast = forecast_by_id[pid]
        actual = realized_by_id[pid]
        xp = _finite(forecast.get("expected_points"), f"player {pid} expected_points")
        expected_minutes = _finite(forecast.get("expected_minutes"), f"player {pid} expected_minutes")
        points = _finite(actual.get("total_points"), f"player {pid} total_points")
        minutes = _finite(actual.get("minutes"), f"player {pid} minutes")
        matched.append({
            "season": season,
            "gameweek": gw,
            "fpl_element_id": pid,
            "expected_points": xp,
            "actual_points": points,
            "points_error_actual_minus_expected": points - xp,
            "absolute_points_error": abs(points - xp),
            "expected_minutes": expected_minutes,
            "actual_minutes": minutes,
            "minutes_error_actual_minus_expected": minutes - expected_minutes,
            "forecast_snapshot_id": forecast_bundle.get("forecast_snapshot_id"),
            "model_version": forecast_bundle.get("model_version"),
            "forecast_as_of_utc": as_of.isoformat(),
            "first_kickoff_utc": first_kickoff.isoformat(),
            "finality_status": "PASS_EXACT_MATCH",
        })

    if not matched:
        raise ForecastOutcomeMatchError("forecast and realized panel have no matched player IDs")
    unmatched_forecast = sorted(set(forecast_by_id) - set(realized_by_id))
    unmatched_realized = sorted(set(realized_by_id) - set(forecast_by_id))
    return {
        "schema_version": "1.0.0",
        "dataset_type": "PROSPECTIVE_CONVENTIONAL_FORECAST_TO_FINAL_OUTCOME_MATCH",
        "season": season,
        "gameweek": gw,
        "forecast_snapshot_id": forecast_bundle.get("forecast_snapshot_id"),
        "model_version": forecast_bundle.get("model_version"),
        "forecast_as_of_utc": as_of.isoformat(),
        "deadline_utc": deadline.isoformat(),
        "first_kickoff_utc": first_kickoff.isoformat(),
        "finality_status": "PASS_EXACT_MATCH",
        "forecast_player_count": len(forecast_by_id),
        "realized_player_gameweek_count": len(realized_by_id),
        "matched_player_count": len(matched),
        "forecast_players_without_observed_realized_row": len(unmatched_forecast),
        "realized_rows_without_forecast": len(unmatched_realized),
        "unmatched_forecast_player_ids": unmatched_forecast,
        "unmatched_realized_player_ids": unmatched_realized,
        "matched_rows": matched,
        "missing_observations_zero_filled": 0,
        "interpretation": "One prospective player-Gameweek forecast snapshot matched to retrospectively final-scoring-reconciled outcomes; not evidence of joint dependence calibration.",
        "decision_weight": 0.0,
        "production_eligible": False,
    }
