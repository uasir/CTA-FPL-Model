"""Build a current recommendation CoVar proxy from conventional xP and historical covariance.

This is an immediately usable, descriptive risk overlay. It combines the
conventional forecast means with a historical, shrinkage-stabilized player
covariance matrix. It does not claim calibrated future scenarios, field-relative
joint outcomes, or production eligibility.
"""
from __future__ import annotations

import math
from datetime import datetime
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




def _quadratic_variance(weights: Mapping[str, float],
                        covariance: Mapping[str, Mapping[str, float]]) -> tuple[float | None, list[str]]:
    missing = sorted({
        pid for pid in weights
        if pid not in covariance or any(other not in covariance[pid] for other in weights)
    }, key=lambda value: (not value.isdigit(), value))
    if missing:
        return None, missing
    value = sum(
        weights[left] * weights[right] * covariance[left][right]
        for left in weights for right in weights
    )
    if value < -1e-8:
        raise HistoricalCoVarOverlayError("field-average portfolio variance is negative")
    return max(0.0, value), []


def _cross_covariance(left_weights: Mapping[str, float], right_weights: Mapping[str, float],
                      covariance: Mapping[str, Mapping[str, float]]) -> tuple[float | None, list[str]]:
    missing = sorted({
        left for left in left_weights
        if left not in covariance or any(right not in covariance[left] for right in right_weights)
    }, key=lambda value: (not value.isdigit(), value))
    if missing:
        return None, missing
    return sum(
        left_weights[left] * right_weights[right] * covariance[left][right]
        for left in left_weights for right in right_weights
    ), []


def _field_average_weights(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or not rows:
        raise HistoricalCoVarOverlayError("field exposure rows must be a non-empty sequence")
    weights: dict[str, float] = {}
    seen = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise HistoricalCoVarOverlayError("field exposure rows must be objects")
        player_id = str(row.get("fpl_element_id", "")).strip()
        if not player_id or player_id in seen:
            raise HistoricalCoVarOverlayError("field exposure rows contain missing or duplicate player IDs")
        seen.add(player_id)
        exposure = _finite(row.get("scoring_exposure_pct"), f"scoring_exposure_pct.{player_id}")
        if exposure < 0 or exposure > 300:
            raise HistoricalCoVarOverlayError(f"scoring_exposure_pct.{player_id} must be between 0 and 300")
        if exposure > 0:
            weights[player_id] = exposure / 100.0
    return weights


def _historical_diagnostics(report: Mapping[str, Any]) -> dict[str, Any]:
    """Expose sample coverage and stability warnings without interpreting them as a score."""
    return {
        "point_in_time_status": report.get("point_in_time_status", "NOT_VERIFIED"),
        "sample_coverage": {
            key: report.get(key)
            for key in (
                "window_size", "rows_in_window", "players_in_window",
                "complete_panel_players", "covariance_players",
                "excluded_zero_variance_players", "excluded_incomplete_players",
                "expected_player_gameweek_cells", "missing_player_gameweek_cells",
            )
        },
        "rolling_correlation_stability": report.get("rolling_correlation_stability"),
        "limitations": list(report.get("limitations", [])),
        "guardrails": list(report.get("guardrails", [])),
    }


def build_historical_covar_recommendation_overlay(
    *,
    recommendation: Mapping[str, Any],
    forecast_rows: Sequence[Mapping[str, Any]],
    covariance_report: Mapping[str, Any],
    covariance_pairs: Sequence[Mapping[str, Any]],
    field_exposure_rows: Sequence[Mapping[str, Any]] | None = None,
    field_exposure_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach historical-covariance metrics to every actual transfer alternative."""
    if not isinstance(recommendation, Mapping) or recommendation.get("system") != "personal_squad":
        raise HistoricalCoVarOverlayError("recommendation must be a personal_squad result")
    if not isinstance(forecast_rows, Sequence) or isinstance(forecast_rows, (str, bytes)):
        raise HistoricalCoVarOverlayError("forecast_rows must be a sequence")
    if not isinstance(covariance_report, Mapping) or not isinstance(covariance_pairs, Sequence):
        raise HistoricalCoVarOverlayError("covariance report and pair rows are required")
    if covariance_report.get("status") not in {"EXPLORATORY_ONLY", "EXPLORATORY_ONSIDE_ACTUALS_ONLY"}:
        raise HistoricalCoVarOverlayError("historical covariance report must be explicitly exploratory")
    if covariance_report.get("production_use") is True:
        raise HistoricalCoVarOverlayError("historical covariance artifact must remain research-only")
    if covariance_report.get("model_trained") is not False:
        raise HistoricalCoVarOverlayError("this overlay accepts historical covariance, not a trained CoVar model")
    source_url = covariance_report.get("source_url")
    source_hash = covariance_report.get("source_sha256")
    retrieved_at = covariance_report.get("retrieved_at_utc")
    attribution = covariance_report.get("source_license_and_attribution")
    if not isinstance(source_url, str) or not source_url.startswith("https://"):
        raise HistoricalCoVarOverlayError("historical covariance source must have an HTTPS source URL")
    if (not isinstance(source_hash, str) or len(source_hash) != 64
            or any(char not in "0123456789abcdef" for char in source_hash.lower())):
        raise HistoricalCoVarOverlayError("historical covariance source hash must be a SHA-256")
    if not isinstance(attribution, str) or not attribution.strip():
        raise HistoricalCoVarOverlayError("historical covariance source attribution is required")
    try:
        retrieved = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError) as exc:
        raise HistoricalCoVarOverlayError("historical covariance retrieval time must be ISO-8601") from exc
    if retrieved.tzinfo is None or retrieved.utcoffset() is None:
        raise HistoricalCoVarOverlayError("historical covariance retrieval time must include a timezone")
    source_panel = covariance_report.get("source_panel")
    if (not isinstance(source_panel, Mapping)
            or source_panel.get("target_field") != "actual_points only"
            or source_panel.get("provider_forecasts_used") is not False):
        raise HistoricalCoVarOverlayError("covariance source panel must use realized actual points only")
    if covariance_report.get("method") != "sample covariance across a complete-case player-gameweek panel":
        raise HistoricalCoVarOverlayError("unsupported historical covariance estimation method")
    stability_diagnostic = covariance_report.get("rolling_correlation_stability")
    if stability_diagnostic is not None and not isinstance(stability_diagnostic, Mapping):
        raise HistoricalCoVarOverlayError("rolling correlation stability diagnostic must be an object")
    window = covariance_report.get("window_gameweeks")
    if not isinstance(window, list) or len(window) < 5 or len(set(window)) != len(window):
        raise HistoricalCoVarOverlayError("covariance report must identify at least five unique historical Gameweeks")
    if covariance_report.get("window_size", len(window)) != len(window):
        raise HistoricalCoVarOverlayError("covariance report window_size does not match window_gameweeks")
    shrinkage = covariance_report.get("shrinkage")
    if not isinstance(shrinkage, Mapping) or shrinkage.get("type") != "diagonal":
        raise HistoricalCoVarOverlayError("diagonal-shrunk covariance provenance is required")
    if shrinkage.get("positive_semidefinite_by_construction") is not True:
        raise HistoricalCoVarOverlayError("covariance report does not establish positive-semidefinite construction")
    shrinkage_parameter = _finite(shrinkage.get("parameter"), "shrinkage.parameter")
    if not 0.0 <= shrinkage_parameter <= 1.0:
        raise HistoricalCoVarOverlayError("covariance shrinkage parameter must be between zero and one")
    if shrinkage.get("off_diagonal_multiplier") != round(1.0 - shrinkage_parameter, 8):
        raise HistoricalCoVarOverlayError("covariance shrinkage multiplier is inconsistent with its parameter")
    if shrinkage.get("diagonal_unchanged") is not True:
        raise HistoricalCoVarOverlayError("covariance shrinkage must preserve the diagonal")

    forecasts: dict[int, Mapping[str, Any]] = {};
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
        if left == right and value < 0:
            raise HistoricalCoVarOverlayError("covariance diagonal values must be non-negative")
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
    baseline_vice_captain = plan.get("vice_captain")
    baseline = _portfolio_metrics(xi, baseline_captain, forecasts, matrix)

    field_weights = None
    field_average_variance = None
    field_missing_ids: list[str] = []
    field_average_portfolio = {
        "status": "NOT_AVAILABLE_NO_FIELD_EXPOSURE_CAPTURE",
        "variance": None,
        "standard_deviation": None,
        "scoring_exposure_source": "PRE_DEADLINE_PROVISIONAL_FIELD_SAMPLE",
        "joint_manager_portfolio_status": "NOT_AVAILABLE_MARGINAL_EXPOSURE_ONLY",
    }
    if field_exposure_rows is not None:
        field_weights = _field_average_weights(field_exposure_rows)
        field_average_variance, field_missing_ids = _quadratic_variance(field_weights, matrix)
        if field_average_variance is None:
            field_average_portfolio.update({
                "status": "NOT_AVAILABLE_INCOMPLETE_FIELD_COVARIANCE_COVERAGE",
                "missing_player_ids": field_missing_ids,
            })
        else:
            sample = field_exposure_provenance.get("sample", {}) if isinstance(field_exposure_provenance, Mapping) else {}
            field_average_portfolio.update({
                "status": "COMPUTED_HISTORICAL_FIELD_AVERAGE_PROXY",
                "variance": round(field_average_variance, 8),
                "standard_deviation": round(math.sqrt(field_average_variance), 8),
                "player_count": len(field_weights),
                "manager_count": sample.get("manager_count"),
                "effective_sample_size": sample.get("effective_sample_size"),
                "captured_at_utc": field_exposure_provenance.get("captured_at_utc"),
                "artifact_id": field_exposure_provenance.get("snapshot_id"),
            })

    def attach_field_relative_metrics(portfolio: dict[str, Any], player_ids: Sequence[int],
                                      captain_id: int) -> dict[str, Any]:
        if (field_weights is None or field_average_variance is None
                or portfolio.get("status") != "COMPUTED_HISTORICAL_PROXY"):
            portfolio["field_average_covariance"] = None
            portfolio["field_average_variance"] = None
            portfolio["relative_variance_vs_field_average"] = None
            return portfolio
        personal_weights = {str(pid): (2.0 if pid == captain_id else 1.0) for pid in player_ids}
        covariance_value, missing_ids = _cross_covariance(personal_weights, field_weights, matrix)
        if covariance_value is None:
            portfolio["field_average_covariance"] = None
            portfolio["field_average_variance"] = round(field_average_variance, 8)
            portfolio["relative_variance_vs_field_average"] = None
            portfolio["field_covariance_missing_player_ids"] = missing_ids
            return portfolio
        relative_variance = portfolio["portfolio_variance"] + field_average_variance - 2.0 * covariance_value
        if relative_variance < -1e-8:
            raise HistoricalCoVarOverlayError("relative portfolio variance is negative")
        portfolio["field_average_covariance"] = round(covariance_value, 8)
        portfolio["field_average_variance"] = round(field_average_variance, 8)
        portfolio["relative_variance_vs_field_average"] = round(max(0.0, relative_variance), 8)
        portfolio["relative_standard_deviation_vs_field_average"] = round(math.sqrt(max(0.0, relative_variance)), 8)
        return portfolio

    baseline = attach_field_relative_metrics(baseline, xi, baseline_captain)

    metrics = []
    excluded_bench_only_alternatives = []
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
            weakest_index, weakest_player = min(
                eligible,
                key=lambda item: (
                    _finite(item[1].get("expected_points"), "starter expected_points"),
                    -_finite(item[1].get("expected_minutes"), "starter expected_minutes"),
                    -item[1]["fpl_element_id"],
                ),
            )
            incoming_order = (
                -_finite(forecasts[incoming].get("expected_points"), "incoming expected_points"),
                -_finite(forecasts[incoming].get("expected_minutes"), "incoming expected_minutes"),
                incoming,
            )
            weakest_order = (
                -_finite(weakest_player.get("expected_points"), "starter expected_points"),
                -_finite(weakest_player.get("expected_minutes"), "starter expected_minutes"),
                weakest_player["fpl_element_id"],
            )
            # A bench-to-bench transfer does not displace a stronger starter.
            if incoming_order < weakest_order:
                index = weakest_index
            else:
                index = None
        if index is None:
            excluded_bench_only_alternatives.append({
                "transfer_out_id": outgoing,
                "transfer_in_id": incoming,
                "reason": "NO_STARTING_XI_IMPROVEMENT",
            })
            continue
        candidate_xi[index] = incoming
        # Preserve the manager-selected captain; use vice only if the captain is transferred out.
        captain_id = baseline_captain if baseline_captain in candidate_xi else (
            baseline_vice_captain if baseline_vice_captain in candidate_xi else _captain(candidate_xi, forecasts)
        )
        result = _portfolio_metrics(candidate_xi, captain_id, forecasts, matrix)
        result = attach_field_relative_metrics(result, candidate_xi, captain_id)
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
            "historical_covariance_diagnostics": _historical_diagnostics(covariance_report),
            "historical_covariance_source": {
                "source_url": covariance_report.get("source_url"),
                "source_sha256": covariance_report.get("source_sha256"),
                "retrieved_at_utc": covariance_report.get("retrieved_at_utc"),
                "source_license_and_attribution": covariance_report.get("source_license_and_attribution"),
            },
            "candidate_metrics": [],
            "excluded_bench_only_alternatives": excluded_bench_only_alternatives,
            "decision_weight": 0.0,
            "production_eligible": False,
            "field_comparison_status": "NOT_AVAILABLE_NO_JOINT_FIELD_PORTFOLIOS",
        }

    for row in metrics:
        row["expected_points_delta_vs_current"] = round(row["expected_points"] - baseline["expected_points"], 8)
        row["variance_delta_vs_current"] = round(row["portfolio_variance"] - baseline["portfolio_variance"], 8)
        row["covariance_delta_vs_current"] = round(row["covariance_contribution"] - baseline["covariance_contribution"], 8)
        if row.get("relative_variance_vs_field_average") is not None and baseline.get("relative_variance_vs_field_average") is not None:
            row["relative_variance_delta_vs_field_average"] = round(
                row["relative_variance_vs_field_average"] - baseline["relative_variance_vs_field_average"], 8
            )
        if row.get("field_average_covariance") is not None and baseline.get("field_average_covariance") is not None:
            row["field_average_covariance_delta_vs_current"] = round(
                row["field_average_covariance"] - baseline["field_average_covariance"], 8
            )

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
        "historical_covariance_stability_diagnostic": stability_diagnostic,
        "historical_covariance_diagnostics": _historical_diagnostics(covariance_report),
        "historical_covariance_source": {
            "source_url": covariance_report.get("source_url"),
            "source_sha256": covariance_report.get("source_sha256"),
            "retrieved_at_utc": covariance_report.get("retrieved_at_utc"),
            "source_license_and_attribution": covariance_report.get("source_license_and_attribution"),
        },

        "point_in_time_status": covariance_report.get("point_in_time_status", "NOT_VERIFIED"),
        "baseline": baseline,
        "field_average_portfolio": field_average_portfolio,
        "candidate_metrics": metrics,
        "excluded_bench_only_alternatives": excluded_bench_only_alternatives,
        "recommendation_policy": {
            "priority": "STARTING_XI_FIRST",
            "bench_role": "BUDGET_EMERGENCY_COVER_ONLY",
            "routine_rotation": False,
            "bench_only_transfers_eligible": False,
            "candidate_must_change_starting_xi": True,
        },
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
        "field_comparison_status": (
            "AVAILABLE_FIELD_AVERAGE_HISTORICAL_PROXY"
            if field_average_variance is not None
            else field_average_portfolio["status"]
        ),
        "field_joint_manager_portfolio_status": "NOT_AVAILABLE_MARGINAL_EXPOSURE_ONLY",
        "decision_weight": 0.0,
        "production_eligible": False,
        "limitations": [
            "Expected points come from the conventional M3 forecast; covariance comes from historical realized points.",
            "Historical dependence is a proxy, not a calibrated forward joint distribution.",
            "The rolling correlation stability diagnostic is reported verbatim as a caution; it is not a formal stationarity test or a forecast validation."
            "Only transfers that change the starting XI are scored; bench-only upgrades are explicitly excluded.",
            "The overlay preserves the current captain and uses the vice-captain only if the captain is transferred out; bench autosubs and chip effects are not simulated.",
            "The field's joint portfolio covariance is unavailable; marginal EO is not used to reconstruct it.",
            "No transfer, starting XI, captaincy or canonical EV ranking is changed automatically.",
        ],
    }
