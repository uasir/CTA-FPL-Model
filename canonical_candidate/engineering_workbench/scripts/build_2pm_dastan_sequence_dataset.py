"""Build 2PM six-token sequences from the pinned Dastan 286-feature contract.

Each sample contains five previous *played fixtures* and one target-fixture query
token. Historical tokens are the 286-feature snapshots recorded for those fixtures;
their own result is never copied into the input. The target label is kept separate.
This is a candidate-data builder, not a feature-admission or training command.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

IDENTITY = ("season", "gameweek", "fixture_id", "fpl_code")
TIME_COLUMNS = ("kickoff_time", "match_completed_at", "deadline_time", "source_as_of_time")
MAX_GAP_DAYS = 21
HISTORY_LENGTH = 5
SEQUENCE_LENGTH = HISTORY_LENGTH + 1


def load_schema(path: Path) -> tuple[list[str], str]:
    schema = json.loads(path.read_text(encoding="utf-8"))
    features = schema.get("feature_order")
    if schema.get("feature_count") != 286 or not isinstance(features, list):
        raise ValueError("Schema must declare exactly 286 ordered features")
    if len(features) != 286 or len(set(features)) != 286:
        raise ValueError("Schema feature_order must contain 286 unique columns")
    digest = hashlib.sha256("\n".join(features).encode("utf-8")).hexdigest()
    return features, digest


def read_frame(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError("Input must be CSV or Parquet")


def write_frame(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in {".parquet", ".pq"}:
        frame.to_parquet(path, index=False)
    elif path.suffix.lower() == ".csv":
        frame.to_csv(path, index=False)
    else:
        raise ValueError("Output must be CSV or Parquet")


def validate_input(frame: pd.DataFrame, features: list[str], fixture_column: str) -> pd.DataFrame:
    required = (set(IDENTITY) - {"fixture_id"}) | set(TIME_COLUMNS) | {
        fixture_column, "minutes", *features
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Input is missing required columns: {missing[:20]}")
    if fixture_column != "fixture_id":
        if "fixture_id" in frame.columns and fixture_column != "fixture_id":
            raise ValueError("Do not provide both fixture_id and a different fixture column")
        frame = frame.rename(columns={fixture_column: "fixture_id"})
    if frame[list(IDENTITY)].isna().any().any():
        raise ValueError("Identity keys contain null values")
    duplicate = frame.duplicated(list(IDENTITY), keep=False)
    if duplicate.any():
        examples = frame.loc[duplicate, list(IDENTITY)].head(5).to_dict("records")
        raise ValueError(f"Duplicate player-fixture keys: {examples}")

    out = frame.copy()
    for column in ("kickoff_time", "deadline_time", "source_as_of_time"):
        out[column] = pd.to_datetime(out[column], utc=True, errors="coerce")
        if out[column].isna().any():
            raise ValueError(f"{column} contains missing or invalid timestamps")
    out["match_completed_at"] = pd.to_datetime(
        out["match_completed_at"], utc=True, errors="coerce"
    )
    if (out["source_as_of_time"] >= out["deadline_time"]).any():
        raise ValueError("At least one feature snapshot was captured at/after its deadline")
    if (out["deadline_time"] > out["kickoff_time"]).any():
        raise ValueError("A target deadline occurs after its fixture kickoff")
    out["minutes"] = pd.to_numeric(out["minutes"], errors="coerce")
    played_without_completion = out["minutes"].gt(0) & out["match_completed_at"].isna()
    if played_without_completion.any():
        raise ValueError("Played fixtures require match_completed_at")
    completed_before_kickoff = (
        out["match_completed_at"].notna()
        & out["match_completed_at"].lt(out["kickoff_time"])
    )
    if completed_before_kickoff.any():
        raise ValueError("match_completed_at precedes kickoff_time")

    for column in ["minutes", *features]:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    values = out[features].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        bad_rows, bad_cols = np.where(~np.isfinite(values))
        examples = [
            {"row": int(r), "feature": features[int(c)]}
            for r, c in zip(bad_rows[:10], bad_cols[:10])
        ]
        raise ValueError(
            "286-feature matrix contains NaN/inf; apply only the documented, "
            f"source-specific missingness policy first. Examples: {examples}"
        )
    if out["minutes"].isna().any() or (out["minutes"] < 0).any():
        raise ValueError("minutes must be numeric, non-null and non-negative")
    return out.sort_values(
        ["fpl_code", "match_completed_at", "kickoff_time", "fixture_id"],
        kind="mergesort",
    ).reset_index(drop=True)


def build_sequences(
    frame: pd.DataFrame,
    features: list[str],
    *,
    max_gap_days: int = MAX_GAP_DAYS,
    require_label: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if max_gap_days <= 0:
        raise ValueError("max_gap_days must be positive")
    has_label = "total_points" in frame.columns
    if require_label and not has_label:
        raise ValueError("total_points is required for a labelled training dataset")
    if has_label:
        frame = frame.copy()
        frame["total_points"] = pd.to_numeric(frame["total_points"], errors="coerce")

    output: list[dict[str, Any]] = []
    counts = {
        "target_rows": int(len(frame)),
        "emitted": 0,
        "insufficient_previous_played_matches": 0,
        "gap_over_21_days": 0,
    }
    grouped = {key: rows for key, rows in frame.groupby("fpl_code", sort=False)}
    for target in frame.itertuples(index=False):
        target_deadline = target.deadline_time
        target_kickoff = target.kickoff_time
        player_rows = grouped[target.fpl_code]
        history = player_rows[
            (player_rows["minutes"] > 0)
            & (player_rows["match_completed_at"] < target_deadline)
            & (player_rows["kickoff_time"] < target_kickoff)
            & (player_rows["fixture_id"].astype(str) != str(target.fixture_id))
        ].sort_values(
            ["match_completed_at", "kickoff_time", "fixture_id"], kind="mergesort"
        ).tail(HISTORY_LENGTH)
        if len(history) < HISTORY_LENGTH:
            counts["insufficient_previous_played_matches"] += 1
            continue

        observation_times = list(history["kickoff_time"]) + [target_kickoff]
        gaps = [
            (observation_times[i] - observation_times[i - 1]).total_seconds() / 86400
            for i in range(1, len(observation_times))
        ]
        if any(gap <= 0 or gap > max_gap_days for gap in gaps):
            counts["gap_over_21_days"] += 1
            continue

        record: dict[str, Any] = {
            "season": str(target.season),
            "gameweek": int(target.gameweek),
            "fixture_id": str(target.fixture_id),
            "fpl_code": int(target.fpl_code),
            "target_kickoff_time": target_kickoff.isoformat(),
            "target_deadline_time": target_deadline.isoformat(),
            "history_fixture_ids": json.dumps(history["fixture_id"].astype(str).tolist()),
            "history_match_completed_at": json.dumps(
                [value.isoformat() for value in history["match_completed_at"]]
            ),
            "sequence_gap_days": json.dumps([round(value, 6) for value in gaps]),
            "sequence_length": SEQUENCE_LENGTH,
            "feature_count_per_token": len(features),
        }
        for token_index, (_, historical_row) in enumerate(history.iterrows()):
            for feature in features:
                record[f"token_{token_index:02d}__{feature}"] = float(historical_row[feature])
        for feature in features:
            record[f"token_05__{feature}"] = float(getattr(target, feature))
        record["target_points"] = (
            float(target.total_points)
            if has_label and pd.notna(target.total_points)
            else None
        )
        output.append(record)
        counts["emitted"] += 1

    columns = [
        "season", "gameweek", "fixture_id", "fpl_code",
        "target_kickoff_time", "target_deadline_time",
        "history_fixture_ids", "history_match_completed_at",
        "sequence_gap_days", "sequence_length", "feature_count_per_token",
        *[
            f"token_{token:02d}__{feature}"
            for token in range(SEQUENCE_LENGTH)
            for feature in features
        ],
        "target_points",
    ]
    result = pd.DataFrame(output, columns=columns)
    return result, {
        "status": "CANDIDATE_SEQUENCE_DATASET",
        "admission_status": "NOT_ADMITTED",
        "sequence_definition": "five_previous_played_fixtures_plus_target_query",
        "historical_token_semantics": "286-feature snapshot for the historical fixture, captured before that fixture deadline",
        "target_token_semantics": "286-feature snapshot captured strictly before the target Gameweek deadline",
        "history_eligibility": "minutes > 0 and match_completed_at < target deadline",
        "maximum_inter_observation_gap_days": max_gap_days,
        "feature_count_per_token": len(features),
        "sequence_length": SEQUENCE_LENGTH,
        "feature_order_sha256": hashlib.sha256("\n".join(features).encode("utf-8")).hexdigest(),
        "counts": counts,
        "limitations": [
            "A structurally valid sequence does not prove each feature's underlying source events were available by the recorded snapshot timestamp.",
            "All 286 features remain subject to the independent feature-admission register.",
            "Historical source-vintage, identity, rights and season-coverage gates remain open.",
            "Target points are labels only and are not included in any token.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Canonical player-fixture candidate frame")
    parser.add_argument("--schema", type=Path, default=Path(__file__).parents[1] / "config" / "2pm_dastan_286_schema.json")
    parser.add_argument("--out", type=Path, required=True, help="Sequence dataset CSV or Parquet")
    parser.add_argument("--report", type=Path, required=True, help="JSON audit report")
    parser.add_argument("--fixture-column", default="fixture", help="Input fixture ID column (default: fixture)")
    parser.add_argument("--max-gap-days", type=int, default=MAX_GAP_DAYS)
    parser.add_argument("--require-label", action="store_true")
    args = parser.parse_args()

    features, _ = load_schema(args.schema)
    frame = validate_input(read_frame(args.input), features, args.fixture_column)
    sequences, report = build_sequences(
        frame, features, max_gap_days=args.max_gap_days, require_label=args.require_label
    )
    write_frame(sequences, args.out)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
