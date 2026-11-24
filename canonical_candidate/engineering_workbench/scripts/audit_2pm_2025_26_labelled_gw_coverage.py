"""Count labelled 2025/26 player-Gameweek samples by GW; never inspect score distributions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REQUIRED = ("season", "gameweek", "fpl_code", "target_points")


def audit_metadata(metadata_dir: Path, *, min_train_gameweeks: int = 10,
                   min_validation_gameweeks: int = 4) -> dict[str, Any]:
    paths = sorted(metadata_dir.rglob("metadata_player_gw_*.csv"))
    if not paths:
        raise FileNotFoundError(f"No metadata_player_gw_*.csv files under {metadata_dir}")
    frames = []
    for path in paths:
        frame = pd.read_csv(path, usecols=list(REQUIRED))
        frames.append(frame)
    data = pd.concat(frames, ignore_index=True)
    missing = sorted(set(REQUIRED) - set(data.columns))
    if missing:
        raise ValueError(f"Metadata missing columns: {missing}")
    data["season"] = data["season"].astype(str)
    if set(data["season"].unique()) != {"2025-26"}:
        raise ValueError("Only 2025-26 labelled metadata may be audited here")
    data["gameweek"] = pd.to_numeric(data["gameweek"], errors="coerce")
    data["fpl_code"] = pd.to_numeric(data["fpl_code"], errors="coerce")
    labels = pd.to_numeric(data["target_points"], errors="coerce")
    if data[["gameweek", "fpl_code"]].isna().any().any():
        raise ValueError("Player-Gameweek identity contains null or non-numeric values")
    if labels.isna().any() or not np.isfinite(labels.to_numpy(dtype=float)).all():
        raise ValueError("2025/26 target labels must all be finite")
    if not np.equal(labels.to_numpy(dtype=float), np.round(labels.to_numpy(dtype=float))).all():
        raise ValueError("FPL target labels must be integer-valued")
    data["gameweek"] = data["gameweek"].astype(int)
    data["fpl_code"] = data["fpl_code"].astype(int)
    if data.duplicated(["season", "gameweek", "fpl_code"]).any():
        raise ValueError("Duplicate player-Gameweek metadata rows")

    counts = data.groupby("gameweek", sort=True).size()
    gameweeks = [int(gw) for gw in counts.index]
    per_gw = {str(int(gw)): int(count) for gw, count in counts.items()}
    candidates = []
    for cutoff in gameweeks:
        train_gws = [gw for gw in gameweeks if gw < cutoff]
        validation_gws = [gw for gw in gameweeks if gw >= cutoff]
        if len(train_gws) < min_train_gameweeks or len(validation_gws) < min_validation_gameweeks:
            continue
        candidates.append({
            "first_validation_gw": cutoff,
            "last_training_gw": max(train_gws),
            "training_gameweeks": train_gws,
            "validation_gameweeks": validation_gws,
            "training_samples": int(counts.loc[train_gws].sum()),
            "validation_samples": int(counts.loc[validation_gws].sum()),
        })
    return {
        "status": "LABELLED_GW_COVERAGE_AUDIT_COMPLETE",
        "season": "2025-26",
        "metadata_files": len(paths),
        "labelled_player_gameweek_samples": int(len(data)),
        "gameweek_count": len(gameweeks),
        "per_gameweek_labelled_samples": per_gw,
        "candidate_chronological_cutoffs": candidates,
        "cutoff_policy": {
            "min_training_gameweeks": min_train_gameweeks,
            "min_validation_gameweeks": min_validation_gameweeks,
            "random_split": False,
            "cutoff_selected": False,
        },
        "label_isolation": {
            "season_2025_26_only": True,
            "target_values_used_only_for_finite_integer_validation": True,
            "target_score_distribution_or_metrics_computed": False,
            "2026_27_labels_read": False,
        },
        "training_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-training-gameweeks", type=int, default=10)
    parser.add_argument("--min-validation-gameweeks", type=int, default=4)
    args = parser.parse_args()
    report = audit_metadata(
        args.metadata_dir,
        min_train_gameweeks=args.min_training_gameweeks,
        min_validation_gameweeks=args.min_validation_gameweeks,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
