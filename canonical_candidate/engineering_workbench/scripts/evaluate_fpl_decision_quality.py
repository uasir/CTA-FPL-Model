#!/usr/bin/env python3
"""Evaluate FPL forecasts as distributions and decisions, not exact-score guesses.

Large realised hauls remain in the evaluation cohort. The evaluator reports
point-error metrics alongside threshold-probability calibration and ranking
quality. Post-deadline event annotations are explanatory only and must never
enter model features or forecast construction.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable, Mapping, Sequence


def _finite(values: Iterable[float]) -> list[float]:
    result = [float(v) for v in values]
    if not result or any(not math.isfinite(v) for v in result):
        raise ValueError("Expected a non-empty sequence of finite values")
    return result


def point_error_metrics(actual: Sequence[float], predicted: Sequence[float]) -> dict:
    y, p = _finite(actual), _finite(predicted)
    if len(y) != len(p):
        raise ValueError("actual and predicted must be aligned")
    errors = [a - b for a, b in zip(y, p)]
    absolute = [abs(e) for e in errors]
    squared = [e * e for e in errors]
    ordered = sorted(absolute)

    def quantile(q: float) -> float:
        index = (len(ordered) - 1) * q
        lo, hi = math.floor(index), math.ceil(index)
        return ordered[lo] if lo == hi else ordered[lo] * (hi-index) + ordered[hi] * (index-lo)

    return {
        "n": len(y),
        "mae": sum(absolute) / len(y),
        "rmse": math.sqrt(sum(squared) / len(y)),
        "mean_signed_error_actual_minus_predicted": sum(errors) / len(errors),
        "absolute_error_p50": quantile(.50),
        "absolute_error_p90": quantile(.90),
        "absolute_error_p95": quantile(.95),
        "absolute_error_p99": quantile(.99),
        "large_error_rate_ge_6": sum(e >= 6 for e in absolute) / len(absolute),
        "large_error_rate_ge_10": sum(e >= 10 for e in absolute) / len(absolute),
        "worst_1pct_squared_error_share": _tail_squared_share(squared, .01),
        "worst_5pct_squared_error_share": _tail_squared_share(squared, .05),
    }


def _tail_squared_share(squared: Sequence[float], fraction: float) -> float:
    total = sum(squared)
    if total <= 0:
        return 0.0
    count = max(1, math.ceil(len(squared) * fraction))
    return sum(sorted(squared, reverse=True)[:count]) / total


def binary_probability_metrics(actual: Sequence[int], probability: Sequence[float]) -> dict:
    y = [int(v) for v in actual]
    p = _finite(probability)
    if len(y) != len(p) or any(v not in (0, 1) for v in y):
        raise ValueError("Binary labels must be 0/1 and aligned with probabilities")
    if any(v < 0 or v > 1 for v in p):
        raise ValueError("Probabilities must be in [0, 1]")
    brier = sum((a - b) ** 2 for a, b in zip(y, p)) / len(y)
    logloss = -sum(a * math.log(max(b, 1e-15)) + (1-a) * math.log(max(1-b, 1e-15))
                   for a, b in zip(y, p)) / len(y)
    bins = []
    for lower in (0.0, .1, .2, .3, .4, .5, .6, .7, .8, .9):
        indices = [i for i, value in enumerate(p) if lower <= value < lower + .1 or
                   (lower == .9 and value == 1.0)]
        if indices:
            bins.append({
                "lower": lower, "upper": lower + .1, "n": len(indices),
                "mean_probability": sum(p[i] for i in indices) / len(indices),
                "observed_rate": sum(y[i] for i in indices) / len(indices),
            })
    return {"n": len(y), "brier": brier, "log_loss": logloss, "reliability_bins": bins}


def threshold_probability_report(actual_points: Sequence[float],
                                 probabilities: Mapping[int, Sequence[float]]) -> dict:
    """Assess P(points >= threshold), e.g. 6+, 8+ and 10+."""
    y = _finite(actual_points)
    result = {}
    for threshold, probs in probabilities.items():
        labels = [int(value >= threshold) for value in y]
        result[f"{threshold}+"] = binary_probability_metrics(labels, probs)
    return result


def rank_quality(actual_points: Sequence[float], score: Sequence[float], top_k: int = 20) -> dict:
    """Measure prospective top-k usefulness; actual points are labels only."""
    y, s = _finite(actual_points), _finite(score)
    if len(y) != len(s):
        raise ValueError("actual and score must be aligned")
    k = min(max(1, int(top_k)), len(y))
    predicted = sorted(range(len(s)), key=lambda i: (-s[i], i))[:k]
    oracle = sorted(range(len(y)), key=lambda i: (-y[i], i))[:k]
    selected_mean = sum(y[i] for i in predicted) / k
    universe_mean = sum(y) / len(y)
    oracle_mean = sum(y[i] for i in oracle) / k
    return {
        "n": len(y), "top_k": k, "selected_mean_points": selected_mean,
        "universe_mean_points": universe_mean, "oracle_top_k_mean_points": oracle_mean,
        "top_k_lift_over_universe": selected_mean - universe_mean,
        "top_k_regret_vs_oracle": oracle_mean - selected_mean,
    }


def forecast_band_error_report(actual: Sequence[float], predicted: Sequence[float]) -> dict:
    y, p = _finite(actual), _finite(predicted)
    if len(y) != len(p):
        raise ValueError("actual and predicted must be aligned")
    bands = {"<1": [], "1-<2": [], "2-<3": [], "3-<5": [], ">=5": []}
    for a, f in zip(y, p):
        key = "<1" if f < 1 else "1-<2" if f < 2 else "2-<3" if f < 3 else "3-<5" if f < 5 else ">=5"
        bands[key].append((a, f))
    report = {}
    for key, rows in bands.items():
        if not rows:
            report[key] = {"n": 0, "mae": None, "rmse": None}
        else:
            metrics = point_error_metrics([r[0] for r in rows], [r[1] for r in rows])
            report[key] = {"n": metrics["n"], "mae": metrics["mae"], "rmse": metrics["rmse"]}
    return report


def prediction_quantile_diagnostics(actual: Sequence[float], predicted: Sequence[float],
                                    bins: int = 10) -> dict:
    """Show where a forecast compresses or misses the upper tail.

    Rows are sorted by predicted expected points and split into near-equal
    count bins. Ties are kept deterministic by original row order. These are
    diagnostics only; they do not change forecasts or model selection.
    """
    y, p = _finite(actual), _finite(predicted)
    if len(y) != len(p):
        raise ValueError("actual and predicted must be aligned")
    if bins < 1:
        raise ValueError("bins must be positive")
    count = min(int(bins), len(y))
    order = sorted(range(len(p)), key=lambda i: (p[i], i))
    report = []
    for b in range(count):
        start = b * len(order) // count
        end = (b + 1) * len(order) // count
        indices = order[start:end]
        actual_bin = [y[i] for i in indices]
        predicted_bin = [p[i] for i in indices]
        errors = [a - f for a, f in zip(actual_bin, predicted_bin)]
        report.append({
            "bin": b + 1,
            "n": len(indices),
            "predicted_mean": sum(predicted_bin) / len(indices),
            "actual_mean": sum(actual_bin) / len(indices),
            "mean_actual_minus_predicted": sum(errors) / len(errors),
            "mae": sum(abs(e) for e in errors) / len(errors),
            "rmse": math.sqrt(sum(e * e for e in errors) / len(errors)),
            "actual_8_plus_rate": sum(a >= 8 for a in actual_bin) / len(indices),
            "actual_10_plus_rate": sum(a >= 10 for a in actual_bin) / len(indices),
        })
    return {
        "method": "EQUAL_COUNT_BINS_SORTED_BY_PREDICTED_EXPECTED_POINTS",
        "bins": report,
        "overall_actual_mean": sum(y) / len(y),
        "overall_predicted_mean": sum(p) / len(p),
        "overall_mean_actual_minus_predicted": sum(a - f for a, f in zip(y, p)) / len(y),
    }


def evaluate_forecast(actual_points: Sequence[float], expected_points: Sequence[float],
                      haul_probabilities: Mapping[int, Sequence[float]] | None = None,
                      ranking_score: Sequence[float] | None = None,
                      top_k: int = 20) -> dict:
    """Composite report; no outcome is dropped or winsorised."""
    report = {
        "status": "RESEARCH_ONLY",
        "point_errors": point_error_metrics(actual_points, expected_points),
        "forecast_band_errors": forecast_band_error_report(actual_points, expected_points),
        "prediction_quantile_diagnostics": prediction_quantile_diagnostics(actual_points, expected_points),
        "principle": "RMSE_IS_DIAGNOSTIC_NOT_SOLE_PROMOTION_GATE",
        "large_outcomes_policy": "RETAIN_ALL_OUTCOMES; assess haul probabilities and ranking separately",
    }
    if haul_probabilities:
        report["haul_probabilities"] = threshold_probability_report(actual_points, haul_probabilities)
    if ranking_score is not None:
        report["ranking"] = rank_quality(actual_points, ranking_score, top_k)
    return report


def explain_post_deadline_events(event_annotations: Sequence[Mapping]) -> dict:
    """Summarise annotations for error review only; never modifies metrics or features."""
    allowed = {"red_card", "opponent_injury", "own_player_injury", "tactical_change",
               "weather_change", "other_unexpected"}
    counts = defaultdict(int)
    for event in event_annotations:
        if event.get("available_at_deadline") is True:
            raise ValueError("Post-deadline event annotations cannot be marked deadline-available")
        kind = str(event.get("event_type", "other_unexpected"))
        if kind not in allowed:
            kind = "other_unexpected"
        counts[kind] += 1
    return {"purpose": "EXPLANATORY_ERROR_REVIEW_ONLY", "counts": dict(counts),
            "excluded_from_forecast_features": True}
