#!/usr/bin/env python3
"""Require exact Python/JavaScript parity for the live-pool personal-squad result."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def first_difference(left, right, path="$"):
    if isinstance(left, bool) or isinstance(right, bool):
        if type(left) is not type(right) or left != right:
            return {"path": path, "python_value": left, "javascript_value": right}
        return None
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        if left != right:
            return {"path": path, "python_value": left, "javascript_value": right}
        return None
    if type(left) is not type(right):
        return {
            "path": path,
            "python_type": type(left).__name__,
            "javascript_type": type(right).__name__,
        }
    if isinstance(left, dict):
        if set(left) != set(right):
            return {"path": path, "python_keys": sorted(left), "javascript_keys": sorted(right)}
        for key in sorted(left):
            difference = first_difference(left[key], right[key], f"{path}.{key}")
            if difference:
                return difference
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return {"path": path, "python_length": len(left), "javascript_length": len(right)}
        for index, (python_value, javascript_value) in enumerate(zip(left, right)):
            difference = first_difference(python_value, javascript_value, f"{path}[{index}]")
            if difference:
                return difference
        return None
    if left != right:
        return {"path": path, "python_value": left, "javascript_value": right}
    return None


def compare(python_result, javascript_result):
    difference = first_difference(python_result, javascript_result)
    if difference:
        return {"status": "FAIL_PERSONAL_SQUAD_PYTHON_JAVASCRIPT_PARITY", "first_difference": difference}
    return {
        "status": "PASS_PERSONAL_SQUAD_PYTHON_JAVASCRIPT_PARITY",
        "forecast_snapshot_id": python_result["forecast_snapshot_id"],
        "system": "personal_squad",
        "recommendation_status": python_result["recommendation_status"],
        "starting_xi_count": len(python_result["squad_plan"]["starting_xi"]),
        "transfer_candidate_count": python_result["transfer_recommendation"]["candidate_count"],
        "covar_used": python_result["portfolio_risk"]["covar_used"],
        "scope": "synthetic 15-player roster evaluated against the full supplied forecast pool",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--javascript", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    python_result = json.loads(args.python.read_text(encoding="utf-8"))
    javascript_result = json.loads(args.javascript.read_text(encoding="utf-8"))
    report = compare(python_result, javascript_result)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "fpl_personal_squad_live_parity_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    if report["status"] != "PASS_PERSONAL_SQUAD_PYTHON_JAVASCRIPT_PARITY":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
