#!/usr/bin/env python3
"""Score player-fixture rows with a saved ABC points model and aggregate by player-GW."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

from train_fpl_exploratory_ridge import predict


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def number(value):
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def score_rows(rows, model_payload):
    model = model_payload["model"]
    model_version = model_payload["model_version"]
    seen = set()
    fixture_predictions = []
    grouped = defaultdict(list)
    for row in rows:
        player = str(row.get("fpl_element_id") or "").strip()
        fixture = str(row.get("fpl_fixture_id") or row.get("fixture_id") or "").strip()
        gameweek = str(row.get("gameweek") or "").strip()
        if not player or not fixture or not gameweek:
            raise ValueError("Prediction rows require fpl_element_id, fixture ID and gameweek")
        key = (player, fixture)
        if key in seen:
            raise ValueError(f"Duplicate prediction player-fixture key: {key}")
        seen.add(key)
        predicted = float(predict(model, row))
        if not math.isfinite(predicted):
            raise ValueError(f"Non-finite ABC points prediction for {key}")
        item = {
            "fpl_element_id": player,
            "gameweek": int(float(gameweek)),
            "fpl_fixture_id": fixture,
            "expected_points": predicted,
            "model_version": model_version,
            "research_eligible_for_analysis": row.get("research_eligible_for_analysis", ""),
            "identity_verified": row.get("identity_verified", ""),
            "cta_snapshot_available_as_of_deadline": row.get("cta_snapshot_available_as_of_deadline", ""),
        }
        fixture_predictions.append(item)
        grouped[(player, int(float(gameweek)))].append(predicted)

    gameweek_forecasts = []
    for (player, gameweek), predictions in sorted(
        grouped.items(), key=lambda item: (int(item[0][0]), item[0][1])
    ):
        gameweek_forecasts.append({
            "fpl_element_id": player,
            "gameweek": gameweek,
            "fixture_count": len(predictions),
            "expected_points": math.fsum(predictions),
            "research_eligible_fixture_count": sum(
                str(item.get("research_eligible_for_analysis", "")).strip().lower() in {"true", "1", "yes"}
                for item in fixture_predictions
                if item["fpl_element_id"] == player and item["gameweek"] == gameweek
            ),
            "model_version": model_version,
        })
    return fixture_predictions, gameweek_forecasts




def _percentile(values, percentile):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _distribution(values):
    if not values:
        return {"count": 0, "min": None, "p05": None, "median": None, "p95": None, "max": None, "negative_count": 0}
    return {
        "count": len(values),
        "min": min(values),
        "p05": _percentile(values, 0.05),
        "median": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "max": max(values),
        "negative_count": sum(value < 0 for value in values),
    }


def build_report(rows, model_payload, manifest, input_report, model_path, fixture_predictions=None):
    feature_order = model_payload["feature_order"]
    coverage = {}
    for feature in feature_order:
        values = [number(row.get(feature)) for row in rows]
        observed_values = [value for value in values if value is not None]
        observed = len(observed_values)
        coverage[feature] = {
            "observed_rows": observed,
            "missing_rows": len(rows) - observed,
            "observed_pct": (observed / len(rows) * 100.0) if rows else 0.0,
            "observed_min": min(observed_values) if observed_values else None,
            "observed_median": _percentile(observed_values, 0.50),
            "observed_max": max(observed_values) if observed_values else None,
        }
    model = model_payload.get("model", {})
    training_names = model.get("source_feature_names", feature_order)
    training_means = model.get("means", [])
    training_scales = model.get("scales", [])
    training_domain = {}
    for feature in feature_order:
        if feature not in training_names:
            continue
        index = training_names.index(feature)
        if index >= len(training_means) or index >= len(training_scales):
            continue
        mean = number(training_means[index])
        scale = number(training_scales[index])
        if mean is None or scale is None or scale <= 0:
            continue
        values = [number(row.get(feature)) for row in rows]
        observed_values = [value for value in values if value is not None]
        z_scores = [abs((value - mean) / scale) for value in observed_values]
        training_domain[feature] = {
            "training_mean": mean,
            "training_scale": scale,
            "current_observed_rows": len(observed_values),
            "current_min": min(observed_values) if observed_values else None,
            "current_max": max(observed_values) if observed_values else None,
            "outside_training_3sd_rows": sum(value > 3.0 for value in z_scores),
            "maximum_absolute_training_z_score": max(z_scores) if z_scores else None,
        }
    fixture_predictions = fixture_predictions or []
    all_predictions = [float(row["expected_points"]) for row in fixture_predictions]
    eligible_predictions = [
        float(row["expected_points"]) for row in fixture_predictions
        if str(row.get("research_eligible_for_analysis", "")).strip().lower() in {"true", "1", "yes"}
    ]
    ineligible_predictions = [
        float(row["expected_points"]) for row in fixture_predictions
        if str(row.get("research_eligible_for_analysis", "")).strip().lower() not in {"true", "1", "yes"}
    ]
    return {
        "prediction_distribution": {
            "all_scored_player_fixtures": _distribution(all_predictions),
            "research_eligible_player_fixtures": _distribution(eligible_predictions),
            "research_ineligible_player_fixtures": _distribution(ineligible_predictions),
            "warning": "Distribution diagnostics only; no clipping or calibration is applied.",
        },
        "status": "PASS_RESEARCH_ONLY_CURRENT_INFERENCE" if rows else "NO_FORECAST_ROWS",
        "model_version": model_payload["model_version"],
        "model_family": manifest.get("model_family"),
        "training_rows": manifest.get("training_rows"),
        "training_unique_players": manifest.get("unique_players"),
        "training_unique_fixtures": manifest.get("unique_fixtures"),
        "training_point_in_time_status": manifest.get("point_in_time_status"),
        "current_target_gameweeks": sorted({int(float(row["gameweek"])) for row in rows}),
        "forecast_rows": len(rows),
        "forecast_players": len({str(row["fpl_element_id"]) for row in rows}),
        "analysis_eligible_rows": sum(
            str(row.get("research_eligible_for_analysis", "")).strip().lower() in {"true", "1", "yes"}
            for row in rows
        ),
        "feature_count": len(feature_order),
        "feature_coverage": coverage,
        "training_feature_domain_diagnostics": training_domain,
        "features_with_zero_observation": [name for name, item in coverage.items() if item["observed_rows"] == 0],
        "current_wyscout_fallback_available": False,
        "current_feature_profile": "11footy current player-match evidence + official FPL lagged form; unsupported historical Wyscout features remain missing",
        "current_input_point_in_time_status": input_report.get("point_in_time_status"),
        "current_input_source_hashes": input_report.get("source_hashes", {}),
        "model_sha256_verified": sha256(model_path) == manifest.get("model_sha256"),
        "decision_weight": 0.0,
        "production_eligible": False,
        "promotion_status": "RESEARCH_ONLY_DO_NOT_PROMOTE",
        "limitations": [
            "Current 11footy source snapshot is pre-deadline, but retrospective official FPL API revisions and historical 11footy source vintages are not fully point-in-time verified.",
            "Current panel has no current-season Wyscout fallback; unsupported Wyscout-trained features are imputed with training medians and missingness indicators.",
            "This forecast is exploratory and must not be sent to M3/M4 production decision logic.",
        ],
    }


def write_csv(path: Path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--model-manifest", type=Path, required=True)
    parser.add_argument("--input-panel", type=Path, required=True)
    parser.add_argument("--input-report", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.model.read_text(encoding="utf-8"))
    manifest = json.loads(args.model_manifest.read_text(encoding="utf-8"))
    input_report = json.loads(args.input_report.read_text(encoding="utf-8"))
    if manifest.get("production_eligible") is not False or float(manifest.get("decision_weight", -1)) != 0.0:
        raise ValueError("Historical ABC model manifest is not explicitly research-only")
    if manifest.get("model_version") != payload.get("model_version"):
        raise ValueError("Model JSON and manifest versions do not match")
    fixture_rows, gameweek_rows = score_rows(read_csv(args.input_panel), payload)
    report = build_report(read_csv(args.input_panel), payload, manifest, input_report, args.model, fixture_rows)
    write_csv(
        args.out_dir / "abc_fixture_points_predictions.csv",
        fixture_rows,
        ["fpl_element_id", "gameweek", "fpl_fixture_id", "expected_points", "model_version", "research_eligible_for_analysis", "identity_verified", "cta_snapshot_available_as_of_deadline"],
    )
    write_csv(
        args.out_dir / "abc_player_gameweek_points_forecasts.csv",
        gameweek_rows,
        ["fpl_element_id", "gameweek", "fixture_count", "expected_points", "research_eligible_fixture_count", "model_version"],
    )
    write_json(args.out_dir / "abc_current_model_forecast_report.json", report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
