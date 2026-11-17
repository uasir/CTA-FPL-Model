#!/usr/bin/env python3
"""Profile the 34-match run for data integrity and FPL-readiness blockers."""
from __future__ import annotations
import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))

def finite_number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-root", type=Path, required=True)
    parser.add_argument("--javascript-root", type=Path, required=True)
    parser.add_argument("--parity-report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-matches", type=int, default=34)
    args = parser.parse_args()

    parity = read_json(args.parity_report)
    match_ids = sorted(path.name for path in args.python_root.iterdir() if path.is_dir())
    report = {
        "scope": {
            "expected_matches": args.expected_matches,
            "matches_found": len(match_ids),
            "source": "StatsBomb Open Data pinned by the multi-match workflow",
        },
        "per_match": {},
        "summary": {},
    }

    totals = Counter()
    fpl_name_rows = 0
    fpl_name_populated = 0
    minutes_positive = 0
    per90_populated = 0
    xt_values = []
    xt_bad = []
    missing_360 = []
    zero_join_360 = []
    partial_join_360 = []
    usable_360 = []
    event_hashes = 0
    frame_hashes = 0
    direction_explicit = 0
    direction_generated = 0
    xt_statuses = Counter()
    model_validation_statuses = Counter()

    for match_id in match_ids:
        py_dir = args.python_root / match_id
        js_dir = args.javascript_root / match_id
        audit = read_json(py_dir / "audit.json")
        manifest = read_json(js_dir / "javascript_run_manifest.json")
        diagnostics = read_json(js_dir / "input_diagnostics.json")
        players = read_csv(py_dir / "player_features.csv")
        sequences = read_csv(py_dir / "sequences.csv")
        grid = read_csv(py_dir / "xt_grid.csv")

        events = int(audit.get("events_processed", 0))
        sequence_count = int(audit.get("sequences_processed", 0))
        player_count = int(audit.get("players_observed", 0))
        totals["events"] += events
        totals["sequences"] += sequence_count
        totals["players"] += len(players)
        totals["xt_grid_cells"] += len(grid)
        totals["matches"] += 1

        for row in players:
            fpl_name_rows += 1
            fpl_name_populated += bool(row.get("fpl_player_name", "").strip())
            minutes = finite_number(row.get("minutes"))
            minutes_positive += minutes is not None and minutes > 0
            per90_populated += bool(row.get("sequences_involved_per90", "").strip())

        for row in grid:
            value = finite_number(row.get("xT"))
            if value is None:
                xt_bad.append({"match_id": match_id, "row": row})
            else:
                xt_values.append(value)
                if value < 0 or value > 1:
                    xt_bad.append({"match_id": match_id, "row": row, "reason": "outside_0_1"})

        frame = audit.get("statsbomb_360_audit", {})
        frame_count = int(frame.get("frames", 0) or 0)
        join_rate = frame.get("frame_to_event_join_rate")
        event_coverage = frame.get("event_coverage_with_frame")
        if frame_count == 0:
            missing_360.append(match_id)
        elif join_rate == 0:
            zero_join_360.append(match_id)
        elif join_rate is not None and float(join_rate) < 0.95:
            partial_join_360.append(match_id)
        else:
            usable_360.append(match_id)

        input_files = manifest.get("input_files", {})
        event_hashes += bool(input_files.get("events", {}).get("sha256"))
        frame_hashes += frame_count > 0 and bool(input_files.get("three_sixty", {}).get("sha256"))
        direction = manifest.get("direction", {})
        direction_explicit += int(direction.get("explicit_direction_keys", 0) or 0)
        direction_generated += int(direction.get("generated_direction_keys", 0) or 0)
        xt_statuses[audit.get("xt", {}).get("xt_status", "unknown")] += 1
        model_validation_statuses[audit.get("validation_status", "unknown")] += 1

        report["per_match"][match_id] = {
            "events": events,
            "sequences": sequence_count,
            "players": player_count,
            "player_rows": len(players),
            "xt_grid_cells": len(grid),
            "360_frames": frame_count,
            "360_join_rate": join_rate,
            "360_event_coverage": event_coverage,
            "fpl_names_populated": sum(bool(row.get("fpl_player_name", "").strip()) for row in players),
            "players_with_positive_minutes": sum(
                (finite_number(row.get("minutes")) or 0) > 0 for row in players
            ),
            "event_sha256_present": bool(input_files.get("events", {}).get("sha256")),
            "three_sixty_sha256_present": frame_count > 0 and bool(input_files.get("three_sixty", {}).get("sha256")),
        }

    structural_issues = []
    if len(match_ids) != args.expected_matches:
        structural_issues.append(f"Expected {args.expected_matches} matches; found {len(match_ids)}")
    if parity.get("summary", {}).get("status") != "PASS":
        structural_issues.append("Python–JavaScript parity report is not PASS")
    for match_id, item in report["per_match"].items():
        if item["events"] <= 0 or item["sequences"] <= 0 or item["players"] <= 0:
            structural_issues.append(f"{match_id}: empty core output")
        if item["player_rows"] != item["players"]:
            structural_issues.append(f"{match_id}: player row count differs from audit count")
        if item["xt_grid_cells"] != 192:
            structural_issues.append(f"{match_id}: expected 192 xT cells, found {item['xt_grid_cells']}")
        if not item["event_sha256_present"]:
            structural_issues.append(f"{match_id}: missing event input SHA-256")
    if xt_bad:
        structural_issues.append(f"{len(xt_bad)} xT values are non-finite or outside [0,1]")

    report["summary"] = {
        "status": "PASS" if not structural_issues else "FAIL",
        "structural_issues": structural_issues,
        "matches": len(match_ids),
        "events": totals["events"],
        "sequences": totals["sequences"],
        "player_rows": totals["players"],
        "xt_grid_cells": totals["xt_grid_cells"],
        "xT_value_min": min(xt_values) if xt_values else None,
        "xT_value_max": max(xt_values) if xt_values else None,
        "xT_nonfinite_or_out_of_range": len(xt_bad),
        "fpl_name_coverage": {
            "populated": fpl_name_populated,
            "total": fpl_name_rows,
            "rate": fpl_name_populated / fpl_name_rows if fpl_name_rows else 0,
        },
        "trusted_minutes_coverage": {
            "positive_minutes": minutes_positive,
            "total": fpl_name_rows,
            "rate": minutes_positive / fpl_name_rows if fpl_name_rows else 0,
        },
        "per90_rows_populated": per90_populated,
        "360": {
            "matches_with_usable_join": len(usable_360),
            "matches_without_source": len(missing_360),
            "matches_with_zero_join": len(zero_join_360),
            "matches_with_partial_join": len(partial_join_360),
            "usable_match_ids": usable_360,
            "missing_source_match_ids": missing_360,
            "zero_join_match_ids": zero_join_360,
            "partial_join_match_ids": partial_join_360,
        },
        "input_provenance": {
            "event_hashes_present": event_hashes,
            "three_sixty_hashes_present": frame_hashes,
        },
        "direction": {
            "explicit_direction_keys": direction_explicit,
            "generated_direction_keys": direction_generated,
        },
        "xt_fit_statuses": dict(xt_statuses),
        "model_validation_statuses": dict(model_validation_statuses),
        "fpl_readiness": "BLOCKED" if (
            fpl_name_populated != fpl_name_rows
            or minutes_positive != fpl_name_rows
            or model_validation_statuses.get("not validated for FPL prediction", 0) > 0
        ) else "REQUIRES_BACKTEST",
        "warnings": [
            "A match with 360 frames but zero event-UUID joins must be investigated before using its 360 data.",
            "Matches without a 360 source are not evidence of zero defensive pressure or zero visible-player coverage.",
            "FPL names and trusted minutes are required before per-90 metrics or FPL player-level modelling.",
            "An exploratory xT fit is not a calibrated xT model or a validated FPL points predictor.",
        ],
    }

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "multimatch_data_quality.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    lines = [
        "# CTA multi-match data quality and FPL readiness",
        "",
        "**Structural status: " + report["summary"]["status"] + "**",
        "**FPL readiness: " + report["summary"]["fpl_readiness"] + "**",
        "",
        "| Measure | Result |",
        "|---|---:|",
        "| Matches | " + str(len(match_ids)) + " |",
        "| Events | " + str(totals["events"]) + " |",
        "| Sequences | " + str(totals["sequences"]) + " |",
        "| Player rows | " + str(totals["players"]) + " |",
        "| xT cells | " + str(totals["xt_grid_cells"]) + " |",
        "| xT range | " + str(report["summary"]["xT_value_min"]) + " to " + str(report["summary"]["xT_value_max"]) + " |",
        "| FPL names populated | " + str(fpl_name_populated) + "/" + str(fpl_name_rows) + " |",
        "| Players with positive minutes | " + str(minutes_positive) + "/" + str(fpl_name_rows) + " |",
        "| Per-90 rows populated | " + str(per90_populated) + " |",
        "| 360 usable joins | " + str(len(usable_360)) + " |",
        "| 360 missing source | " + str(len(missing_360)) + " |",
        "| 360 zero-join matches | " + str(len(zero_join_360)) + " |",
        "",
        "## Blockers and warnings",
        "",
    ]
    lines.extend("- " + warning for warning in report["summary"]["warnings"])
    lines.extend(["", "## 360 exceptions", ""])
    lines.extend("- Missing 360 source: " + (", ".join(missing_360) or "none"))
    lines.extend("- Zero event-UUID join: " + (", ".join(zero_join_360) or "none"))
    lines.extend(["", "## Structural issues", ""])
    lines.extend("- " + issue for issue in structural_issues) if structural_issues else lines.append("- None")
    (args.out / "multimatch_data_quality.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    raise SystemExit(0 if not structural_issues else 2)

if __name__ == "__main__":
    main()
