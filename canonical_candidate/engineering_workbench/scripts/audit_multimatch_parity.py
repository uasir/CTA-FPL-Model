#!/usr/bin/env python3
"""Compare per-match Python and JavaScript CTA outputs for the supported v1.0.2 core."""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path

PLAYER_FEATURES = [
    "event_involvements", "passes", "completed_passes", "pressured_events",
    "box_entries", "final_third_entries", "progressive_actions",
    "action_xt_gain_sum", "action_xt_gain_n", "passes_received",
    "pressured_passes_received", "receipts", "carries", "sequences_involved",
    "shot_linked_sequences", "non_shot_candidate_sequences", "shots",
    "shot_xg_reference_only", "mean_action_xt_gain", "pressured_receipts",
]
SEQUENCE_FEATURES = [
    "sequence_id", "match_id", "period", "possession_id", "team",
    "event_count", "duration_seconds", "players", "passes", "completed_passes",
    "carries", "receipts", "pressured_events", "pressured_receipts",
    "box_entries", "final_third_entries", "progressive_actions", "shot_count",
    "shot_xg_reference_only", "mean_action_xt_gain",
    "positive_action_xt_gain_sum", "direction_available", "sequence_class",
]
TABLES = {
    "players": ("player_features.csv", "players.json", ["statsbomb_player_name"], PLAYER_FEATURES),
    "sequences": ("sequences.csv", "sequences.json", ["sequence_id"], SEQUENCE_FEATURES),
    "xt_grid": ("xt_grid.csv", "xt_grid.json", ["x_cell", "y_cell"], ["xT"]),
}
NUMERIC_TOLERANCE = {"rtol": 1e-7, "atol": 1.01e-6}

def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def nullish(value):
    return value is None or (isinstance(value, str) and value.strip().lower() in ("", "null", "none", "nan"))

def normalized_key(row, columns):
    return tuple(str(row.get(column, "")).strip() for column in columns)

def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None

def compare_table(py_rows, js_rows, key_columns, features):
    py_map = {}
    js_map = {}
    py_duplicates = []
    js_duplicates = []
    for rows, target, duplicates in ((py_rows, py_map, py_duplicates), (js_rows, js_map, js_duplicates)):
        for row in rows:
            key = normalized_key(row, key_columns)
            if key in target:
                duplicates.append(key)
            else:
                target[key] = row
    py_keys, js_keys = set(py_map), set(js_map)
    shared = py_keys & js_keys
    feature_report = {}
    mismatch_samples = []
    for feature in features:
        compared = 0
        exact = 0
        within = 0
        null_mismatches = 0
        max_error = 0.0
        for key in sorted(shared):
            a = py_map[key].get(feature)
            b = js_map[key].get(feature)
            na, nb = nullish(a), nullish(b)
            compared += 1
            if na or nb:
                if na and nb:
                    exact += 1
                    within += 1
                else:
                    null_mismatches += 1
                    if len(mismatch_samples) < 30:
                        mismatch_samples.append({"key": key, "feature": feature, "python": a, "javascript": b, "reason": "null_mismatch"})
                continue
            an, bn = number(a), number(b)
            if an is not None and bn is not None:
                error = abs(an - bn)
                max_error = max(max_error, error)
                if an == bn:
                    exact += 1
                if math.isclose(an, bn, rel_tol=NUMERIC_TOLERANCE["rtol"], abs_tol=NUMERIC_TOLERANCE["atol"]):
                    within += 1
                elif len(mismatch_samples) < 30:
                    mismatch_samples.append({"key": key, "feature": feature, "python": an, "javascript": bn, "abs_error": error, "reason": "numeric_out_of_tolerance"})
            elif str(a) == str(b):
                exact += 1
                within += 1
            elif len(mismatch_samples) < 30:
                mismatch_samples.append({"key": key, "feature": feature, "python": a, "javascript": b, "reason": "exact_mismatch"})
        feature_report[feature] = {
            "compared": compared,
            "exact_matches": exact,
            "within_tolerance": within,
            "null_mismatches": null_mismatches,
            "max_absolute_error": max_error,
            "pass": compared == len(shared) and within == compared and null_mismatches == 0,
        }
    structural_pass = (
        len(py_keys) == len(py_rows)
        and len(js_keys) == len(js_rows)
        and not py_duplicates
        and not js_duplicates
        and py_keys == js_keys
    )
    feature_pass = all(item["pass"] for item in feature_report.values())
    return {
        "status": "PASS" if structural_pass and feature_pass else "FAIL",
        "python_rows": len(py_rows),
        "javascript_rows": len(js_rows),
        "shared_rows": len(shared),
        "python_only_rows": len(py_keys - js_keys),
        "javascript_only_rows": len(js_keys - py_keys),
        "python_duplicate_keys": len(py_duplicates),
        "javascript_duplicate_keys": len(js_duplicates),
        "features_passed": sum(item["pass"] for item in feature_report.values()),
        "features_total": len(feature_report),
        "features": feature_report,
        "mismatch_samples": mismatch_samples,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-root", type=Path, required=True)
    parser.add_argument("--javascript-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-matches", type=int, default=34)
    args = parser.parse_args()
    matches = sorted(path.name for path in args.python_root.iterdir() if path.is_dir())
    report = {
        "scope": {
            "matches": len(matches),
            "expected_matches": args.expected_matches,
            "numeric_tolerance": NUMERIC_TOLERANCE,
            "note": "The 1.01e-6 absolute tolerance accommodates one-unit differences in six-decimal rounded StatsBomb xG sums; other comparisons are exact or tighter through relative tolerance.",
        },
        "matches": {},
    }
    for match_id in matches:
        py_dir = args.python_root / match_id
        js_dir = args.javascript_root / match_id
        tables = {}
        for table, (py_name, js_name, key_columns, features) in TABLES.items():
            tables[table] = compare_table(read_csv(py_dir / py_name), read_json(js_dir / js_name), key_columns, features)
        py_audit = read_json(py_dir / "audit.json")
        js_diag = read_json(js_dir / "input_diagnostics.json")
        py_360 = py_audit.get("statsbomb_360_audit", {})
        js_360 = js_diag.get("statsbomb_360_audit", {})
        frame_fields = [
            "frames", "frames_with_event_uuid", "unique_event_uuids",
            "duplicate_frame_event_uuids", "matched_frame_uuids",
            "unmatched_frame_uuids", "frame_to_event_join_rate",
            "event_coverage_with_frame",
        ]
        frame_diffs = {
            field: {"python": py_360.get(field), "javascript": js_360.get(field)}
            for field in frame_fields if py_360.get(field) != js_360.get(field)
        }
        summaries = {
            "python": {
                "events": py_audit.get("events_processed"),
                "sequences": py_audit.get("sequences_processed"),
                "players": py_audit.get("players_observed"),
                "xt_grid_cells": sum(1 for _ in read_csv(py_dir / "xt_grid.csv")),
            },
            "javascript": {
                "events": read_json(js_dir / "javascript_run_manifest.json")["core_summary"]["events_processed"],
                "sequences": len(read_json(js_dir / "sequences.json")),
                "players": len(read_json(js_dir / "players.json")),
                "xt_grid_cells": len(read_json(js_dir / "xt_grid.json")),
            },
        }
        summary_pass = summaries["python"] == summaries["javascript"]
        frame_pass = not frame_diffs
        table_pass = all(value["status"] == "PASS" for value in tables.values())
        report["matches"][match_id] = {
            "status": "PASS" if summary_pass and frame_pass and table_pass else "FAIL",
            "summary_counts": summaries,
            "summary_counts_pass": summary_pass,
            "frame_linkage_pass": frame_pass,
            "frame_linkage_differences": frame_diffs,
            "tables": tables,
        }
    match_passes = sum(item["status"] == "PASS" for item in report["matches"].values())
    report["summary"] = {
        "status": "PASS" if len(matches) == args.expected_matches and match_passes == len(matches) else "FAIL",
        "matches_passed": match_passes,
        "matches_total": len(matches),
        "matches_expected": args.expected_matches,
        "table_rows_compared": {
            table: sum(item["tables"][table]["shared_rows"] for item in report["matches"].values())
            for table in TABLES
        },
        "feature_checks_passed": {
            table: sum(sum(feature["compared"] for feature in item["tables"][table]["features"].values()) for item in report["matches"].values())
            for table in TABLES
        },
        "feature_checks_within_tolerance": {
            table: sum(sum(feature["within_tolerance"] for feature in item["tables"][table]["features"].values()) for item in report["matches"].values())
            for table in TABLES
        },
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "multimatch_parity_report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    lines = [
        "# CTA multi-match Python–JavaScript parity",
        "",
        "**Overall status: " + report["summary"]["status"] + "**",
        "",
        "| Metric | Result |",
        "|---|---:|",
        "| Matches passed | " + str(match_passes) + "/" + str(len(matches)) + " |",
    ]
    for table, count in report["summary"]["table_rows_compared"].items():
        lines.append("| " + table + " rows compared | " + str(count) + " |")
    for match_id, item in report["matches"].items():
        lines.extend(["", "## Match " + match_id + ": " + item["status"], ""])
        for table, result in item["tables"].items():
            lines.append("- " + table + ": " + result["status"] + " (" + str(result["shared_rows"]) + " rows; " + str(result["features_passed"]) + "/" + str(result["features_total"]) + " features)")
        lines.append("- 360 frame linkage: " + ("PASS" if item["frame_linkage_pass"] else "FAIL"))
        if item["frame_linkage_differences"]:
            lines.append("  - Differences: " + json.dumps(item["frame_linkage_differences"], sort_keys=True))
    (args.out / "multimatch_parity_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    raise SystemExit(0 if report["summary"]["status"] == "PASS" else 2)

if __name__ == "__main__":
    main()
