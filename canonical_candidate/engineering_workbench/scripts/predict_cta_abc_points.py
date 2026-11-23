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
    fixture_rows, gameweek_rows = score_rows(read_csv(args.input_panel), payload)
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
    print(json.dumps({
        "status": "PASS_RESEARCH_ONLY_SCORING",
        "model_version": payload["model_version"],
        "fixture_prediction_rows": len(fixture_rows),
        "player_gameweek_forecasts": len(gameweek_rows),
        "promotion_status": "RESEARCH_ONLY_DO_NOT_PROMOTE",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
