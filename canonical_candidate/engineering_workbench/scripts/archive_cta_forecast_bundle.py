from __future__ import annotations
import argparse, csv, hashlib, json, zipfile
from pathlib import Path
from typing import Any

ARCHIVE_FILES = (
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
)

def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read required JSON report {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def archive_bundle(bundle_dir: Path, archive_root: Path, *, run_id: str,
                   commit_sha: str, run_url: str) -> dict[str, Any]:
    bundle_dir = bundle_dir.resolve()
    archive_root.mkdir(parents=True, exist_ok=True)
    forecast = read_json(bundle_dir / "forecasts/forecast_report.json")
    validation = read_json(bundle_dir / "forecasts/bundle_validation_report.json")
    source = read_json(bundle_dir / "source_preparation_report.json")
    model = read_json(bundle_dir / "models/cta_points_model_manifest.json")
    if forecast.get("status") != "PASS_CTA_FIVE_GW_CANDIDATE_FORECAST":
        raise ValueError("forecast report is not a successful CTA candidate forecast")
    if validation.get("status") != "PASS_CTA_FORECAST_BUNDLE_INTEGRITY":
        raise ValueError("forecast bundle integrity validation did not pass")
    if model.get("status") != "CANDIDATE_TRAINED_M2_VALIDATION_PENDING":
        raise ValueError("CTA points model is not in the expected M2-pending candidate state")
    safeguards = forecast.get("decision_safeguards", {})
    if (safeguards.get("status") != "EXPLORATORY_NOT_PRODUCTION"
        or safeguards.get("production_eligible") is not False
        or safeguards.get("decision_weight") != 0
        or safeguards.get("covar_used") is not False):
        raise ValueError("candidate forecast release safeguards are missing or changed")
    provenance = forecast.get("provenance", {})
    if not isinstance(provenance, dict):
        raise ValueError("forecast provenance is missing")
    required_hashes = {
        "source manifest": ("source_download_manifest.json", provenance.get("source_manifest_sha256")),
        "feature matrix": ("feature_matrix.csv", provenance.get("feature_matrix_sha256")),
        "minutes predictions": ("minutes_predictions.csv", provenance.get("minutes_predictions_sha256")),
        "CTA points model manifest": ("models/cta_points_model_manifest.json", provenance.get("points_model_manifest_sha256")),
    }
    missing = [name for name in ARCHIVE_FILES if not (bundle_dir / name).is_file()]
    if missing:
        raise ValueError(f"forecast bundle is missing archive inputs: {missing}")
    for label, (relative_path, expected_hash) in required_hashes.items():
        path = bundle_dir / relative_path
        if not isinstance(expected_hash, str) or not expected_hash or sha256(path) != expected_hash:
            raise ValueError(f"{label} SHA-256 does not match forecast provenance")
    if source.get("source_manifest_sha256") != provenance.get("source_manifest_sha256"):
        raise ValueError("source preparation report manifest SHA-256 does not match forecast provenance")
    if source.get("feature_source_mode") != forecast.get("feature_source_mode") or model.get("feature_source_mode") != forecast.get("feature_source_mode"):
        raise ValueError("source, forecast and model feature-source modes do not match")
    if model.get("validation", {}).get("status") != "NOT_RUN_M2_DEFERRED":
        raise ValueError("CTA M2 validation state is not explicitly deferred")

    positions = model.get("positions")
    if not isinstance(positions, dict) or set(positions) != {"GKP", "DEF", "MID", "FWD"}:
        raise ValueError("CTA model manifest must contain all four position models")
    forecast_model_hashes = forecast.get("model_hashes", {})
    for position, details in positions.items():
        expected_hash = details.get("model_sha256") if isinstance(details, dict) else None
        relative_path = f"models/cta_points_{position}.json"
        if (not isinstance(expected_hash, str) or not expected_hash
                or forecast_model_hashes.get(position) != expected_hash
                or sha256(bundle_dir / relative_path) != expected_hash):
            raise ValueError(f"CTA {position} model binary SHA-256 does not match model provenance")

    minutes_hashes = provenance.get("minutes_artifact_hashes")
    if not isinstance(minutes_hashes, dict) or not minutes_hashes:
        raise ValueError("Dastan minutes artifact hashes are missing from forecast provenance")
    for filename, details in minutes_hashes.items():
        if not isinstance(details, dict):
            raise ValueError(f"invalid Dastan minutes artifact metadata for {filename}")
        path = bundle_dir / "dastan_model" / filename
        if (not path.is_file()
                or sha256(path) != details.get("sha256")
                or path.stat().st_size != details.get("bytes")):
            raise ValueError(f"Dastan minutes artifact {filename} failed hash/size verification")

    if validation.get("forecast_snapshot_id") != forecast.get("forecast_snapshot_id"):
        raise ValueError("forecast and bundle-validation snapshot IDs disagree")
    if (validation.get("production_eligible") is not False
            or validation.get("decision_weight") != 0
            or validation.get("covar_used") is not False):
        raise ValueError("bundle validation candidate safeguards are missing or changed")

    for filename, count_key in (
        ("forecasts/fixture_forecasts.csv", "fixture_player_rows"),
        ("forecasts/player_gameweek_forecasts.csv", "player_gameweek_rows"),
        ("forecasts/player_five_gw_forecasts.csv", "five_gameweek_player_rows"),
    ):
        with (bundle_dir / filename).open("r", encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        if len(rows) != int(forecast.get(count_key, -1)):
            raise ValueError(f"{filename} row count does not match forecast report")
        for row in rows:
            if row.get("forecast_snapshot_id") != forecast.get("forecast_snapshot_id"):
                raise ValueError(f"{filename} contains a different forecast snapshot ID")
            if row.get("model_status") != "CANDIDATE_NOT_VALIDATED":
                raise ValueError(f"{filename} contains a non-candidate model row")
            if row.get("production_eligible", "").strip().lower() != "false":
                raise ValueError(f"{filename} contains a production-eligible candidate row")
            if float(row.get("decision_weight", "nan")) != 0:
                raise ValueError(f"{filename} contains a non-zero decision weight")
    season = str(forecast.get("season", ""))
    gameweeks = forecast.get("gameweeks")
    snapshot = str(forecast.get("forecast_snapshot_id", ""))
    if not season or not snapshot or not isinstance(gameweeks, list) or len(gameweeks) < 5:
        raise ValueError("forecast season, snapshot ID, or five-Gameweek horizon is invalid")
    weeks = [int(x) for x in gameweeks]
    if weeks != list(range(weeks[0], weeks[0] + len(weeks))):
        raise ValueError("forecast Gameweeks must be consecutive")
    row_key_pairs = (
        ("fixture_player_rows", "fixture_rows"),
        ("player_gameweek_rows", "player_gameweek_rows"),
        ("five_gameweek_player_rows", "five_gameweek_player_rows"),
    )
    for forecast_key, validation_key in row_key_pairs:
        if int(forecast.get(forecast_key, -1)) != int(validation.get(validation_key, -2)):
            raise ValueError(f"forecast and validation row counts disagree for {forecast_key}")
    relative = Path("snapshots") / season / f"gw{weeks[0]:02d}-{weeks[-1]:02d}" / snapshot
    destination = archive_root / relative
    destination.mkdir(parents=True, exist_ok=False)
    zip_path = destination / "forecast_bundle.zip"
    file_hashes = {}
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in ARCHIVE_FILES:
            path = bundle_dir / name
            file_hashes[name] = {"sha256": sha256(path), "size_bytes": path.stat().st_size}
            archive.write(path, arcname=name)
    manifest = {
        "schema_version": "1.0.0",
        "archive_type": "CTA_FIVE_GAMEWEEK_CANDIDATE_FORECAST",
        "season": season, "gameweeks": weeks, "forecast_snapshot_id": snapshot,
        "source_mode": source.get("feature_source_mode"),
        "forecast_status": forecast["status"],
        "bundle_validation_status": validation["status"],
        "model_status": model["status"],
        "decision_safeguards": safeguards,
        "source_commit": source.get("source_commit"),
        "source_manifest_sha256": forecast.get("provenance", {}).get("source_manifest_sha256"),
        "provenance_hashes_verified": True,
        "feature_matrix_sha256": forecast.get("provenance", {}).get("feature_matrix_sha256"),
        "points_model_hashes": forecast.get("model_hashes", {}),
        "source_run": {"run_id": str(run_id), "commit_sha": commit_sha, "run_url": run_url},
        "files": file_hashes,
        "archive": {"file": "forecast_bundle.zip", "sha256": sha256(zip_path),
                    "size_bytes": zip_path.stat().st_size},
    }
    (destination / "archive_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest = {"archive_path": str(relative / "forecast_bundle.zip"),
              "manifest_path": str(relative / "archive_manifest.json"),
              "season": season, "gameweeks": weeks, "forecast_snapshot_id": snapshot,
              "source_run": manifest["source_run"], "archive_sha256": manifest["archive"]["sha256"]}
    (archive_root / "latest.json").write_text(
        json.dumps(latest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest

def main() -> None:
    parser = argparse.ArgumentParser(description="Create a compact durable CTA forecast snapshot archive.")
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--run-url", required=True)
    args = parser.parse_args()
    print(json.dumps(archive_bundle(args.bundle_dir, args.archive_root, run_id=args.run_id,
        commit_sha=args.commit_sha, run_url=args.run_url), indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
