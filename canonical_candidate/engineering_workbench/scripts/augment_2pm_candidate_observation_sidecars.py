"""Add raw-source observation sidecars to an existing 2PM candidate.

This migration preserves the existing candidate feature values. It recomputes the
same feature reconstruction from pinned raw match tables, compares every feature
value, and writes sidecars only if the reconstruction is exactly equivalent
within the declared numeric tolerance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from rebuild_2pm_fixture_context import (
    rebuild_deadline_team_context,
    rebuild_fixture_context,
    rebuild_player_history_features,
)

OBSERVED_PREFIX = "__observed__"
PINNED_DASTAN_COMMIT = "758db9247e8b3a9a870c991064f74d8339d61cd0"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_existing_sidecars(
    frame: pd.DataFrame, feature_order: list[str]
) -> dict[str, Any]:
    columns = [f"{OBSERVED_PREFIX}{name}" for name in feature_order]
    missing = [column for column in columns if column not in frame]
    if missing:
        raise ValueError(f"Existing candidate has incomplete sidecars: {missing[:20]}")
    values = frame[columns].apply(pd.to_numeric, errors="coerce")
    if values.isna().any().any() or not values.isin([0, 1]).all().all():
        raise ValueError("Existing candidate sidecars contain missing or non-binary values")
    return {
        "status": "ALREADY_PRESENT",
        "sidecar_count": len(columns),
        "rows": len(frame),
        "observed_cells": int(values.to_numpy(dtype=np.uint8).sum()),
    }


def augment_candidate_frame(
    candidate: pd.DataFrame,
    player_matches: pd.DataFrame,
    team_matches: pd.DataFrame,
    features_module: Any,
    feature_order: list[str],
    sentinel_features: list[str],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build sidecars from raw inputs and preserve values only after parity passes."""
    if len(feature_order) != 286 or len(set(feature_order)) != 286:
        raise ValueError("Expected the pinned ordered 286-feature schema")
    missing_features = sorted(set(feature_order) - set(candidate.columns))
    if missing_features:
        raise ValueError(f"Candidate is missing schema features: {missing_features[:20]}")

    existing = [name for name in candidate.columns if name.startswith(OBSERVED_PREFIX)]
    expected_columns = [f"{OBSERVED_PREFIX}{name}" for name in feature_order]
    if existing:
        if set(existing) != set(expected_columns):
            raise ValueError("Candidate contains a partial or unexpected observation-sidecar set")
        return candidate, _validate_existing_sidecars(candidate, feature_order)

    required_retained = [
        "is_home_num", "value", "selected", "transfers_balance",
        "ar_ep_next", "sig_status_risk", "sig_chance_playing", "sig_has_news",
    ]
    missing_retained = sorted(set(required_retained) - set(candidate.columns))
    if missing_retained:
        raise ValueError(f"Candidate is missing retained context/snapshot fields: {missing_retained}")

    working = candidate.copy()
    home = pd.to_numeric(working["is_home_num"], errors="coerce")
    if home.isna().any() or not home.isin([0, 1]).all():
        raise ValueError("is_home_num must be complete binary data for sidecar reconstruction")
    working["is_home"] = home.astype(bool)

    working, player_report = rebuild_player_history_features(
        working, player_matches, features_module
    )
    working, team_report = rebuild_deadline_team_context(
        working, team_matches, features_module
    )
    working, fixture_report = rebuild_fixture_context(working, player_matches)

    for feature in required_retained:
        numeric = pd.to_numeric(working[feature], errors="coerce")
        observed = np.isfinite(numeric.to_numpy(dtype=float))
        if feature in set(sentinel_features):
            observed &= numeric.to_numpy(dtype=float) != -1.0
        working[f"{OBSERVED_PREFIX}{feature}"] = observed.astype(np.uint8)

    missing_sidecars = [
        column for column in expected_columns if column not in working.columns
    ]
    if missing_sidecars:
        raise ValueError(
            "Raw-source reconstruction did not produce all 286 sidecars: "
            f"{missing_sidecars[:20]}"
        )

    # Do not silently change a cached feature candidate during a mask-only migration.
    before = candidate[feature_order].apply(pd.to_numeric, errors="coerce").to_numpy(
        dtype=float
    )
    after = working[feature_order].apply(pd.to_numeric, errors="coerce").to_numpy(
        dtype=float
    )
    same_nan = np.isnan(before) & np.isnan(after)
    same_numeric = np.isclose(before, after, rtol=1e-8, atol=1e-8, equal_nan=False)
    mismatch = ~(same_nan | same_numeric)
    mismatch_counts = {
        feature: int(mismatch[:, index].sum())
        for index, feature in enumerate(feature_order)
        if mismatch[:, index].any()
    }
    if mismatch.any():
        raise ValueError(
            "Raw-source sidecar reconstruction changed cached feature values; "
            "refusing to migrate this candidate. "
            f"mismatch_cells={int(mismatch.sum())}, "
            f"features={dict(list(mismatch_counts.items())[:20])}. "
            "Rerun the workflow with rebuild_candidate=true for a full candidate rebuild."
        )

    sidecars = working[expected_columns].apply(pd.to_numeric, errors="coerce")
    if sidecars.isna().any().any() or not sidecars.isin([0, 1]).all().all():
        raise ValueError("Generated source-observation sidecars must contain only 0/1")

    augmented = pd.concat(
        [candidate.copy(), sidecars.astype(np.uint8)],
        axis=1,
    )
    report = {
        "status": "AUGMENTED_FROM_PINNED_RAW_MATCHES",
        "sidecar_count": len(expected_columns),
        "rows": len(augmented),
        "observed_cells": int(sidecars.to_numpy(dtype=np.uint8).sum()),
        "feature_value_parity": {
            "status": "PASS",
            "mismatch_cells": 0,
            "rtol": 1e-8,
            "atol": 1e-8,
        },
        "reconstruction_status": {
            "player_history": str(player_report.get("status", "UNKNOWN")),
            "team_context": str(team_report.get("status", "UNKNOWN")),
            "fixture_context": str(fixture_report.get("status", "UNKNOWN")),
        },
    }
    return augmented, report


def augment_candidate_directory(
    candidate_dir: Path,
    dastan_root: Path,
    schema_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    candidate_path = candidate_dir / "features_286_candidate.parquet"
    player_path = candidate_dir / "player_matches_with_availability.parquet"
    team_path = candidate_dir / "team_matches.parquet"
    report_path = candidate_dir / "2pm_dastan_286_candidate_report.json"
    for path in (candidate_path, player_path, team_path, report_path):
        if not path.is_file():
            raise FileNotFoundError(
                f"Cannot augment cached candidate without required artifact: {path}. "
                "If the cached raw match tables are unavailable, rerun with rebuild_candidate=true."
            )

    actual_commit = subprocess.run(
        ["git", "-C", str(dastan_root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if actual_commit != PINNED_DASTAN_COMMIT:
        raise RuntimeError(
            f"Dastan pin mismatch: expected {PINNED_DASTAN_COMMIT}, got {actual_commit}"
        )

    sys.path.insert(0, str(dastan_root))
    from dastan.rebuild import features as features_module  # noqa: E402

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    feature_order = schema["feature_order"]
    candidate = pd.read_parquet(candidate_path)
    if any(name.startswith(OBSERVED_PREFIX) for name in candidate.columns):
        result = _validate_existing_sidecars(candidate, feature_order)
        result["candidate_sha256"] = _sha256(candidate_path)
        candidate_report = json.loads(report_path.read_text(encoding="utf-8"))
        candidate_report["candidate_sha256"] = result["candidate_sha256"]
        candidate_report["raw_source_observation_sidecar_count"] = result["sidecar_count"]
        candidate_report["source_observation_sidecar_status"] = result["status"]
        candidate_report["source_observation_sidecar_report"] = result
        report_path.write_text(
            json.dumps(candidate_report, indent=2) + "\n", encoding="utf-8"
        )
        return result

    player_matches = pd.read_parquet(player_path)
    team_matches = pd.read_parquet(team_path)
    augmented, result = augment_candidate_frame(
        candidate,
        player_matches,
        team_matches,
        features_module,
        feature_order,
        manifest.get("snapshot_missing_sentinel_features", []),
    )

    temporary_path = candidate_path.with_name(
        candidate_path.stem + ".with_observation_sidecars.tmp.parquet"
    )
    augmented.to_parquet(temporary_path, index=False)
    os.replace(temporary_path, candidate_path)

    candidate_report = json.loads(report_path.read_text(encoding="utf-8"))
    candidate_report["candidate_sha256"] = _sha256(candidate_path)
    candidate_report["raw_source_observation_sidecar_count"] = result["sidecar_count"]
    candidate_report["source_observation_sidecar_status"] = result["status"]
    candidate_report["source_observation_sidecar_report"] = result
    report_path.write_text(json.dumps(candidate_report, indent=2) + "\n", encoding="utf-8")
    result["candidate_sha256"] = candidate_report["candidate_sha256"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--dastan-root", type=Path, required=True)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config" / "2pm_dastan_286_schema.json",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config" / "2pm_feature_group_manifest.json",
    )
    args = parser.parse_args()
    result = augment_candidate_directory(
        args.candidate_dir, args.dastan_root, args.schema, args.manifest
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
