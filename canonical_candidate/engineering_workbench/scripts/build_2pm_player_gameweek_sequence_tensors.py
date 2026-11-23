"""Build one 2PM training/inference sample per player-Gameweek.

Each fixture query receives the same five post-match historical state tokens and
its own strictly pre-deadline target token. The tensor stores fixture queries as
[B, F, 6, 286], so the existing encoder can be called once per fixture by
flattening B*F. A Double Gameweek is one player-Gameweek sample with multiple
fixture queries and exactly one Gameweek label.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from build_2pm_dastan_sequence_dataset import load_schema

GROUP_KEYS = ["season", "gameweek", "fpl_code"]
HISTORY_LENGTH = 5
MAX_GAP_DAYS = 21


def _read_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def _prepare_features(frame: pd.DataFrame, features: list[str], label: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    missing = sorted(set(features) - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing 286 feature columns: {missing[:20]}")
    numeric = frame[features].apply(pd.to_numeric, errors="coerce")
    if np.isinf(numeric.to_numpy(dtype=np.float64)).any():
        raise ValueError(f"{label} contains infinite feature values")
    nan_by_feature = {
        name: int(numeric[name].isna().sum())
        for name in features if numeric[name].isna().any()
    }
    out = frame.copy()
    out.loc[:, features] = numeric.fillna(0.0)
    return out, {
        "residual_nan_values_imputed_to_zero": int(numeric.isna().sum().sum()),
        "raw_nan_counts_by_feature": nan_by_feature,
        "preserved_minus_one_sentinels": int(numeric.eq(-1.0).sum().sum()),
    }


def _label_for_group(rows: pd.DataFrame, label_column: str, label_grain: str) -> float:
    values = pd.to_numeric(rows[label_column], errors="coerce")
    if values.isna().any():
        raise ValueError("A labelled player-Gameweek group contains missing fixture labels")
    if not np.isfinite(values.to_numpy(dtype=float)).all():
        raise ValueError("Target labels must be finite")
    if not np.equal(values.to_numpy(dtype=float), np.round(values.to_numpy(dtype=float))).all():
        raise ValueError("FPL target points must be integer-valued")
    if label_grain == "player_fixture":
        return float(values.sum())
    if label_grain == "player_gameweek":
        unique = values.unique()
        if len(unique) != 1:
            raise ValueError(
                "player_gameweek labels must repeat the same GW total on every fixture row"
            )
        return float(unique[0])
    raise ValueError("label_grain must be 'player_fixture' or 'player_gameweek'")


def build_player_gameweek_sequence_tensors(
    postmatch_states_path: Path,
    target_frame_path: Path,
    schema_path: Path,
    output_dir: Path,
    report_path: Path,
    *,
    target_season: str,
    target_gameweek: int,
    target_mode: str,
    label_grain: str | None = None,
    shard_size: int = 10000,
) -> dict[str, Any]:
    """Create fixture-query tensors grouped into one player-Gameweek sample."""
    if target_mode not in {"historical", "inference"}:
        raise ValueError("target_mode must be 'historical' or 'inference'")
    if shard_size <= 0:
        raise ValueError("shard_size must be positive")
    features, feature_hash = load_schema(schema_path)
    history, history_missingness = _prepare_features(
        _read_parquet(postmatch_states_path), features, "Post-match state frame"
    )
    targets, target_missingness = _prepare_features(
        _read_parquet(target_frame_path), features, "Target frame"
    )

    required_history = {
        *GROUP_KEYS, "fixture", "kickoff_time", "minutes",
        "match_available_at", "postmatch_state_as_of_time",
        "postmatch_state_semantics",
    }
    required_target = {
        *GROUP_KEYS, "fixture", "kickoff_time", "deadline_time",
        "feature_cutoff_time", "minutes",
    }
    for frame, required, label in (
        (history, required_history, "Post-match state frame"),
        (targets, required_target, "Target frame"),
    ):
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"{label} is missing required columns: {missing}")

    history["season"] = history["season"].astype(str)
    targets["season"] = targets["season"].astype(str)
    for frame, label in ((history, "history"), (targets, "target")):
        frame["fpl_code"] = pd.to_numeric(frame["fpl_code"], errors="coerce")
        frame["gameweek"] = pd.to_numeric(frame["gameweek"], errors="coerce")
        if frame[["fpl_code", "gameweek"]].isna().any().any():
            raise ValueError(f"{label} player/Gameweek keys must be numeric and non-null")
        frame["fpl_code"] = frame["fpl_code"].astype("int64")
        frame["gameweek"] = frame["gameweek"].astype("int64")
        frame["fixture"] = frame["fixture"].astype(str)
    for frame, columns in (
        (history, ["kickoff_time", "match_available_at", "postmatch_state_as_of_time"]),
        (targets, ["kickoff_time", "deadline_time", "feature_cutoff_time"]),
    ):
        for column in columns:
            frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
            if frame[column].isna().any():
                raise ValueError(f"{column} contains invalid timestamps")
    if not history["postmatch_state_semantics"].eq(
        "AFTER_MATCH_DATA_AVAILABLE_CONSERVATIVE"
    ).all():
        raise ValueError("Historical tokens must be explicitly marked as post-match states")
    if not pd.to_numeric(history["minutes"], errors="coerce").gt(0).all():
        raise ValueError("Historical state rows must represent actual player appearances")
    if history.duplicated(["season", "fixture", "fpl_code"]).any():
        raise ValueError("Post-match state rows must be unique at player-fixture grain")
    if history["postmatch_state_as_of_time"].le(history["match_available_at"]).any():
        raise ValueError("Post-match state timestamp must follow match data availability")
    if history["postmatch_state_as_of_time"].lt(history["kickoff_time"]).any():
        raise ValueError("Post-match state cannot precede its match kickoff")

    if target_mode == "inference":
        if "row_role" not in targets:
            raise ValueError("Inference target frame must contain row_role=TARGET_QUERY")
        targets = targets[targets["row_role"].eq("TARGET_QUERY")].copy()
        if targets.empty:
            raise ValueError("No TARGET_QUERY rows found")
        label_column = None
        for label_name in ("target_points", "total_points"):
            if label_name in targets and targets[label_name].notna().any():
                raise ValueError("Inference target queries must not contain realized points")
        if targets["kickoff_time"].le(targets["deadline_time"]).any():
            raise ValueError("Every inference fixture must start after its deadline")
        if targets["feature_cutoff_time"].ne(targets["deadline_time"]).any():
            raise ValueError("Inference feature cutoff must equal the official deadline")
        if label_grain is not None:
            raise ValueError("Inference mode does not accept a target label grain")
    else:
        label_candidates = [
            name for name in ("total_points", "target_points")
            if name in targets and targets[name].notna().any()
        ]
        label_column = label_candidates[0] if label_candidates else None
        if label_column is None:
            raise ValueError("Historical training targets require total_points or target_points")
        declared_grains = (
            set(targets["target_label_grain"].dropna().astype(str).unique())
            if "target_label_grain" in targets else set()
        )
        declared_semantics = (
            set(targets["target_points_semantics"].dropna().astype(str).unique())
            if "target_points_semantics" in targets else set()
        )
        if "target_label_grain" in targets and targets["target_label_grain"].isna().any():
            raise ValueError("Target label-grain metadata is incomplete")
        if "target_points_semantics" in targets and targets["target_points_semantics"].isna().any():
            raise ValueError("Target point-semantics metadata is incomplete")
        if label_grain is None:
            if (
                declared_grains == {"player_fixture"}
                and declared_semantics == {"FPL_POINTS_SCORED_IN_THIS_FIXTURE"}
            ):
                label_grain = "player_fixture"
            else:
                raise ValueError(
                    "Historical training requires an explicit label_grain unless "
                    "the target frame carries verified player-fixture semantics"
                )
        if label_grain not in {"player_fixture", "player_gameweek"}:
            raise ValueError("label_grain must be 'player_fixture' or 'player_gameweek'")
        if declared_grains and declared_grains != {label_grain}:
            raise ValueError(
                f"Requested label_grain={label_grain} conflicts with target frame {declared_grains}"
            )
        if label_grain == "player_fixture" and "target_points_semantics" in targets:
            if declared_semantics != {"FPL_POINTS_SCORED_IN_THIS_FIXTURE"}:
                raise ValueError("Fixture-grain target semantics are not verified")
        target_minutes = pd.to_numeric(targets["minutes"], errors="coerce")
        if target_minutes.isna().any() or target_minutes.lt(0).any():
            raise ValueError("Historical target minutes must be numeric and non-negative")
        # Keep non-appearances as valid target outcomes (normally zero points).
        # The five historical input tokens are separately restricted to played matches.
        if targets.empty:
            raise ValueError("No historical target fixtures found")
        if targets[label_column].isna().any():
            raise ValueError("Historical training target points contain missing values")
        if targets["feature_cutoff_time"].ne(targets["deadline_time"]).any():
            raise ValueError("Historical target feature cutoff must equal its official deadline")
        if targets["kickoff_time"].le(targets["deadline_time"]).any():
            raise ValueError("Historical target fixture must start after its deadline")

    targets = targets[
        targets["season"].eq(str(target_season))
        & pd.to_numeric(targets["gameweek"], errors="coerce").eq(int(target_gameweek))
    ].copy()
    if targets.empty:
        raise ValueError(f"No {target_mode} target rows for {target_season} GW{target_gameweek}")
    if "source_as_of_time" in targets:
        source_as_of = pd.to_datetime(
            targets["source_as_of_time"], utc=True, errors="coerce"
        )
        if source_as_of.isna().any():
            raise ValueError("source_as_of_time contains missing or invalid capture timestamps")
        if source_as_of.ge(targets["deadline_time"]).any():
            raise ValueError("A target source snapshot was captured at/after its deadline")
    snapshot_value_groups = {
        "ep_next_snapshot_at": ("ar_ep_next",),
        "signals_snapshot_at": ("sig_status_risk", "sig_chance_playing", "sig_has_news"),
        "market_snapshot_at": ("value", "selected", "transfers_balance"),
    }
    for snapshot_column, value_columns in snapshot_value_groups.items():
        if snapshot_column not in targets:
            continue
        captured = pd.to_datetime(
            targets[snapshot_column], utc=True, errors="coerce"
        )
        invalid = targets[snapshot_column].notna() & captured.isna()
        if invalid.any():
            raise ValueError(f"{snapshot_column} contains invalid capture timestamps")
        present = captured.notna()
        missing_capture = ~present
        if missing_capture.any():
            available_values = [name for name in value_columns if name in targets]
            if available_values:
                values = targets.loc[missing_capture, available_values].apply(
                    pd.to_numeric, errors="coerce"
                )
                # -1 is the explicit missing-snapshot sentinel in the pinned
                # candidate schema. Real values without provenance are rejected.
                if not values.eq(-1.0).all(axis=None):
                    raise ValueError(
                        f"{snapshot_column} is missing while its feature values are not all -1 sentinels"
                    )
        if present.any():
            age = targets.loc[present, "deadline_time"] - captured.loc[present]
            if age.le(pd.Timedelta(minutes=5)).any():
                raise ValueError(
                    f"{snapshot_column} violates the five-minute deadline safety buffer"
                )
    if targets.duplicated([*GROUP_KEYS, "fixture"]).any():
        raise ValueError("Target frame contains duplicate player-Gameweek-fixture rows")

    target_groups = list(targets.groupby(GROUP_KEYS, sort=True))
    max_fixtures = max(len(group) for _, group in target_groups)
    if max_fixtures < 1:
        raise ValueError("No target fixtures available")

    # History is deliberately season-scoped: no previous-season token is carried
    # into a current-season sequence without a separate identity/continuity admission.
    history_groups = {
        (str(season), int(code)): group
        for (season, code), group in history.groupby(["season", "fpl_code"], sort=False)
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    tensor_buffer = np.zeros(
        (shard_size, max_fixtures, HISTORY_LENGTH + 1, len(features)),
        dtype=np.float32,
    )
    mask_buffer = np.zeros((shard_size, max_fixtures), dtype=np.uint8)
    label_buffer = np.full(shard_size, np.nan, dtype=np.float32)
    metadata_rows: list[dict[str, Any]] = []
    shards: list[dict[str, Any]] = []
    shard_index = 0
    in_shard = 0
    counts = {
        "player_gameweek_groups": len(target_groups),
        "emitted": 0,
        "insufficient_previous_played_matches": 0,
        "postmatch_state_not_available_by_deadline": 0,
        "gap_over_21_days": 0,
    }

    def flush() -> None:
        nonlocal shard_index, in_shard, metadata_rows
        if not in_shard:
            return
        tensor_name = f"X_player_gw_{shard_index:05d}.npy"
        mask_name = f"fixture_mask_{shard_index:05d}.npy"
        metadata_name = f"metadata_player_gw_{shard_index:05d}.csv"
        np.save(output_dir / tensor_name, tensor_buffer[:in_shard])
        np.save(output_dir / mask_name, mask_buffer[:in_shard])
        label_name = None
        if target_mode == "historical":
            label_name = f"y_player_gw_{shard_index:05d}.npy"
            np.save(output_dir / label_name, label_buffer[:in_shard])
        pd.DataFrame(metadata_rows).to_csv(output_dir / metadata_name, index=False)
        shards.append({
            "tensor": tensor_name,
            "fixture_mask": mask_name,
            "labels": label_name,
            "metadata": metadata_name,
            "samples": in_shard,
        })
        shard_index += 1
        in_shard = 0
        tensor_buffer.fill(0.0)
        mask_buffer.fill(0)
        label_buffer.fill(np.nan)
        metadata_rows = []

    for group_key, group in target_groups:
        season, gameweek, code = group_key
        group = group.sort_values(["kickoff_time", "fixture"], kind="mergesort")
        deadlines = group["deadline_time"].drop_duplicates()
        if len(deadlines) != 1:
            raise ValueError("All fixtures in one player-Gameweek must share one official deadline")
        deadline = deadlines.iloc[0]
        first_kickoff = group["kickoff_time"].min()
        player_history = history_groups.get((str(season), int(code)))
        if player_history is None:
            counts["insufficient_previous_played_matches"] += 1
            continue
        prior_played = player_history[
            player_history["kickoff_time"].lt(first_kickoff)
        ]
        eligible = prior_played[
            prior_played["postmatch_state_as_of_time"].lt(deadline)
        ].sort_values(
            ["postmatch_state_as_of_time", "kickoff_time", "fixture"],
            kind="mergesort",
        ).tail(HISTORY_LENGTH)
        if len(eligible) < HISTORY_LENGTH:
            if len(prior_played) >= HISTORY_LENGTH:
                counts["postmatch_state_not_available_by_deadline"] += 1
            else:
                counts["insufficient_previous_played_matches"] += 1
            continue
        if eligible["postmatch_state_as_of_time"].ge(deadline).any():
            counts["postmatch_state_not_available_by_deadline"] += 1
            continue
        observation_kickoffs = list(eligible["kickoff_time"]) + [first_kickoff]
        gaps = [
            (observation_kickoffs[i] - observation_kickoffs[i - 1]).total_seconds() / 86400
            for i in range(1, len(observation_kickoffs))
        ]
        if any(gap <= 0 or gap > MAX_GAP_DAYS for gap in gaps):
            counts["gap_over_21_days"] += 1
            continue

        sample_index = in_shard
        history_values = eligible[features].to_numpy(dtype=np.float32)
        fixture_ids = []
        for fixture_index, target in enumerate(group.itertuples(index=False)):
            tensor_buffer[sample_index, fixture_index, :HISTORY_LENGTH, :] = history_values
            tensor_buffer[sample_index, fixture_index, HISTORY_LENGTH, :] = np.asarray(
                [getattr(target, feature) for feature in features], dtype=np.float32
            )
            mask_buffer[sample_index, fixture_index] = 1
            fixture_ids.append(str(target.fixture))
        if target_mode == "historical":
            label_buffer[sample_index] = _label_for_group(
                group, label_column, label_grain
            )
        metadata_rows.append({
            "season": str(season),
            "gameweek": int(gameweek),
            "fpl_code": int(code),
            "fixture_ids": json.dumps(fixture_ids),
            "fixture_count": len(group),
            "history_fixture_ids": json.dumps(eligible["fixture"].astype(str).tolist()),
            "history_state_as_of_times": json.dumps(
                [value.isoformat() for value in eligible["postmatch_state_as_of_time"]]
            ),
            "target_deadline_time": deadline.isoformat(),
            "target_first_kickoff_time": first_kickoff.isoformat(),
            "sequence_gap_days": json.dumps([round(value, 6) for value in gaps]),
            "target_points": (
                float(label_buffer[sample_index]) if target_mode == "historical" else None
            ),
            "fixture_target_points": (
                json.dumps(
                    pd.to_numeric(group[label_column], errors="raise").astype(float).tolist()
                )
                if target_mode == "historical" and label_grain == "player_fixture"
                else None
            ),
            "label_grain": label_grain,
        })
        in_shard += 1
        counts["emitted"] += 1
        if in_shard == shard_size:
            flush()
    flush()

    report = {
        "status": "PLAYER_GAMEWEEK_SEQUENCE_TENSORS_BUILT",
        "admission_status": "NOT_ADMITTED",
        "target_mode": target_mode,
        "target_season": str(target_season),
        "target_gameweek": int(target_gameweek),
        "sample_grain": "player_gameweek",
        "fixture_query_grain": "player_fixture",
        "sequence_definition": "five_postmatch_played_fixture_states_plus_one_prematch_fixture_query_per_target_fixture",
        "tensor_shape_per_sample": [max_fixtures, HISTORY_LENGTH + 1, len(features)],
        "tensor_dtype": "float32",
        "fixture_mask_shape_per_sample": [max_fixtures],
        "feature_order_sha256": feature_hash,
        "label_grain": label_grain,
        "double_gameweek_rule": "one player-Gameweek sample; one query per target fixture; one GW label, never duplicated per fixture",
        "training_forward_rule": "flatten player-Gameweek and fixture-query axes for the Transformer; reshape fixture mixture outputs and aggregate them before one player-Gameweek loss",
        "cross_season_history": "excluded; only same-season post-match states are eligible",
        "maximum_inter_observation_gap_days": MAX_GAP_DAYS,
        "missingness": {
            "postmatch_history": history_missingness,
            "target_queries": target_missingness,
        },
        "counts": counts,
        "shards": shards,
        "limitations": [
            "The player-Gameweek training label grain must be explicitly verified as fixture-level or Gameweek-level before training.",
            "Fixture-score aggregation requires a declared cross-fixture dependence model; independent convolution is provisional.",
            "All 286 features and post-match state vintages remain NOT_ADMITTED pending the independent admission audit.",
            "No model training or M3/M4 integration is performed.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postmatch-states", type=Path, required=True)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=Path(__file__).parents[1] / "config" / "2pm_dastan_286_schema.json")
    parser.add_argument("--target-season", required=True)
    parser.add_argument("--target-gameweek", type=int, required=True)
    parser.add_argument("--target-mode", choices=("historical", "inference"), required=True)
    parser.add_argument("--label-grain", choices=("player_fixture", "player_gameweek"))
    parser.add_argument("--tensor-out-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--shard-size", type=int, default=10000)
    args = parser.parse_args()
    report = build_player_gameweek_sequence_tensors(
        args.postmatch_states,
        args.targets,
        args.schema,
        args.tensor_out_dir,
        args.report,
        target_season=args.target_season,
        target_gameweek=args.target_gameweek,
        target_mode=args.target_mode,
        label_grain=args.label_grain,
        shard_size=args.shard_size,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
