"""Build leakage-safe expanding-window historical-frequency reference forecasts."""
from __future__ import annotations

from datetime import datetime
import math
from typing import Any, Mapping, Sequence


class HistoricalFrequencyBenchmarkError(ValueError):
    """Invalid or temporally contaminated reference benchmark inputs."""


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise HistoricalFrequencyBenchmarkError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HistoricalFrequencyBenchmarkError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HistoricalFrequencyBenchmarkError(f"{field} must include a timezone")
    return parsed


def build_expanding_window_frequency_reference(
    forecasts: Sequence[Mapping[str, Any]],
    historical_outcomes: Sequence[Mapping[str, Any]],
    state_catalogue: Sequence[str],
    *,
    smoothing_alpha: float = 1.0,
) -> dict[str, Any]:
    """Attach an expanding-window historical-frequency reference per forecast.

    historical_outcomes contains one realized joint state per completed
    Gameweek, with gameweek_id and first_kickoff_utc. Only outcomes whose
    Gameweek kickoff strictly precedes that forecast's training cutoff are
    eligible. Repeated forecast snapshots never become additional outcome
    observations. The explicit state catalogue is fixed for all rows.
    """
    if not isinstance(forecasts, Sequence) or isinstance(forecasts, (str, bytes)) or not forecasts:
        raise HistoricalFrequencyBenchmarkError("forecasts must be a non-empty sequence")
    if not isinstance(historical_outcomes, Sequence) or isinstance(historical_outcomes, (str, bytes)) or not historical_outcomes:
        raise HistoricalFrequencyBenchmarkError("historical_outcomes must be a non-empty sequence")
    if not isinstance(state_catalogue, Sequence) or isinstance(state_catalogue, (str, bytes)) or not state_catalogue:
        raise HistoricalFrequencyBenchmarkError("state_catalogue must be a non-empty sequence")
    states = [str(value).strip() for value in state_catalogue]
    if any(not value for value in states) or len(states) != len(set(states)):
        raise HistoricalFrequencyBenchmarkError("state_catalogue values must be non-empty and unique")
    if isinstance(smoothing_alpha, bool) or not isinstance(smoothing_alpha, (int, float)) or not math.isfinite(float(smoothing_alpha)) or smoothing_alpha <= 0:
        raise HistoricalFrequencyBenchmarkError("smoothing_alpha must be finite and greater than zero")

    outcomes = {}
    for row in historical_outcomes:
        if not isinstance(row, Mapping):
            raise HistoricalFrequencyBenchmarkError("each historical outcome must be an object")
        gw = str(row.get("gameweek_id", "")).strip()
        state = str(row.get("observed_state_id", "")).strip()
        if not gw or gw in outcomes:
            raise HistoricalFrequencyBenchmarkError("historical outcomes require unique non-empty Gameweek IDs")
        if state not in states:
            raise HistoricalFrequencyBenchmarkError("historical outcome state is outside the declared catalogue")
        kickoff = _time(row.get("first_kickoff_utc"), "historical first_kickoff_utc")
        outcomes[gw] = {"state": state, "kickoff": kickoff}

    forecast_ids = set()
    result_rows = []
    for row in forecasts:
        if not isinstance(row, Mapping):
            raise HistoricalFrequencyBenchmarkError("each forecast must be an object")
        forecast_id = str(row.get("forecast_id", "")).strip()
        gameweek_id = str(row.get("gameweek_id", "")).strip()
        if not forecast_id or forecast_id in forecast_ids or not gameweek_id:
            raise HistoricalFrequencyBenchmarkError("forecast IDs must be unique and Gameweek IDs non-empty")
        forecast_ids.add(forecast_id)
        cutoff = _time(row.get("training_cutoff_utc"), "training_cutoff_utc")
        as_of = _time(row.get("as_of_utc"), "as_of_utc")
        kickoff = _time(row.get("first_kickoff_utc"), "first_kickoff_utc")
        if not cutoff <= as_of < kickoff:
            raise HistoricalFrequencyBenchmarkError("forecast timestamps violate cutoff <= as-of < kickoff")
        if gameweek_id in outcomes:
            raise HistoricalFrequencyBenchmarkError("target Gameweek cannot appear in historical outcomes")
        eligible = [item for item in outcomes.values() if item["kickoff"] < cutoff]
        counts = {state: 0 for state in states}
        for item in eligible:
            counts[item["state"]] += 1
        denominator = len(eligible) + float(smoothing_alpha) * len(states)
        probabilities = {
            state: (counts[state] + float(smoothing_alpha)) / denominator
            for state in states
        }
        result_rows.append({
            **dict(row),
            "reference_probabilities": probabilities,
            "reference_benchmark": {
                "method": "EXPANDING_WINDOW_GAMEWEEK_HISTORICAL_FREQUENCY",
                "training_gameweek_count": len(eligible),
                "state_counts": counts,
                "smoothing_alpha": float(smoothing_alpha),
                "training_cutoff_utc": cutoff.isoformat(),
                "eligible_gameweek_ids": sorted(
                    gw for gw, item in outcomes.items() if item["kickoff"] < cutoff
                ),
            },
        })
    return {
        "schema_version": "1.0.0",
        "benchmark_status": "LEAKAGE_CHECKED_REFERENCE_FORECASTS_BUILT",
        "forecast_count": len(result_rows),
        "historical_outcome_gameweek_count": len(outcomes),
        "state_catalogue": states,
        "reference_method": "EXPANDING_WINDOW_GAMEWEEK_HISTORICAL_FREQUENCY",
        "smoothing_alpha": float(smoothing_alpha),
        "forecasts": result_rows,
        "leakage_policy": "ONLY_GAMEWEEK_OUTCOMES_WITH_FIRST_KICKOFF_STRICTLY_BEFORE_EACH_FORECAST_TRAINING_CUTOFF",
        "decision_weight": 0.0,
        "production_eligible": False,
    }
