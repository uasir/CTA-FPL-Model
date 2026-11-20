"""Private shared partition-key reader for matched ABC/2PM experiments."""
from __future__ import annotations
import csv
import hashlib
from collections import defaultdict
from pathlib import Path

PARTITIONS = ("fit", "calibration", "test")

def canonical_season(value):
    raw = str(value).strip().replace("/", "-")
    parts = raw.split("-")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise ValueError(f"Unsupported season label in matched keys: {raw!r}")
    return f"{parts[0]}-{parts[1][-2:]}"

def canonical_key(season, player_id, gameweek):
    return (canonical_season(season), str(player_id).strip(), int(gameweek))

def sha_keys(keys):
    payload = "\n".join("|".join(map(str, key)) for key in sorted(keys))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def load_partition_keys(path):
    grouped = defaultdict(lambda: {name: [] for name in PARTITIONS})
    seen = set()
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            fold = int(row["fold"])
            partition = str(row["partition"]).strip()
            if partition not in PARTITIONS:
                raise ValueError(f"Unknown matched partition: {partition}")
            key = canonical_key(row["season"], row["fpl_element_id"], row["gameweek"])
            marker = (fold, partition, key)
            if marker in seen:
                raise ValueError(f"Duplicate matched partition key: {marker}")
            seen.add(marker)
            grouped[fold][partition].append(key)
    if not grouped:
        raise ValueError("Matched partition-key CSV is empty")
    result = {}
    for fold, parts in sorted(grouped.items()):
        sets = {name: set(parts[name]) for name in PARTITIONS}
        if any(not parts[name] for name in PARTITIONS):
            raise ValueError(f"Fold {fold} has an empty fit/calibration/test partition")
        if sets["fit"] & sets["calibration"] or sets["fit"] & sets["test"] or sets["calibration"] & sets["test"]:
            raise ValueError(f"Fold {fold} partitions overlap")
        result[fold] = {name: sorted(sets[name]) for name in PARTITIONS}
    return result

def verify_manifest_partition_hashes(partitions, manifest):
    if manifest.get("status") != "PASS_MATCHED_FOLD_MANIFEST":
        raise ValueError("Matched fold manifest is not in PASS_MATCHED_FOLD_MANIFEST state")
    manifest_folds = {int(item["fold"]): item for item in manifest.get("folds", [])}
    if any(item.get("status") != "READY" for item in manifest_folds.values()):
        raise ValueError("Matched fold manifest contains a blocked fold")
    if set(partitions) != set(manifest_folds):
        raise ValueError("Private partition CSV fold IDs do not match the public manifest")
    for fold, parts in partitions.items():
        expected = manifest_folds[fold]
        for name in PARTITIONS:
            actual_hash = sha_keys(parts[name])
            expected_hash = expected.get(f"{name}_key_sha256")
            if actual_hash != expected_hash:
                raise ValueError(f"Fold {fold} {name} partition hash differs from manifest")
    return True
