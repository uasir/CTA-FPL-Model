#!/usr/bin/env python3
"""Build a research-only multi-season FPL panel from a pinned public dataset revision.

Raw data is downloaded to the supplied runner-local output directory. No xP,
ownership, transfer, or post-match modified fields enter the predictor.
Historical snapshots are retrospective and are NOT point-in-time verified.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from train_fpl_exploratory_ridge import FEATURES, fit_ridge, predict, mae, rmse

REPOSITORY = "https://github.com/vaastav/Fantasy-Premier-League"
RAW_BASE = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League"
SOURCE_COMMIT = "d7b05b51d137bfefef4b692386d18c610975b9b9"
SEASONS = [
    "2016-17", "2017-18", "2018-19", "2019-20", "2020-21",
    "2021-22", "2022-23", "2023-24", "2024-25", "2025-26",
]


def optional_number(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def parse_bool(value):
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def fetch_bytes(url):
    request = urllib.request.Request(url, headers={"User-Agent": "CTA-FPL-Model-research/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def read_csv_bytes(payload):
    import io
    try:
        decoded = payload.decode("utf-8-sig")
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        # Historical exports contain accented names encoded as Windows-1252.
        decoded = payload.decode("cp1252")
        encoding = "cp1252"
    return list(csv.DictReader(io.StringIO(decoded))), encoding


def first_value(row, *names):
    for name in names:
        if name in row and str(row[name]).strip() != "":
            return row[name]
    return None


def load_season(season, out_dir):
    url = f"{RAW_BASE}/{SOURCE_COMMIT}/data/{season}/gws/merged_gw.csv"
    payload = fetch_bytes(url)
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{season}_merged_gw.csv"
    raw_path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    source_rows, source_encoding = read_csv_bytes(payload)
    if not source_rows:
        raise ValueError(f"No rows in source file for {season}")
    required = {"round", "kickoff_time", "minutes", "total_points"}
    missing = sorted(required - set(source_rows[0]))
    if missing:
        raise ValueError(f"{season}: missing required source columns: {missing}")
    return source_rows, {
        "season": season,
        "url": url,
        "sha256": digest,
        "bytes": len(payload),
        "source_rows": len(source_rows),
        "encoding": source_encoding,
        "raw_file": str(raw_path),
    }


def build_season_rows(season, source_rows):
    grouped = defaultdict(lambda: defaultdict(list))
    for raw in source_rows:
        element = first_value(raw, "element", "id")
        gameweek = optional_number(first_value(raw, "round", "gameweek"))
        if element is None or gameweek is None or gameweek < 1:
            continue
        kickoff = first_value(raw, "kickoff_time")
        if not kickoff:
            raise ValueError(f"{season}: missing kickoff_time for player {element}, GW{gameweek}")
        try:
            parsed_kickoff = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{season}: invalid kickoff_time {kickoff!r}") from exc
        grouped[str(element)][int(gameweek)].append({
            "kickoff_time": parsed_kickoff,
            "element": str(element),
            "gameweek": int(gameweek),
            "minutes": optional_number(raw.get("minutes")),
            "total_points": optional_number(raw.get("total_points")),
            "expected_goals": optional_number(raw.get("expected_goals")),
            "expected_assists": optional_number(raw.get("expected_assists")),
            "was_home": parse_bool(raw.get("was_home")),
            "fixture": first_value(raw, "fixture"),
        })

    output = []
    for element, gameweeks in grouped.items():
        history = []
        for gameweek in sorted(gameweeks):
            current = gameweeks[gameweek]
            prior = history[-1:]
            prior3 = history[-3:]
            prior5 = history[-5:]

            def complete_sum(rows, field):
                vals = [row[field] for row in rows]
                return sum(vals) if vals and all(v is not None for v in vals) else None

            def complete_mean(rows, field):
                total = complete_sum(rows, field)
                return total / len(rows) if total is not None else None

            prior_points = complete_sum(prior[0]["fixtures"], "total_points") if prior else None
            prior_minutes = complete_sum(prior[0]["fixtures"], "minutes") if prior else None
            prior3_points = [complete_sum(gw["fixtures"], "total_points") for gw in prior3]
            prior5_points = [complete_sum(gw["fixtures"], "total_points") for gw in prior5]
            prior3_minutes = [complete_sum(gw["fixtures"], "minutes") for gw in prior3]
            prior5_minutes = [complete_sum(gw["fixtures"], "minutes") for gw in prior5]
            prior3_xg = [complete_sum(gw["fixtures"], "expected_goals") for gw in prior3]
            prior3_xa = [complete_sum(gw["fixtures"], "expected_assists") for gw in prior3]

            def avg(values):
                return sum(values) / len(values) if values and all(v is not None for v in values) else None

            season_points = complete_sum([{"total_points": complete_sum(gw["fixtures"], "total_points")} for gw in history], "total_points") if history else None
            season_minutes = complete_sum([{"minutes": complete_sum(gw["fixtures"], "minutes")} for gw in history], "minutes") if history else None
            season_points_per90 = (
                season_points * 90.0 / season_minutes
                if season_points is not None and season_minutes is not None and season_minutes > 0
                else None
            )
            for fixture in current:
                output.append({
                    "season": season,
                    "fpl_element_id": element,
                    "gameweek": gameweek,
                    "kickoff_time": fixture["kickoff_time"].isoformat(),
                    "prior_gameweeks_count": len(history),
                    "prior_gw_points": prior_points,
                    "prior_gw_minutes": prior_minutes,
                    "prior3_gw_points_avg": avg(prior3_points),
                    "prior5_gw_points_avg": avg(prior5_points),
                    "prior3_gw_minutes_avg": avg(prior3_minutes),
                    "prior5_gw_minutes_avg": avg(prior5_minutes),
                    "prior3_gw_xg_avg": avg(prior3_xg),
                    "prior3_gw_xa_avg": avg(prior3_xa),
                    "season_to_date_points_per90": season_points_per90,
                    "was_home": 1.0 if fixture["was_home"] else 0.0,
                    "target_total_points": fixture["total_points"],
                    "target_minutes": fixture["minutes"],
                    "fixture_id": fixture["fixture"],
                })
            history.append({"gameweek": gameweek, "fixtures": current})
    return output


def evaluate(rows, holdout_fraction=0.2):
    eligible = [
        row for row in rows
        if row["prior_gameweeks_count"] >= 1
        and row["target_total_points"] is not None
        and row["target_minutes"] is not None
    ]
    chronology = sorted({(row["season"], row["gameweek"]) for row in eligible})
    if len(chronology) < 20:
        raise ValueError("Insufficient chronological gameweeks for multi-season evaluation")
    holdout_count = max(1, math.ceil(len(chronology) * holdout_fraction))
    validation_keys = set(chronology[-holdout_count:])
    train = [row for row in eligible if (row["season"], row["gameweek"]) not in validation_keys]
    validation = [row for row in eligible if (row["season"], row["gameweek"]) in validation_keys]
    if not train or not validation:
        raise ValueError("Empty chronological train or validation partition")
    model = fit_ridge(train, "target_total_points")
    groups = defaultdict(list)
    for row in validation:
        key = (row["season"], row["fpl_element_id"], row["gameweek"])
        groups[key].append(row)
    scored = []
    for (season, element, gameweek), fixtures in sorted(groups.items()):
        baseline = fixtures[0]["prior5_gw_points_avg"]
        if baseline is None:
            continue
        scored.append({
            "season": season,
            "fpl_element_id": element,
            "gameweek": gameweek,
            "actual_points": sum(row["target_total_points"] for row in fixtures),
            "predicted_points": sum(predict(model, row) for row in fixtures),
            "baseline_points": baseline,
            "actual_minutes": sum(row["target_minutes"] for row in fixtures),
            "fixture_count": len(fixtures),
        })
    if not scored:
        raise ValueError("No validation player-gameweeks have a complete last-five baseline")
    actual = [row["actual_points"] for row in scored]
    predicted = [row["predicted_points"] for row in scored]
    baseline = [row["baseline_points"] for row in scored]
    appeared = [row for row in scored if row["actual_minutes"] > 0]
    appearance_diagnostic = None
    if appeared:
        appeared_actual = [row["actual_points"] for row in appeared]
        appeared_predicted = [row["predicted_points"] for row in appeared]
        appeared_baseline = [row["baseline_points"] for row in appeared]
        appearance_diagnostic = {
            "scored_player_gameweeks_with_positive_minutes": len(appeared),
            "model_mae": round(mae(appeared_actual, appeared_predicted), 6),
            "model_rmse": round(rmse(appeared_actual, appeared_predicted), 6),
            "last5_baseline_mae": round(mae(appeared_actual, appeared_baseline), 6),
            "last5_baseline_rmse": round(rmse(appeared_actual, appeared_baseline), 6),
            "interpretation": "Post-outcome conditional diagnostic only; actual minutes are not available at prediction time and must not be used to select the live forecast cohort.",
        }
    per_season = {}
    for season in sorted({row["season"] for row in scored}):
        season_rows = [row for row in scored if row["season"] == season]
        season_actual = [row["actual_points"] for row in season_rows]
        season_predicted = [row["predicted_points"] for row in season_rows]
        season_baseline = [row["baseline_points"] for row in season_rows]
        season_appeared = [row for row in season_rows if row["actual_minutes"] > 0]
        per_season[season] = {
            "scored_player_gameweeks": len(season_rows),
            "model_mae": round(mae(season_actual, season_predicted), 6),
            "model_rmse": round(rmse(season_actual, season_predicted), 6),
            "last5_baseline_mae": round(mae(season_actual, season_baseline), 6),
            "last5_baseline_rmse": round(rmse(season_actual, season_baseline), 6),
            "mae_delta_model_minus_baseline": round(mae(season_actual, season_predicted) - mae(season_actual, season_baseline), 6),
            "rmse_delta_model_minus_baseline": round(rmse(season_actual, season_predicted) - rmse(season_actual, season_baseline), 6),
            "zero_minute_player_gameweek_share": round(sum(1 for row in season_rows if row["actual_minutes"] == 0) / len(season_rows), 6),
            "mean_actual_points": round(sum(season_actual) / len(season_actual), 6),
            "positive_minute_player_gameweeks": len(season_appeared),
            "positive_minute_model_mae": round(mae(
                [row["actual_points"] for row in season_appeared],
                [row["predicted_points"] for row in season_appeared],
            ), 6) if season_appeared else None,
            "positive_minute_last5_baseline_mae": round(mae(
                [row["actual_points"] for row in season_appeared],
                [row["baseline_points"] for row in season_appeared],
            ), 6) if season_appeared else None,
        }
    return {
        "status": "RESEARCH_ONLY",
        "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_SOURCE_VINTAGES",
        "train_gameweeks": len({(row["season"], row["gameweek"]) for row in train}),
        "validation_gameweeks": len(validation_keys),
        "train_fixture_rows": len(train),
        "validation_fixture_rows": len(validation),
        "scored_player_gameweeks": len(scored),
        "rows_excluded_for_missing_baseline": len(groups) - len(scored),
        "model": {
            "mae": round(mae(actual, predicted), 6),
            "rmse": round(rmse(actual, predicted), 6),
        },
        "last5_gameweek_points_baseline": {
            "mae": round(mae(actual, baseline), 6),
            "rmse": round(rmse(actual, baseline), 6),
        },
        "delta_model_minus_baseline": {
            "mae": round(mae(actual, predicted) - mae(actual, baseline), 6),
            "rmse": round(rmse(actual, predicted) - rmse(actual, baseline), 6),
        },
        "zero_minute_player_gameweek_share": round(sum(1 for row in scored if row["actual_minutes"] == 0) / len(scored), 6),
        "mean_actual_points": round(sum(actual) / len(actual), 6),
        "positive_minute_conditional_diagnostic": appearance_diagnostic,
        "per_season_validation_metrics": per_season,
        "features": list(FEATURES),
        "model_missing_value_policy": model["missing_value_policy"],
        "validation_seasons": sorted({row["season"] for row in validation}),
        "validation_first_gameweek": min(validation_keys),
        "validation_last_gameweek": max(validation_keys),
        "leakage_exclusions": [
            "xP (potential post-match leakage per source README)",
            "selected/ownership and transfers",
            "modified/post-match update timestamp",
            "target-fixture statistics",
        ],
        "limitations": [
            "Source files are retrospective season/gameweek exports, not archived pre-deadline vintages.",
            "FPL element IDs are season-scoped and are not treated as persistent player identities.",
            "No CTA/Opta/Wyscout features are included in this FPL-only baseline.",
            "Results are research-only and cannot promote CTA or 2PM-Transformer.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--seasons", nargs="*", default=SEASONS)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifests = []
    panel = []
    for season in args.seasons:
        source_rows, source_manifest = load_season(season, args.out_dir)
        manifests.append(source_manifest)
        panel.extend(build_season_rows(season, source_rows))
    panel.sort(key=lambda row: (row["season"], row["gameweek"], row["kickoff_time"], row["fpl_element_id"]))
    panel_path = args.out_dir / "vaastav_fpl_multiseason_panel.csv"
    fields = list(panel[0]) if panel else []
    with panel_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(panel)
    report = evaluate(panel)
    report.update({
        "source": "vaastav/Fantasy-Premier-League",
        "source_repository": REPOSITORY,
        "source_commit": SOURCE_COMMIT,
        "source_rights_status": "NOASSERTION_UNRESOLVED",
        "authorized_project_use": "USER_DIRECTED_RESEARCH_ONLY",
        "handling_policy": "Runner-local raw data and player-level outputs; do not redistribute source files or player-level extracts.",
        "source_files": manifests,
        "panel_rows": len(panel),
        "panel_sha256": hashlib.sha256(panel_path.read_bytes()).hexdigest(),
        "panel_path": str(panel_path),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    })
    (args.out_dir / "vaastav_fpl_multiseason_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
