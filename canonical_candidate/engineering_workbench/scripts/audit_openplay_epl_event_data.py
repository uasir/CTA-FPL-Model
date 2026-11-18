#!/usr/bin/env python3
"""Audit a pinned Openplay EPL event-data season using its checksum-verified package."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def _plain(value):
    if value is None:
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    try:
        import pandas as pd
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _frame_summary(frame):
    return {
        "rows": int(len(frame)),
        "columns": [str(column) for column in frame.columns],
    }


def audit_openplay(comp="eng", season="2024/25"):
    import openplay as op
    import pyarrow.parquet as pq
    from openplay import _data

    normalized_season = op.normalize_season(season)
    event_filename = "events_" + str(comp) + "_" + normalized_season + ".parquet"
    event_path = _data.fetch(event_filename)
    checksums = _data.checksums()
    parquet = pq.ParquetFile(event_path)
    event_columns = list(parquet.schema.names)

    candidates = [
        "match_id", "player_id", "team_id", "type", "event_type", "subtype",
        "x", "y", "end_x", "end_y", "minute", "second", "period",
        "possession_id", "outcome", "xg", "xa",
    ]
    selected = [column for column in candidates if column in event_columns]
    type_column = "type" if "type" in event_columns else (
        "event_type" if "event_type" in event_columns else None
    )

    event_types = Counter()
    unique_players = set()
    unique_matches = set()
    rows_scanned = 0
    for batch in parquet.iter_batches(columns=selected, batch_size=65536):
        rows_scanned += batch.num_rows
        if type_column:
            event_types.update(str(value) for value in batch.column(type_column).to_pylist() if value is not None)
        if "player_id" in selected:
            unique_players.update(value for value in batch.column("player_id").to_pylist() if value is not None)
        if "match_id" in selected:
            unique_matches.update(value for value in batch.column("match_id").to_pylist() if value is not None)

    matches = op.matches(comp, season)
    player_match = op.player_match_stats(comp, season)
    shots = op.shots(comp, season)
    lineups = op.lineups(comp, season)
    coverage = op.coverage_report(comp, season, warn=False)
    gaps = op.known_gaps(comp, season)
    issues = op.data_issues(comp, season)

    shot_xg_column = "xg" if "xg" in shots.columns else (
        "expected_goals" if "expected_goals" in shots.columns else None
    )
    shot_xg_values = shots[shot_xg_column].dropna() if shot_xg_column else []
    starter_column = "is_starter" if "is_starter" in lineups.columns else None

    report = {
        "provider": "openplay",
        "data_repository": str(op.DATA_REPO),
        "data_release": str(op.DATA_TAG),
        "package_version": str(op.__version__),
        "competition_code": str(comp),
        "season": str(season),
        "license": "CC BY 4.0",
        "attribution": "openplay (Noah Bair)",
        "event_file": event_filename,
        "event_file_sha256": checksums.get(event_filename, {}).get("sha256"),
        "event_rows_metadata": int(parquet.metadata.num_rows),
        "event_rows_scanned": int(rows_scanned),
        "event_columns": event_columns,
        "event_type_column": type_column,
        "event_type_counts": dict(event_types.most_common(40)),
        "unique_event_players": len(unique_players),
        "unique_event_matches": len(unique_matches),
        "event_context_columns_present": {
            key: key in event_columns for key in (
                "player_id", "team_id", "type", "x", "y", "end_x", "end_y",
                "minute", "second", "period", "possession_id", "outcome"
            )
        },
        "matches": _frame_summary(matches),
        "player_match_statistics": _frame_summary(player_match),
        "player_match_statistics_columns": [str(c) for c in player_match.columns],
        "shots": _frame_summary(shots),
        "shot_columns": [str(c) for c in shots.columns],
        "shot_xg_column": shot_xg_column,
        "shots_with_xg": int(len(shot_xg_values)),
        "shot_xg_sum": round(float(shot_xg_values.sum()), 6) if shot_xg_column else None,
        "lineups": _frame_summary(lineups),
        "lineup_starters": (
            int(lineups[starter_column].fillna(False).astype(bool).sum())
            if starter_column else None
        ),
        "coverage": [
            {str(k): _plain(v) for k, v in row.items()}
            for row in coverage.to_dict(orient="records")
        ],
        "known_gaps": int(len(gaps)),
        "known_data_issues": int(len(issues)),
        "status": "PASS_STRUCTURAL_ONLY",
        "prediction_validation": "NOT_EVALUATED",
        "identity_mapping": "NOT_ATTEMPTED",
        "limitations": [
            "Openplay v0.1.0 is a preview release; preserve its published checksum and known-gap/data-issue reports.",
            "This audit covers one historical EPL season and does not create a current-season feed.",
            "Player IDs are provider-specific and are not FPL element IDs; a season-scoped verified crosswalk is required.",
            "Event locations support on-ball action features but do not provide continuous off-ball tracking or StatsBomb 360 freeze frames.",
            "No raw event rows, player names or player-level outputs are uploaded.",
        ],
    }
    return report


def main():
    parser = argparse.ArgumentParser(description="Audit one Openplay EPL event-data season")
    parser.add_argument("--competition", default="eng")
    parser.add_argument("--season", default="2024/25")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    report = audit_openplay(args.competition, args.season)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    output = args.out_dir / "openplay_epl_event_data_audit.json"
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({
        "provider": report["provider"],
        "release": report["data_release"],
        "season": report["season"],
        "event_rows": report["event_rows_metadata"],
        "event_types": report["event_type_counts"],
        "matches": report["matches"]["rows"],
        "player_match_rows": report["player_match_statistics"]["rows"],
        "shots": report["shots"]["rows"],
        "shots_with_xg": report["shots_with_xg"],
        "coverage": report["coverage"],
        "known_gaps": report["known_gaps"],
        "known_data_issues": report["known_data_issues"],
        "status": report["status"],
        "prediction_validation": report["prediction_validation"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
