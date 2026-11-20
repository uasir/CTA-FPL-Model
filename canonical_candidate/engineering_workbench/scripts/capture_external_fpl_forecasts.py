#!/usr/bin/env python3
"""Freeze actual public player-level FPL forecast outputs without reinterpretation.

Raw source bytes are retained unchanged. CSV variants are labelled by the page
that exposes them; this collector never infers hidden model variants.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}: invalid ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label}: timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def finite_number(value, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}: forecast value is not numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label}: forecast value must be finite")
    return number


def unique_ids(values, label: str) -> None:
    normalized = [str(value).strip() for value in values]
    if any(not value for value in normalized):
        raise ValueError(f"{label}: blank player ID")
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label}: duplicate player IDs")


def validate_payload(source: str, data: bytes, gameweek: int, content_type: str) -> dict:
    if not data:
        raise ValueError(f"{source}: empty response")
    if "text/html" in content_type.lower():
        raise ValueError(f"{source}: received HTML instead of forecast data")
    if source == "fpl_cat_player_xp":
        payload = json.loads(data.decode("utf-8"))
        if int(payload.get("gameweek", -1)) != gameweek:
            raise ValueError("FPL Cat payload gameweek mismatch")
        if not payload.get("computed_at") or not payload.get("deadline") or not isinstance(payload.get("players"), list):
            raise ValueError("FPL Cat payload missing computed_at, deadline or players")
        generated_at = parse_timestamp(payload["computed_at"], "FPL Cat computed_at")
        deadline = parse_timestamp(payload["deadline"], "FPL Cat deadline")
        if generated_at >= deadline:
            raise ValueError("FPL Cat forecast was generated at or after the deadline")
        players = payload["players"]
        if not players or any("id" not in row or "xp" not in row for row in players):
            raise ValueError("FPL Cat payload missing player IDs or xp values")
        unique_ids([row["id"] for row in players], "FPL Cat")
        for row in players:
            finite_number(row["xp"], "FPL Cat xp")
        return {"row_count": len(players), "grain": "player_gameweek",
                "generated_at": payload["computed_at"], "deadline_utc": payload["deadline"],
                "variant": "published_xP", "player_id_column": "id",
                "forecast_column": "xp", "timestamp_eligibility": "PROVIDER_GENERATED_BEFORE_DEADLINE"}
    if source == "sideline_quant_fixture_xp":
        payload = json.loads(data.decode("utf-8"))
        if int(payload.get("gameweek", -1)) != gameweek:
            raise ValueError("Sideline Quant payload gameweek mismatch")
        if not payload.get("generated_at") or not isinstance(payload.get("n_rows"), int):
            raise ValueError("Sideline Quant payload missing generation timestamp or row count")
        if not isinstance(payload.get("n_players"), int):
            raise ValueError("Sideline Quant payload missing player count")
        rows = payload.get("rows")
        if not isinstance(rows, list) or len(rows) != payload["n_rows"] or not rows:
            raise ValueError("Sideline Quant row payload does not match n_rows")
        if any("player_id" not in row or "fixture_id" not in row for row in rows):
            raise ValueError("Sideline Quant rows missing player_id or fixture_id")
        unique_ids([f'{row["player_id"]}:{row["fixture_id"]}' for row in rows],
                   "Sideline Quant player-fixture keys")
        player_ids = {str(row["player_id"]) for row in rows}
        if len(player_ids) != payload["n_players"]:
            raise ValueError("Sideline Quant n_players does not match row identities")
        parse_timestamp(payload["generated_at"], "Sideline Quant generated_at")
        return {"row_count": payload["n_rows"], "grain": "player_fixture",
                "generated_at": payload["generated_at"], "variant": "published_xP",
                "player_count": payload["n_players"], "timestamp_eligibility": "PENDING_DEADLINE_CROSSCHECK"}
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    rows = list(reader)
    if not fields or not rows:
        raise ValueError(f"{source}: CSV has no header or player rows")
    lowered = {x.strip().lower() for x in fields}
    if source == "fpl_rogue_accepted_xpts_csv":
        required = {"player_id", "next_gw_xpts", "gameweek", "captured_at", "model_version"}
        if not required.issubset(lowered):
            raise ValueError("FPLRogue CSV missing expected player, target-GW xPts or release metadata columns")
        if any(str(row.get("gameweek")) != str(gameweek) for row in rows):
            raise ValueError("FPLRogue CSV contains a different target gameweek")
        unique_ids([row.get("player_id") for row in rows], "FPLRogue")
        for row in rows:
            finite_number(row.get("next_gw_xpts"), "FPLRogue next_gw_xpts")
        captured_at_values = {str(row.get("captured_at", "")).strip() for row in rows}
        if len(captured_at_values) != 1 or not next(iter(captured_at_values)):
            raise ValueError("FPLRogue captured_at must be present and consistent across rows")
        captured_at = next(iter(captured_at_values))
        parse_timestamp(captured_at, "FPLRogue captured_at")
        versions = {str(row.get("model_version", "")).strip() for row in rows}
        if len(versions) != 1 or not next(iter(versions)):
            raise ValueError("FPLRogue model_version must be present and consistent across rows")
        return {"row_count": len(rows), "grain": "player_gameweek",
                "variant": "accepted_xpts_v1", "player_id_column": "player_id",
                "forecast_column": "next_gw_xpts", "provider_captured_at": captured_at,
                "model_version": next(iter(versions)), "columns": fields,
                "timestamp_eligibility": "PENDING_DEADLINE_CROSSCHECK"}
    if source == "fpl_lucho_served_xp_csv":
        player_column = "id"
        forecast_column = f"xp_gw{gameweek}"
        if player_column not in lowered or forecast_column not in lowered:
            raise ValueError("FPL Lucho CSV missing expected player ID or target-GW served-xP column")
        unique_ids([row.get(player_column) for row in rows], "FPL Lucho")
        for row in rows:
            finite_number(row.get(forecast_column), f"FPL Lucho {forecast_column}")
        return {"row_count": len(rows), "grain": "player_gameweek",
                "variant": "served_xP_not_assumed_Odds_xP",
                "player_id_column": player_column, "forecast_column": forecast_column,
                "timestamp_eligibility": "UNVERIFIED_PROVIDER_GENERATION_TIME_NOT_DISCLOSED",
                "columns": fields}
    raise ValueError("Unknown source: " + source)


def fetch(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "CTA-FPL-Research-Benchmark/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read()
        return data, response.headers.get("Content-Type", ""), response.geturl()


def capture(gameweek: int, out_dir: Path, fetcher=fetch):
    out_dir.mkdir(parents=True, exist_ok=True)
    specs = [
        ("fpl_cat_player_xp", "https://fplcat.com/api/v1/projections", "json"),
        ("sideline_quant_fixture_xp",
         f"https://sidelinequant.com/data/gw/{gameweek}/projections.json", "json"),
        ("fpl_rogue_accepted_xpts_csv",
         "https://www.fplrogue.com/research/projections.csv", "csv"),
        ("fpl_lucho_served_xp_csv",
         "https://fpllucho.pythonanywhere.com/export/predictions.csv", "csv"),
    ]
    captured_at = datetime.now(timezone.utc)
    manifest = {
        "schema_version": "1.1",
        "capture_status": "PASS_RAW_OUTPUTS_CAPTURED",
        "target_gameweek": gameweek,
        "captured_at_utc": captured_at.isoformat(),
        "comparison_status": "NOT_YET_EVALUATED",
        "sources": [],
    }
    for source, url, extension in specs:
        data, content_type, final_url = fetcher(url)
        details = validate_payload(source, data, gameweek, content_type)
        filename = f"{source}.{'json' if extension == 'json' else 'csv'}"
        (out_dir / filename).write_bytes(data)
        manifest["sources"].append({
            "source": source, "url": url, "final_url": final_url,
            "content_type": content_type, "raw_file": filename,
            "sha256": sha256(data), **details,
        })

    cat = next(s for s in manifest["sources"] if s["source"] == "fpl_cat_player_xp")
    deadline = parse_timestamp(cat["deadline_utc"], "official FPL Cat deadline")
    if captured_at >= deadline:
        raise ValueError("Collector capture occurred at or after the target deadline")
    for source in manifest["sources"]:
        provider_time = source.get("generated_at") or source.get("provider_captured_at")
        if provider_time:
            if parse_timestamp(provider_time, f'{source["source"]} provider timestamp') >= deadline:
                raise ValueError(f'{source["source"]}: provider timestamp is at or after the target deadline')
            source["timestamp_eligibility"] = "PROVIDER_TIMESTAMP_BEFORE_DEADLINE"
    (out_dir / "capture_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gameweek", type=int, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = capture(args.gameweek, args.out_dir)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
