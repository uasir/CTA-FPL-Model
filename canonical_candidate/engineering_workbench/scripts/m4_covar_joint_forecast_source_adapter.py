"""Source-neutral private adapter for complete explicit joint FPL forecasts."""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, stat, sys, tempfile
from pathlib import Path
from typing import Any, Mapping
from m4_covar_joint_forecast_intake import validate_joint_forecast_intake
from m4_covar_joint_forecast_archive_verifier import verify_joint_forecast_archive

class JointForecastSourceAdapterError(ValueError):
    pass

def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def archive_explicit_joint_forecast(*, document: Mapping[str, Any],
        artifact_bytes: Mapping[str, bytes], archive_root: str | Path) -> dict[str, Any]:
    """Validate, rehash and privately archive exact source/model/config/forecast bytes."""
    intake = validate_joint_forecast_intake(document)
    fid = intake["forecast_id"]
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", fid) or fid in {".", ".."}:
        raise JointForecastSourceAdapterError("unsafe forecast_id")
    prov = document["provenance"]
    required = {"model_artifact", "config", "forecast_payload"}
    required.update("source:" + row["source_id"] for row in prov["source_snapshots"])
    if set(artifact_bytes) != required:
        raise JointForecastSourceAdapterError("artifact byte keys must exactly match provenance")
    expected = {
        "model_artifact": prov["model_artifact_sha256"],
        "config": prov["config_sha256"],
        "forecast_payload": prov["forecast_payload_sha256"],
    }
    expected.update({"source:" + row["source_id"]: row["content_sha256"] for row in prov["source_snapshots"]})
    for key in required:
        if not isinstance(artifact_bytes[key], bytes) or _sha(artifact_bytes[key]) != expected[key]:
            raise JointForecastSourceAdapterError(f"{key} SHA-256 mismatch or non-bytes input")

    root = Path(archive_root).expanduser().resolve(strict=False)
    if root.exists():
        raise JointForecastSourceAdapterError("archive destination already exists")
    if any(((parent / ".git").exists() or (parent / ".git").is_file()) for parent in (root, *root.parents)):
        raise JointForecastSourceAdapterError("archive destination must be outside a Git repository")
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".covar-joint-", dir=str(root.parent)))
    os.chmod(staging, 0o700)
    entries = []
    try:
        def write(key, rel, kind, source_id=None):
            path = staging / rel
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with path.open("xb") as stream:
                stream.write(artifact_bytes[key])
            os.chmod(path, 0o600)
            row = {"forecast_id": fid, "artifact_type": kind, "archive_path": rel}
            if source_id is not None:
                row["source_id"] = source_id
            entries.append(row)
        for source in prov["source_snapshots"]:
            sid = source["source_id"]
            if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", sid) or sid in {".", ".."}:
                raise JointForecastSourceAdapterError("unsafe source_id")
            write("source:" + sid, "sources/" + sid + ".bin", "source_snapshot", sid)
        write("model_artifact", "model/model.bin", "model_artifact")
        write("config", "model/config.bin", "config")
        write("forecast_payload", "forecast/payload.bin", "forecast_payload")
        verification = verify_joint_forecast_archive(
            [{"forecast_id": fid, "provenance": prov}], staging, entries)
        # Preserve the complete validated joint-scenario document separately from
        # the source payload whose hash is declared in provenance.
        document_bytes = (json.dumps(document, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False) + "\n").encode("utf-8")
        document_path = staging / "forecast" / "validated_document.json"
        with document_path.open("xb") as stream:
            stream.write(document_bytes)
        os.chmod(document_path, 0o600)
        manifest = {
            "schema_version": "1.0.0",
            "archive_type": "PRIVATE_EXPLICIT_JOINT_COVAR_FORECAST",
            "forecast_id": fid,
            "season": intake["season"],
            "target_gameweek": intake["target_gameweek"],
            "as_of_utc": intake["as_of_utc"],
            "deadline_utc": intake["deadline_utc"],
            "intake_report": intake,
            "byte_verification": verification,
            "artifacts": entries,
            "validated_forecast_document": {
                "archive_path": "forecast/validated_document.json",
                "sha256": _sha(document_bytes),
                "byte_count": len(document_bytes),
                "scenario_count": intake["scenario_count"],
                "player_count": intake["player_count"],
                "fixture_count": intake["fixture_count"],
            },
            "privacy": {"manager_identity_included": False,
                        "manager_squad_included": False,
                        "bank_or_transfer_state_included": False,
                        "private_archive_required": True},
            "decision_weight": 0.0,
            "production_eligible": False,
            "provider_authenticity_verified": False,
            "historical_availability_authenticated": False,
        }
        mp = staging / "archive_manifest.json"
        mp.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.chmod(mp, 0o600)
        os.replace(staging, root)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {"archive_path": str(root), "archive_manifest_path": str(root / "archive_manifest.json"),
            "forecast_id": fid, "verification_status": verification["verification_status"],
            "verified_artifact_count": verification["verified_artifact_count"],
            "decision_weight": 0.0, "production_eligible": False}

def _read_regular_artifact(root: Path, relative: str) -> bytes:
    path = root / relative
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise JointForecastSourceAdapterError(f"missing artifact file: {relative}") from exc
    if not stat.S_ISREG(mode):
        raise JointForecastSourceAdapterError(f"artifact must be a regular non-symlink file: {relative}")
    return path.read_bytes()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and privately archive an explicit joint FPL forecast.")
    parser.add_argument("--document", required=True, help="Complete joint forecast JSON document.")
    parser.add_argument("--artifact-dir", required=True, help="Directory containing source/, model/ and forecast/ bytes.")
    parser.add_argument("--archive-root", required=True, help="New private archive destination outside the Git checkout.")
    args = parser.parse_args(argv)
    document_path = Path(args.document).expanduser()
    artifact_root = Path(args.artifact_dir).expanduser().resolve(strict=True)
    if not artifact_root.is_dir():
        raise JointForecastSourceAdapterError("artifact-dir must be a directory")
    try:
        document = json.loads(document_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise JointForecastSourceAdapterError(f"cannot read forecast document: {exc}") from exc
    if not isinstance(document, Mapping) or not isinstance(document.get("provenance"), Mapping):
        raise JointForecastSourceAdapterError("forecast document and provenance must be JSON objects")
    provenance = document["provenance"]
    artifact_bytes: dict[str, bytes] = {
        "model_artifact": _read_regular_artifact(artifact_root, "model/model.bin"),
        "config": _read_regular_artifact(artifact_root, "model/config.bin"),
        "forecast_payload": _read_regular_artifact(artifact_root, "forecast/payload.bin"),
    }
    snapshots = provenance.get("source_snapshots")
    if not isinstance(snapshots, list):
        raise JointForecastSourceAdapterError("provenance source_snapshots must be a list")
    for source in snapshots:
        if not isinstance(source, Mapping):
            raise JointForecastSourceAdapterError("source snapshot rows must be objects")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", source_id) or source_id in {".", ".."}:
            raise JointForecastSourceAdapterError("unsafe source_id in provenance")
        artifact_bytes["source:" + source_id] = _read_regular_artifact(
            artifact_root, "sources/" + source_id + ".bin")
    result = archive_explicit_joint_forecast(
        document=document, artifact_bytes=artifact_bytes, archive_root=args.archive_root)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except JointForecastSourceAdapterError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
