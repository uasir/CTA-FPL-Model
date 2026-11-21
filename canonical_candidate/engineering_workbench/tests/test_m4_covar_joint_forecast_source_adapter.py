from __future__ import annotations
import hashlib, json, os, pytest
from m4_covar_joint_forecast_source_adapter import JointForecastSourceAdapterError, archive_explicit_joint_forecast, main

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
    manifest = json.loads((dest / "archive_manifest.json").read_text())
    saved = dest / manifest["validated_forecast_document"]["archive_path"]
    archived_document = json.loads(saved.read_text())
    assert archived_document == doc
    assert hashlib.sha256(saved.read_bytes()).hexdigest() == manifest["validated_forecast_document"]["sha256"]
    assert os.stat(saved).st_mode & 0o777 == 0o600

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

def test_refuses_git_checkout_destination_reached_through_symlink(tmp_path):
    doc, blobs = sample()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    link = tmp_path / "repo-link"
    try:
        link.symlink_to(repo, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks are unavailable")
    with pytest.raises(JointForecastSourceAdapterError, match="outside a Git repository"):
        archive_explicit_joint_forecast(document=doc, artifact_bytes=blobs,
                                        archive_root=link / "archive")

def test_cli_archives_complete_forecast_from_provider_artifact_layout(tmp_path, capsys):
    doc, blobs = sample()
    artifact_root = tmp_path / "input"
    (artifact_root / "sources").mkdir(parents=True)
    (artifact_root / "model").mkdir()
    (artifact_root / "forecast").mkdir()
    (artifact_root / "sources" / "feed.bin").write_bytes(blobs["source:feed"])
    (artifact_root / "model" / "model.bin").write_bytes(blobs["model_artifact"])
    (artifact_root / "model" / "config.bin").write_bytes(blobs["config"])
    (artifact_root / "forecast" / "payload.bin").write_bytes(blobs["forecast_payload"])
    document_path = tmp_path / "forecast.json"
    document_path.write_text(json.dumps(doc), encoding="utf-8")
    destination = tmp_path / "private-archive"
    assert main(["--document", str(document_path), "--artifact-dir", str(artifact_root),
                 "--archive-root", str(destination)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["verification_status"] == "COMPLETE_PROVENANCE_CHAIN_BYTES_VERIFIED"
    archived = json.loads((destination / "forecast" / "validated_document.json").read_text())
    assert archived == doc


def test_cli_rejects_symlinked_artifact_files(tmp_path):
    doc, blobs = sample()
    artifact_root = tmp_path / "input"
    (artifact_root / "sources").mkdir(parents=True)
    (artifact_root / "model").mkdir()
    (artifact_root / "forecast").mkdir()
    (artifact_root / "sources" / "feed.bin").write_bytes(blobs["source:feed"])
    (artifact_root / "model" / "config.bin").write_bytes(blobs["config"])
    (artifact_root / "forecast" / "payload.bin").write_bytes(blobs["forecast_payload"])
    external = tmp_path / "external-model.bin"
    external.write_bytes(blobs["model_artifact"])
    try:
        (artifact_root / "model" / "model.bin").symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("file symlinks are unavailable")
    document_path = tmp_path / "forecast.json"
    document_path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(JointForecastSourceAdapterError, match="regular non-symlink"):
        main(["--document", str(document_path), "--artifact-dir", str(artifact_root),
              "--archive-root", str(tmp_path / "private-archive")])
