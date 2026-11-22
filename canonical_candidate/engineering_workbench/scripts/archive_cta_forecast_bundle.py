from __future__ import annotations
import argparse, hashlib, json, zipfile
from pathlib import Path
from typing import Any

ARCHIVE_FILES = (
    "target_gameweeks.json", "feature_matrix.csv", "feature_matrix_report.json",
    "minutes_predictions.csv", "minutes_report.json", "source_preparation_report.json",
    "source_download_manifest.json", "dastan_artifact_manifest.json",
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
    season = str(forecast.get("season", ""))
    gameweeks = forecast.get("gameweeks")
    snapshot = str(forecast.get("forecast_snapshot_id", ""))
    if not season or not snapshot or not isinstance(gameweeks, list) or len(gameweeks) < 5:
        raise ValueError("forecast season, snapshot ID, or five-Gameweek horizon is invalid")
    weeks = [int(x) for x in gameweeks]
    if weeks != list(range(weeks[0], weeks[0] + len(weeks))):
        raise ValueError("forecast Gameweeks must be consecutive")
    # The forecast report names its fixture grain `fixture_player_rows`, while
    # the bundle validator uses `fixture_rows`. Compare the semantic quantity
    # across the two versioned report schemas rather than requiring identical keys.
    row_key_pairs = (
        ("fixture_player_rows", "fixture_rows"),
        ("player_gameweek_rows", "player_gameweek_rows"),
        ("five_gameweek_player_rows", "five_gameweek_player_rows"),
    )
    for forecast_key, validation_key in row_key_pairs:
        if int(forecast.get(forecast_key, -1)) != int(validation.get(validation_key, -2)):
            raise ValueError(
                f"forecast and validation row counts disagree: "
                f"{forecast_key} vs {validation_key}"
            )
    missing = [name for name in ARCHIVE_FILES if not (bundle_dir / name).is_file()]
    if missing:
        raise ValueError(f"forecast bundle is missing archive inputs: {missing}")
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
