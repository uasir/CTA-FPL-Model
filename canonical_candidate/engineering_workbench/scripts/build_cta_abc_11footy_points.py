#!/usr/bin/env python3
"""Train and run an exploratory 11footy-only ABC FPL points forecaster.

Historical player-fixture labels are official FPL total_points. Features are
strictly lagged 11footy player-match statistics. The first candidate is Ridge;
historical 11footy source vintages are not point-in-time verified.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from train_fpl_exploratory_ridge import fit_ridge, predict, optional_number

FEATURES = (
    "abc_player_key_pass_rate", "abc_player_tracked_xg_rate",
    "abc_recent_key_pass_trend", "abc_recent_xg_trend",
    "abc_player_fouls_committed_rate", "abc_minutes_trend",
    "abc_attacking_involvement", "abc_threat_creation_rate",
    "abc_threat_reception_rate", "abc_threat_realisation_rate",
    "abc_attacking_involvement_rate",
)


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["fpl_element_id", "gameweek", "predicted_points"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def dt(value):
    if not value:
        raise ValueError("Missing match kickoff")
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Match kickoff must include timezone")
    return result


def mean(rows, key):
    values = [optional_number(row.get(key)) for row in rows]
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def total(rows, key):
    values = [optional_number(row.get(key)) for row in rows]
    values = [v for v in values if v is not None]
    return sum(values) if values else None


def per90(rows, key):
    numerator, minutes = total(rows, key), total(rows, "minutes_played")
    return numerator * 90.0 / minutes if numerator is not None and minutes and minutes > 0 else None


def make_features(prior_rows):
    p3, p5 = prior_rows[-3:], prior_rows[-5:]
    kp3, kp5 = mean(p3, "key_passes"), mean(p5, "key_passes")
    xg3, xg5 = mean(p3, "tracked_xg_sum"), mean(p5, "tracked_xg_sum")
    shots3, goals3 = mean(p3, "shots"), total(p3, "goals")
    xg_sum3 = total(p3, "tracked_xg_sum")
    key_rate, xg_rate = per90(p3, "key_passes"), per90(p3, "tracked_xg_sum")
    involvement = kp3 + shots3 if kp3 is not None and shots3 is not None else None
    minutes3, minutes5 = mean(p3, "minutes_played"), mean(p5, "minutes_played")
    shots_rate = per90(p3, "shots")
    return {
        "abc_player_key_pass_rate": key_rate,
        "abc_player_tracked_xg_rate": xg_rate,
        "abc_recent_key_pass_trend": kp3 - kp5 if kp3 is not None and kp5 is not None else None,
        "abc_recent_xg_trend": xg3 - xg5 if xg3 is not None and xg5 is not None else None,
        "abc_player_fouls_committed_rate": per90(p3, "fouls_committed"),
        "abc_minutes_trend": minutes3 - minutes5 if minutes3 is not None and minutes5 is not None else None,
        "abc_attacking_involvement": involvement,
        "abc_threat_creation_rate": key_rate,
        "abc_threat_reception_rate": per90(p3, "attempts_inside_box"),
        "abc_threat_realisation_rate": goals3 / xg_sum3 if goals3 is not None and xg_sum3 is not None and xg_sum3 > 0 else None,
        "abc_attacking_involvement_rate": key_rate + shots_rate if key_rate is not None and shots_rate is not None else None,
    }


def build_training_rows(panel):
    by_player = defaultdict(list)
    for row in panel:
        if str(row.get("join_status") or "") != "VERIFIED_IDENTITY_AND_FIXTURE":
            continue
        player_id = str(row.get("fpl_element_id") or "").strip()
        target, gw = optional_number(row.get("fpl_total_points")), optional_number(row.get("gameweek"))
        if not player_id or target is None or gw is None:
            continue
        by_player[player_id].append((dt(row.get("match_kickoff_utc")), row))

    output = []
    for player_id, matches in by_player.items():
        matches.sort(key=lambda item: (item[0], str(item[1].get("fpl_fixture_id") or "")))
        prior = []
        for kickoff, row in matches:
            if len(prior) >= 3:
                output.append({
                    **make_features(prior),
                    "fpl_element_id": player_id,
                    "fixture_id": row.get("fpl_fixture_id", ""),
                    "gameweek": int(float(row["gameweek"])),
                    "kickoff_time_utc": kickoff.isoformat(),
                    "target_fpl_total_points": float(row["fpl_total_points"]),
                })
            prior.append(row)
    return sorted(output, key=lambda row: (row["gameweek"], row["kickoff_time_utc"], row["fpl_element_id"]))


def aggregate(records):
    groups = defaultdict(list)
    for row in records:
        groups[(str(row["fpl_element_id"]), int(float(row["gameweek"])))].append(row)
    return [{
        "fpl_element_id": player_id,
        "gameweek": gw,
        "fixture_count": len(rows),
        "actual_points": sum(float(r["target_fpl_total_points"]) for r in rows),
        "predicted_points": sum(float(r["predicted_points"]) for r in rows),
    } for (player_id, gw), rows in sorted(groups.items(), key=lambda item: (item[0][1], item[0][0]))]


def mae(actual, predicted):
    return sum(abs(a - p) for a, p in zip(actual, predicted)) / len(actual) if actual else None


def rmse(actual, predicted):
    return math.sqrt(sum((a - p) ** 2 for a, p in zip(actual, predicted)) / len(actual)) if actual else None


def run(training_rows, upcoming_rows, ridge_lambda=10.0, holdout_gameweeks=4):
    if not training_rows:
        raise ValueError("No verified 11footy training rows with prior player-match history")
    gameweeks = sorted({int(r["gameweek"]) for r in training_rows})
    if len(gameweeks) <= holdout_gameweeks:
        raise ValueError("Not enough historical gameweeks for chronological holdout")
    holdout = set(gameweeks[-holdout_gameweeks:])
    train = [r for r in training_rows if int(r["gameweek"]) not in holdout]
    test = [r for r in training_rows if int(r["gameweek"]) in holdout]
    features = [name for name in FEATURES if any(optional_number(r.get(name)) is not None for r in train)]
    if len(train) < len(features) + 2 or not features:
        raise ValueError("Insufficient verified historical rows or observed 11footy features")

    validation_model = fit_ridge(train, "target_fpl_total_points", features, ridge_lambda)
    validation_fixture = [{**row, "predicted_points": predict(validation_model, row)} for row in test]
    validation_gw = aggregate(validation_fixture)
    actual = [r["actual_points"] for r in validation_gw]
    predicted = [r["predicted_points"] for r in validation_gw]

    final_model = fit_ridge(training_rows, "target_fpl_total_points", features, ridge_lambda)
    forecast_fixture = []
    for row in upcoming_rows:
        if not str(row.get("fpl_element_id") or "").strip():
            continue
        if any(optional_number(row.get(name)) is None for name in features):
            # Missing values are allowed and handled by training-only imputation.
            pass
        forecast_fixture.append({
            "fpl_element_id": str(row["fpl_element_id"]),
            "gameweek": int(float(row["gameweek"])),
            "fixture_id": str(row.get("fixture_id") or ""),
            "predicted_points": predict(final_model, row),
        })
    groups = defaultdict(list)
    for row in forecast_fixture:
        groups[(row["fpl_element_id"], row["gameweek"])].append(row)
    forecasts = [{
        "fpl_element_id": player_id, "gameweek": gw, "fixture_count": len(items),
        "predicted_points": round(sum(x["predicted_points"] for x in items), 4),
        "forecast_type": "EXPLORATORY_11FOOTY_ABC_POINTS",
    } for (player_id, gw), items in sorted(groups.items(), key=lambda item: (item[0][1], item[0][0]))]

    report = {
        "status": "EXPLORATORY_FORECAST_BUILT",
        "model_version": "abc-11footy-ridge-v0.1",
        "target": "Official FPL total_points per player-fixture, aggregated to player-Gameweek",
        "provider": "11footy verified player-match features only",
        "feature_names": features,
        "training_fixture_rows": len(train),
        "historical_rows_including_holdout": len(training_rows),
        "validation_gameweeks": sorted(holdout),
        "validation_player_gameweeks": len(validation_gw),
        "validation_mae": mae(actual, predicted),
        "validation_rmse": rmse(actual, predicted),
        "ridge_lambda": ridge_lambda,
        "training_rows_source_vintage": "RETROSPECTIVE_NOT_POINT_IN_TIME_VERIFIED",
        "identity_policy": "Only VERIFIED_IDENTITY_AND_FIXTURE rows enter training.",
        "feature_policy": "Features use only earlier verified player matches; missing values use training-fold medians plus missingness indicators.",
        "forecast_rows": len(forecasts),
        "forecast_gameweeks": sorted({r["gameweek"] for r in forecasts}),
        "promotion_status": "RESEARCH_ONLY_DO_NOT_PROMOTE",
        "limitations": [
            "Historical 11footy source vintages were not archived at each historical FPL deadline; holdout is chronological but not a strict historical point-in-time backtest.",
            "This is a first Ridge point-prediction candidate, not a final model-family selection.",
            "Only 11footy-supported features are used; unsupported A/B/C concepts remain excluded rather than imputed from other providers.",
            "No expected-minutes model is included; output is per-player fixture points aggregated to the Gameweek.",
        ],
    }
    return final_model, forecasts, report, validation_gw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--historical-panel", type=Path, required=True)
    parser.add_argument("--upcoming-panel", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--ridge-lambda", type=float, default=10.0)
    parser.add_argument("--holdout-gameweeks", type=int, default=4)
    args = parser.parse_args()
    training_rows = build_training_rows(read_csv(args.historical_panel))
    model, forecasts, report, validation = run(
        training_rows, read_csv(args.upcoming_panel), args.ridge_lambda, args.holdout_gameweeks
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "abc_11footy_points_model.json").write_text(json.dumps(model, indent=2), encoding="utf-8")
    (args.out_dir / "abc_11footy_points_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_csv(args.out_dir / "abc_11footy_points_forecast.csv", forecasts)
    write_csv(args.out_dir / "abc_11footy_points_validation.csv", validation)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
