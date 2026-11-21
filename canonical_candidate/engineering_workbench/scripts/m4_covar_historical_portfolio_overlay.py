"""Build a current recommendation CoVar proxy from conventional xP and historical covariance.

This is an immediately usable, descriptive risk overlay. It combines the
conventional forecast means with a historical, shrinkage-stabilized player
covariance matrix. It does not claim calibrated future scenarios, field-relative
joint outcomes, or production eligibility.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence


class HistoricalCoVarOverlayError(ValueError):
    """Inputs cannot support a safe historical covariance overlay."""


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise HistoricalCoVarOverlayError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise HistoricalCoVarOverlayError(f"{label} must be a finite number") from exc
    if not math.isfinite(result):
        raise HistoricalCoVarOverlayError(f"{label} must be a finite number")
    return result


def _portfolio_metrics(
    player_ids: Sequence[int],
    captain_id: int,
    forecasts: Mapping[int, Mapping[str, Any]],
    covariance: Mapping[str, Mapping[str, float]],
) -> dict[str, Any]:
    weights = {str(pid): (2.0 if pid == captain_id else 1.0) for pid in player_ids}
    expected_points = sum(
        _finite(forecasts[pid].get("expected_points"), f"expected_points.{pid}") * weights[str(pid)]
        for pid in player_ids
    )
    missing = sorted(
        pid for pid in weights
        if pid not in covariance or any(other not in covariance[pid] for other in weights)
    )
    if missing:
        return {"status": "INCOMPLETE_COVARIANCE_COVERAGE", "missing_player_ids": missing,
                "expected_points": expected_points}

    individual_variance = 0.0
    covariance_contribution = 0.0
    for left in weights:
        for right in weights:
            contribution = weights[left] * weights[right] * covariance[left][right]
            if left == right:
                individual_variance += contribution
            else:
                covariance_contribution += contribution
    variance = individual_variance + covariance_contribution
    if variance < -1e-8:
        raise HistoricalCoVarOverlayError("portfolio variance is negative; covariance input is invalid")
    variance = max(0.0, variance)
    return {
        "status": "COMPUTED_HISTORICAL_PROXY",
        "expected_points": round(expected_points, 8),
        "individual_variance": round(individual_variance, 8),
        "covariance_contribution": round(covariance_contribution, 8),
        "portfolio_variance": round(variance, 8),
        "portfolio_standard_deviation": round(math.sqrt(variance), 8),
        "captain_id": captain_id,
        "player_count": len(player_ids),
    }


def _captain(player_ids: Sequence[int], forecasts: Mapping[int, Mapping[str, Any]]) -> int:
    return sorted(
        player_ids,
        key=lambda pid: (
            -_finite(forecasts[pid].get("expected_points"), f"expected_points.{pid}"),
            -_finite(forecasts[pid].get("expected_minutes"), f"expected_minutes.{pid}"),
            pid,
        ),
    )[0]


def build_historical_covar_recommendation_overlay(
    *,
    recommendation: Mapping[str, Any],
    forecast_rows: Sequence[Mapping[str, Any]],
    covariance_report: Mapping[str, Any],
    covariance_pairs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Attach historical-covariance metrics to every actual transfer alternative."""
    if not isinstance(recommendation, Mapping) or recommendation.get("system") != "personal_squad":
        raise HistoricalCoVarOverlayError("recommendation must be a personal_squad result")
    if not isinstance(forecast_rows, Sequence) or isinstance(forecast_rows, (str, bytes)):
        raise HistoricalCoVarOverlayError("forecast_rows must be a sequence")
    if not isinstance(covariance_report, Mapping) or not isinstance(covariance_pairs, Sequence):
        raise HistoricalCoVarOverlayError("covariance report and pair rows are required")
    if covariance_report.get("status") != "EXPLORATORY_ONLY":
        raise HistoricalCoVarOverlayError("historical covariance report must be explicitly exploratory")
    if covariance_report.get("model_trained") is not False:
        raise HistoricalCoVarOverlayError("this overlay accepts historical covariance, not a trained CoVar model")
    window = covariance_report.get("window_gameweeks")
    if not isinstance(window, list) or len(window) < 2 or len(set(window)) != len(window):
        raise HistoricalCoVarOverlayError("covariance report must identify at least two unique historical Gameweeks")
    shrinkage = covariance_report.get("shrinkage")
    if not isinstance(shrinkage, Mapping) or shrinkage.get("type") != "diagonal":
        raise HistoricalCoVarOverlayError("diagonal-shrunk covariance provenance is required")
    if shrinkage.get("positive_semidefinite_by_construction") is not True:
        raise HistoricalCoVarOverlayError("covariance report does not establish positive-semidefinite construction")

    forecasts: dict[int, Mapping[str, Any]] = {}
    for row in forecast_rows:
        if not isinstance(row, Mapping):
            raise HistoricalCoVarOverlayError("forecast rows must be objects")
        pid = row.get("fpl_element_id")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1 or pid in forecasts:
            raise HistoricalCoVarOverlayError("forecast player IDs must be unique positive integers")
        _finite(row.get("expected_points"), f"expected_points.{pid}")
        _finite(row.get("expected_minutes"), f"expected_minutes.{pid}")
        forecasts[pid] = row

    matrix: dict[str, dict[str, float]] = {}
    seen: set[tuple[str, str]] = set()
    for row in covariance_pairs:
        if not isinstance(row, Mapping):
            raise HistoricalCoVarOverlayError("covariance pair rows must be objects")
        left, right = str(row.get("player1_id", "")), str(row.get("player2_id", ""))
        if not left or not right:
            raise HistoricalCoVarOverlayError("covariance rows require both player IDs")
        key = tuple(sorted((left, right)))
        if key in seen:
            raise HistoricalCoVarOverlayError(f"duplicate covariance pair {key}")
        seen.add(key)
        value = _finite(row.get("shrunk_covariance"), f"shrunk_covariance.{left}.{right}")
        matrix.setdefault(left, {})[right] = value
        matrix.setdefault(right, {})[left] = value

    plan = recommendation.get("current_squad_plan")
    transfer = recommendation.get("transfer_recommendation")
    if not isinstance(plan, Mapping) or not isinstance(transfer, Mapping):
        raise HistoricalCoVarOverlayError("recommendation must include current_squad_plan and transfer_recommendation")
    xi = plan.get("starting_xi")
    alternatives = transfer.get("alternatives")
    if not isinstance(xi, list) or len(xi) != 11 or len(set(xi)) != 11:
        raise HistoricalCoVarOverlayError("current starting XI must contain 11 unique players")
    if not isinstance(alternatives, list):
        raise HistoricalCoVarOverlayError("transfer alternatives must be a list")
    if any(pid not in forecasts for pid in xi):
        raise HistoricalCoVarOverlayError("current starting XI player is missing from conventional forecasts")

    baseline_captain = plan.get("captain")
    if baseline_captain not in xi:
        baseline_captain = _captain(xi, forecasts)
    baseline = _portfolio_metrics(xi, baseline_captain, forecasts, matrix)

    metrics = []
    for alternative in alternatives:
        if not isinstance(alternative, Mapping):
            raise HistoricalCoVarOverlayError("transfer alternatives must be objects")
        outgoing, incoming = alternative.get("transfer_out_id"), alternative.get("transfer_in_id")
        if (isinstance(outgoing, bool) or not isinstance(outgoing, int)
                or isinstance(incoming, bool) or not isinstance(incoming, int)
                or outgoing not in forecasts or incoming not in forecasts):
            raise HistoricalCoVarOverlayError("transfer alternative player IDs are missing from forecasts")
        if forecasts[outgoing].get("position") != forecasts[incoming].get("position"):
            raise HistoricalCoVarOverlayError("transfer alternative must preserve the outgoing player's position")
        candidate_xi = list(xi)
        if outgoing in candidate_xi:
            index = candidate_xi.index(outgoing)
        else:
            incoming_position = forecasts[incoming].get("position")
            eligible = [
                (index, forecasts[pid])
                for index, pid in enumerate(candidate_xi)
                if forecasts[pid].get("position") == incoming_position
            ]
            if not eligible:
                raise HistoricalCoVarOverlayError("incoming player has no legal same-position XI slot")
            index = min(
                eligible,
                key=lambda item: (
                    _finite(item[1].get("expected_points"), "starter expected_points"),
                    -_finite(item[1].get("expected_minutes"), "starter expected_minutes"),
                    -item[1]["fpl_element_id"],
                ),
            )[0]
        candidate_xi[index] = incoming
        captain_id = _captain(candidate_xi, forecasts)
        result = _portfolio_metrics(candidate_xi, captain_id, forecasts, matrix)
        metrics.append({
            "transfer_out_id": outgoing,
            "transfer_in_id": incoming,
            "starting_xi_ids": candidate_xi,
            **result,
        })

    missing = set()
    if baseline.get("status") != "COMPUTED_HISTORICAL_PROXY":
        missing.update(baseline.get("missing_player_ids", []))
    for row in metrics:
        if row.get("status") != "COMPUTED_HISTORICAL_PROXY":
            missing.update(row.get("missing_player_ids", []))
    if missing:
        return {
            "status": "NOT_AVAILABLE_INCOMPLETE_COVARIANCE_COVERAGE",
            "method": "HISTORICAL_SHRUNK_PLAYER_COVARIANCE",
            "missing_player_ids": sorted(missing, key=lambda value: (not value.isdigit(), value)),
            "historical_window_gameweeks": window,
            "candidate_metrics": [],
            "decision_weight": 0.0,
            "production_eligible": False,
            "field_comparison_status": "NOT_AVAILABLE_NO_JOINT_FIELD_PORTFOLIOS",
        }

    for row in metrics:
        row["expected_points_delta_vs_current"] = round(row["expected_points"] - baseline["expected_points"], 8)
        row["variance_delta_vs_current"] = round(row["portfolio_variance"] - baseline["portfolio_variance"], 8)
        row["covariance_delta_vs_current"] = round(row["covariance_contribution"] - baseline["covariance_contribution"], 8)

    pareto = []
    for row in metrics:
        dominated = any(
            other is not row
            and other["expected_points"] >= row["expected_points"] - 1e-10
            and other["portfolio_variance"] <= row["portfolio_variance"] + 1e-10
            and (
                other["expected_points"] > row["expected_points"] + 1e-10
                or other["portfolio_variance"] < row["portfolio_variance"] - 1e-10
            )
            for other in metrics
        )
        if not dominated:
            pareto.append((row["transfer_out_id"], row["transfer_in_id"]))
    lowest_variance = min(metrics, key=lambda row: (row["portfolio_variance"], -row["expected_points"])) if metrics else None
    highest_ev = max(metrics, key=lambda row: (row["expected_points"], -row["portfolio_variance"])) if metrics else None

    return {
        "status": "AVAILABLE_HISTORICAL_COVAR_PROXY",
        "method": "HISTORICAL_SHRUNK_PLAYER_COVARIANCE",
        "forecast_snapshot_id": recommendation.get("forecast_snapshot_id"),
        "model_version": recommendation.get("model_version"),
        "historical_window_gameweeks": window,
        "historical_window_size": len(window),
        "historical_covariance_shrinkage": shrinkage.get("parameter"),
        "point_in_time_status": covariance_report.get("point_in_time_status", "NOT_VERIFIED"),
        "baseline": baseline,
        "candidate_metrics": metrics,
        "pareto_frontier_transfer_pairs": [
            {"transfer_out_id": pair[0], "transfer_in_id": pair[1]} for pair in pareto
        ],
        "lowest_variance_alternative": (
            {"transfer_out_id": lowest_variance["transfer_out_id"],
             "transfer_in_id": lowest_variance["transfer_in_id"],
             "expected_points_delta_vs_current": lowest_variance["expected_points_delta_vs_current"],
             "variance_delta_vs_current": lowest_variance["variance_delta_vs_current"]}
            if lowest_variance else None
        ),
        "highest_expected_points_alternative": (
            {"transfer_out_id": highest_ev["transfer_out_id"],
             "transfer_in_id": highest_ev["transfer_in_id"],
             "variance_delta_vs_current": highest_ev["variance_delta_vs_current"]}
            if highest_ev else None
        ),
        "field_comparison_status": "NOT_AVAILABLE_NO_JOINT_FIELD_PORTFOLIOS",
        "decision_weight": 0.0,
        "production_eligible": False,
        "limitations": [
            "Expected points come from the conventional M3 forecast; covariance comes from historical realized points.",
            "Historical dependence is a proxy, not a calibrated forward joint distribution.",
            "The overlay scores the starting XI with the current captain multiplier; bench autosubs and chip effects are not simulated.",
            "The field's joint portfolio covariance is unavailable; marginal EO is not used to reconstruct it.",
            "No transfer, starting XI, captaincy or canonical EV ranking is changed automatically.",
        ],
    }
}
