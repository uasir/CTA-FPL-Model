#!/usr/bin/env python3
"""Score player-fixture rows with a saved ABC points model and aggregate by player-GW."""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

from train_fpl_exploratory_ridge import predict


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def validate_model_payload(model_payload):
    if not isinstance(model_payload, dict) or model_payload.get("schema_version") != "1.0":
        raise ValueError("Unsupported or missing ABC model artifact schema_version")
    if not str(model_payload.get("model_version") or "").strip():
        raise ValueError("ABC model artifact is missing model_version")
    model = model_payload.get("model")
    if not isinstance(model, dict):
        raise ValueError("ABC model artifact is missing its fitted model")
    feature_order = model_payload.get("feature_order")
    source_names = model.get("source_feature_names")
    if not isinstance(feature_order, list) or not feature_order:
        raise ValueError("ABC model artifact feature_order must be a non-empty list")
    if not isinstance(source_names, list) or source_names != feature_order:
        raise ValueError("Artifact feature_order does not match fitted model source_feature_names")
    if len(source_names) != len(set(source_names)):
        raise ValueError("ABC model artifact contains duplicate source features")
    required_arrays = ("imputation_values", "means", "scales", "coefficients")
    if any(not isinstance(model.get(name), list) for name in required_arrays):
        raise ValueError("ABC fitted model is missing its numerical parameter arrays")
    design_size = len(source_names) * 2
    if len(model["imputation_values"]) != len(source_names):
        raise ValueError("ABC imputation vector does not match source feature count")
    if len(model["means"]) != design_size or len(model["scales"]) != design_size:
        raise ValueError("ABC scaling vectors do not match feature and missingness-indicator design")
    if len(model["coefficients"]) != design_size + 1:
        raise ValueError("ABC coefficient vector does not match fitted design")
    if model.get("missing_value_policy") != "TRAINING_MEDIAN_PLUS_MISSINGNESS_INDICATOR":
        raise ValueError("Unsupported ABC model missing-value policy")
    return model


def score_rows(rows, model_payload):
    model = validate_model_payload(model_payload)
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
            "model_version": model_version,
        })
    return fixture_predictions, gameweek_forecasts


def write_csv(path: Path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--input-panel", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.model.read_text(encoding="utf-8"))
    source_rows = read_csv(args.input_panel)
    eligible_rows = research_eligible_rows(source_rows)
    fixture_rows, gameweek_rows = score_rows(eligible_rows, payload)
    write_csv(
        args.out_dir / "abc_fixture_points_predictions.csv",
        fixture_rows,
        ["fpl_element_id", "gameweek", "fpl_fixture_id", "expected_points", "model_version"],
    )
    write_csv(
        args.out_dir / "abc_player_gameweek_points_forecasts.csv",
        gameweek_rows,
        ["fpl_element_id", "gameweek", "fixture_count", "expected_points", "model_version"],
    )
    report = {
        "status": "PASS_RESEARCH_ONLY_INFERENCE_SMOKE_TEST",
        "inference_purpose": "IN_SAMPLE_PIPELINE_SMOKE_TEST_NOT_PERFORMANCE_EVALUATION",
        "model_version": payload["model_version"],
        "input_rows": len(source_rows),
        "research_eligible_rows": len(eligible_rows),
        "rows_excluded_for_research_ineligibility": len(source_rows) - len(eligible_rows),
        "fixture_prediction_rows": len(fixture_rows),
        "player_gameweek_forecasts": len(gameweek_rows),
        "unique_players": len({row["fpl_element_id"] for row in gameweek_rows}),
        "gameweeks": sorted({row["gameweek"] for row in gameweek_rows}),
        "promotion_status": "RESEARCH_ONLY_DO_NOT_PROMOTE",
        "decision_weight": 0.0,
        "production_eligible": False,
    }
    (args.out_dir / "abc_points_inference_report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
