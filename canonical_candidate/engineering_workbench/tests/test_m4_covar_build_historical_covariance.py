from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from m4_covar_build_historical_covariance import (
    HistoricalCovarianceBuildError,
    build_historical_covariance_from_finality,
)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def build_source(root: Path):
    panel = root / "covar-realized-panel" / "fpl_realized_player_gameweek.csv"
    panel.parent.mkdir(parents=True)
    rows = []
    for gw in range(1, 6):
        for pid, points in ((1, gw), (2, gw * 2), (3, 6 - gw)):
            rows.append({
                "season": "2026-27", "gameweek": str(gw),
                "fpl_element_id": str(pid), "total_points": str(points),
            })
    with panel.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    digest = hashlib.sha256(panel.read_bytes()).hexdigest()
    write_json(root / "covar-realized-panel" / "dataset_manifest.json", {
        "status": "PASS_STRUCTURAL_ONLY",
        "season": "2026-27",
        "finished_gameweeks": [1, 2, 3, 4, 5],
        "archive_artifacts": {"fpl_realized_player_gameweek.csv": digest},
    })
    write_json(root / "covar-finality-result" / "finality_batch_report.json", {
        "status": "PASS_ALL_EVENTS",
        "all_event_finality_reconciled": True,
        "season": "2026-27",
        "reports": [
            {"event_id": gw, "status": "PASS_EXACT_MATCH", "finality_reconciled": True}
            for gw in range(1, 6)
        ],
    })
    write_json(root / "covar-finality-captures" / "event_5" / "bootstrap_static.json", {
        "elements": [
            {"id": 1, "web_name": "A", "element_type": 3},
            {"id": 2, "web_name": "B", "element_type": 3},
            {"id": 3, "web_name": "C", "element_type": 4},
        ],
        "element_types": [
            {"id": 3, "singular_name_short": "MID"},
            {"id": 4, "singular_name_short": "FWD"},
        ],
    })


def test_builds_reconciled_historical_covariance_artifacts(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "output"
    build_source(source)
    report = build_historical_covariance_from_finality(source, output, window_size=5, shrinkage=0.5)
    assert report["status"] == "EXPLORATORY_ONLY"
    assert report["source_finality_status"] == "PASS_ALL_EVENTS"
    assert report["window_gameweeks"] == [1, 2, 3, 4, 5]
    assert report["point_in_time_status"] == "NOT_VERIFIED_RETROSPECTIVE_FINAL_SCORING_AUDIT"
    assert report["decision_weight"] == 0
    assert report["production_eligible"] is False
    assert (output / "fpl_covariance_pairs.csv").exists()
    assert (output / "fpl_covariance_report.json").exists()


def test_rejects_failed_finality_batch(tmp_path):
    source = tmp_path / "source"
    build_source(source)
    path = source / "covar-finality-result" / "finality_batch_report.json"
    report = json.loads(path.read_text())
    report["status"] = "FAIL_MISMATCHES"
    write_json(path, report)
    with pytest.raises(HistoricalCovarianceBuildError, match="PASS_ALL_EVENTS"):
        build_historical_covariance_from_finality(source, tmp_path / "output", window_size=5)


def test_rejects_panel_hash_mismatch(tmp_path):
    source = tmp_path / "source"
    build_source(source)
    panel = source / "covar-realized-panel" / "fpl_realized_player_gameweek.csv"
    panel.write_text(panel.read_text() + "\n", encoding="utf-8")
    with pytest.raises(HistoricalCovarianceBuildError, match="SHA-256"):
        build_historical_covariance_from_finality(source, tmp_path / "output", window_size=5)


def test_rejects_windows_shorter_than_five_gameweeks(tmp_path):
    source = tmp_path / "source"
    build_source(source)
    with pytest.raises(HistoricalCovarianceBuildError, match="at least five"):
        build_historical_covariance_from_finality(source, tmp_path / "output", window_size=4)

def refresh_panel_manifest_hash(source: Path):
    panel = source / "covar-realized-panel" / "fpl_realized_player_gameweek.csv"
    manifest_path = source / "covar-realized-panel" / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["archive_artifacts"]["fpl_realized_player_gameweek.csv"] = hashlib.sha256(panel.read_bytes()).hexdigest()
    write_json(manifest_path, manifest)


def rewrite_panel(source: Path, rows):
    panel = source / "covar-realized-panel" / "fpl_realized_player_gameweek.csv"
    with panel.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["season", "gameweek", "fpl_element_id", "total_points"])
        writer.writeheader()
        writer.writerows(rows)
    refresh_panel_manifest_hash(source)


def test_rejects_panel_gameweek_outside_finality_reconciled_set(tmp_path):
    source = tmp_path / "source"
    build_source(source)
    panel = source / "covar-realized-panel" / "fpl_realized_player_gameweek.csv"
    with panel.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows.append({"season": "2026-27", "gameweek": "6", "fpl_element_id": "1", "total_points": "4"})
    rewrite_panel(source, rows)
    with pytest.raises(HistoricalCovarianceBuildError, match="outside the finality-reconciled set"):
        build_historical_covariance_from_finality(source, tmp_path / "output", window_size=5)


def test_rejects_panel_missing_a_finality_reconciled_gameweek(tmp_path):
    source = tmp_path / "source"
    build_source(source)
    panel = source / "covar-realized-panel" / "fpl_realized_player_gameweek.csv"
    with panel.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["gameweek"] != "5"]
    rewrite_panel(source, rows)
    with pytest.raises(HistoricalCovarianceBuildError, match="Gameweek set does not exactly match"):
        build_historical_covariance_from_finality(source, tmp_path / "output", window_size=5)


def test_rejects_duplicate_finality_gameweek_ids(tmp_path):
    source = tmp_path / "source"
    build_source(source)
    path = source / "covar-finality-result" / "finality_batch_report.json"
    report = json.loads(path.read_text())
    report["reports"].append(report["reports"][-1].copy())
    write_json(path, report)
    with pytest.raises(HistoricalCovarianceBuildError, match="duplicate Gameweek"):
        build_historical_covariance_from_finality(source, tmp_path / "output", window_size=5)


def test_rejects_duplicate_player_gameweek_rows_even_with_updated_manifest_hash(tmp_path):
    source = tmp_path / "source"
    build_source(source)
    panel = source / "covar-realized-panel" / "fpl_realized_player_gameweek.csv"
    with panel.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows.append(rows[0].copy())
    rewrite_panel(source, rows)
    with pytest.raises(HistoricalCovarianceBuildError, match="duplicate player-Gameweek"):
        build_historical_covariance_from_finality(source, tmp_path / "output", window_size=5)


def test_rejects_non_integer_fpl_points_even_with_updated_manifest_hash(tmp_path):
    source = tmp_path / "source"
    build_source(source)
    panel = source / "covar-realized-panel" / "fpl_realized_player_gameweek.csv"
    with panel.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["total_points"] = "2.5"
    rewrite_panel(source, rows)
    with pytest.raises(HistoricalCovarianceBuildError, match="finite integer FPL points"):
        build_historical_covariance_from_finality(source, tmp_path / "output", window_size=5)
