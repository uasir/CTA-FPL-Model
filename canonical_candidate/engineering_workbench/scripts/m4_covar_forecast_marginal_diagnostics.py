#!/usr/bin/env python3
"""Evaluate conventional player forecasts against final outcomes, clustered by Gameweek.

This is marginal player-forecast diagnostics only. It does not assess joint
player-outcome dependence or establish CoVar calibration.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any, Mapping


class ForecastDiagnosticsError(ValueError):
    """The matched panel is invalid or incomplete."""


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ForecastDiagnosticsError(f"{field} must be finite numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ForecastDiagnosticsError(f"{field} must be finite numeric") from exc
    if not math.isfinite(result):
        raise ForecastDiagnosticsError(f"{field} must be finite numeric")
    return result


def _metrics(rows: list[dict[str, float]]) -> dict[str, float | int]:
    n = len(rows)
    point_errors = [r["actual_points"] - r["expected_points"] for r in rows]
    minute_errors = [r["actual_minutes"] - r["expected_minutes"] for r in rows]
    return {
        "count": n,
        "mean_expected_points": sum(r["expected_points"] for r in rows) / n,
        "mean_actual_points": sum(r["actual_points"] for r in rows) / n,
        "points_bias_actual_minus_expected": sum(point_errors) / n,
        "points_mae": sum(abs(x) for x in point_errors) / n,
        "points_rmse": math.sqrt(sum(x * x for x in point_errors) / n),
        "mean_expected_minutes": sum(r["expected_minutes"] for r in rows) / n,
        "mean_actual_minutes": sum(r["actual_minutes"] for r in rows) / n,
        "minutes_bias_actual_minus_expected": sum(minute_errors) / n,
        "minutes_mae": sum(abs(x) for x in minute_errors) / n,
        "minutes_rmse": math.sqrt(sum(x * x for x in minute_errors) / n),
    }


def _bands(rows: list[dict[str, float]], field: str, boundaries: list[float]) -> list[dict[str, Any]]:
    labels = []
    for lo, hi in zip(boundaries, boundaries[1:]):
        selected = [r for r in rows if lo <= r[field] < hi]
        labels.append({
            "lower_inclusive": lo,
            "upper_exclusive": hi if math.isfinite(hi) else None,
            **(_metrics(selected) if selected else {"count": 0}),
        })
    return labels


def _percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    pos = (len(ordered) - 1) * p
    low, high = math.floor(pos), math.ceil(pos)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - pos) + ordered[high] * (pos - low)


def evaluate_matched_forecast_panel(
    panel: Mapping[str, Any], *, resamples: int = 2000, seed: int = 42
) -> dict[str, Any]:
    """Return pooled and Gameweek-cluster-bootstrap marginal diagnostics."""
    if not isinstance(panel, Mapping) or panel.get("dataset_type") != "MULTI_GAMEWEEK_PROSPECTIVE_CONVENTIONAL_FORECAST_OUTCOME_PANEL":
        raise ForecastDiagnosticsError("unsupported panel dataset type")
    if panel.get("decision_weight") != 0.0 or panel.get("production_eligible") is not False:
        raise ForecastDiagnosticsError("panel must remain research-only")
    if panel.get("cluster_unit") != "GAMEWEEK" or panel.get("joint_dependence_inferred_from_marginal_player_rows") is not False:
        raise ForecastDiagnosticsError("panel must preserve Gameweek clustering and exclude inferred joint dependence")
    if panel.get("missing_observations_zero_filled") != 0:
        raise ForecastDiagnosticsError("zero-filled missing observations are not allowed")
    if isinstance(resamples, bool) or not isinstance(resamples, int) or resamples < 100:
        raise ForecastDiagnosticsError("resamples must be an integer of at least 100")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ForecastDiagnosticsError("seed must be an integer")
    declared_gws = panel.get("gameweeks")
    if not isinstance(declared_gws, list) or not declared_gws:
        raise ForecastDiagnosticsError("panel must declare Gameweeks")
    if len(set(declared_gws)) != len(declared_gws) or any(isinstance(g, bool) or not isinstance(g, int) or g < 1 for g in declared_gws):
        raise ForecastDiagnosticsError("Gameweeks must be unique positive integers")
    raw_rows = panel.get("matched_rows")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ForecastDiagnosticsError("matched_rows must be non-empty")
    rows: list[dict[str, float]] = []
    seen = set()
    for raw in raw_rows:
        if not isinstance(raw, Mapping):
            raise ForecastDiagnosticsError("each matched row must be an object")
        gw, pid = raw.get("gameweek"), raw.get("fpl_element_id")
        if isinstance(gw, bool) or not isinstance(gw, int) or gw not in declared_gws:
            raise ForecastDiagnosticsError("row Gameweek is not declared by panel")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1 or (gw, pid) in seen:
            raise ForecastDiagnosticsError("player-Gameweek keys must be unique positive IDs")
        seen.add((gw, pid))
        if raw.get("finality_status") != "PASS_EXACT_MATCH":
            raise ForecastDiagnosticsError("every row must pass exact finality reconciliation")
        rows.append({
            "gameweek": float(gw),
            "expected_points": _number(raw.get("expected_points"), "expected_points"),
            "actual_points": _number(raw.get("actual_points"), "actual_points"),
            "expected_minutes": _number(raw.get("expected_minutes"), "expected_minutes"),
            "actual_minutes": _number(raw.get("actual_minutes"), "actual_minutes"),
        })
    if set(int(r["gameweek"]) for r in rows) != set(declared_gws):
        raise ForecastDiagnosticsError("every declared Gameweek must contain matched rows")
    if any(r["expected_minutes"] < 0 or r["actual_minutes"] < 0 for r in rows):
        raise ForecastDiagnosticsError("minutes values are outside valid bounds")
    grouped: dict[int, list[dict[str, float]]] = {}
    for row in rows:
        grouped.setdefault(int(row["gameweek"]), []).append(row)
    overall = _metrics(rows)
    per_gameweek = [
        {"gameweek": gw, **_metrics(grouped[gw])}
        for gw in sorted(grouped)
    ]
    rng = random.Random(seed)
    keys = sorted(grouped)
    metric_names = (
        "points_bias_actual_minus_expected", "points_mae", "points_rmse",
        "minutes_bias_actual_minus_expected", "minutes_mae", "minutes_rmse",
    )
    draws = {name: [] for name in metric_names}
    for _ in range(resamples):
        sample_rows = []
        for _ in keys:
            sample_rows.extend(grouped[keys[rng.randrange(len(keys))]])
        sample = _metrics(sample_rows)
        for name in metric_names:
            draws[name].append(float(sample[name]))
    intervals = {
        name: {"lower_2_5": _percentile(values, .025), "upper_97_5": _percentile(values, .975)}
        for name, values in draws.items()
    }
    return {
        "schema_version": "1.0.0",
        "status": "MARGINAL_FORECAST_DIAGNOSTICS_CREATED",
        "dataset_type": "CONVENTIONAL_PLAYER_FORECAST_MARGINAL_DIAGNOSTICS",
        "season": panel.get("season"),
        "gameweek_count": len(keys),
        "gameweeks": keys,
        "matched_player_gameweek_rows": len(rows),
        "cluster_unit": "GAMEWEEK",
        "overall_pooled_player_gameweek_metrics": overall,
        "per_gameweek_metrics": per_gameweek,
        "expected_points_bands": _bands(rows, "expected_points", [0, 2, 4, 6, 8, 10, math.inf]),
        "expected_minutes_bands": _bands(rows, "expected_minutes", [0, 15, 30, 45, 60, 75, 90, 105, 120, 150, 180, math.inf]),
        "gameweek_cluster_bootstrap": {
            "method": "PAIRED_PERCENTILE_BOOTSTRAP_RESAMPLING_WHOLE_GAMEWEEKS",
            "confidence_level": 0.95,
            "resamples": resamples,
            "seed": seed,
            "independent_clusters": len(keys),
            "intervals": intervals,
            "small_sample_warning": "Fewer than 20 independent Gameweeks; intervals are exploratory and unstable." if len(keys) < 20 else None,
        },
        "interpretation_limits": [
            "Player-Gameweek rows are not treated as independent bootstrap samples; whole Gameweeks are resampled.",
            "Pooled metrics weight each matched player-Gameweek row equally; the bootstrap preserves within-Gameweek dependence.",
            "Bands are descriptive diagnostics, not proof of calibrated predictive distributions.",
            "These marginal diagnostics do not evaluate or establish joint player-outcome dependence calibration.",
            "No forecast fitting, recalibration, recommendation change, or production use is performed.",
        ],
        "decision_weight": 0.0,
        "production_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    panel = json.loads(args.panel.read_text(encoding="utf-8"))
    result = evaluate_matched_forecast_panel(panel, resamples=args.resamples, seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "gameweek_count": result["gameweek_count"], "rows": result["matched_player_gameweek_rows"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
