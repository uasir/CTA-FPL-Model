"""Build current target-query tensors from historical and active 286-feature candidates.

The six completed-season candidate and active-season candidate remain separate source
artifacts. This command combines them in memory, uses only played rows for history,
and emits tensors only for the selected TARGET_QUERY rows.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from build_2pm_dastan_sequence_dataset import (
    HISTORY_LENGTH,
    MAX_GAP_DAYS,
    SEQUENCE_LENGTH,
    load_schema,
    validate_input,
)


def build_target_query_tensors(
    historical_path: Path,
    active_path: Path,
    schema_path: Path,
    output_dir: Path,
    report_path: Path,
    *,
    target_season: str,
    target_gameweek: int,
    shard_size: int = 10000,
) -> dict[str, Any]:
    features, feature_hash = load_schema(schema_path)
    historical = pd.read_parquet(historical_path)
    active = pd.read_parquet(active_path)
    frame = pd.concat([historical, active], ignore_index=True, sort=False)

    missing = sorted(set(features) - set(frame.columns))
    if missing:
        raise ValueError(f"Combined candidate is missing features: {missing[:20]}")
    numeric = frame[features].apply(pd.to_numeric, errors="coerce")
    values = numeric.to_numpy(dtype=np.float64)
    if np.isinf(values).any():
        raise ValueError("Combined candidate contains infinite feature values")
    residual_nan_count = int(numeric.isna().sum().sum())
    sentinel_count = int(numeric.eq(-1.0).sum().sum())
    frame.loc[:, features] = numeric.fillna(0.0)
    if int(frame[features].eq(-1.0).sum().sum()) != sentinel_count:
        raise RuntimeError("Imputation changed missing-snapshot -1 sentinels")
    frame = validate_input(frame, features, fixture_column="fixture")

    if "row_role" not in frame:
        raise ValueError("Active candidate is missing row_role metadata")
    targets = frame[
        frame["row_role"].eq("TARGET_QUERY")
        & frame["season"].astype(str).eq(str(target_season))
        & pd.to_numeric(frame["gameweek"], errors="coerce").eq(int(target_gameweek))
    ].copy()
    if targets.empty:
        raise ValueError(
            f"No TARGET_QUERY rows found for {target_season} GW{target_gameweek}"
        )
    if targets.duplicated(["season", "gameweek", "fixture_id", "fpl_code"]).any():
        raise ValueError("Target query rows contain duplicate player-fixture keys")

    grouped = {
        key: rows for key, rows in frame.groupby("fpl_code", sort=False)
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    tensor_buffer = np.empty(
        (shard_size, SEQUENCE_LENGTH, len(features)), dtype=np.float32
    )
    metadata_rows: list[dict[str, Any]] = []
    shards = []
    shard_index = 0
    in_shard = 0
    counts = {
        "target_query_rows": int(len(targets)),
        "emitted": 0,
        "insufficient_previous_played_matches": 0,
        "gap_over_21_days": 0,
    }

    def flush():
        nonlocal in_shard, shard_index, metadata_rows
        if not in_shard:
            return
        tensor_name = f"X_target_{shard_index:05d}.npy"
        metadata_name = f"metadata_target_{shard_index:05d}.csv"
        np.save(output_dir / tensor_name, tensor_buffer[:in_shard])
        pd.DataFrame(metadata_rows).to_csv(output_dir / metadata_name, index=False)
        shards.append(
            {"tensor": tensor_name, "metadata": metadata_name, "samples": in_shard}
        )
        shard_index += 1
        in_shard = 0
        metadata_rows = []

    for target in targets.itertuples(index=False):
        player_rows = grouped.get(target.fpl_code)
        if player_rows is None:
            counts["insufficient_previous_played_matches"] += 1
            continue
        history = player_rows[
            (player_rows["minutes"] > 0)
            & (player_rows["match_available_at"] < target.deadline_time)
            & (player_rows["kickoff_time"] < target.kickoff_time)
            & (player_rows["fixture_id"].astype(str) != str(target.fixture_id))
        ].sort_values(
            ["match_available_at", "kickoff_time", "fixture_id"],
            kind="mergesort",
        ).tail(HISTORY_LENGTH)
        if len(history) < HISTORY_LENGTH:
            counts["insufficient_previous_played_matches"] += 1
            continue
        times = list(history["kickoff_time"]) + [target.kickoff_time]
        gaps = [
            (times[index] - times[index - 1]).total_seconds() / 86400
            for index in range(1, len(times))
        ]
        if any(gap <= 0 or gap > MAX_GAP_DAYS for gap in gaps):
            counts["gap_over_21_days"] += 1
            continue

        tensor_buffer[in_shard, :HISTORY_LENGTH, :] = history[features].to_numpy(
            dtype=np.float32
        )
        tensor_buffer[in_shard, HISTORY_LENGTH, :] = np.asarray(
            [getattr(target, feature) for feature in features],
            dtype=np.float32,
        )
        metadata_rows.append(
            {
                "season": str(target.season),
                "gameweek": int(target.gameweek),
                "fixture_id": str(target.fixture_id),
                "fpl_code": int(target.fpl_code),
                "target_kickoff_time": target.kickoff_time.isoformat(),
                "target_deadline_time": target.deadline_time.isoformat(),
                "target_source_vintage_status": str(target.source_vintage_status),
                "history_fixture_ids": json.dumps(
                    history["fixture_id"].astype(str).tolist()
                ),
                "history_match_available_at": json.dumps(
                    [value.isoformat() for value in history["match_available_at"]]
                ),
                "history_source_vintage_status": json.dumps(
                    history["source_vintage_status"].astype(str).tolist()
                ),
                "sequence_gap_days": json.dumps(
                    [round(value, 6) for value in gaps]
                ),
                "target_points": None,
            }
        )
        in_shard += 1
        counts["emitted"] += 1
        if in_shard == shard_size:
            flush()
    flush()

    report = {
        "status": "CURRENT_TARGET_QUERY_TENSORS_BUILT",
        "admission_status": "NOT_ADMITTED",
        "target_season": str(target_season),
        "target_gameweek": int(target_gameweek),
        "sequence_definition": "five_previous_played_fixtures_plus_target_query",
        "sequence_shape": [SEQUENCE_LENGTH, len(features)],
        "tensor_dtype": "float32",
        "feature_order_sha256": feature_hash,
        "residual_nan_values_imputed_to_zero": residual_nan_count,
        "residual_nan_imputation_policy": "0.0, matching pinned Dastan model.py feature-matrix fillna(0.0)",
        "preserved_minus_one_snapshot_sentinels": sentinel_count,
        "maximum_inter_observation_gap_days": MAX_GAP_DAYS,
        "counts": counts,
        "shards": shards,
        "limitations": [
            "Only TARGET_QUERY rows are emitted as inference samples; played historical rows provide context only.",
            "Historical source-vintage and all 286 feature-admission gates remain open.",
            "The active candidate must be built before any fixture in the target Gameweek starts.",
            "The current sequence token semantics remain provisional and use pre-match Dastan snapshots.",
            "No model training or M3/M4 integration is performed.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-input", type=Path, required=True)
    parser.add_argument("--active-input", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=Path(__file__).parents[1] / "config" / "2pm_dastan_286_schema.json")
    parser.add_argument("--target-season", required=True)
    parser.add_argument("--target-gameweek", type=int, required=True)
    parser.add_argument("--tensor-out-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--shard-size", type=int, default=10000)
    args = parser.parse_args()
    report = build_target_query_tensors(
        args.historical_input,
        args.active_input,
        args.schema,
        args.tensor_out_dir,
        args.report,
        target_season=args.target_season,
        target_gameweek=args.target_gameweek,
        shard_size=args.shard_size,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
