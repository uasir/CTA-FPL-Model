"""Evaluate pre-kickoff joint Gameweek probabilities against realized outcomes.

This is an evaluation harness, not a probability estimator. It requires a
predeclared reference forecast and strictly pre-kickoff forecast metadata.
"""
from __future__ import annotations
from datetime import datetime
import math
from typing import Any, Mapping, Sequence


class JointProbabilityCalibrationError(ValueError):
    """Invalid or temporally contaminated calibration input."""


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise JointProbabilityCalibrationError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise JointProbabilityCalibrationError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise JointProbabilityCalibrationError(f"{field} must include a timezone")
    return parsed


def _probability_map(raw: Any, field: str) -> dict[str, float]:
    if not isinstance(raw, Mapping) or not raw:
        raise JointProbabilityCalibrationError(f"{field} must be a non-empty state probability map")
    result = {}
    for raw_state, raw_probability in raw.items():
        state = str(raw_state).strip()
        if not state or state in result or isinstance(raw_probability, bool):
            raise JointProbabilityCalibrationError(f"{field} contains an invalid state or probability")
        try:
            probability = float(raw_probability)
        except (TypeError, ValueError) as exc:
            raise JointProbabilityCalibrationError(f"{field} probabilities must be numeric") from exc
        if not math.isfinite(probability) or probability < 0 or probability > 1:
            raise JointProbabilityCalibrationError(f"{field} probabilities must be finite and between 0 and 1")
        result[state] = probability
    if not math.isclose(sum(result.values()), 1.0, rel_tol=0, abs_tol=1e-9):
        raise JointProbabilityCalibrationError(f"{field} probabilities must sum to 1")
    return result


def _scores(probabilities: Mapping[str, float], observed: str) -> tuple[float, float | None]:
    brier = sum((probability - (1.0 if state == observed else 0.0)) ** 2
                for state, probability in probabilities.items())
    actual_probability = probabilities[observed]
    log_loss = -math.log(actual_probability) if actual_probability > 0 else None
    return brier, log_loss


def _reliability_bins(rows: Sequence[tuple[float, int]], bin_count: int) -> list[dict[str, Any]]:
    bins = []
    for index in range(bin_count):
        lower = index / bin_count
        upper = (index + 1) / bin_count
        selected = [(p, y) for p, y in rows
                    if lower <= p < upper or (index == bin_count - 1 and p == 1.0)]
        bins.append({
            "bin": index,
            "lower_bound": lower,
            "upper_bound": upper,
            "count": len(selected),
            "mean_forecast_probability": (sum(p for p, _ in selected) / len(selected)) if selected else None,
            "observed_frequency": (sum(y for _, y in selected) / len(selected)) if selected else None,
        })
    return bins


def evaluate_joint_probability_calibration(
    forecasts: Sequence[Mapping[str, Any]], *, reliability_bin_count: int = 10,
) -> dict[str, Any]:
    """Score joint-state forecasts against outcomes and a supplied reference.

    Each row requires forecast_id, gameweek_id, as_of_utc, first_kickoff_utc,
    training_cutoff_utc, probabilities, reference_probabilities and
    observed_state_id. The reference must be a genuinely predeclared benchmark
    (for example, a historical-frequency forecast); this function cannot prove
    how it was produced, so its provenance must be audited separately.
    """
    if not isinstance(forecasts, Sequence) or isinstance(forecasts, (str, bytes)) or not forecasts:
        raise JointProbabilityCalibrationError("forecasts must be a non-empty sequence")
    if isinstance(reliability_bin_count, bool) or not isinstance(reliability_bin_count, int) or not 2 <= reliability_bin_count <= 20:
        raise JointProbabilityCalibrationError("reliability_bin_count must be an integer from 2 to 20")

    seen = set()
    per_forecast = []
    reliability_rows: list[tuple[float, int]] = []
    total_model_brier = total_reference_brier = 0.0
    model_log_losses, reference_log_losses = [], []
    zero_model, zero_reference = 0, 0
    by_gameweek: dict[str, list[dict[str, Any]]] = {}

    for row in forecasts:
        if not isinstance(row, Mapping):
            raise JointProbabilityCalibrationError("each forecast must be an object")
        forecast_id = str(row.get("forecast_id", "")).strip()
        gameweek_id = str(row.get("gameweek_id", "")).strip()
        if not forecast_id or forecast_id in seen or not gameweek_id:
            raise JointProbabilityCalibrationError("forecast IDs must be unique and Gameweek IDs non-empty")
        seen.add(forecast_id)
        as_of = _timestamp(row.get("as_of_utc"), "as_of_utc")
        kickoff = _timestamp(row.get("first_kickoff_utc"), "first_kickoff_utc")
        training_cutoff = _timestamp(row.get("training_cutoff_utc"), "training_cutoff_utc")
        if not training_cutoff <= as_of < kickoff:
            raise JointProbabilityCalibrationError("training cutoff must not follow forecast as-of, and as-of must precede first kickoff")

        model = _probability_map(row.get("probabilities"), "probabilities")
        reference = _probability_map(row.get("reference_probabilities"), "reference_probabilities")
        if set(model) != set(reference):
            raise JointProbabilityCalibrationError("model and reference must use the same joint state catalogue")
        observed = str(row.get("observed_state_id", "")).strip()
        if observed not in model:
            raise JointProbabilityCalibrationError("observed joint state must exist in the forecast state catalogue")

        model_brier, model_log = _scores(model, observed)
        ref_brier, ref_log = _scores(reference, observed)
        total_model_brier += model_brier
        total_reference_brier += ref_brier
        if model_log is None:
            zero_model += 1
        else:
            model_log_losses.append(model_log)
        if ref_log is None:
            zero_reference += 1
        else:
            reference_log_losses.append(ref_log)
        for state, probability in model.items():
            reliability_rows.append((probability, int(state == observed)))

        result = {
            "forecast_id": forecast_id,
            "gameweek_id": gameweek_id,
            "joint_state_count": len(model),
            "observed_state_id": observed,
            "model_brier_score": model_brier,
            "reference_brier_score": ref_brier,
            "brier_score_difference_model_minus_reference": model_brier - ref_brier,
            "model_log_loss": model_log,
            "reference_log_loss": ref_log,
        }
        per_forecast.append(result)
        by_gameweek.setdefault(gameweek_id, []).append(result)

    count = len(per_forecast)
    mean_model_brier = total_model_brier / count
    mean_reference_brier = total_reference_brier / count
    grouped = {}
    for gameweek_id, rows in sorted(by_gameweek.items()):
        grouped[gameweek_id] = {
            "forecast_count": len(rows),
            "mean_model_brier_score": sum(r["model_brier_score"] for r in rows) / len(rows),
            "mean_reference_brier_score": sum(r["reference_brier_score"] for r in rows) / len(rows),
        }
    return {
        "schema_version": "1.0.0",
        "evaluation_status": "HISTORICAL_BACKTEST_ONLY",
        "forecast_count": count,
        "gameweek_count": len(grouped),
        "by_gameweek": grouped,
        "mean_model_brier_score": mean_model_brier,
        "mean_reference_brier_score": mean_reference_brier,
        "brier_skill_score_vs_reference": (
            1.0 - mean_model_brier / mean_reference_brier
            if mean_reference_brier > 0 else None
        ),
        "mean_model_log_loss": (
            sum(model_log_losses) / count if zero_model == 0 else None
        ),
        "mean_reference_log_loss": (
            sum(reference_log_losses) / count if zero_reference == 0 else None
        ),
        "zero_probability_actual_count_model": zero_model,
        "zero_probability_actual_count_reference": zero_reference,
        "reliability": {
            "method": "JOINT_STATE_ONE_VS_REST_EQUAL_WIDTH",
            "bin_count": reliability_bin_count,
            "bins": _reliability_bins(reliability_rows, reliability_bin_count),
        },
        "per_forecast": per_forecast,
        "decision_weight": 0.0,
        "production_eligible": False,
    }
