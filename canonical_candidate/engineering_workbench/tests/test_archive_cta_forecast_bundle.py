import hashlib, json, zipfile
from pathlib import Path
import pytest
from archive_cta_forecast_bundle import archive_bundle

def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) if isinstance(value, dict) else str(value), encoding="utf-8")

def bundle(root: Path):
    files = [
        "target_gameweeks.json", "feature_matrix.csv", "feature_matrix_report.json",
        "minutes_predictions.csv", "minutes_report.json", "source_preparation_report.json",
        "source_download_manifest.json", "dastan_artifact_manifest.json",
        "training/release_manifest.json", "training/source_pins.json",
        "models/cta_points_model_manifest.json", "models/cta_points_GKP.json",
        "models/cta_points_DEF.json", "models/cta_points_MID.json", "models/cta_points_FWD.json",
        "forecasts/fixture_forecasts.csv", "forecasts/player_gameweek_forecasts.csv",
        "forecasts/player_five_gw_forecasts.csv"]
    for name in files: write(root / name, "payload-" + name)
    write(root / "source_preparation_report.json", {"feature_source_mode":"FPL_PLAYER_UNDERSTAT"})
    write(root / "models/cta_points_model_manifest.json", {"status":"CANDIDATE_TRAINED_M2_VALIDATION_PENDING"})
    safeguards = {"status":"EXPLORATORY_NOT_PRODUCTION","production_eligible":False,
                  "decision_weight":0,"covar_used":False}
    write(root / "forecasts/forecast_report.json", {
        "status":"PASS_CTA_FIVE_GW_CANDIDATE_FORECAST","season":"2026-27",
        "gameweeks":[12,13,14,15,16],"forecast_snapshot_id":"snapshot-123",
        "fixture_rows":3,"player_gameweek_rows":3,"five_gameweek_player_rows":2,
        "model_hashes":{"GKP":"abc"},"provenance":{"source_manifest_sha256":"source",
        "feature_matrix_sha256":"matrix"},"decision_safeguards":safeguards})
    write(root / "forecasts/bundle_validation_report.json", {
        "status":"PASS_CTA_FORECAST_BUNDLE_INTEGRITY","fixture_rows":3,
        "player_gameweek_rows":3,"five_gameweek_player_rows":2})
    return root

def test_archives_hash_verified_forecast_and_models(tmp_path):
    root=bundle(tmp_path/"bundle"); out=tmp_path/"archive"
    archive_bundle(root,out,run_id="12345",commit_sha="deadbeef",run_url="https://github.com/example/run/12345")
    snap=out/"snapshots/2026-27/gw12-16/snapshot-123"
    archive=snap/"forecast_bundle.zip"; manifest=json.loads((snap/"archive_manifest.json").read_text())
    assert manifest["archive"]["sha256"]==hashlib.sha256(archive.read_bytes()).hexdigest()
    assert manifest["source_run"]["run_id"]=="12345"
    with zipfile.ZipFile(archive) as z:
        assert "forecasts/fixture_forecasts.csv" in z.namelist()
        assert "models/cta_points_FWD.json" in z.namelist()
    assert json.loads((out/"latest.json").read_text())["forecast_snapshot_id"]=="snapshot-123"

def test_rejects_bundle_without_passed_integrity_report(tmp_path):
    root=bundle(tmp_path/"bundle")
    write(root/"forecasts/bundle_validation_report.json",{"status":"FAIL"})
    with pytest.raises(ValueError,match="integrity validation did not pass"):
        archive_bundle(root,tmp_path/"archive",run_id="1",commit_sha="sha",run_url="https://example.test/run")

def test_rejects_candidate_safeguard_drift(tmp_path):
    root=bundle(tmp_path/"bundle")
    report=json.loads((root/"forecasts/forecast_report.json").read_text())
    report["decision_safeguards"]["production_eligible"]=True
    write(root/"forecasts/forecast_report.json",report)
    with pytest.raises(ValueError,match="release safeguards"):
        archive_bundle(root,tmp_path/"archive",run_id="1",commit_sha="sha",run_url="https://example.test/run")
