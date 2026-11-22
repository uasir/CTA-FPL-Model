#!/usr/bin/env python3
"""Accumulate verified per-Gameweek prospective forecast/outcome matches.

Gameweek is the clustering unit. This utility validates and concatenates already
matched archives; it does not fit a model, infer joint dependence, or fill gaps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any


class MatchedPanelError(ValueError):
    """An input match archive is incomplete, altered, or incompatible."""


def _read_archive(directory: Path) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    manifest_path = directory / "match_manifest.json"
    panel_path = directory / "matched_forecast_outcomes.json"
    if not manifest_path.is_file() or not panel_path.is_file():
        raise MatchedPanelError(f"{directory} is not a complete matched archive")
    manifest_bytes = manifest_path.read_bytes()
    panel_bytes = panel_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    panel = json.loads(panel_bytes.decode("utf-8"))
    expected = manifest.get("matched_output_sha256")
    actual = hashlib.sha256(panel_bytes).hexdigest()
    if not isinstance(expected, str) or expected != actual:
        raise MatchedPanelError(f"{directory} matched output hash mismatch")
    if manifest.get("status") != "MATCHED_RESEARCH_PANEL_CREATED":
        raise MatchedPanelError(f"{directory} archive status is not complete")
    if panel.get("dataset_type") != "PROSPECTIVE_CONVENTIONAL_FORECAST_TO_FINAL_OUTCOME_MATCH":
        raise MatchedPanelError(f"{directory} unsupported matched dataset type")
    if panel.get("decision_weight") != 0.0 or panel.get("production_eligible") is not False:
        raise MatchedPanelError(f"{directory} archive is not research-only")
    if panel.get("finality_status") != "PASS_EXACT_MATCH":
        raise MatchedPanelError(f"{directory} finality was not passed")
    if panel.get("missing_observations_zero_filled") != 0:
        raise MatchedPanelError(f"{directory} declares zero-filled missing observations")
    if manifest.get("season") != panel.get("season") or manifest.get("gameweek") != panel.get("gameweek"):
        raise MatchedPanelError(f"{directory} manifest and panel identity disagree")
    rows = panel.get("matched_rows")
    if not isinstance(rows, list) or not rows:
        raise MatchedPanelError(f"{directory} matched rows are empty")
    if len(rows) != manifest.get("matched_player_count"):
        raise MatchedPanelError(f"{directory} matched player count mismatch")
    for row in rows:
        if row.get("season") != panel["season"] or row.get("gameweek") != panel["gameweek"]:
            raise MatchedPanelError(f"{directory} contains cross-Gameweek player rows")
        if row.get("finality_status") != "PASS_EXACT_MATCH":
            raise MatchedPanelError(f"{directory} contains a row without finality pass")
    return manifest, panel, panel_bytes


def build_matched_panel_archive(
    archive_dirs: list[Path], output_dir: Path, *, repository_root: Path | None = None
) -> dict[str, Any]:
    if not archive_dirs:
        raise MatchedPanelError("at least one per-Gameweek matched archive is required")
    if not output_dir.is_absolute():
        raise MatchedPanelError("output_dir must be absolute")
    root = Path(repository_root).resolve() if repository_root else Path(__file__).resolve().parents[3]
    target = output_dir.resolve()
    if target.is_relative_to(root):
        raise MatchedPanelError("accumulated matched panel must be outside repository")
    if target.exists():
        raise FileExistsError("refusing to overwrite existing accumulated panel")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(mode=stat.S_IRWXU)
    try:
        entries = []
        seen_gws = set()
        season = None
        total_rows = 0
        for directory in archive_dirs:
            manifest, panel, raw = _read_archive(directory)
            if season is None:
                season = panel["season"]
            elif panel["season"] != season:
                raise MatchedPanelError("cannot combine different seasons")
            gw = panel["gameweek"]
            if isinstance(gw, bool) or not isinstance(gw, int) or gw < 1 or gw in seen_gws:
                raise MatchedPanelError("Gameweeks must be unique positive integers")
            seen_gws.add(gw)
            entries.append({
                "gameweek": gw,
                "forecast_snapshot_id": panel.get("forecast_snapshot_id"),
                "forecast_as_of_utc": panel.get("forecast_as_of_utc"),
                "finality_status": panel["finality_status"],
                "outcome_available_at_utc": panel.get("outcome_available_at_utc"),
                "matched_player_count": len(panel["matched_rows"]),
                "source_match_manifest_sha256": hashlib.sha256(
                    (directory / "match_manifest.json").read_bytes()
                ).hexdigest(),
                "source_matched_output_sha256": hashlib.sha256(raw).hexdigest(),
            })
            total_rows += len(panel["matched_rows"])
        entries.sort(key=lambda item: item["gameweek"])
        # Re-read only after validating all inputs; preserve source rows exactly.
        all_rows = []
        for directory in archive_dirs:
            _, panel, _ = _read_archive(directory)
            all_rows.extend(panel["matched_rows"])
        output = {
            "schema_version": "1.0.0",
            "dataset_type": "MULTI_GAMEWEEK_PROSPECTIVE_CONVENTIONAL_FORECAST_OUTCOME_PANEL",
            "season": season,
            "gameweek_count": len(entries),
            "gameweeks": [item["gameweek"] for item in entries],
            "gameweek_clusters": entries,
            "matched_player_gameweek_rows": total_rows,
            "matched_rows": sorted(all_rows, key=lambda row: (row["gameweek"], row["fpl_element_id"])),
            "cluster_unit": "GAMEWEEK",
            "player_rows_within_gameweek_are_not_independent_gameweek_samples": True,
            "missing_observations_zero_filled": 0,
            "joint_dependence_inferred_from_marginal_player_rows": False,
            "decision_weight": 0.0,
            "production_eligible": False,
            "limitations": [
                "This archive concatenates prospectively captured conventional player forecasts matched to retrospectively finality-reconciled outcomes.",
                "Gameweeks, not player rows, are the independent clustering unit for downstream uncertainty analysis.",
                "The panel does not contain complete joint player outcome scenarios and cannot establish joint dependence calibration.",
                "No forecast recalibration, model fitting, or production recommendation is performed.",
            ],
        }
        data_path = target / "multi_gameweek_matched_panel.json"
        data_path.write_text(json.dumps(output, indent=2, sort_keys=True, allow_nan=False) + "\n")
        summary = {
            "schema_version": "1.0.0",
            "status": "MULTI_GAMEWEEK_PANEL_CREATED",
            "season": season,
            "gameweek_count": len(entries),
            "gameweeks": output["gameweeks"],
            "matched_player_gameweek_rows": total_rows,
            "input_archives": entries,
            "panel_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
            "cluster_unit": "GAMEWEEK",
            "decision_weight": 0.0,
            "production_eligible": False,
        }
        manifest_path = target / "multi_gameweek_panel_manifest.json"
        manifest_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        for path in (data_path, manifest_path):
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        return summary
    except Exception:
        marker = target / "PANEL_INCOMPLETE"
        marker.write_text("Accumulation failed; do not use this panel.\n")
        os.chmod(marker, stat.S_IRUSR | stat.S_IWUSR)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", action="append", type=Path, required=True,
                        help="Per-Gameweek match archive directory; repeat once per Gameweek")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_matched_panel_archive(args.archive, args.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
