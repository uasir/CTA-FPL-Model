#!/usr/bin/env python3
"""Multi-Gameweek team exposure and player-correlation diagnostics for M4.

Expected points are additive. Stacking changes concentration and the distribution
of squad outcomes; it must not be presented as an automatic EV bonus. Covariance
is computed only from supplied joint player-point scenarios, never inferred from
club identity or marginal EO.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Mapping, Sequence


class TeamExposureError(ValueError):
    """Invalid multi-Gameweek exposure or joint-scenario input."""


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise TeamExposureError(f"{field} must be a finite number")
    return float(value)


def _positive_id(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise TeamExposureError(f"{field} must be a positive integer")
    return value


def build_team_exposure_report(
    *,
    squad_player_ids: Sequence[int],
    player_gameweek_forecasts: Sequence[Mapping[str, Any]],
    joint_scenarios: Sequence[Mapping[str, Any]] | None = None,
    minimum_horizon_gameweeks: int = 5,
    forecast_snapshot_id: str | None = None,
    model_version: str | None = None,
) -> dict[str, Any]:
    """Summarize squad club/position stacking and scenario-derived covariance.

    Forecast rows require fpl_element_id, team_id, position, gameweek and
    expected_points. Joint scenario rows require gameweek, scenario_id and a
    player_points mapping keyed by string or integer FPL element ID. Scenarios
    must be joint draws from one coherent forecast distribution for that GW.
    """
    if not isinstance(squad_player_ids, (list, tuple)) or not squad_player_ids:
        raise TeamExposureError("squad_player_ids must be a non-empty sequence")
    ids = [_positive_id(value, "squad_player_ids item") for value in squad_player_ids]
    if len(ids) != len(set(ids)):
        raise TeamExposureError("squad_player_ids must be unique")
    if isinstance(minimum_horizon_gameweeks, bool) or not isinstance(minimum_horizon_gameweeks, int) or minimum_horizon_gameweeks < 5:
        raise TeamExposureError("minimum_horizon_gameweeks must be an integer of at least 5")
    if not isinstance(player_gameweek_forecasts, (list, tuple)) or not player_gameweek_forecasts:
        raise TeamExposureError("player_gameweek_forecasts must be a non-empty sequence")

    forecasts: dict[tuple[int, int], dict[str, Any]] = {}
    weeks = set()
    for index, row in enumerate(player_gameweek_forecasts):
        if not isinstance(row, Mapping):
            raise TeamExposureError(f"forecast row {index} must be an object")
        player_id = _positive_id(row.get("fpl_element_id"), f"forecast row {index}.fpl_element_id")
        if player_id not in ids:
            continue
        team_id = _positive_id(row.get("team_id"), f"forecast row {index}.team_id")
        position = row.get("position")
        if position not in {"GKP", "DEF", "MID", "FWD"}:
            raise TeamExposureError(f"forecast row {index}.position is invalid")
        gw = _positive_id(row.get("gameweek"), f"forecast row {index}.gameweek")
        xp = _finite(row.get("expected_points"), f"forecast row {index}.expected_points")
        key = (player_id, gw)
        if key in forecasts:
            raise TeamExposureError(f"duplicate player/Gameweek forecast: {key}")
        forecasts[key] = {"fpl_element_id": player_id, "team_id": team_id,
                          "position": position, "gameweek": gw, "expected_points": xp}
        weeks.add(gw)

    if len(weeks) < minimum_horizon_gameweeks:
        raise TeamExposureError(
            f"at least {minimum_horizon_gameweeks} distinct Gameweeks are required; got {len(weeks)}"
        )
    ordered_weeks = sorted(weeks)
    if ordered_weeks != list(range(ordered_weeks[0], ordered_weeks[0] + len(ordered_weeks))):
        raise TeamExposureError("forecast horizon must contain consecutive Gameweeks")
    missing = [(pid, gw) for pid in ids for gw in ordered_weeks if (pid, gw) not in forecasts]
    if missing:
        raise TeamExposureError(f"forecast coverage is incomplete for {len(missing)} player/Gameweek rows")

    player_totals = {pid: sum(forecasts[(pid, gw)]["expected_points"] for gw in ordered_weeks) for pid in ids}
    team_ids = sorted({forecasts[(pid, gw)]["team_id"] for pid in ids for gw in ordered_weeks})
    team_rows = []
    for team_id in team_ids:
        by_week = {}
        all_player_ids = set()
        position_totals = {pos: 0 for pos in ("GKP", "DEF", "MID", "FWD")}
        for gw in ordered_weeks:
            members = [pid for pid in ids if forecasts[(pid, gw)]["team_id"] == team_id]
            all_player_ids.update(members)
            by_week[str(gw)] = round(sum(forecasts[(pid, gw)]["expected_points"] for pid in members), 6)
            for pos in position_totals:
                position_totals[pos] += sum(forecasts[(pid, gw)]["position"] == pos for pid in members)
        if not all_player_ids:
            continue
        position_counts = {pos: count / len(ordered_weeks) for pos, count in position_totals.items()}
        has_defensive = position_totals["GKP"] + position_totals["DEF"] > 0
        has_attacking = position_totals["MID"] + position_totals["FWD"] > 0
        team_rows.append({
            "team_id": team_id,
            "squad_player_ids": sorted(all_player_ids),
            "average_player_count": round(sum(
                sum(forecasts[(pid, gw)]["team_id"] == team_id for pid in ids)
                for gw in ordered_weeks
            ) / len(ordered_weeks), 4),
            "position_counts_average": position_counts,
            "expected_points_by_gameweek": by_week,
            "expected_points_horizon": round(sum(by_week.values()), 6),
            "stack_type": (
                "MIXED_TEAM_EXPOSURE" if has_defensive and has_attacking
                else "DEFENSIVE_CLEAN_SHEET_EXPOSURE" if has_defensive
                else "ATTACKING_EXPOSURE"
            ),
        })

    scenario_rows = joint_scenarios or []
    if not isinstance(scenario_rows, (list, tuple)):
        raise TeamExposureError("joint_scenarios must be a sequence")
    by_week: dict[int, dict[str, dict[int, float]]] = defaultdict(dict)
    for index, row in enumerate(scenario_rows):
        if not isinstance(row, Mapping):
            raise TeamExposureError(f"joint scenario {index} must be an object")
        gw = _positive_id(row.get("gameweek"), f"joint scenario {index}.gameweek")
        if gw not in weeks:
            raise TeamExposureError(f"joint scenario {index} is outside the forecast horizon")
        scenario_id = row.get("scenario_id")
        if not isinstance(scenario_id, str) or not scenario_id.strip():
            raise TeamExposureError(f"joint scenario {index}.scenario_id is required")
        if scenario_id in by_week[gw]:
            raise TeamExposureError(f"duplicate scenario_id in Gameweek {gw}: {scenario_id}")
        raw_points = row.get("player_points")
        if not isinstance(raw_points, Mapping):
            raise TeamExposureError(f"joint scenario {index}.player_points must be an object")
        values = {}
        for raw_id, points in raw_points.items():
            try:
                pid = int(raw_id)
            except (TypeError, ValueError) as exc:
                raise TeamExposureError(f"joint scenario {index} has an invalid player ID") from exc
            if pid in ids:
                values[pid] = _finite(points, f"joint scenario {index}.player_points[{pid}]")
        by_week[gw][scenario_id] = values

    covariance_sum: dict[tuple[int, int], float] = defaultdict(float)
    variance_sum: dict[int, float] = defaultdict(float)
    scenario_counts: dict[tuple[int, int], int] = defaultdict(int)
    for gw, scenarios in by_week.items():
        for pid in ids:
            values = [draw[pid] for draw in scenarios.values() if pid in draw]
            if len(values) >= 2:
                mean = sum(values) / len(values)
                variance_sum[pid] += sum((value - mean) ** 2 for value in values) / (len(values) - 1)
        for index, left in enumerate(ids):
            for right in ids[index + 1:]:
                paired = [(draw[left], draw[right]) for draw in scenarios.values()
                          if left in draw and right in draw]
                if len(paired) < 2:
                    continue
                left_mean = sum(pair[0] for pair in paired) / len(paired)
                right_mean = sum(pair[1] for pair in paired) / len(paired)
                covariance_sum[(left, right)] += sum(
                    (a - left_mean) * (b - right_mean) for a, b in paired
                ) / (len(paired) - 1)
                scenario_counts[(left, right)] += len(paired)

    pair_rows = []
    for index, left in enumerate(ids):
        for right in ids[index + 1:]:
            key = (left, right)
            cov = covariance_sum.get(key)
            count = scenario_counts.get(key, 0)
            if cov is None or count < 2:
                status, correlation = "NOT_ESTIMABLE_INSUFFICIENT_JOINT_SCENARIOS", None
            else:
                denom = math.sqrt(max(0.0, variance_sum[left]) * max(0.0, variance_sum[right]))
                correlation = round(max(-1.0, min(1.0, cov / denom)), 6) if denom > 0 else None
                status = "ESTIMATED_FROM_JOINT_SCENARIOS" if correlation is not None else "ZERO_VARIANCE_NOT_ESTIMABLE"
            pair_rows.append({
                "player_a_id": left, "player_b_id": right,
                "covariance_horizon": round(cov, 8) if cov is not None else None,
                "correlation_horizon": correlation,
                "paired_scenario_count": count, "status": status,
                "portfolio_variance_contribution": round(2 * cov, 8) if cov is not None else None,
            })

    if forecast_snapshot_id is not None and (not isinstance(forecast_snapshot_id, str) or not forecast_snapshot_id.strip()):
        raise TeamExposureError("forecast_snapshot_id must be a non-empty string when supplied")
    if model_version is not None and (not isinstance(model_version, str) or not model_version.strip()):
        raise TeamExposureError("model_version must be a non-empty string when supplied")

    return {
        "contract_version": "1.0.0",
        "forecast_snapshot_id": forecast_snapshot_id,
        "model_version": model_version,
        "status": "TEAM_EXPOSURE_COMPUTED" if not scenario_rows else "TEAM_EXPOSURE_AND_SCENARIO_COVARIANCE_COMPUTED",
        "horizon_gameweeks": ordered_weeks,
        "horizon_size": len(ordered_weeks),
        "expected_points_are_additive": True,
        "team_exposure": team_rows,
        "player_horizon_expected_points": {str(pid): round(value, 6) for pid, value in player_totals.items()},
        "pairwise_player_dependence": pair_rows,
        "covariance_status": "JOINT_SCENARIO_ESTIMATE" if scenario_rows else "NOT_AVAILABLE_NO_JOINT_SCENARIOS",
        "cross_gameweek_assumption": "GAMEWEEK_OUTCOMES_TREATED_AS_INDEPENDENT; within-Gameweek joint covariance is summed across the horizon",
        "decision_weight": 0.0,
        "production_eligible": False,
        "limitations": [
            "Club membership alone does not create a covariance estimate.",
            "Expected points are summed player by player; stacking is not an EV bonus.",
            "Covariance is estimated only from complete paired joint scenarios and is not inferred from marginal expected points or EO.",
            "The horizon covariance assumes Gameweek outcomes are independent; within-Gameweek covariance is summed across Gameweeks.",
            "This diagnostic does not change transfer ranking, starting XI, captaincy or hit decisions.",
        ],
    }
