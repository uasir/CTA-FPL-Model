#!/usr/bin/env python3
"""Create a private, manager-free archive from one sealed M3 decision run.

This tool must run only after the M3 evidence bundle and frozen result exist.
It delegates all provenance and forecast-equivalence checks to the M3 CoVar
adapter, then writes only the sanitized forecast bundle and a hash manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from m3_covar_forecast_snapshot_adapter import extract_m3_covar_forecast_bundle
from m3_covar_forecast_anchor_acceptance import accept_m3_forecast_anchor


class M3CoVarArchivePackagingError(ValueError):
    """The sanitized M3 forecast archive could not be safely written."""


def _load_json(path: Path, label: str) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise M3CoVarArchivePackagingError(f"{label} is not readable JSON") from exc
    if not isinstance(value, Mapping):
        raise M3CoVarArchivePackagingError(f"{label} must contain a JSON object")
    return value


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def package_m3_covar_forecast_archive(
    *,
    evidence_path: Path,
    result_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Validate, sanitize, and write a new private archive directory."""
    evidence_path = Path(evidence_path).resolve()
    result_path = Path(result_path).resolve()
    output_dir = Path(output_dir).resolve()
    repo_root = _repo_root()
    if output_dir == repo_root or repo_root in output_dir.parents:
        raise M3CoVarArchivePackagingError("output directory must be outside the repository")
    if output_dir.exists():
        raise M3CoVarArchivePackagingError("output directory already exists; refusing overwrite")
    evidence = _load_json(evidence_path, "M3 evidence bundle")
    result = _load_json(result_path, "M3 decision result")

    sanitized = extract_m3_covar_forecast_bundle(evidence, result)
    if sanitized.get("privacy") != {
        "manager_identity_included": False,
        "manager_squad_included": False,
        "bank_or_transfer_state_included": False,
        "frozen_decision_included": False,
    }:
        raise M3CoVarArchivePackagingError("sanitized bundle privacy contract failed")
    if sanitized.get("decision_weight") != 0.0 or sanitized.get("production_eligible") is not False:
        raise M3CoVarArchivePackagingError("CoVar research-only contract failed")

    try:
        output_dir.mkdir(parents=True, mode=0o700)
        os.chmod(output_dir, 0o700)
        bundle_name = f"m3_covar_forecast_gw{int(sanitized['target_gameweek'])}.json"
        bundle_path = output_dir / bundle_name
        bundle_bytes = (json.dumps(
            sanitized, sort_keys=True, indent=2, allow_nan=False
        ) + "\n").encode("utf-8")
        fd = os.open(bundle_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(bundle_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(bundle_path, 0o600)

        manifest = {
            "schema_version": "1.0.0",
            "archive_type": "PRIVATE_MANAGER_FREE_M3_COVAR_FORECAST_ARCHIVE",
            "season": sanitized["season"],
            "target_gameweek": sanitized["target_gameweek"],
            "as_of_utc": sanitized["as_of_utc"],
            "deadline_utc": sanitized["deadline_utc"],
            "forecast_snapshot_id": sanitized["forecast_snapshot_id"],
            "model_version": sanitized["model_version"],
            "bundle_file": bundle_name,
            "bundle_sha256": hashlib.sha256(bundle_bytes).hexdigest(),
            "bundle_bytes": len(bundle_bytes),
            "source_archives": [
                {
                    "source_type": source["source_type"],
                    "raw_snapshot_id": source["raw_snapshot_id"],
                    "raw_sha256": source["raw_sha256"],
                    "captured_at_utc": source["captured_at_utc"],
                    "source_url": source["source_url"],
                }
                for source in sanitized["source_archives"]
            ],
            "privacy": dict(sanitized["privacy"]),
            "decision_weight": 0.0,
            "production_eligible": False,
            "point_in_time_status": sanitized["point_in_time_status"],
            "retention": "PRIVATE_DESTINATION_POLICY_REQUIRED",
        }
        anchor_acceptance = accept_m3_forecast_anchor(bundle_bytes, manifest)
        manifest["anchor_acceptance"] = anchor_acceptance
        manifest_bytes = (json.dumps(
            manifest, sort_keys=True, indent=2, allow_nan=False
        ) + "\n").encode("utf-8")
        manifest_path = output_dir / "archive_manifest.json"
        fd = os.open(manifest_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(manifest_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(manifest_path, 0o600)
    except Exception:
        # Leave no partial archive that could be mistaken for a completed capture.
        for child in output_dir.glob("*") if output_dir.exists() else []:
            try:
                child.unlink()
            except OSError:
                pass
        try:
            output_dir.rmdir()
        except OSError:
            pass
        raise

    return {
        "status": "PASS_MANAGER_FREE_ARCHIVE_CREATED",
        "archive_dir": str(output_dir),
        "bundle_file": bundle_name,
        "bundle_sha256": manifest["bundle_sha256"],
        "manifest_file": str(manifest_path),
        "forecast_snapshot_id": sanitized["forecast_snapshot_id"],
        "target_gameweek": sanitized["target_gameweek"],
        "decision_weight": 0.0,
        "production_eligible": False,
        "anchor_acceptance_status": anchor_acceptance["acceptance_status"],
        "joint_distribution_available": False,
        "private_destination_configured": False,
        "note": "This creates a local private archive only; a private durable storage destination and retention policy remain separate requirements.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True,
                        help="Sealed M3 evidence JSON from the pre-deadline capture")
    parser.add_argument("--m3-result", type=Path, required=True,
                        help="Frozen conventional M3 recommendation result JSON")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="New absolute directory outside the repository")
    args = parser.parse_args()
    if not args.output_dir.is_absolute():
        raise M3CoVarArchivePackagingError("--output-dir must be absolute")
    result = package_m3_covar_forecast_archive(
        evidence_path=args.evidence,
        result_path=args.m3_result,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
