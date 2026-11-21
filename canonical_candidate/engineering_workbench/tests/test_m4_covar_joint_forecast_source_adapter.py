from __future__ import annotations
import hashlib, json, os, pytest
from m4_covar_joint_forecast_source_adapter import JointForecastSourceAdapterError, archive_explicit_joint_forecast

def sample():
    blobs = {"source:feed": b"raw provider snapshot", "model_artifact": b"model bytes",
             "config": b"config bytes", "forecast_payload": b"payload bytes"}
    h = lambda k: hashlib.sha256(blobs[k]).hexdigest()
    doc = {
      "schema_version":"1.0.0","forecast_kind":"EXPLICIT_JOINT_GAMEWEEK_DISTRIBUTION",
      "forecast_id":"gw11-joint-01","season":"2026-27","target_gameweek":11,
      "deadline_utc":"2026-11-21T11:00:00Z","as_of_utc":"2026-11-21T10:30:00Z",
      "training_cutoff_utc":"2026-11-20T23:00:00Z",
      "player_universe":[{"player_id":1,"team_id":"A"},{"player_id":2,"team_id":"B"}],
      "fixtures":[{"fixture_id":10,"home_team_id":"A","away_team_id":"B"}],
      "scenarios":[
        {"scenario_id":"s1","probability":0.5,"probability_basis":"EXPLICIT_SOURCE_SUPPLIED",
         "fixture_states":[{"fixture_id":10,"home_goals":0,"away_goals":0}],
         "player_outcomes":[{"player_id":1,"minutes":90,"played":True,"fpl_points":2},
                            {"player_id":2,"minutes":0,"played":False,"fpl_points":0}]},
        {"scenario_id":"s2","probability":0.5,"probability_basis":"EXPLICIT_SOURCE_SUPPLIED",
         "fixture_states":[{"fixture_id":10,"home_goals":1,"away_goals":0}],
         "player_outcomes":[{"player_id":1,"minutes":90,"played":True,"fpl_points":8},
                            {"player_id":2,"minutes":90,"played":True,"fpl_points":2}]}],
      "provenance":{
        "model_artifact_sha256":h("model_artifact"),"model_version":"joint-v1",
        "model_training_cutoff_utc":"2026-11-20T22:00:00Z",
        "config_sha256":h("config"),"config_version":"cfg-v1","state_catalogue_version":"state-v1",
        "forecast_payload_sha256":h("forecast_payload"),"generated_at_utc":"2026-11-21T10:29:00Z",
        "source_snapshots":[{"source_id":"feed","source_version":"v1","content_sha256":h("source:feed"),
          "available_at_utc":"2026-11-21T09:00:00Z","retrieved_at_utc":"2026-11-21T09:05:00Z"}]}}
    return doc, blobs

def test_archives_and_rehashes_private_bytes(tmp_path):
    doc, blobs = sample(); dest = tmp_path / "archive"
    result = archive_explicit_joint_forecast(document=doc, artifact_bytes=blobs, archive_root=dest)
    assert result["verification_status"] == "COMPLETE_PROVENANCE_CHAIN_BYTES_VERIFIED"
    assert result["verified_artifact_count"] == 4
    assert os.stat(dest).st_mode & 0o777 == 0o700
    assert os.stat(dest / "archive_manifest.json").st_mode & 0o777 == 0o600
    assert json.loads((dest / "archive_manifest.json").read_text())["production_eligible"] is False

def test_rejects_tampered_bytes(tmp_path):
    doc, blobs = sample(); blobs["source:feed"] = b"tampered"
    with pytest.raises(JointForecastSourceAdapterError, match="SHA-256"):
        archive_explicit_joint_forecast(document=doc, artifact_bytes=blobs, archive_root=tmp_path/"archive")

def test_rejects_missing_artifacts(tmp_path):
    doc, blobs = sample(); del blobs["config"]
    with pytest.raises(JointForecastSourceAdapterError, match="exactly match"):
        archive_explicit_joint_forecast(document=doc, artifact_bytes=blobs, archive_root=tmp_path/"archive")

def test_refuses_overwrite(tmp_path):
    doc, blobs = sample(); dest=tmp_path/"archive"
    archive_explicit_joint_forecast(document=doc, artifact_bytes=blobs, archive_root=dest)
    with pytest.raises(JointForecastSourceAdapterError, match="already exists"):
        archive_explicit_joint_forecast(document=doc, artifact_bytes=blobs, archive_root=dest)

def test_refuses_git_checkout_destination(tmp_path):
    doc, blobs = sample(); repo=tmp_path/"repo"; repo.mkdir(); (repo/".git").mkdir()
    with pytest.raises(JointForecastSourceAdapterError, match="outside a Git repository"):
        archive_explicit_joint_forecast(document=doc, artifact_bytes=blobs, archive_root=repo/"archive")
