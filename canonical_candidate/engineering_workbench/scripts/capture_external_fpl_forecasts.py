#!/usr/bin/env python3
"""Freeze the actual public player-level FPL forecast outputs without reinterpretation.

Raw source bytes are retained unchanged. CSV variants are labelled by the page
that exposes them; this collector never infers hidden model variants.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_payload(source: str, data: bytes, gameweek: int, content_type: str) -> dict:
    if not data:
        raise ValueError(f"{source}: empty response")
    if "text/html" in content_type.lower():
        raise ValueError(f"{source}: received HTML instead of forecast data")
    if source == "fpl_cat_player_xp":
        payload = json.loads(data.decode("utf-8"))
        if int(payload.get("gameweek", -1)) != gameweek:
            raise ValueError("FPL Cat payload gameweek mismatch")
        if not payload.get("computed_at") or not isinstance(payload.get("players"), list):
            raise ValueError("FPL Cat payload missing computed_at or players")
        players = payload["players"]
        if not players or any("id" not in row or "xp" not in row for row in players):
            raise ValueError("FPL Cat payload missing player IDs or xp values")
        return {"row_count": len(players), "grain": "player_gameweek",
                "generated_at": payload["computed_at"], "variant": "published_xP",
                "player_id_column": "id", "forecast_column": "xp"}
    if source == "sideline_quant_fixture_xp":
        payload = json.loads(data.decode("utf-8"))
        if int(payload.get("gameweek", -1)) != gameweek:
            raise ValueError("Sideline Quant payload gameweek mismatch")
        if not payload.get("generated_at") or not isinstance(payload.get("n_rows"), int):
            raise ValueError("Sideline Quant payload missing generation timestamp or row count")
        if not isinstance(payload.get("n_players"), int):
            raise ValueError("Sideline Quant payload missing player count")
        return {"row_count": payload["n_rows"], "grain": "player_fixture",
                "generated_at": payload["generated_at"], "variant": "published_xP"}
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
            raise ValueError("FPLRogue CSV missing expected player, GW11 xPts or release metadata columns")
        if any(str(row.get("gameweek")) != str(gameweek) for row in rows):
            raise ValueError("FPLRogue CSV contains a different target gameweek")
        return {"row_count": len(rows), "grain": "player_gameweek",
                "variant": "accepted_xpts_v1", "player_id_column": "player_id",
                "forecast_column": "next_gw_xpts", "columns": fields}
    if source == "fpl_wildcard_public_xpts_csv":
        required = {"gameweek", "player", "profile_url", "xpts"}
        if not required.issubset(lowered):
            raise ValueError("FPL Wildcard CSV missing documented player/GW/xPts fields")
        if any(str(row.get("gameweek")) != str(gameweek) for row in rows):
            raise ValueError("FPL Wildcard CSV contains a different target gameweek")
        return {"row_count": len(rows), "grain": "player_gameweek",
                "variant": "published_xpts_v11_or_current",
                "player_key_column": "profile_url", "forecast_column": "xpts",
                "columns": fields, "redistribution_status": "NOT_LICENSED_INTERNAL_RESEARCH_ONLY"}
    if source == "fpl_lucho_served_xp_csv":
        player_column = "id"
        forecast_column = f"xp_gw{gameweek}"
        if player_column not in lowered or forecast_column not in lowered:
            raise ValueError("FPL Lucho CSV missing expected player ID or target-GW served-xP column")
        return {"row_count": len(rows), "grain": "player_gameweek",
                "variant": "served_xP_not_assumed_Odds_xP",
                "player_id_column": player_column, "forecast_column": forecast_column,
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
        ("fpl_wildcard_public_xpts_csv",
         "https://fplwildcard.com/data/projections/current.csv", "csv"),
    ]
    manifest = {
        "schema_version": "1.0",
        "capture_status": "PASS_RAW_OUTPUTS_CAPTURED",
        "target_gameweek": gameweek,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
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
