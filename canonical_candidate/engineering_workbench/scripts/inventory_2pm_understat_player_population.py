"""Inventory the complete Dastan-mapped Understat player population.

Source-coverage inventory only; no row-vintage or feature-admission claim.
Selection mirrors Dastan's _latest_player_paths() semantics.
"""
from __future__ import annotations
import argparse, csv, json, os, re, tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any
import requests

VAASTAV_REPOSITORY = "vaastav/Fantasy-Premier-League"
VAASTAV_COMMIT = "8c97b2adb123863c3dd581e730f1360e89815ac2"
DASTAN_REPOSITORY = "qazybekb/smartplayfpl-dastan"
DASTAN_COMMIT = "758db9247e8b3a9a870c991064f74d8339d61cd0"
ASSIGNMENT_PATH = "data/mappings/fpl_understat_training_assignments.csv"
PLAYER_PATH = re.compile(r"^data/(20\d\d-\d\d)/understat/.+_(\d+)\.csv$")

def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    temporary.replace(path)

def cached_get(session: requests.Session, url: str, cache: Path) -> bytes:
    if cache.is_file() and cache.stat().st_size:
        return cache.read_bytes()
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = session.get(url, headers=headers, timeout=90)
    response.raise_for_status()
    if not response.content:
        raise RuntimeError(f"Empty response for {url}")
    atomic_write(cache, response.content)
    return response.content

def read_assignments(payload: bytes) -> list[dict[str, Any]]:
    rows = list(csv.DictReader(payload.decode("utf-8-sig").splitlines()))
    required = {"season", "fpl_code", "understat_id", "first_gameweek", "last_gameweek"}
    if not rows or required - set(rows[0]):
        raise ValueError(f"Assignment file missing required columns: {sorted(required - set(rows[0] if rows else []))}")
    for row in rows:
        for field in ("fpl_code", "understat_id", "first_gameweek", "last_gameweek"):
            row[field] = int(row[field])
        if row["first_gameweek"] > row["last_gameweek"]:
            raise ValueError(f"Invalid Gameweek interval: {row}")
    if len({(r["season"], r["fpl_code"]) for r in rows}) != len(rows):
        raise ValueError("Duplicate (season, fpl_code) assignment rows")
    return rows

def latest_player_paths(tree: dict[str, Any], wanted: set[int]):
    if tree.get("truncated") is not False:
        raise RuntimeError("Pinned Vaastav recursive Git tree is truncated or lacks explicit false")
    candidates = defaultdict(list)
    for item in tree.get("tree", []):
        if item.get("type") != "blob":
            continue
        match = PLAYER_PATH.match(item.get("path", ""))
        if match:
            season, raw_id = match.groups()
            player_id = int(raw_id)
            if player_id in wanted:
                candidates[player_id].append((season, item["path"]))
    selected, paths_by_id = {}, {}
    for player_id, values in candidates.items():
        paths_by_id[player_id] = [path for _, path in values]
        season, path = max(values, key=lambda item: item[0])
        selected[player_id] = {"season": season, "path": path}
    return selected, paths_by_id

def build_report(assignments, tree):
    wanted = {row["understat_id"] for row in assignments}
    selected, paths_by_id = latest_player_paths(tree, wanted)
    by_season, by_id_season = defaultdict(list), defaultdict(list)
    for row in assignments:
        by_season[row["season"]].append(row)
        by_id_season[(row["season"], row["understat_id"])].append(row)
    collisions = []
    for (season, player_id), group in sorted(by_id_season.items()):
        codes = sorted({row["fpl_code"] for row in group})
        if len(codes) < 2:
            continue
        overlaps = []
        for i, left in enumerate(group):
            for right in group[i + 1:]:
                if left["fpl_code"] == right["fpl_code"]:
                    continue
                start = max(left["first_gameweek"], right["first_gameweek"])
                end = min(left["last_gameweek"], right["last_gameweek"])
                if start <= end:
                    overlaps.append({"fpl_code_a": left["fpl_code"], "fpl_code_b": right["fpl_code"],
                                     "overlap_first_gameweek": start, "overlap_last_gameweek": end})
        collisions.append({"season": season, "understat_id": player_id, "fpl_codes": codes,
                           "overlapping_assignment_intervals": overlaps,
                           "identity_status": "AMBIGUOUS_OVERLAPPING_ASSIGNMENT" if overlaps
                           else "SHARED_ID_NONOVERLAPPING_INTERVALS"})
    detail = []
    collision_map = {(c["season"], c["understat_id"]): c for c in collisions}
    for row in assignments:
        player_id = row["understat_id"]
        source = selected.get(player_id)
        collision = collision_map.get((row["season"], player_id))
        detail.append({**row,
            "selected_pinned_path": source["path"] if source else None,
            "selected_file_season": source["season"] if source else None,
            "all_pinned_paths_for_id": ";".join(paths_by_id.get(player_id, [])),
            "pinned_path_status": "PINNED_PATH_FOUND" if source else "PINNED_PATH_ABSENT_FALLBACK_CANDIDATE",
            "identity_status": collision["identity_status"] if collision else "NO_SHARED_ID_COLLISION_IN_SEASON",
            "source_publication_vintage": "UNKNOWN"})
    season_summary = {}
    for season, rows in sorted(by_season.items()):
        ids = {row["understat_id"] for row in rows}
        missing = ids - set(selected)
        shared = [c for c in collisions if c["season"] == season]
        season_summary[season] = {
            "assignment_rows": len(rows), "unique_understat_ids": len(ids),
            "ids_with_selected_pinned_path": len(ids - missing),
            "ids_without_selected_pinned_path": len(missing),
            "shared_understat_id_groups": len(shared),
            "overlapping_assignment_groups": sum(c["identity_status"] == "AMBIGUOUS_OVERLAPPING_ASSIGNMENT" for c in shared)}
    report = {
        "schema_version": 1,
        "audit_type": "complete_dastan_mapped_understat_player_population_inventory",
        "dastan_repository": DASTAN_REPOSITORY, "dastan_commit": DASTAN_COMMIT,
        "assignment_path": ASSIGNMENT_PATH, "vaastav_repository": VAASTAV_REPOSITORY,
        "vaastav_commit": VAASTAV_COMMIT, "assignment_rows": len(assignments),
        "unique_understat_ids_across_seasons": len(wanted),
        "unique_ids_with_selected_pinned_player_csv": len(selected),
        "unique_ids_without_selected_pinned_player_csv": len(wanted - set(selected)),
        "pinned_player_csv_paths_discovered_for_mapped_ids": sum(len(v) for v in paths_by_id.values()),
        "shared_id_collision_groups": collisions, "season_summary": season_summary,
        "limitations": [
            "This inventory mirrors Dastan's latest-season-path selection; it does not audit CSV row histories or feature values.",
            "A missing pinned path is a fallback candidate, not proof that a successful live fallback was captured in the candidate build.",
            "A present pinned path may be incomplete and may be superseded by Dastan's live fallback after its expected-date completeness check.",
            "Git-tree presence and commit timestamps do not establish original Understat public-publication time.",
            "Overlapping assignments for a shared Understat ID are identity ambiguities and must not be silently joined."],
        "admission_decision": "NO_FEATURES_ADMITTED", "training_authorized": False}
    return report, detail

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--detail-output", type=Path, required=True)
    args = parser.parse_args()
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    assignment_url = f"https://raw.githubusercontent.com/{DASTAN_REPOSITORY}/{DASTAN_COMMIT}/{ASSIGNMENT_PATH}"
    assignment_payload = cached_get(session, assignment_url, args.cache_dir / "dastan-assignments.csv")
    tree_url = f"https://api.github.com/repos/{VAASTAV_REPOSITORY}/git/trees/{VAASTAV_COMMIT}?recursive=1"
    tree_payload = cached_get(session, tree_url, args.cache_dir / "vaastav-pinned-tree.json")
    report, detail = build_report(read_assignments(assignment_payload), json.loads(tree_payload))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    with args.detail_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(detail[0]))
        writer.writeheader()
        writer.writerows(detail)
    print(json.dumps({k:v for k,v in report.items() if k not in {"shared_id_collision_groups","season_summary","limitations"}}, indent=2))
    print(json.dumps({"season_summary":report["season_summary"],"shared_id_collision_groups":report["shared_id_collision_groups"]}, indent=2))

if __name__ == "__main__":
    main()
