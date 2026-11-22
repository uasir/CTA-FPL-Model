#!/usr/bin/env python3
"""Build descriptive field-exposure concentration baselines without covariance."""
from __future__ import annotations

import math
from typing import Any, Mapping


class PortfolioBaselineError(ValueError):
    pass


METRICS = (
    "owned_by_pct", "effective_ownership_pct", "starting_pct",
    "captain_pct", "triple_captain_pct", "scoring_exposure_pct",
)


def _value(row: Mapping[str, Any], field: str) -> float | None:
    value = row.get(field)
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise PortfolioBaselineError(f"{field} must be numeric or null")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise PortfolioBaselineError(f"{field} must be numeric or null") from exc
    if not math.isfinite(result) or result < 0:
        raise PortfolioBaselineError(f"{field} must be finite and non-negative")
    return result


def _complete_sum(rows: list[Mapping[str, Any]], field: str) -> tuple[float | None, int]:
    values = [_value(row, field) for row in rows]
    missing = sum(value is None for value in values)
    return (sum(value for value in values if value is not None) if missing == 0 else None), missing


def _concentration(rows: list[Mapping[str, Any]], field: str) -> dict[str, Any]:
    values = [_value(row, field) for row in rows]
    if any(value is None for value in values):
        return {
            "available": False, "reason": "one_or_more_player_values_missing",
            "top_3_share_pct": None, "top_5_share_pct": None,
            "hhi": None, "effective_contributor_count": None,
        }
    total = sum(values)
    if total <= 0:
        return {
            "available": False, "reason": "zero_total_exposure",
            "top_3_share_pct": None, "top_5_share_pct": None,
            "hhi": None, "effective_contributor_count": None,
        }
    shares = sorted((value / total for value in values), reverse=True)
    hhi = sum(share * share for share in shares)
    return {
        "available": True, "reason": None,
        "top_3_share_pct": round(sum(shares[:3]) * 100, 8),
        "top_5_share_pct": round(sum(shares[:5]) * 100, 8),
        "hhi": round(hhi, 10),
        "effective_contributor_count": round(1 / hhi, 8) if hhi > 0 else None,
    }


def build_portfolio_exposure_baseline(
    binding: Mapping[str, Any],
    comparison: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize template overlap and exposure concentration; never infer covariance."""
    if not isinstance(binding, Mapping) or binding.get("contract_version") != "1.0.0":
        raise PortfolioBaselineError("a validated M4 field-context binding is required")
    field_rows = binding.get("field_eo_rows")
    if not isinstance(field_rows, list) or not field_rows:
        raise PortfolioBaselineError("field EO rows are required")
    field_by_id = {}
    for row in field_rows:
        player_id = str(row.get("fpl_element_id", ""))
        if not player_id or player_id in field_by_id:
            raise PortfolioBaselineError("field rows contain missing or duplicate player IDs")
        field_by_id[player_id] = row

    candidate = binding.get("candidate") or {}
    scenarios = [{
        "scenario": "HOLD",
        "squad_ids": list(map(str, candidate.get("squad_15", []))),
        "starting_ids": list(map(str, candidate.get("starting_xi", []))),
        "bench_ids": list(map(str, candidate.get("bench_order", []))),
        "captain_id": str(candidate.get("captain_id", "")),
    }]
    if comparison is not None:
        proposed = comparison.get("frozen_candidate")
        if not isinstance(proposed, Mapping):
            raise PortfolioBaselineError("comparison frozen_candidate scenario is required")
        proposed_rows = proposed.get("players")
        if not isinstance(proposed_rows, list):
            raise PortfolioBaselineError("comparison scenario player rows are required")
        scenarios.append({
            "scenario": str(proposed.get("scenario", "FROZEN_CANDIDATE")),
            "squad_ids": [str(row["fpl_element_id"]) for row in proposed_rows if row.get("in_squad")],
            "starting_ids": [str(row["fpl_element_id"]) for row in proposed_rows if row.get("in_starting_xi")],
            "bench_ids": [str(row["fpl_element_id"]) for row in proposed_rows if row.get("in_outfield_bench")],
            "captain_id": str(proposed.get("captain_id", "")),
        })

    results = []
    for scenario in scenarios:
        squad_ids = scenario["squad_ids"]
        starting_ids = scenario["starting_ids"]
        bench_ids = scenario["bench_ids"]
        if len(squad_ids) != 15 or len(set(squad_ids)) != 15 or len(starting_ids) != 11:
            raise PortfolioBaselineError(f"{scenario['scenario']} squad or XI is malformed")
        if set(starting_ids) & set(bench_ids) or set(starting_ids) | set(bench_ids) | (
            {str(candidate.get("reserve_goalkeeper_id", ""))}
        ) != set(squad_ids):
            raise PortfolioBaselineError(f"{scenario['scenario']} lineup does not partition the squad")
        if scenario["captain_id"] not in starting_ids:
            raise PortfolioBaselineError(f"{scenario['scenario']} captain must be a starter")
        missing = sorted(set(squad_ids) - set(field_by_id))
        if missing:
            raise PortfolioBaselineError("field EO missing squad players: " + ", ".join(missing))

        squad_rows = [field_by_id[player_id] for player_id in squad_ids]
        xi_rows = [field_by_id[player_id] for player_id in starting_ids]
        bench_rows = [field_by_id[player_id] for player_id in bench_ids]
        captain_row = field_by_id[scenario["captain_id"]]
        metric_sums = {}
        for metric in METRICS:
            squad_sum, squad_missing = _complete_sum(squad_rows, metric)
            xi_sum, xi_missing = _complete_sum(xi_rows, metric)
            bench_sum, bench_missing = _complete_sum(bench_rows, metric)
            metric_sums[metric] = {
                "squad_sum_pct_points": squad_sum,
                "squad_missing_count": squad_missing,
                "starting_xi_sum_pct_points": xi_sum,
                "starting_xi_missing_count": xi_missing,
                "bench_sum_pct_points": bench_sum,
                "bench_missing_count": bench_missing,
            }
        eo_concentration = _concentration(squad_rows, "effective_ownership_pct")
        starting_concentration = _concentration(xi_rows, "effective_ownership_pct")
        top_players = []
        for row in sorted(
            squad_rows,
            key=lambda item: (
                _value(item, "effective_ownership_pct") is None,
                -(_value(item, "effective_ownership_pct") or 0.0),
                str(item["fpl_element_id"]),
            ),
        )[:5]:
            top_players.append({
                "fpl_element_id": str(row["fpl_element_id"]),
                "effective_ownership_pct": _value(row, "effective_ownership_pct"),
                "starting_pct": _value(row, "starting_pct"),
            })
        captain_field_pct = _value(captain_row, "captain_pct")
        results.append({
            "scenario": scenario["scenario"],
            "squad_player_count": len(squad_ids),
            "starting_xi_count": len(starting_ids),
            "outfield_bench_count": len(bench_ids),
            "captain_id": scenario["captain_id"],
            "field_exposure_sums": metric_sums,
            "field_eo_concentration_within_squad": eo_concentration,
            "field_eo_concentration_within_starting_xi": starting_concentration,
            "captaincy": {
                "field_captain_pct": captain_field_pct,
                "personal_captain_share_pct": 100.0,
                "captain_share_delta_pct_points": (
                    round(100.0 - captain_field_pct, 8) if captain_field_pct is not None else None
                ),
            },
            "top_five_squad_field_eo_players": top_players,
        })

    return {
        "status": "PASS_NONCOVARIANCE_PORTFOLIO_EXPOSURE_BASELINE",
        "snapshot_id": binding.get("snapshot_id"),
        "season": binding.get("season"),
        "target_gameweek": binding.get("target_gameweek"),
        "field_cohort": binding.get("cohort"),
        "field_sample": binding.get("sample"),
        "field_scope": binding.get("field_scope"),
        "scenarios": results,
        "method_boundary": (
            "Concentration and template-overlap summaries use marginal field exposure only. "
            "They do not estimate player covariance, correlation, points variance or rank movement."
        ),
        "expected_points": "NOT_COMBINED_WITH_EO",
        "covar": "DISABLED",
        "release_eligible": False,
    }
