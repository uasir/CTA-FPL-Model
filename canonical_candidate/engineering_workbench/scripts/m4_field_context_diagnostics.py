#!/usr/bin/env python3
"""Summarize field cohort, coverage, missingness and EO interval uncertainty."""
from __future__ import annotations

import math
from statistics import median
from typing import Any, Mapping


class FieldDiagnosticsError(ValueError):
    pass


METRICS = (
    "owned_by_pct", "effective_ownership_pct", "starting_pct",
    "captain_pct", "triple_captain_pct", "scoring_exposure_pct",
)


def _number(value: Any, label: str) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise FieldDiagnosticsError(f"{label} must be numeric or null")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise FieldDiagnosticsError(f"{label} must be numeric or null") from exc
    if not math.isfinite(result) or result < 0:
        raise FieldDiagnosticsError(f"{label} must be finite and non-negative")
    return result


def _nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def build_field_context_diagnostics(binding: Mapping[str, Any]) -> dict[str, Any]:
    """Produce descriptive diagnostics; no score, forecast or release decision."""
    if not isinstance(binding, Mapping) or binding.get("contract_version") != "1.0.0":
        raise FieldDiagnosticsError("a validated M4 field-context binding is required")
    rows = binding.get("field_eo_rows")
    if not isinstance(rows, list) or not rows:
        raise FieldDiagnosticsError("field EO rows are required")
    sample = binding.get("sample") or {}
    cohort = binding.get("cohort") or {}
    coverage = binding.get("coverage") or {}
    if not isinstance(sample, Mapping) or not isinstance(cohort, Mapping) or not isinstance(coverage, Mapping):
        raise FieldDiagnosticsError("cohort, sample and coverage metadata must be objects")

    metric_summary = {}
    for metric in METRICS:
        values = [_number(row.get(metric), f"{row.get('fpl_element_id')}.{metric}") for row in rows]
        available = [value for value in values if value is not None]
        metric_summary[metric] = {
            "available_player_count": len(available),
            "null_player_count": len(values) - len(available),
            "minimum_pct": min(available) if available else None,
            "median_pct": median(available) if available else None,
            "maximum_pct": max(available) if available else None,
        }

    ci_widths = []
    ci_missing = 0
    for row in rows:
        player_id = str(row.get("fpl_element_id", ""))
        low = _number(row.get("effective_ownership_pct_ci95_low"),
                      f"{player_id}.effective_ownership_pct_ci95_low")
        high = _number(row.get("effective_ownership_pct_ci95_high"),
                       f"{player_id}.effective_ownership_pct_ci95_high")
        if (low is None) != (high is None):
            raise FieldDiagnosticsError(f"{player_id} has an incomplete effective-ownership interval")
        if low is None:
            ci_missing += 1
        elif high < low:
            raise FieldDiagnosticsError(f"{player_id} effective-ownership interval is inverted")
        else:
            ci_widths.append(high - low)

    widths = sorted(ci_widths)
    candidate = binding.get("candidate") or {}
    return {
        "status": "PASS_FIELD_CONTEXT_DIAGNOSTICS",
        "snapshot_id": binding.get("snapshot_id"),
        "season": binding.get("season"),
        "target_gameweek": binding.get("target_gameweek"),
        "deadline_utc": binding.get("deadline_utc"),
        "captured_at_utc": binding.get("captured_at_utc"),
        "field_scope": binding.get("field_scope"),
        "cohort": dict(cohort),
        "sample": dict(sample),
        "coverage": {
            **dict(coverage),
            "field_player_row_count": len(rows),
            "missing_player_ids": list(coverage.get("missing_player_ids", [])),
        },
        "metric_missingness_and_ranges": metric_summary,
        "effective_ownership_ci95": {
            "available_interval_count": len(widths),
            "missing_interval_count": ci_missing,
            "median_width_pct_points": median(widths) if widths else None,
            "p95_width_pct_points": _nearest_rank(widths, 0.95),
            "maximum_width_pct_points": max(widths) if widths else None,
        },
        "candidate_coverage": {
            "manager_team_id": candidate.get("manager_team_id"),
            "squad_player_count": len(candidate.get("squad_15", [])),
            "candidate_squad_covered": coverage.get("candidate_squad_covered") is True,
        },
        "interpretation": (
            "Descriptive sample, coverage and interval diagnostics only. "
            "No rank forecast, expected-points conversion, portfolio utility or CoVar is computed."
        ),
        "expected_points": "NOT_COMBINED_WITH_EO",
        "covar": "DISABLED",
        "release_eligible": False,
    }
