#!/usr/bin/env python3
"""Run the registered v1.0.2 Python–JavaScript parity contract over each match."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

WORKBENCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKBENCH / "src"))
from cta_audit.audit import audit, load_registry, load_rows

TABLES = ("sequences", "players", "xt_grid")
FRAME_FIELDS = (
    "frames", "frames_with_event_uuid", "unique_event_uuids",
    "duplicate_frame_event_uuids", "matched_frame_uuids",
    "unmatched_frame_uuids", "frame_to_event_join_rate",
    "event_coverage_with_frame",
)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-root", type=Path, required=True)
    parser.add_argument("--javascript-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-matches", type=int, default=34)
    args = parser.parse_args()

    contract_path = WORKBENCH / "config" / "cta_core_parity_contract.json"
    registries = {table: load_registry(contract_path, table) for table in TABLES}
    match_ids = sorted(path.name for path in args.python_root.iterdir() if path.is_dir())
    report = {
        "contract": str(contract_path.relative_to(WORKBENCH)),
        "contract_version": json.loads(contract_path.read_text(encoding="utf-8"))["contract_version"],
        "scope": {
            "expected_matches": args.expected_matches,
            "matches_found": len(match_ids),
            "player_grain": "one player per isolated single-match run",
        },
        "matches": {},
    }

    for match_id in match_ids:
        py_dir = args.python_root / match_id
        js_dir = args.javascript_root / match_id
        table_results = {}
        for table in TABLES:
            py_name = {"sequences": "sequences.csv", "players": "player_features.csv", "xt_grid": "xt_grid.csv"}[table]
            js_name = {"sequences": "sequences.json", "players": "players.json", "xt_grid": "xt_grid.json"}[table]
            py_rows = load_rows(py_dir / py_name)
            js_rows = load_rows(js_dir / js_name)
            table_results[table] = audit(py_rows, js_rows, registries[table])

        py_audit = json.loads((py_dir / "audit.json").read_text(encoding="utf-8"))
        js_diag = json.loads((js_dir / "input_diagnostics.json").read_text(encoding="utf-8"))
        py_360 = py_audit.get("statsbomb_360_audit", {})
        js_360 = js_diag.get("statsbomb_360_audit", {})
        frame_diffs = {
            field: {"python": py_360.get(field), "javascript": js_360.get(field)}
            for field in FRAME_FIELDS
            if py_360.get(field) != js_360.get(field)
        }
        js_manifest = json.loads((js_dir / "javascript_run_manifest.json").read_text(encoding="utf-8"))
        py_summary = {
            "events": py_audit.get("events_processed"),
            "sequences": py_audit.get("sequences_processed"),
            "players": py_audit.get("players_observed"),
            "xt_grid_cells": len(load_rows(py_dir / "xt_grid.csv")),
        }
        js_summary = {
            "events": js_manifest["core_summary"]["events_processed"],
            "sequences": js_manifest["core_summary"]["sequences_processed"],
            "players": js_manifest["core_summary"]["players_observed"],
            "xt_grid_cells": js_manifest["core_summary"]["xt_grid_cells"],
        }
        summary_pass = py_summary == js_summary
        frame_pass = not frame_diffs
        table_pass = all(result["summary"]["status"] == "PASS" for result in table_results.values())
        report["matches"][match_id] = {
            "status": "PASS" if summary_pass and frame_pass and table_pass else "FAIL",
            "python_summary": py_summary,
            "javascript_summary": js_summary,
            "summary_counts_pass": summary_pass,
            "frame_linkage_pass": frame_pass,
            "frame_linkage_differences": frame_diffs,
            "tables": table_results,
        }

    matches_passed = sum(result["status"] == "PASS" for result in report["matches"].values())
    feature_comparisons = {}
    within_tolerance = {}
    exact_matches = {}
    for table in TABLES:
        feature_comparisons[table] = sum(
            feature["compared"]
            for match in report["matches"].values()
            for feature in match["tables"][table]["features"].values()
        )
        within_tolerance[table] = sum(
            feature["within_tolerance"]
            for match in report["matches"].values()
            for feature in match["tables"][table]["features"].values()
        )
        exact_matches[table] = sum(
            feature["exact_matches"]
            for match in report["matches"].values()
            for feature in match["tables"][table]["features"].values()
        )
    overall_pass = len(match_ids) == args.expected_matches and matches_passed == len(match_ids)
    report["summary"] = {
        "status": "PASS" if overall_pass else "FAIL",
        "matches_passed": matches_passed,
        "matches_total": len(match_ids),
        "matches_expected": args.expected_matches,
        "feature_comparisons": feature_comparisons,
        "within_tolerance": within_tolerance,
        "exact_matches": exact_matches,
    }

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "multimatch_parity_report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    lines = [
        "# CTA multi-match Python–JavaScript parity",
        "",
        "**Overall status: " + report["summary"]["status"] + "**",
        "",
        "Contract version: " + str(report["contract_version"]),
        "",
        "| Metric | Result |",
        "|---|---:|",
        "| Matches passed | " + str(matches_passed) + "/" + str(len(match_ids)) + " |",
    ]
    for table in TABLES:
        lines.append("| " + table + " feature comparisons | " + str(feature_comparisons[table]) + " |")
        lines.append("| " + table + " within tolerance | " + str(within_tolerance[table]) + " |")
    for match_id, result in report["matches"].items():
        lines.extend(["", "## Match " + match_id + ": " + result["status"], ""])
        for table in TABLES:
            summary = result["tables"][table]["summary"]
            lines.append(
                "- " + table + ": " + summary["status"] + " ("
                + str(summary["python_rows"]) + " rows; "
                + str(summary["features_passed"]) + "/" + str(summary["features_total"])
                + " registered features)"
            )
        lines.append("- 360 frame linkage: " + ("PASS" if result["frame_linkage_pass"] else "FAIL"))
        if result["frame_linkage_differences"]:
            lines.append("  - " + json.dumps(result["frame_linkage_differences"], sort_keys=True))
    (args.out / "multimatch_parity_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    raise SystemExit(0 if overall_pass else 2)

if __name__ == "__main__":
    main()
