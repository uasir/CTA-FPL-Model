#!/usr/bin/env python3
"""Fetch a SHA-pinned StatsBomb Open Data sample from GitHub.

This is an input-staging utility only. It does not run the CTA model or
validate feature correctness. Every downloaded file is verified against its
Git blob SHA-1 and recorded byte size before being atomically installed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

REPO = "hudl/open-data"
HEX40 = re.compile(r"^[0-9a-f]{40}$")


class IntegrityError(RuntimeError):
    pass


def git_blob_sha1(payload: bytes) -> str:
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def verify_payload(payload: bytes, expected_sha: str, expected_size: int) -> None:
    if len(payload) != expected_size:
        raise IntegrityError(
            f"size mismatch: expected {expected_size}, received {len(payload)}"
        )
    actual_sha = git_blob_sha1(payload)
    if actual_sha != expected_sha:
        raise IntegrityError(
            f"Git blob SHA mismatch: expected {expected_sha}, received {actual_sha}"
        )


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def fetch_verified(
    url: str,
    destination: Path,
    expected_sha: str,
    expected_size: int,
    *,
    timeout: int = 90,
    retries: int = 3,
    opener=urlopen,
    sleep=time.sleep,
) -> str:
    if not HEX40.fullmatch(expected_sha):
        raise ValueError(f"Invalid Git blob SHA: {expected_sha!r}")
    if expected_size < 0:
        raise ValueError("Expected size must be non-negative")

    if destination.exists():
        existing = destination.read_bytes()
        try:
            verify_payload(existing, expected_sha, expected_size)
            return "existing_verified"
        except IntegrityError:
            # Never trust or silently keep a corrupt partial file.
            destination.unlink()

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            request = Request(url, headers={"User-Agent": "CTA-FPL-Model-data-stager/1.0"})
            with opener(request, timeout=timeout) as response:
                payload = response.read()
            verify_payload(payload, expected_sha, expected_size)
            _atomic_write(destination, payload)
            return "downloaded_verified"
        except (HTTPError, URLError, TimeoutError, OSError, IntegrityError) as exc:
            last_error = exc
            if attempt < retries:
                sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"Failed to fetch and verify {url}: {last_error}") from last_error


def validate_manifest(manifest: dict) -> tuple[str, list[dict]]:
    source = manifest.get("source") or {}
    if source.get("repository") != REPO:
        raise ValueError(f"Manifest repository must be {REPO}")
    commit = source.get("commit_sha")
    if not isinstance(commit, str) or not HEX40.fullmatch(commit):
        raise ValueError("Manifest source.commit_sha must be a 40-character Git SHA")
    matches = manifest.get("matches")
    if not isinstance(matches, list) or not matches:
        raise ValueError("Manifest must contain a non-empty matches array")
    seen = set()
    for item in matches:
        match_id = str(item.get("match_id", ""))
        if not match_id.isdigit() or match_id in seen:
            raise ValueError(f"Invalid or duplicate match_id: {match_id!r}")
        seen.add(match_id)
        if not HEX40.fullmatch(str(item.get("events_blob_sha", ""))):
            raise ValueError(f"Missing/invalid events blob SHA for match {match_id}")
        if not isinstance(item.get("events_size_bytes"), int):
            raise ValueError(f"Missing/invalid events size for match {match_id}")
        has_360 = item.get("has_360")
        if not isinstance(has_360, bool):
            raise ValueError(f"Missing/invalid has_360 flag for match {match_id}")
        has_360_source = item.get("has_360_source", has_360)
        if not isinstance(has_360_source, bool):
            raise ValueError(f"Missing/invalid has_360_source flag for match {match_id}")
        if has_360 and not has_360_source:
            raise ValueError(f"Usable 360 data must have a source for match {match_id}")
        if has_360_source:
            if not HEX40.fullmatch(str(item.get("three_sixty_blob_sha", ""))):
                raise ValueError(f"Missing/invalid 360 blob SHA for match {match_id}")
            if not isinstance(item.get("three_sixty_size_bytes"), int):
                raise ValueError(f"Missing/invalid 360 size for match {match_id}")
            if not has_360 and not str(item.get("three_sixty_exclusion_reason", "")).strip():
                raise ValueError(f"Excluded 360 source requires a reason for match {match_id}")
        elif item.get("three_sixty_blob_sha") is not None:
            raise ValueError(f"Unexpected 360 blob SHA for unavailable match {match_id}")
    return commit, matches


def download_sample(
    manifest: dict,
    output_dir: Path,
    *,
    timeout: int = 90,
    retries: int = 3,
    opener=urlopen,
    sleep=time.sleep,
) -> dict:
    commit, matches = validate_manifest(manifest)
    report = {
        "status": "running",
        "repository": REPO,
        "commit_sha": commit,
        "matches_requested": len(matches),
        "events_verified": 0,
        "three_sixty_verified": 0,
        "three_sixty_unavailable": 0,
        "three_sixty_excluded": 0,
        "excluded_sources": [],
        "failures": [],
        "files": [],
    }
    base = f"https://raw.githubusercontent.com/{REPO}/{commit}/data"
    for item in matches:
        match_id = str(item["match_id"])
        tasks = [
            (
                "events",
                f"{base}/events/{match_id}.json",
                output_dir / "events" / f"{match_id}.json",
                item["events_blob_sha"],
                item["events_size_bytes"],
            )
        ]
        if item["has_360"]:
            tasks.append((
                "three_sixty",
                f"{base}/three-sixty/{match_id}.json",
                output_dir / "three-sixty" / f"{match_id}.json",
                item["three_sixty_blob_sha"],
                item["three_sixty_size_bytes"],
            ))
        elif item.get("has_360_source", False):
            report["three_sixty_excluded"] += 1
            report["excluded_sources"].append({
                "match_id": int(match_id),
                "blob_sha": item["three_sixty_blob_sha"],
                "size_bytes": item["three_sixty_size_bytes"],
                "reason": item["three_sixty_exclusion_reason"],
            })
        else:
            report["three_sixty_unavailable"] += 1

        for kind, url, destination, sha, size in tasks:
            try:
                status = fetch_verified(
                    url, destination, sha, size,
                    timeout=timeout, retries=retries, opener=opener, sleep=sleep,
                )
                if kind == "events":
                    report["events_verified"] += 1
                else:
                    report["three_sixty_verified"] += 1
                report["files"].append({
                    "match_id": int(match_id), "kind": kind,
                    "path": str(destination), "blob_sha": sha,
                    "size_bytes": size, "status": status,
                })
            except Exception as exc:  # retain all failures for the run report
                report["failures"].append({
                    "match_id": int(match_id), "kind": kind,
                    "url": url, "error": str(exc),
                })

    report["status"] = "passed" if not report["failures"] else "failed"
    report["matches_with_events_verified"] = report["events_verified"]
    report["expected_360_unavailable"] = report["three_sixty_unavailable"]
    report["expected_360_excluded"] = report["three_sixty_excluded"]
    output_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(
        output_dir / "download_report.json",
        json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8"),
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = download_sample(
        manifest, args.output_dir, timeout=args.timeout, retries=args.retries
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())