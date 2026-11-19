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
    if source == "sideline_quant_fixture_xp":
        payload = json.loads(data.decode("utf-8"))
        if int(payload.get("gameweek", -1)) != gameweek:
            raise ValueError("Sideline Quant payload gameweek mismatch")
        if not payload.get("generated_at") or not isinstance(payload.get("n_rows"), int):
            raise ValueError("Sideline Quant payload missing generation timestamp or row count")
        if payload.get("n_players") != payload.get("n_rows"):
            raise ValueError("Unexpected Sideline Quant player/row counts; inspect fixture-grain structure")
        return {"row_count": payload["n_rows"], "grain": "player_fixture",
                "generated_at": payload["generated_at"], "variant": "published_xP"}
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    rows = list(reader)
    if not fields or not rows:
        raise ValueError(f"{source}: CSV has no header or player rows")
    if source == "fpl_rogue_accepted_xpts_csv":
        return {"row_count": len(rows), "grain": "verify_from_csv_columns",
                "variant": "accepted_xpts_v1", "columns": fields}
    if source == "fpl_lucho_served_xp_csv":
        return {"row_count": len(rows), "grain": "provider_export_rows",
                "variant": "served_xP_not_assumed_Odds_xP", "columns": fields}
    raise ValueError("Unknown source: " + source)


def fetch(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "CTA-FPL-Research-Benchmark/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read()
        return data, response.headers.get("Content-Type", ""), response.geturl()


def capture(gameweek: int, out_dir: Path, fetcher=fetch):
    out_dir.mkdir(parents=True, exist_ok=True)
    specs = [
        ("sideline_quant_fixture_xp",
         f"https://sidelinequant.com/data/gw/{gameweek}/projections.json", "json"),
        ("fpl_rogue_accepted_xpts_csv",
         "https://www.fplrogue.com/research/projections.csv", "csv"),
        ("fpl_lucho_served_xp_csv",
         "https://fpllucho.pythonanywhere.com/export/predictions.csv", "csv"),
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
