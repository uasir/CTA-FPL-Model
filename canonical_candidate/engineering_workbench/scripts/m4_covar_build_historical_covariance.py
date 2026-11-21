#!/usr/bin/env python3
"""Build a historical CoVar matrix from finality-reconciled official FPL evidence."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from estimate_fpl_covariance import estimate_covariance, write_outputs


class HistoricalCovarianceBuildError(ValueError):
    """The official historical panel is not suitable for covariance estimation."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _one(root: Path, relative: str) -> Path:
    matches = list(root.rglob(relative))
    if len(matches) != 1:
        raise HistoricalCovarianceBuildError(f"expected exactly one {relative}, found {len(matches)}")
    return matches[0]


def _latest_bootstrap(root: Path, max_gameweek: int) -> Path:
    matches = []
    for path in root.rglob("bootstrap_static.json"):
        parent = path.parent.name
        if parent.startswith("event_") and parent[6:].isdigit():
            event_id = int(parent[6:])
            if event_id <= max_gameweek:
                matches.append((event_id, path))
    if not matches:
        raise HistoricalCovarianceBuildError("no official bootstrap snapshot found for the historical window")
    return max(matches, key=lambda row: row[0])[1]


def build_historical_covariance_from_finality(
    source_dir: Path,
    output_dir: Path,
    *,
    window_size: int = 10,
    shrinkage: float = 0.5,
) -> dict[str, Any]:
    finality_path = _one(source_dir, "finality_batch_report.json")
    manifest_path = _one(source_dir, "dataset_manifest.json")
    panel_path = _one(source_dir, "fpl_realized_player_gameweek.csv")
    finality = json.loads(finality_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if finality.get("status") != "PASS_ALL_EVENTS" or finality.get("all_event_finality_reconciled") is not True:
        raise HistoricalCovarianceBuildError("finality batch must PASS_ALL_EVENTS")
    reports = finality.get("reports")
    if not isinstance(reports, list) or not reports:
        raise HistoricalCovarianceBuildError("finality batch reports are required")
    if any(row.get("status") != "PASS_EXACT_MATCH" or row.get("finality_reconciled") is not True for row in reports):
        raise HistoricalCovarianceBuildError("every Gameweek must have PASS_EXACT_MATCH finality")
    if manifest.get("status") != "PASS_STRUCTURAL_ONLY":
        raise HistoricalCovarianceBuildError("realized panel manifest must PASS_STRUCTURAL_ONLY")
    if finality.get("season") != manifest.get("season"):
        raise HistoricalCovarianceBuildError("finality and realized panel seasons do not match")
    expected_hash = (manifest.get("archive_artifacts") or {}).get("fpl_realized_player_gameweek.csv")
    if not isinstance(expected_hash, str) or _sha256(panel_path) != expected_hash:
        raise HistoricalCovarianceBuildError("realized player-Gameweek panel SHA-256 does not match its manifest")
    finished_gws = manifest.get("finished_gameweeks")
    finality_gws = sorted(int(row.get("event_id")) for row in reports)
    if not isinstance(finished_gws, list) or sorted(int(value) for value in finished_gws) != finality_gws:
        raise HistoricalCovarianceBuildError("finality Gameweek set does not match realized panel manifest")
    if len(finality_gws) < window_size or window_size < 5:
        raise HistoricalCovarianceBuildError("at least five finality-reconciled Gameweeks are required")

    bootstrap_path = _latest_bootstrap(source_dir, max(finality_gws))
    bootstrap = json.loads(bootstrap_path.read_text(encoding="utf-8"))
    elements = bootstrap.get("elements")
    element_types = bootstrap.get("element_types")
    if not isinstance(elements, list) or not isinstance(element_types, list):
        raise HistoricalCovarianceBuildError("official bootstrap must contain elements and element_types")
    position_by_type = {int(row["id"]): row.get("singular_name_short", "") for row in element_types}
    player_rows = []
    for row in elements:
        player_rows.append({
            "fpl_element_id": str(row.get("id")),
            "web_name": row.get("web_name", ""),
            "position": position_by_type.get(int(row.get("element_type", 0)), ""),
        })

    with panel_path.open(newline="", encoding="utf-8-sig") as handle:
        raw_rows = list(csv.DictReader(handle))
    rows = []
    for row in raw_rows:
        if row.get("season") != finality.get("season"):
            raise HistoricalCovarianceBuildError("player-Gameweek row season mismatch")
        rows.append({
            "season": row.get("season"),
            "gameweek": row.get("gameweek"),
            "fpl_element_id": row.get("fpl_element_id"),
            "target_total_points": row.get("total_points"),
        })

    pairs, summaries, report = estimate_covariance(
        rows, player_rows, shrinkage=shrinkage, window_size=window_size
    )
    report.update({
        "source": "OFFICIAL_FPL_REALIZED_PANEL_WITH_FINALITY_RECONCILIATION",
        "source_season": finality.get("season"),
        "source_finality_status": finality.get("status"),
        "source_finality_gameweeks": finality_gws,
        "source_finality_report_sha256": _sha256(finality_path),
        "source_dataset_manifest_sha256": _sha256(manifest_path),
        "source_player_gameweek_panel_sha256": _sha256(panel_path),
        "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_FINAL_SCORING_AUDIT",
        "model_trained": False,
        "decision_weight": 0.0,
        "production_eligible": False,
        "limitations": list(report.get("limitations", [])) + [
            "Finality reconciliation validates retrospective realized scores, not original deadline-time information.",
            "Historical covariance is a descriptive dependence proxy, not a calibrated forward joint forecast.",
            "No manager-level field portfolios or marginal-EO-derived joint portfolios are included.",
        ],
    })
    write_outputs(pairs, summaries, report, output_dir)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--window-size", type=int, default=10)
    parser.add_argument("--shrinkage", type=float, default=0.5)
    args = parser.parse_args()
    report = build_historical_covariance_from_finality(
        args.source_dir, args.out_dir,
        window_size=args.window_size, shrinkage=args.shrinkage,
    )
    print(json.dumps({
        "status": report["status"],
        "season": report["season"],
        "window_gameweeks": report["window_gameweeks"],
        "covariance_players": report["covariance_players"],
        "pairwise_estimates_including_diagonal": report["pairwise_estimates_including_diagonal"],
        "point_in_time_status": report["point_in_time_status"],
        "decision_weight": 0.0,
        "production_eligible": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
