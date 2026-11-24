"""Prepare isolated 2025/26 inputs from the pinned run-80 tensor artifact.

The warm-up path reads only identity plus the schema-derived defensive features.
The label-coverage path copies only 2025/26 metadata files; it never reads OOT
metadata, tensor labels, or target-score distributions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from audit_2pm_defensive_warmup import (
    IDENTITY_COLUMNS,
    derive_defensive_features,
    sha256,
)


ARTIFACT_POSTMATCH = Path(
    "2pm-dastan-candidate/postmatch-grouped-dataset/postmatch_states.parquet"
)
ARTIFACT_TENSORS = Path(
    "2pm-dastan-candidate/postmatch-grouped-dataset/player_gameweek_tensors"
)
METADATA_PATTERN = "2025-26_gw*/metadata_player_gw_*.csv"


def prepare_inputs(
    artifact_dir: Path,
    schema_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    artifact_dir = artifact_dir.resolve()
    postmatch_path = artifact_dir / ARTIFACT_POSTMATCH
    tensor_root = artifact_dir / ARTIFACT_TENSORS
    if not postmatch_path.is_file():
        raise FileNotFoundError(f"Run-80 postmatch state file missing: {postmatch_path}")
    if not tensor_root.is_dir():
        raise FileNotFoundError(f"Run-80 tensor directory missing: {tensor_root}")

    schema_bytes = schema_path.read_bytes()
    schema = json.loads(schema_bytes)
    features = derive_defensive_features(schema)

    # Explicit projection prevents target_points/total_points from being loaded.
    columns = [*IDENTITY_COLUMNS, *features]
    frame = pd.read_parquet(postmatch_path, columns=columns)
    frame["season"] = frame["season"].astype(str)
    selected = frame.loc[frame["season"].eq("2025-26"), columns].copy()
    if selected.empty:
        raise ValueError("Run-80 artifact contains no 2025/26 postmatch states")
    if set(selected["season"].unique()) != {"2025-26"}:
        raise ValueError("Filtered warm-up input is not exclusively 2025/26")

    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = output_dir / "postmatch_states_2025-26_defensive_only.parquet"
    selected.to_parquet(candidate_path, index=False)
    metadata_dir = output_dir / "metadata_2025-26"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    metadata_paths = sorted(tensor_root.glob(METADATA_PATTERN))
    if not metadata_paths:
        raise FileNotFoundError("No 2025/26 player-Gameweek metadata files in run-80 artifact")
    copied_metadata = []
    for source in metadata_paths:
        # Inspect only season identity here; the dedicated audit validates labels.
        meta = pd.read_csv(source, usecols=["season"])
        if set(meta["season"].astype(str).unique()) != {"2025-26"}:
            raise ValueError(f"Unexpected season in metadata file: {source}")
        destination = metadata_dir / source.parent.name / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied_metadata.append(str(destination.relative_to(metadata_dir)))

    report = {
        "status": "DEFENSIVE_AUDIT_INPUTS_PREPARED",
        "artifact_postmatch_sha256": sha256(postmatch_path),
        "schema_sha256": hashlib.sha256(schema_bytes).hexdigest(),
        "selected_season": "2025-26",
        "defensive_feature_count": len(features),
        "postmatch_rows_selected": int(len(selected)),
        "postmatch_columns_read": columns,
        "target_points_loaded_for_warmup": False,
        "total_points_loaded_for_warmup": False,
        "metadata_files_copied": len(copied_metadata),
        "metadata_files": copied_metadata,
        "oot_metadata_copied": False,
        "oot_tensor_labels_read": False,
    }
    (output_dir / "input_manifest.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = prepare_inputs(args.artifact_dir, args.schema, args.output_dir)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
