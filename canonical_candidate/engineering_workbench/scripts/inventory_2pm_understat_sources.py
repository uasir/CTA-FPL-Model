"""Inventory exact Understat source files selected by the pinned Dastan loader.

This is a provenance inventory, not a deadline-vintage admission audit. It records
whether Dastan selected a pinned CSV or a live fallback for each player/team
history and preserves the distinction between source acquisition and publication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

PLAYER_PATH = re.compile(r"^data/(20\d\d-\d\d)/understat/.+_(\d+)\.csv$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def latest_player_paths(tree_paths: list[str], wanted_ids: set[int]) -> dict[int, str]:
    latest: dict[int, tuple[str, str]] = {}
    for source in tree_paths:
        match = PLAYER_PATH.match(source)
        if not match:
            continue
        season, player_id = match.group(1), int(match.group(2))
        if player_id in wanted_ids and (
            player_id not in latest or season > latest[player_id][0]
        ):
            latest[player_id] = (season, source)
    return {player_id: value[1] for player_id, value in latest.items()}


def team_paths(tree_paths: list[str], season: str) -> list[str]:
    prefix = f"data/{season}/understat/understat_"
    return sorted(
        path for path in tree_paths
        if path.startswith(prefix)
        and path.endswith(".csv")
        and not path.endswith("understat_player.csv")
    )


def _file_record(path: Path, source_kind: str, source_path: str | None,
                 source_commit: str, manifest: dict[str, Any]) -> dict[str, Any]:
    relative = path.as_posix()
    entry = manifest.get("files", {}).get(relative, {})
    return {
        "source_kind": source_kind,
        "source_path": source_path,
        "local_path": relative,
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else None,
        "sha256": sha256(path) if path.is_file() else None,
        "manifest_sha256": entry.get("sha256"),
        "manifest_hash_matches": (
            sha256(path) == entry.get("sha256")
            if path.is_file() and entry.get("sha256") else None
        ),
        "source_commit": source_commit if source_kind.startswith("pinned") else None,
        "acquisition_at": manifest.get("created_at"),
        "historical_publication_vintage": "UNKNOWN",
    }


def build_inventory(raw_dir: Path, dastan_root: Path, seasons: list[str]) -> dict[str, Any]:
    pins = json.loads((dastan_root / "data" / "source_pins.json").read_text())
    manifest_path = raw_dir / "downloads.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    tree_path = raw_dir / "vaastav" / "tree.json"
    tree = json.loads(tree_path.read_text()) if tree_path.exists() else {"tree": []}
    if tree.get("truncated"):
        raise RuntimeError("Pinned Vaastav tree is truncated; cannot inventory sources")
    paths = [item["path"] for item in tree.get("tree", []) if item.get("type") == "blob"]
    if not paths:
        raise RuntimeError(f"Pinned Vaastav source tree is missing or empty: {tree_path}")

    assignments = pd.read_csv(dastan_root / "data" / "mappings" /
                               "fpl_understat_training_snapshot.csv")
    if "understat_id" not in assignments:
        raise ValueError("FPL-Understat mapping lacks understat_id")
    wanted = set(pd.to_numeric(assignments["understat_id"], errors="coerce").dropna().astype(int))
    selected = latest_player_paths(paths, wanted)

    players = []
    for player_id in sorted(wanted):
        pinned_path = raw_dir / "vaastav" / "understat" / "players" / f"{player_id}.csv"
        fallback_path = raw_dir / "understat" / "players" / f"{player_id}.json"
        if fallback_path.is_file():
            record = _file_record(fallback_path, "live_player_fallback", None,
                                  pins["vaastav"]["commit"], manifest)
        elif pinned_path.is_file():
            record = _file_record(pinned_path, "pinned_player_csv", selected.get(player_id),
                                  pins["vaastav"]["commit"], manifest)
        else:
            record = _file_record(pinned_path, "missing_player_source", selected.get(player_id),
                                  pins["vaastav"]["commit"], manifest)
        record.update({"understat_id": player_id,
                       "selected_pinned_tree_path": selected.get(player_id)})
        players.append(record)

    teams = []
    for season in seasons:
        pinned_sources = team_paths(paths, season)
        local_dir = raw_dir / "vaastav" / "understat" / "teams" / season
        local_files = sorted(local_dir.glob("*.csv"))
        fallback = raw_dir / "understat" / "teams" / f"{season}.json"
        if fallback.is_file():
            teams.append(_file_record(fallback, "live_team_fallback", None,
                                      pins["vaastav"]["commit"], manifest) |
                         {"season": season})
        elif local_files:
            for path in local_files:
                source_name = path.name
                source_path = next((p for p in pinned_sources if p.endswith("/" + source_name)), None)
                teams.append(_file_record(path, "pinned_team_csv", source_path,
                                          pins["vaastav"]["commit"], manifest) |
                             {"season": season})
        else:
            teams.append({
                "season": season, "source_kind": "missing_team_source",
                "source_paths_expected": pinned_sources, "exists": False,
                "historical_publication_vintage": "UNKNOWN",
                "acquisition_at": manifest.get("created_at"),
            })

    counts: dict[str, int] = {}
    for row in players + teams:
        key = row["source_kind"]
        counts[key] = counts.get(key, 0) + 1
    return {
        "schema_version": 1,
        "audit_type": "understat_source_file_inventory_not_deadline_vintage",
        "dastan_repository_commit": "758db9247e8b3a9a870c991064f74d8339d61cd0",
        "vaastav_repository": pins["vaastav"]["repository"],
        "vaastav_commit": pins["vaastav"]["commit"],
        "seasons": seasons,
        "download_manifest_created_at": manifest.get("created_at"),
        "source_kind_counts": counts,
        "players": players,
        "teams": teams,
        "admission_decision": "NO_FEATURES_ADMITTED",
        "historical_publication_vintage_claim": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--dastan-root", type=Path, required=True)
    parser.add_argument("--seasons", default="2020-21,2021-22,2022-23,2023-24,2024-25,2025-26")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--detail-output", type=Path, required=True)
    args = parser.parse_args()
    report = build_inventory(args.raw_dir, args.dastan_root, args.seasons.split(","))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    rows = report["players"] + report["teams"]
    pd.DataFrame(rows).to_csv(args.detail_output, index=False)
    print(json.dumps({"source_kind_counts": report["source_kind_counts"],
                      "player_records": len(report["players"]),
                      "team_records": len(report["teams"]),
                      "admission_decision": report["admission_decision"]}, indent=2))


if __name__ == "__main__":
    main()
