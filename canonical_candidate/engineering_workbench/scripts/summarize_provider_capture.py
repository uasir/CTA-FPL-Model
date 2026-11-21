#!/usr/bin/env python3
"""Create a metadata-only summary safe for a public GitHub Actions artifact.

Never include provider forecast rows, raw response bytes, FPL bootstrap data,
or Wildcard payloads. Restricted/private providers must not use this uploader.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


class SummaryError(ValueError):
    pass


def summarize_capture(provider: str, capture: Mapping[str, Any],
                      normalized: Mapping[str, Any] | None = None) -> dict[str, Any]:
    name = provider.strip().casefold()
    if name == "fpl wildcard":
        raise SummaryError("FPL Wildcard data must never be placed in public workflow artifacts")

    if name == "fpl cat":
        snap = capture.get("provider_snapshot", {})
        timing = snap.get("timing", {})
        source = snap.get("source", {})
        records = snap.get("records", [])
        summary = {
            "provider": "FPL Cat",
            "snapshot_id": snap.get("snapshot_id"),
            "target_gameweek": snap.get("target_gameweek"),
            "provider_row_count": len(records),
            "generated_at_utc": timing.get("generated_at_utc"),
            "captured_at_utc": timing.get("captured_at_utc"),
            "deadline_utc": timing.get("deadline_utc"),
            "provider_raw_sha256": source.get("raw_sha256"),
            "generation_time_status": capture.get("capture_status", {}).get(
                "provider_generation_time_status"
            ),
        }
    elif name == "sideline quant":
        timing = capture.get("timing", {})
        source = capture.get("source", {})
        coverage = capture.get("coverage", {})
        canonical = (normalized or {}).get("canonical_snapshot", {})
        summary = {
            "provider": "Sideline Quant",
            "snapshot_id": capture.get("capture_id"),
            "target_gameweek": capture.get("target_gameweek"),
            "provider_row_count": coverage.get("declared_row_count"),
            "provider_player_count": coverage.get("declared_player_count"),
            "generated_at_utc": timing.get("generated_at_utc"),
            "captured_at_utc": timing.get("captured_at_utc"),
            "deadline_utc": timing.get("deadline_utc"),
            "provider_raw_sha256": source.get("raw_sha256"),
            "normalized_fixture_row_count": canonical.get("coverage", {}).get("row_count"),
            "decision_eligible": canonical.get("decision_eligible"),
        }
    elif name == "fplrogue":
        timing = capture.get("timing", {})
        source = capture.get("source", {})
        schema = capture.get("schema_inspection", {})
        summary = {
            "provider": "FPLRogue",
            "snapshot_id": capture.get("capture_id"),
            "target_gameweek": capture.get("target_gameweek"),
            "provider_row_count": schema.get("csv_row_count"),
            "csv_headers": schema.get("csv_headers"),
            "release_updated_at_utc": timing.get("provider_release_at_utc"),
            "model_trained_at_utc": timing.get("model_trained_at_utc"),
            "captured_at_utc": timing.get("csv_captured_at_utc"),
            "deadline_utc": timing.get("deadline_utc"),
            "provider_csv_sha256": source.get("csv_raw_sha256"),
            "generated_at_utc": timing.get("generated_at_utc"),
        }
    else:
        raise SummaryError(f"unsupported public summary provider: {provider}")

    # Defensive allow-list: summary must contain only metadata, never records/raw archives.
    forbidden = {"records", "rows", "raw_archives", "csv_base64",
                 "provider_response_base64", "official_fpl_bootstrap_base64"}
    if forbidden.intersection(summary):
        raise SummaryError("summary contains a forbidden payload field")
    return {key: value for key, value in summary.items() if value is not None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--normalized", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    capture = json.loads(args.input.read_text(encoding="utf-8"))
    normalized = (
        json.loads(args.normalized.read_text(encoding="utf-8"))
        if args.normalized else None
    )
    summary = summarize_capture(args.provider, capture, normalized)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
