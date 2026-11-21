"""Gameweek-clustered confidence intervals for joint calibration scores."""
from __future__ import annotations
import math
import random
from typing import Any, Mapping, Sequence

class GameweekClusterBootstrapError(ValueError):
    pass

def _percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    pos = (len(ordered) - 1) * p
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - pos) + ordered[hi] * (pos - lo)

def evaluate_gameweek_cluster_bootstrap(
    per_forecast: Sequence[Mapping[str, Any]], *, resamples: int = 2000, seed: int = 42
) -> dict[str, Any]:
    """Bootstrap Gameweeks as paired clusters; average repeated rows within each GW."""
    if not isinstance(per_forecast, Sequence) or isinstance(per_forecast, (str, bytes)) or not per_forecast:
        raise GameweekClusterBootstrapError("per_forecast must be a non-empty sequence")
    if isinstance(resamples, bool) or not isinstance(resamples, int) or resamples < 100:
        raise GameweekClusterBootstrapError("resamples must be an integer of at least 100")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise GameweekClusterBootstrapError("seed must be an integer")
    groups: dict[str, list[dict[str, float]]] = {}
    seen = set()
    for row in per_forecast:
        if not isinstance(row, Mapping):
            raise GameweekClusterBootstrapError("each forecast score must be an object")
        fid = str(row.get("forecast_id", "")).strip()
        gw = str(row.get("gameweek_id", "")).strip()
        if not fid or fid in seen or not gw:
            raise GameweekClusterBootstrapError("forecast IDs must be unique and Gameweek IDs non-empty")
        seen.add(fid)
        values = {}
        for field in ("model_brier_score", "reference_brier_score", "brier_score_difference_model_minus_reference"):
            value = row.get(field)
            if isinstance(value, bool):
                raise GameweekClusterBootstrapError("score values must be finite numbers")
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise GameweekClusterBootstrapError("score values must be finite numbers") from exc
            if not math.isfinite(number):
                raise GameweekClusterBootstrapError("score values must be finite numbers")
            values[field] = number
        groups.setdefault(gw, []).append(values)
    keys = sorted(groups)
    cluster = {gw: {
        "model": sum(x["model_brier_score"] for x in rows) / len(rows),
        "reference": sum(x["reference_brier_score"] for x in rows) / len(rows),
        "difference": sum(x["brier_score_difference_model_minus_reference"] for x in rows) / len(rows),
    } for gw, rows in groups.items()}
    def stats(sample):
        m = sum(cluster[g]["model"] for g in sample) / len(sample)
        r = sum(cluster[g]["reference"] for g in sample) / len(sample)
        d = sum(cluster[g]["difference"] for g in sample) / len(sample)
        return (m, r, d, 1.0 - m / r if r > 0 else None)
    point = stats(keys)
    rng = random.Random(seed)
    draws = [stats([keys[rng.randrange(len(keys))] for _ in keys]) for _ in range(resamples)]
    names = ("mean_model_brier_score", "mean_reference_brier_score", "mean_brier_difference_model_minus_reference", "brier_skill_score_vs_reference")
    intervals = {}
    for i, name in enumerate(names):
        vals = [draw[i] for draw in draws if draw[i] is not None]
        intervals[name] = {"lower_2_5": _percentile(vals, .025) if vals else None, "upper_97_5": _percentile(vals, .975) if vals else None, "valid_resamples": len(vals)}
    return {
        "method": "PAIRED_PERCENTILE_CLUSTER_BOOTSTRAP_BY_GAMEWEEK",
        "confidence_level": 0.95, "resamples": resamples, "seed": seed,
        "independent_clusters": len(keys), "cluster_unit": "GAMEWEEK",
        "within_cluster_forecast_aggregation": "ARITHMETIC_MEAN",
        "point_estimate": dict(zip(names, point)), "intervals": intervals,
        "small_sample_warning": "Few independent Gameweeks; intervals are unstable and exploratory." if len(keys) < 20 else None,
        "decision_weight": 0.0, "production_eligible": False,
    }
