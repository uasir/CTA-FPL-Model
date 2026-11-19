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


def decision_outcome_metrics(decisions: Sequence[Mapping],
                             utility_definition: str = "actual_points") -> dict:
    """Score recommendations against feasible alternatives, independently of forecast error.

    Each decision contains chosen_option_id and an options list. Every option
    supplies a unique option_id, realised actual_utility and an optional
    feasible flag (default True). Utility may be player points, net points
    after transfer hits, or full-squad GW points after FPL rules; callers must
    use one consistent definition within a report.
    """
    if not decisions:
        raise ValueError("At least one decision is required")
    if not isinstance(utility_definition, str) or not utility_definition.strip():
        raise ValueError("utility_definition must be a non-empty string")

    rows = []
    pairwise_wins = pairwise_ties = pairwise_losses = 0
    total_selected = total_oracle = total_regret = 0.0
    optimal_count = 0
    for index, decision in enumerate(decisions):
        options = decision.get("options")
        if not isinstance(options, Sequence) or isinstance(options, (str, bytes)) or len(options) < 2:
            raise ValueError("Each decision requires at least two alternative options")
        option_ids = [str(option.get("option_id", "")) for option in options]
        if any(not value for value in option_ids) or len(set(option_ids)) != len(option_ids):
            raise ValueError("Option IDs must be non-empty and unique within each decision")
        chosen_id = str(decision.get("chosen_option_id", ""))
        if chosen_id not in option_ids:
            raise ValueError("chosen_option_id must identify one supplied option")

        feasible = []
        for option, option_id in zip(options, option_ids):
            is_feasible = option.get("feasible", True)
            if not isinstance(is_feasible, bool):
                raise ValueError("Option feasible flags must be booleans")
            utility = float(option.get("actual_utility"))
            if not math.isfinite(utility):
                raise ValueError("Option actual_utility values must be finite")
            if is_feasible:
                feasible.append((option_id, utility))
        selected = next((utility for option_id, utility in feasible if option_id == chosen_id), None)
        if selected is None:
            raise ValueError("The recommended option must be feasible")

        best_utility = max(utility for _, utility in feasible)
        regret = max(0.0, best_utility - selected)
        alternatives = [utility for option_id, utility in feasible if option_id != chosen_id]
        wins = sum(selected > value for value in alternatives)
        ties = sum(selected == value for value in alternatives)
        losses = sum(selected < value for value in alternatives)
        pairwise_wins += wins
        pairwise_ties += ties
        pairwise_losses += losses
        total_selected += selected
        total_oracle += best_utility
        total_regret += regret
        is_optimal = regret == 0.0
        optimal_count += int(is_optimal)
        rows.append({
            "decision_id": str(decision.get("decision_id", index)),
            "chosen_option_id": chosen_id,
            "selected_actual_utility": selected,
            "best_feasible_actual_utility": best_utility,
            "regret": regret,
            "recommendation_optimal": is_optimal,
            "pairwise_wins": wins,
            "pairwise_ties": ties,
            "pairwise_losses": losses,
            "feasible_option_count": len(feasible),
        })

    n = len(rows)
    comparisons = pairwise_wins + pairwise_ties + pairwise_losses
    return {
        "n_decisions": n,
        "utility_definition": utility_definition,
        "mean_selected_actual_utility": total_selected / n,
        "mean_best_feasible_actual_utility": total_oracle / n,
        "mean_regret_vs_best_feasible": total_regret / n,
        "total_regret": total_regret,
        "zero_regret_rate": optimal_count / n,
        "recommendation_optimal_rate": optimal_count / n,
        "pairwise_comparisons": comparisons,
        "pairwise_win_rate": pairwise_wins / comparisons if comparisons else None,
        "pairwise_tie_rate": pairwise_ties / comparisons if comparisons else None,
        "pairwise_loss_rate": pairwise_losses / comparisons if comparisons else None,
        "decisions": rows,
        "oracle_note": "Best feasible realised outcome is a retrospective regret reference, not an achievable forecast.",
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

    Rows are sorted by predicted expected points and assigned to approximate
    equal-count bins. Identical forecasts stay together, so ties may make bin
    sizes uneven. Original row order breaks sorting ties deterministically.
    These diagnostics do not change forecasts or model selection.
    """
    y, p = _finite(actual), _finite(predicted)
    if len(y) != len(p):
        raise ValueError("actual and predicted must be aligned")
    if bins < 1:
        raise ValueError("bins must be positive")
    count = min(int(bins), len(y))
    order = sorted(range(len(p)), key=lambda i: (p[i], i))
    # Keep identical forecasts together. Splitting a large tie across adjacent
    # quantile bins would manufacture apparent calibration differences.
    tied_groups = []
    for index in order:
        if not tied_groups or p[index] != p[tied_groups[-1][0]]:
            tied_groups.append([index])
        else:
            tied_groups[-1].append(index)
    grouped_bins = {}
    cursor = 0
    for group in tied_groups:
        midpoint = cursor + (len(group) - 1) / 2.0
        bin_index = min(count - 1, int(midpoint * count / len(order)))
        grouped_bins.setdefault(bin_index, []).extend(group)
        cursor += len(group)
    report = []
    for indices in grouped_bins.values():
        actual_bin = [y[i] for i in indices]
        predicted_bin = [p[i] for i in indices]
        errors = [a - f for a, f in zip(actual_bin, predicted_bin)]
        report.append({
            "bin": len(report) + 1,
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
        "method": "APPROX_EQUAL_COUNT_BINS_TIES_KEPT_INTACT",
        "bins": report,
        "overall_actual_mean": sum(y) / len(y),
        "overall_predicted_mean": sum(p) / len(p),
        "overall_mean_actual_minus_predicted": sum(a - f for a, f in zip(y, p)) / len(y),
    }


def evaluate_forecast(actual_points: Sequence[float], expected_points: Sequence[float],
                      haul_probabilities: Mapping[int, Sequence[float]] | None = None,
                      ranking_score: Sequence[float] | None = None,
                      top_k: int = 20,
                      decision_records: Sequence[Mapping] | None = None,
                      decision_utility_definition: str = "actual_points") -> dict:
    """Composite forecast/ranking report with a separate optional decision scorecard.

    Decision records are the recommendation layer's chosen options and feasible
    alternatives. Their realised utility is scored separately from expected-point
    errors; a poor point forecast can therefore accompany a successful decision.
    """
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
    if decision_records is not None:
        report["decision_performance"] = decision_outcome_metrics(
            decision_records, utility_definition=decision_utility_definition
        )
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
