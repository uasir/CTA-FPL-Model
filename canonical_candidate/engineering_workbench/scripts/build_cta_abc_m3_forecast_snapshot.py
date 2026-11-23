#!/usr/bin/env python3
"""Package ABC fixture predictions and Dastan minutes in the existing M3 contract.

This is an adapter only: it does not change ABC, M3, or any minutes model.
ABC supplies total FPL points per fixture; Dastan supplies expected minutes.
The resulting player_forecasts are five-Gameweek, squad-independent records.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

POSITION_MAP = {"1": "GKP", "2": "DEF", "3": "MID", "4": "FWD",
                "Goalkeeper": "GKP", "Defender": "DEF",
                "Midfielder": "MID", "Forward": "FWD",
                "GKP": "GKP", "DEF": "DEF", "MID": "MID", "FWD": "FWD"}


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def finite(value, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be numeric: {value!r}")
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def parse_time(value: str, field: str) -> datetime:
    if not value:
        raise ValueError(f"Missing {field}")
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def normalize_players(rows: list[dict]) -> dict[str, dict]:
    result = {}
    for row in rows:
        element = str(row.get("id") or row.get("fpl_element_id") or "").strip()
        if not element.isdigit() or int(element) < 1:
            raise ValueError("FPL player roster contains an invalid element ID")
        if element in result:
            raise ValueError(f"Duplicate FPL roster element ID: {element}")
        team = row.get("team") or row.get("team_id")
        position_raw = row.get("element_type") or row.get("position")
        team_id = int(finite(team, f"player {element} team_id"))
        position = POSITION_MAP.get(str(position_raw))
        price_raw = row.get("now_cost")
        price = finite(price_raw, f"player {element} now_cost") / 10.0
        if team_id < 1 or position is None or price <= 0:
            raise ValueError(f"FPL roster metadata invalid for element {element}")
        result[element] = {
            "fpl_element_id": int(element),
            "web_name": str(row.get("web_name") or ""),
            "team_id": team_id,
            "position": position,
            "price": price,
        }
    if not result:
        raise ValueError("FPL player roster is empty")
    return result


def normalize_fixtures(rows: list[dict], gameweeks: list[int], as_of: datetime) -> dict[str, dict]:
    result = {}
    for row in rows:
        event = row.get("event") or row.get("gameweek")
        if event in (None, ""):
            continue
        gw = int(finite(event, "fixture gameweek"))
        if gw not in gameweeks:
            continue
        fixture_id = str(row.get("id") or row.get("fixture_id") or "").strip()
        if not fixture_id or fixture_id in result:
            raise ValueError(f"Missing or duplicate FPL fixture ID: {fixture_id!r}")
        kickoff = parse_time(row.get("kickoff_time"), f"fixture {fixture_id} kickoff_time")
        if kickoff <= as_of:
            raise ValueError(f"Target fixture {fixture_id} is not after forecast as-of time")
        home = int(finite(row.get("team_h") or row.get("team_h_id"), "team_h"))
        away = int(finite(row.get("team_a") or row.get("team_a_id"), "team_a"))
        result[fixture_id] = {"gameweek": gw, "kickoff_time": kickoff,
                              "team_h": home, "team_a": away}
    if not result:
        raise ValueError("No upcoming FPL fixtures found in the declared five-Gameweek horizon")
    return result


def build_snapshot(prediction_rows: list[dict], minutes_rows: list[dict],
                   players_rows: list[dict], fixtures_rows: list[dict],
                   model_payload: dict, model_manifest: dict,
                   as_of_utc: str, gameweeks: list[int],
                   input_hashes: dict | None = None) -> tuple[dict, dict, dict]:
    if len(gameweeks) != 5 or gameweeks != list(range(gameweeks[0], gameweeks[0] + 5)):
        raise ValueError("Exactly five consecutive Gameweeks must be declared")
    as_of = parse_time(as_of_utc, "forecast as_of_utc")
    model_version = str(model_payload.get("model_version") or "").strip()
    if not model_version:
        raise ValueError("ABC model artifact has no model_version")
    if model_manifest.get("model_version") != model_version:
        raise ValueError("ABC model artifact and manifest versions do not match")
    if model_manifest.get("production_eligible") is not False or float(model_manifest.get("decision_weight", 0)) != 0:
        raise ValueError("ABC model manifest must remain research-only with zero decision weight")
    if model_manifest.get("model_sha256") and input_hashes and input_hashes.get("model_sha256"):
        if model_manifest["model_sha256"] != input_hashes["model_sha256"]:
            raise ValueError("ABC model manifest hash does not match model artifact")

    players = normalize_players(players_rows)
    fixtures = normalize_fixtures(fixtures_rows, gameweeks, as_of)

    prediction_by_key = {}
    for row in prediction_rows:
        element = str(row.get("fpl_element_id") or "").strip()
        fixture = str(row.get("fpl_fixture_id") or row.get("fixture_id") or "").strip()
        gw = int(finite(row.get("gameweek"), "ABC prediction gameweek"))
        points = finite(row.get("expected_points"), "ABC expected_points")
        version = str(row.get("model_version") or "")
        key = (element, fixture)
        if key in prediction_by_key:
            raise ValueError(f"Duplicate ABC player-fixture prediction: {key}")
        if element not in players or fixture not in fixtures:
            raise ValueError(f"ABC prediction references unknown FPL player/fixture: {key}")
        fixture_info = fixtures[fixture]
        if gw != fixture_info["gameweek"]:
            raise ValueError(f"ABC prediction Gameweek disagrees with FPL fixture: {key}")
        if players[element]["team_id"] not in {fixture_info["team_h"], fixture_info["team_a"]}:
            raise ValueError(f"ABC player team does not participate in fixture: {key}")
        if version != model_version:
            raise ValueError(f"ABC prediction model version mismatch for {key}")
        prediction_by_key[key] = {"fpl_element_id": int(element), "gameweek": gw,
                                  "fixture_id": fixture, "expected_points": points}

    minutes_by_key = {}
    for row in minutes_rows:
        element = str(row.get("fpl_element_id") or "").strip()
        fixture = str(row.get("fixture_id") or row.get("fpl_fixture_id") or "").strip()
        gw = int(finite(row.get("gameweek"), "Dastan minutes gameweek"))
        minutes = finite(row.get("expected_minutes"), "Dastan expected_minutes")
        key = (element, fixture)
        if key in minutes_by_key:
            raise ValueError(f"Duplicate Dastan player-fixture minutes: {key}")
        if element not in players or fixture not in fixtures:
            raise ValueError(f"Dastan row references unknown FPL player/fixture: {key}")
        if gw != fixtures[fixture]["gameweek"]:
            raise ValueError(f"Dastan Gameweek disagrees with FPL fixture: {key}")
        if players[element]["team_id"] not in {fixtures[fixture]["team_h"], fixtures[fixture]["team_a"]}:
            raise ValueError(f"Dastan player team does not participate in fixture: {key}")
        if not 0 <= minutes <= 90:
            raise ValueError(f"Dastan expected_minutes outside [0, 90] for {key}")
        minutes_by_key[key] = minutes

    if set(prediction_by_key) != set(minutes_by_key):
        missing_minutes = sorted(set(prediction_by_key) - set(minutes_by_key))
        missing_points = sorted(set(minutes_by_key) - set(prediction_by_key))
        raise ValueError(
            f"ABC/Dastan fixture universes differ; missing minutes={missing_minutes[:10]}, "
            f"missing ABC predictions={missing_points[:10]}"
        )

    fixture_out = []
    by_player_gw = defaultdict(list)
    by_player = defaultdict(list)
    for key, prediction in sorted(prediction_by_key.items()):
        fixture_info = fixtures[key[1]]
        item = {
            **prediction,
            "expected_minutes": minutes_by_key[key],
            "kickoff_time": fixture_info["kickoff_time"].isoformat(),
            "model_version": model_version,
        }
        fixture_out.append(item)
        by_player_gw[(key[0], prediction["gameweek"])].append(item)
        by_player[key[0]].append(item)

    gameweek_out = []
    for (element, gw), rows in sorted(by_player_gw.items(), key=lambda x: (int(x[0][0]), x[0][1])):
        gameweek_out.append({
            "fpl_element_id": int(element), "gameweek": gw,
            "fixture_count": len(rows),
            "expected_points": math.fsum(row["expected_points"] for row in rows),
            "expected_minutes": math.fsum(row["expected_minutes"] for row in rows),
            "model_version": model_version,
        })

    player_forecasts = []
    horizon_out = []
    for element, metadata in sorted(players.items(), key=lambda x: int(x[0])):
        rows = by_player[element]
        expected_points = math.fsum(row["expected_points"] for row in rows)
        expected_minutes = math.fsum(row["expected_minutes"] for row in rows)
        player_forecasts.append({
            "fpl_element_id": int(element),
            "expected_points": expected_points,
            "expected_minutes": expected_minutes,
            "price": metadata["price"],
            "position": metadata["position"],
            "team_id": metadata["team_id"],
        })
        horizon_out.append({
            "fpl_element_id": int(element),
            "expected_points_5gw": expected_points,
            "expected_minutes_5gw": expected_minutes,
            "fixture_count_5gw": len(rows),
            "gameweeks_with_fixtures": len({row["gameweek"] for row in rows}),
            "gameweeks": ",".join(map(str, gameweeks)),
            "model_version": model_version,
        })

    provenance = dict(input_hashes or {})
    snapshot_identity = {
        "model_version": model_version, "gameweeks": gameweeks,
        "as_of_utc": as_of.isoformat(), "provenance": provenance,
        "player_forecasts": player_forecasts,
    }
    snapshot_id = hashlib.sha256(
        json.dumps(snapshot_identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    quality = {
        "validation_status": "EXPLORATORY_ONLY",
        "point_in_time_status": "NOT_VERIFIED",
        "data_coverage": {
            "target_gameweeks": gameweeks,
            "as_of_utc": as_of.isoformat(),
            "fpl_roster_players": len(players),
            "upcoming_fixtures": len(fixtures),
            "abc_fixture_predictions": len(fixture_out),
            "players_with_fixture_predictions": len(by_player),
            "dastan_minutes_rows": len(minutes_by_key),
            "model_training_point_in_time_status": model_manifest.get("point_in_time_status", "NOT_VERIFIED"),
            "source_hashes": provenance,
        },
        "limitations": [
            "ABC is a research-only candidate trained on restricted historical data; its forecasts are not production validated.",
            "Historical provider source vintages at FPL deadlines are not verified.",
            "Expected minutes are supplied by the independent Dastan minutes forecast; ABC does not estimate minutes.",
            "Players without a fixture in the five-Gameweek horizon receive zero expected points and zero expected minutes.",
            "The forecast snapshot must not be promoted into live recommendations while validation_status is EXPLORATORY_ONLY.",
        ],
    }
    snapshot = {
        "forecast_snapshot_id": snapshot_id,
        "model_version": model_version,
        "forecast_horizon_gameweeks": 5,
        "forecast_quality": quality,
        "player_forecasts": player_forecasts,
    }
    report = {
        "status": "PASS_RESEARCH_ONLY_M3_SNAPSHOT",
        "forecast_snapshot_id": snapshot_id,
        "model_version": model_version,
        "gameweeks": gameweeks,
        "fpl_roster_players": len(players),
        "fixture_prediction_rows": len(fixture_out),
        "player_gameweek_rows": len(gameweek_out),
        "player_five_gameweek_rows": len(horizon_out),
        "m3_contract_version": "1.0.0",
        "validation_status": "EXPLORATORY_ONLY",
        "point_in_time_status": "NOT_VERIFIED",
        "decision_weight": 0.0,
        "production_eligible": False,
        "covar_used": False,
        "aggregation": "ABC fixture expected points and Dastan fixture expected minutes are independently summed to player and five-Gameweek horizons.",
        "outputs": {},
    }
    return snapshot, {"fixture": fixture_out, "gameweek": gameweek_out, "horizon": horizon_out}, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--abc-fixture-predictions", type=Path, required=True)
    parser.add_argument("--dastan-minutes", type=Path, required=True)
    parser.add_argument("--fpl-players", type=Path, required=True)
    parser.add_argument("--fpl-fixtures", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--model-manifest", type=Path, required=True)
    parser.add_argument("--as-of-utc", required=True)
    parser.add_argument("--gameweeks", required=True, help="Five consecutive Gameweeks, e.g. 12,13,14,15,16")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    gameweeks = [int(value.strip()) for value in args.gameweeks.split(",") if value.strip()]
    hashes = {
        "abc_fixture_predictions_sha256": sha256(args.abc_fixture_predictions),
        "dastan_minutes_sha256": sha256(args.dastan_minutes),
        "fpl_players_sha256": sha256(args.fpl_players),
        "fpl_fixtures_sha256": sha256(args.fpl_fixtures),
        "model_sha256": sha256(args.model),
        "model_manifest_sha256": sha256(args.model_manifest),
    }
    snapshot, tables, report = build_snapshot(
        read_csv(args.abc_fixture_predictions), read_csv(args.dastan_minutes),
        read_csv(args.fpl_players), read_csv(args.fpl_fixtures),
        json.loads(args.model.read_text(encoding="utf-8")),
        json.loads(args.model_manifest.read_text(encoding="utf-8")),
        args.as_of_utc, gameweeks, hashes,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "abc_m3_fixture_forecasts.csv", tables["fixture"],
              ["fpl_element_id", "gameweek", "fixture_id", "expected_points",
               "expected_minutes", "kickoff_time", "model_version"])
    write_csv(args.out_dir / "abc_m3_player_gameweek_forecasts.csv", tables["gameweek"],
              ["fpl_element_id", "gameweek", "fixture_count", "expected_points",
               "expected_minutes", "model_version"])
    write_csv(args.out_dir / "abc_m3_player_five_gameweek_forecasts.csv", tables["horizon"],
              ["fpl_element_id", "expected_points_5gw", "expected_minutes_5gw",
               "fixture_count_5gw", "gameweeks_with_fixtures", "gameweeks", "model_version"])
    (args.out_dir / "abc_m3_forecast_snapshot.json").write_text(
        json.dumps(snapshot, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    report["outputs"] = {
        name: {"path": str(args.out_dir / filename), "sha256": sha256(args.out_dir / filename)}
        for name, filename in (
            ("snapshot", "abc_m3_forecast_snapshot.json"),
            ("fixture", "abc_m3_fixture_forecasts.csv"),
            ("player_gameweek", "abc_m3_player_gameweek_forecasts.csv"),
            ("player_five_gameweek", "abc_m3_player_five_gameweek_forecasts.csv"),
        )
    }
    (args.out_dir / "abc_m3_forecast_report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
