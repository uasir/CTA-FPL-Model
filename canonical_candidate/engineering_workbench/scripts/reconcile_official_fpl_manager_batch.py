#!/usr/bin/env python3
"""Run independent official FPL manager reconciliation across multiple Gameweeks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from capture_and_reconcile_official_fpl_manager_result import (
    CaptureReconciliationError,
    capture_and_reconcile,
)


def parse_gameweeks(value: str) -> list[int]:
    try:
        parsed = [int(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise ValueError("gameweeks must be comma-separated positive integers") from exc
    if not parsed or any(gw < 1 for gw in parsed):
        raise ValueError("gameweeks must contain at least one positive integer")
    if len(set(parsed)) != len(parsed):
        raise ValueError("gameweeks must not contain duplicates")
    return parsed


def reconcile_batch(
    manager_team_id: int,
    gameweeks: list[int],
    capture_fn: Callable[[int, int], dict] = capture_and_reconcile,
) -> dict:
    if manager_team_id < 1:
        raise ValueError("manager_team_id must be positive")
    if not gameweeks or any(gw < 1 for gw in gameweeks) or len(set(gameweeks)) != len(gameweeks):
        raise ValueError("gameweeks must be a non-empty list of unique positive integers")

    results = []
    for gameweek in gameweeks:
        try:
            result = capture_fn(manager_team_id, gameweek)
            results.append({
                "gameweek": gameweek,
                "status": result["reconciliation"]["status"],
                "result": result,
            })
        except Exception as exc:
            # Preserve the failure as an explicit exclusion; never silently drop a requested GW.
            results.append({
                "gameweek": gameweek,
                "status": "EXCLUDED",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "diagnostic_record": getattr(exc, "diagnostic_record", None),
                "historical_evidence_admitted": False,
            })

    reconciled = [row for row in results if row["status"] == "RECONCILED"]
    excluded = [row for row in results if row["status"] != "RECONCILED"]
    autosub_gws = [
        row["gameweek"] for row in reconciled
        if row["result"]["reconciliation"]["automatic_substitutions"]
    ]
    hit_gws = [
        row["gameweek"] for row in reconciled
        if row["result"]["reconciliation"]["official_transfer_cost"] > 0
    ]
    return {
        "batch_contract_version": "0.1.0",
        "manager_team_id": manager_team_id,
        "requested_gameweeks": gameweeks,
        "reconciled_count": len(reconciled),
        "excluded_count": len(excluded),
        "reconciled_gameweeks": [row["gameweek"] for row in reconciled],
        "excluded_gameweeks": [row["gameweek"] for row in excluded],
        "gameweeks_with_automatic_substitutions": autosub_gws,
        "gameweeks_with_transfer_hits": hit_gws,
        "historical_evidence_admitted": False,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manager-team-id", type=int, required=True)
    parser.add_argument("--gameweeks", required=True, help="Comma-separated completed Gameweeks")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = reconcile_batch(args.manager_team_id, parse_gameweeks(args.gameweeks))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "results"}, indent=2))
    # A partial cohort is useful diagnostic output but remains a failed batch for CI visibility.
    return 0 if result["excluded_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
