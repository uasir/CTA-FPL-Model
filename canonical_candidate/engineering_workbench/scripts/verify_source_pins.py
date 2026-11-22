#!/usr/bin/env python3
"""Verify pinned source files and emit a reproducible SHA-256 acquisition manifest.

Pin file contract:
{
  "schema_version": 1,
  "sources": [{
    "source_id": "vaastav-fpl",
    "repository": "Vaastav/Fantasy-Premier-League",
    "commit": "<40-character commit SHA>",
    "files": [{"path": "data/2026-27/merged_gw.csv", "sha256": "<64 hex>", "required": true}]
  }]
}

The verifier never downloads or mutates source data. It fails closed on missing
required files, malformed pins, path traversal, and digest mismatches.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _safe_source_path(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"unsafe source path: {relative!r}")
    resolved_root = root.resolve()
    candidate = (resolved_root / Path(*pure.parts)).resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise ValueError(f"source path escapes root: {relative!r}")
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_source_pins(pin_document: dict, source_root: Path) -> dict:
    if pin_document.get("schema_version") != 1:
        raise ValueError("source pin schema_version must equal 1")
    sources = pin_document.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("source pins must contain a non-empty sources list")

    seen_source_ids: set[str] = set()
    verified_sources = []
    failures = []
    for source in sources:
        source_id = str(source.get("source_id", "")).strip()
        repository = str(source.get("repository", "")).strip()
        commit = str(source.get("commit", "")).lower().strip()
        if not source_id or source_id in seen_source_ids:
            raise ValueError(f"blank or duplicate source_id: {source_id!r}")
        seen_source_ids.add(source_id)
        if not repository or not _SHA1.fullmatch(commit):
            raise ValueError(f"{source_id}: repository and full 40-character commit SHA are required")
        files = source.get("files")
        if not isinstance(files, list) or not files:
            raise ValueError(f"{source_id}: files must be a non-empty list")

        verified_files = []
        for item in files:
            relative = str(item.get("path", "")).strip()
            expected = str(item.get("sha256", "")).lower().strip()
            required = item.get("required", True)
            if not relative or not isinstance(required, bool):
                raise ValueError(f"{source_id}: each file needs path and boolean required")
            if not _SHA256.fullmatch(expected):
                raise ValueError(f"{source_id}:{relative}: expected a full SHA-256 digest")
            path = _safe_source_path(source_root, relative)
            if not path.is_file():
                status = "MISSING_REQUIRED" if required else "MISSING_OPTIONAL"
                verified_files.append({"path": relative, "status": status, "expected_sha256": expected, "actual_sha256": None})
                if required:
                    failures.append(f"{source_id}:{relative}: required file is missing")
                continue
            actual = _sha256(path)
            status = "VERIFIED" if actual == expected else "HASH_MISMATCH"
            verified_files.append({"path": relative, "status": status, "expected_sha256": expected, "actual_sha256": actual})
            if actual != expected:
                failures.append(f"{source_id}:{relative}: SHA-256 mismatch")

        verified_sources.append({
            "source_id": source_id,
            "repository": repository,
            "commit": commit,
            "files": verified_files,
        })

    report = {
        "schema_version": 1,
        "verification_status": "PASS" if not failures else "FAIL",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_count": len(verified_sources),
        "file_count": sum(len(source["files"]) for source in verified_sources),
        "failures": failures,
        "sources": verified_sources,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pins", type=Path, required=True, help="JSON source pin document")
    parser.add_argument("--source-root", type=Path, required=True, help="Root containing acquired source files")
    parser.add_argument("--out", type=Path, required=True, help="Output verification manifest JSON")
    args = parser.parse_args()

    pins = json.loads(args.pins.read_text(encoding="utf-8"))
    report = verify_source_pins(pins, args.source_root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "sources"}, indent=2))
    return 0 if report["verification_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
