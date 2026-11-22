import csv
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from archive_cta_forecast_bundle import archive_bundle


ARCHIVE_FILES = [
    "target_gameweeks.json", "feature_matrix.csv", "feature_matrix_report.json",
    "minutes_predictions.csv", "minutes_report.json", "source_preparation_report.json",
    "source_download_manifest.json", "dastan_artifact_manifest.json",
    "canonical_player_matches.parquet", "canonical_team_matches.parquet",
    "canonical_player_lookup.csv", "safe_current_player_mapping.csv",
    "snapshots/bootstrap-static.json", "snapshots/fixtures.json",
    "dastan_mappings/current_fpl_understat_players.csv",
    "dastan_mappings/current_fpl_understat_clubs.csv",
    "dastan_mappings/fpl_understat_current.csv",
    "dastan_mappings/fpl_understat_identity_audit.csv",
    "dastan_mappings/fpl_understat_players.csv",
    "dastan_mappings/fpl_understat_training_assignments.csv",
    "dastan_mappings/fpl_understat_training_snapshot.csv",
    "dastan_mappings/current_manifest.json",
    "dastan_model/feature_cols.json", "dastan_model/minutes_calibration.json",
    "dastan_model/p60_GKP.json", "dastan_model/p60_DEF.json",
    "dastan_model/p60_MID.json", "dastan_model/p60_FWD.json",
    "training/release_manifest.json", "training/source_pins.json",
    "models/cta_points_model_manifest.json",
    "models/cta_points_GKP.json", "models/cta_points_DEF.json",
    "models/cta_points_MID.json", "models/cta_points_FWD.json",
    "forecasts/fixture_forecasts.csv", "forecasts/player_gameweek_forecasts.csv",
    "forecasts/player_five_gw_forecasts.csv", "forecasts/forecast_report.json",
    "forecasts/bundle_validation_report.json",
]


def write_text(root: Path, relative: str, content: str = "payload"):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_json(root: Path, relative: str, value):
    return write_text(root, relative, json.dumps(value, sort_keys=True) + "\n")


def write_csv(root: Path, relative: str, rows):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bundle(root: Path):
    root.mkdir(parents=True)
    for name in ARCHIVE_FILES:
        write_text(root, name, "payload-" + name)

    source_manifest = {"source": "pinned", "feature_source_mode": "FPL_PLAYER_UNDERSTAT"}
    write_json(root, "source_download_manifest.json", source_manifest)
    source_sha = digest(root / "source_download_manifest.json")

    minutes_files = [
        "feature_cols.json", "minutes_calibration.json",
        "p60_GKP.json", "p60_DEF.json", "p60_MID.json", "p60_FWD.json",
    ]
    minutes_hashes = {}
    for name in minutes_files:
        path = root / "dastan_model" / name
        minutes_hashes[name] = {"sha256": digest(path), "bytes": path.stat().st_size}

    model_hashes = {}
    positions = {}
    for position in ("GKP", "DEF", "MID", "FWD"):
        path = root / f"models/cta_points_{position}.json"
        model_hashes[position] = digest(path)
        positions[position] = {
            "model_path": f"outputs/cta-five-gw/models/cta_points_{position}.json",
            "model_sha256": model_hashes[position],
        }
    model_manifest = {
        "status": "CANDIDATE_TRAINED_M2_VALIDATION_PENDING",
        "feature_source_mode": "FPL_PLAYER_UNDERSTAT",
        "validation": {"status": "NOT_RUN_M2_DEFERRED"},
        "production_eligible": False,
        "decision_weight": 0,
        "positions": positions,
    }
    write_json(root, "models/cta_points_model_manifest.json", model_manifest)
    model_manifest_sha = digest(root / "models/cta_points_model_manifest.json")

    feature_sha = digest(root / "feature_matrix.csv")
    minutes_sha = digest(root / "minutes_predictions.csv")
    write_json(root, "source_preparation_report.json", {
        "feature_source_mode": "FPL_PLAYER_UNDERSTAT",
        "source_manifest_sha256": source_sha,
    })

    snapshot = "snapshot-123"
    fixture_rows = [
        {"forecast_snapshot_id": snapshot, "expected_points_model_status": "CANDIDATE_NOT_VALIDATED",
         "production_eligible": False, "decision_weight": 0, "covar_used": False}
        for _ in range(3)
    ]
    gw_rows = [
        {"forecast_snapshot_id": snapshot, "model_status": "CANDIDATE_NOT_VALIDATED",
         "production_eligible": False, "decision_weight": 0}
        for _ in range(3)
    ]
    five_rows = [
        {"forecast_snapshot_id": snapshot, "model_status": "CANDIDATE_NOT_VALIDATED",
         "production_eligible": False, "decision_weight": 0}
        for _ in range(2)
    ]
    write_csv(root, "forecasts/fixture_forecasts.csv", fixture_rows)
    write_csv(root, "forecasts/player_gameweek_forecasts.csv", gw_rows)
    write_csv(root, "forecasts/player_five_gw_forecasts.csv", five_rows)

    safeguards = {
        "status": "EXPLORATORY_NOT_PRODUCTION",
        "production_eligible": False,
        "decision_weight": 0,
        "covar_used": False,
    }
    write_json(root, "forecasts/forecast_report.json", {
        "status": "PASS_CTA_FIVE_GW_CANDIDATE_FORECAST",
        "season": "2026-27",
        "gameweeks": [12, 13, 14, 15, 16],
        "forecast_snapshot_id": snapshot,
        "fixture_player_rows": 3,
        "player_gameweek_rows": 3,
        "five_gameweek_player_rows": 2,
        "feature_source_mode": "FPL_PLAYER_UNDERSTAT",
        "model_hashes": model_hashes,
        "provenance": {
            "source_manifest_sha256": source_sha,
            "feature_matrix_sha256": feature_sha,
            "minutes_predictions_sha256": minutes_sha,
            "points_model_manifest_sha256": model_manifest_sha,
            "minutes_artifact_hashes": minutes_hashes,
        },
        "decision_safeguards": safeguards,
    })
    write_json(root, "forecasts/bundle_validation_report.json", {
        "status": "PASS_CTA_FORECAST_BUNDLE_INTEGRITY",
        "forecast_snapshot_id": snapshot,
        "fixture_rows": 3,
        "player_gameweek_rows": 3,
        "five_gameweek_player_rows": 2,
        "production_eligible": False,
        "decision_weight": 0,
        "covar_used": False,
    })
    return root


def test_archives_full_provenance_verified_forecast_and_models(tmp_path):
    root = bundle(tmp_path / "bundle")
    out = tmp_path / "archive"
    archive_bundle(root, out, run_id="12345", commit_sha="deadbeef",
                   run_url="https://github.com/example/run/12345")
    snap = out / "snapshots/2026-27/gw12-16/snapshot-123/archive-v2"
    archive = snap / "forecast_bundle.zip"
    manifest = json.loads((snap / "archive_manifest.json").read_text())
    assert manifest["archive"]["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert manifest["source_run"]["run_id"] == "12345"
    assert manifest["provenance_hashes_verified"] is True
    with zipfile.ZipFile(archive) as z:
        names = set(z.namelist())
        assert "forecasts/fixture_forecasts.csv" in names
        assert "models/cta_points_FWD.json" in names
        assert "dastan_model/p60_DEF.json" in names
        assert "snapshots/bootstrap-static.json" in names
        assert "canonical_player_lookup.csv" in names
    assert json.loads((out / "latest.json").read_text())["forecast_snapshot_id"] == "snapshot-123"


def test_rejects_bundle_without_passed_integrity_report(tmp_path):
    root = bundle(tmp_path / "bundle")
    write_json(root, "forecasts/bundle_validation_report.json", {"status": "FAIL"})
    with pytest.raises(ValueError, match="integrity validation did not pass"):
        archive_bundle(root, tmp_path / "archive", run_id="1", commit_sha="sha",
                       run_url="https://example.test/run")


def test_rejects_candidate_safeguard_drift(tmp_path):
    root = bundle(tmp_path / "bundle")
    report = json.loads((root / "forecasts/forecast_report.json").read_text())
    report["decision_safeguards"]["production_eligible"] = True
    write_json(root, "forecasts/forecast_report.json", report)
    with pytest.raises(ValueError, match="release safeguards"):
        archive_bundle(root, tmp_path / "archive", run_id="1", commit_sha="sha",
                       run_url="https://example.test/run")


def test_rejects_feature_matrix_hash_mismatch(tmp_path):
    root = bundle(tmp_path / "bundle")
    write_text(root, "feature_matrix.csv", "tampered")
    with pytest.raises(ValueError, match="feature matrix SHA-256"):
        archive_bundle(root, tmp_path / "archive", run_id="1", commit_sha="sha",
                       run_url="https://example.test/run")


def test_rejects_cta_model_binary_hash_mismatch(tmp_path):
    root = bundle(tmp_path / "bundle")
    write_text(root, "models/cta_points_MID.json", "tampered")
    with pytest.raises(ValueError, match="CTA MID model binary SHA-256"):
        archive_bundle(root, tmp_path / "archive", run_id="1", commit_sha="sha",
                       run_url="https://example.test/run")


def test_rejects_actual_csv_row_count_mismatch(tmp_path):
    root = bundle(tmp_path / "bundle")
    write_csv(root, "forecasts/fixture_forecasts.csv", [
        {"forecast_snapshot_id": "snapshot-123", "expected_points_model_status": "CANDIDATE_NOT_VALIDATED",
         "production_eligible": False, "decision_weight": 0, "covar_used": False}
    ])
    with pytest.raises(ValueError, match="row count does not match forecast report"):
        archive_bundle(root, tmp_path / "archive", run_id="1", commit_sha="sha",
                       run_url="https://example.test/run")
