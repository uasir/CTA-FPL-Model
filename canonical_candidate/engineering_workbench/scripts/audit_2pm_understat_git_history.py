"""Trace Understat CSV row/value revisions in the pinned Vaastav Git history.

Repository commit timestamps are repository-lineage evidence only. They are not
Understat publication timestamps and must not be treated as proof of public
availability. Live fallback JSONs have no historical revision chain here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
import requests

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
DEFAULT_REPOSITORY = "vaastav/Fantasy-Premier-League"


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_json(session: requests.Session, url: str, params: dict[str, Any] | None = None):
    response = session.get(url, params=params, headers=_headers(), timeout=45)
    if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
        reset = int(response.headers.get("X-RateLimit-Reset", "0"))
        raise RuntimeError(f"GitHub API rate limit exhausted; reset epoch {reset}")
    response.raise_for_status()
    return response.json()


def _get_text(session: requests.Session, url: str) -> bytes:
    response = session.get(url, headers=_headers(), timeout=45)
    response.raise_for_status()
    return response.content


def list_path_commits(session: requests.Session, repository: str, path: str,
                      pinned_commit: str, max_commits: int) -> list[dict[str, Any]]:
    url = f"{API}/repos/{repository}/commits"
    commits: list[dict[str, Any]] = []
    page = 1
    while len(commits) < max_commits:
        batch = _get_json(session, url, {
            "path": path, "sha": pinned_commit, "per_page": min(100, max_commits-len(commits)),
            "page": page,
        })
        if not batch:
            break
        commits.extend(batch)
        if len(batch) < min(100, max_commits-(len(commits)-len(batch))):
            break
        page += 1
        time.sleep(0.08)
    return commits[:max_commits]


def _row_key(row: dict[str, Any], kind: str, player_id: int | None = None) -> str:
    date = str(row.get("date", "")).strip()
    if kind == "player":
        # Pinned Dastan loader enforces uniqueness on (understat_id, date_only).
        identity = player_id if player_id is not None else row.get("understat_id", "")
        return "|".join((str(identity).strip(), date[:10]))
    # Team files are per-team; date + fixture home/away names identify the match.
    home = str(row.get("h_team", row.get("h", ""))).strip()
    away = str(row.get("a_team", row.get("a", ""))).strip()
    return "|".join((date[:10], home, away))


def audit_file(session: requests.Session, repository: str, pinned_commit: str,
               source_path: str, kind: str, max_commits: int, player_id: int | None = None) -> dict[str, Any]:
    commits = list_path_commits(session, repository, source_path, pinned_commit, max_commits)
    # API returns newest first; process oldest to newest so first-seen and revisions are explicit.
    commits = list(reversed(commits))
    row_history: dict[str, dict[str, Any]] = {}
    commit_rows = []
    errors = []
    for index, commit in enumerate(commits):
        sha = commit["sha"]
        committed_at = commit["commit"]["committer"]["date"]
        raw_url = f"{RAW}/{repository}/{sha}/{quote(source_path)}"
        try:
            payload = _get_text(session, raw_url)
            digest = hashlib.sha256(payload).hexdigest()
            frame = pd.read_csv(io.BytesIO(payload), low_memory=False).fillna("")
            current: dict[str, str] = {}
            duplicate_keys: set[str] = set()
            for row in frame.to_dict("records"):
                key = _row_key(row, kind, player_id)
                if not key.strip("|"):
                    continue
                # Exclude volatile row index; compare all source fields as serialized values.
                signature = json.dumps({str(k): str(v) for k, v in row.items()},
                                       sort_keys=True, separators=(",", ":"))
                if key in current:
                    duplicate_keys.add(key)
                current[key] = signature
                previous = row_history.get(key)
                if previous is None:
                    row_history[key] = {
                        "first_seen_commit": sha, "first_seen_at": committed_at,
                        "first_value_signature": signature, "latest_value_signature": signature,
                        "latest_commit": sha, "latest_at": committed_at,
                        "last_seen_commit": sha, "last_seen_at": committed_at,
                        "value_revision_count": 0, "missing_revision_count": 0,
                        "reappearance_count": 0, "present_in_latest_revision": True,
                    }
                else:
                    if not previous["present_in_latest_revision"]:
                        previous["reappearance_count"] += 1
                    previous["last_seen_commit"] = sha
                    previous["last_seen_at"] = committed_at
                    previous["present_in_latest_revision"] = True
                    if previous["latest_value_signature"] != signature:
                        previous["value_revision_count"] += 1
                        previous["latest_value_signature"] = signature
                        previous["latest_commit"] = sha
                        previous["latest_at"] = committed_at
            for key, previous in row_history.items():
                if key not in current:
                    previous["missing_revision_count"] += 1
                    previous["present_in_latest_revision"] = False
            if duplicate_keys:
                raise ValueError(
                    f"{len(duplicate_keys)} duplicate row keys in {source_path} at {sha}; "
                    f"sample={sorted(duplicate_keys)[:5]}"
                )
            commit_rows.append({
                "commit": sha, "committed_at": committed_at,
                "file_sha256": digest, "rows": len(frame),
                "distinct_row_keys": len(current),
            })
        except Exception as exc:  # retain a visible incomplete result; never imply completeness
            errors.append({"commit": sha, "committed_at": committed_at, "error": str(exc)})
    return {
        "source_path": source_path, "source_kind": f"pinned_{kind}_csv",
        "pinned_commit": pinned_commit, "commit_count_returned": len(commits),
        "history_truncated": len(commits) >= max_commits,
        "commit_rows": commit_rows, "row_history": row_history, "errors": errors,
        "historical_publication_vintage": "UNKNOWN",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--pinned-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-commits-per-file", type=int, default=1000)
    parser.add_argument("--limit-files", type=int, default=0,
                        help="Optional smoke-test cap; 0 means all pinned CSV files")
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text())
    sources = []
    for row in inventory["players"]:
        if row["source_kind"] == "pinned_player_csv" and row.get("selected_pinned_tree_path"):
            sources.append(("player", row["selected_pinned_tree_path"], int(row["understat_id"])))
    for row in inventory["teams"]:
        if row["source_kind"] == "pinned_team_csv" and row.get("source_path"):
            sources.append(("team", row["source_path"], None))
    if args.limit_files:
        sources = sources[:args.limit_files]
    session = requests.Session()
    results = []
    for number, (kind, path, player_id) in enumerate(sources, 1):
        print(f"[{number}/{len(sources)}] {kind} {path}", flush=True)
        try:
            results.append(audit_file(session, args.repository, args.pinned_commit,
                                      path, kind, args.max_commits_per_file, player_id))
        except Exception as exc:
            results.append({"source_path": path, "source_kind": f"pinned_{kind}_csv",
                            "error": str(exc), "historical_publication_vintage": "UNKNOWN"})
    report = {
        "schema_version": 1,
        "audit_type": "understat_pinned_git_row_revision_history",
        "repository": args.repository, "pinned_commit": args.pinned_commit,
        "files_requested": len(sources), "files_audited": len(results),
        "results": results,
        "limitations": [
            "Git commit timestamps are repository-lineage evidence, not original Understat publication timestamps.",
            "A file revision's commit time does not prove public visibility at that exact time.",
            "Live fallback JSONs are excluded because they have no pinned repository revision chain.",
            "Files whose history reaches max_commits_per_file are explicitly truncated.",
            "Row keys are provisional date/match identifiers and require reconciliation against FPL fixture IDs.",
        ],
        "admission_decision": "NO_FEATURES_ADMITTED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"files_requested": len(sources), "files_audited": len(results),
                      "files_with_errors": sum(bool(r.get("error") or r.get("errors")) for r in results),
                      "admission_decision": report["admission_decision"]}, indent=2))


if __name__ == "__main__":
    main()
