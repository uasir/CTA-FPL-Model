"""Build current-season 2PM inference tensors using post-match history states.

This is the active-season counterpart to the historical grouped dataset builder:
played fixtures become conservative post-match history tokens, while only the
selected Gameweek's TARGET_QUERY rows become pre-deadline fixture queries.
It performs no training and does not admit the 286-feature candidate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from build_2pm_dastan_sequence_dataset import load_schema
from build_2pm_player_gameweek_sequence_tensors import (
    build_player_gameweek_sequence_tensors,
)
from build_2pm_postmatch_state_vectors import build_postmatch_state_vectors
from rebuild_2pm_dastan_286_candidate import load_dastan_package


def build_active_postmatch_inference(
    dastan_root: Path,
    candidate_path: Path,
    player_matches_path: Path,
    team_matches_path: Path,
    schema_path: Path,
    output_dir: Path,
    report_path: Path,
    *,
    target_season: str,
    target_gameweek: int,
    shard_size: int = 10000,
) -> dict[str, Any]:
    features, feature_hash = load_schema(schema_path)
    _, _, features_module, _, _ = load_dastan_package(dastan_root)

    candidate = pd.read_parquet(candidate_path)
    player_matches = pd.read_parquet(player_matches_path)
    team_matches = pd.read_parquet(team_matches_path)
    required = {
        "row_role", "season", "gameweek", "fixture", "fpl_code",
        "kickoff_time", "deadline_time", "feature_cutoff_time", "minutes",
        "match_available_at", "source_vintage_status", "team_name",
        "opponent_team_name",
    }
    missing = sorted(required - set(candidate.columns))
    if missing:
        raise ValueError(f"Active candidate is missing required metadata: {missing}")
    if not candidate["row_role"].isin(
        {"HISTORICAL_FIXTURE", "TARGET_QUERY"}
    ).all():
        raise ValueError("Active candidate contains an unknown row_role")
    target_queries = candidate[
        candidate["row_role"].eq("TARGET_QUERY")
        & candidate["season"].astype(str).eq(str(target_season))
        & pd.to_numeric(candidate["gameweek"], errors="coerce").eq(int(target_gameweek))
    ].copy()
    if target_queries.empty:
        raise ValueError(
            f"No TARGET_QUERY rows found for {target_season} GW{target_gameweek}"
        )
    if target_queries["target_points"].notna().any():
        raise ValueError("Active TARGET_QUERY rows must not contain realized points")

    # Include all candidate rows as the state-builder input. It filters to actual
    # appearances itself; future target queries remain schedule/context only.
    postmatch, postmatch_report = build_postmatch_state_vectors(
        candidate, player_matches, team_matches, features_module, features
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    states_path = output_dir / "postmatch_states.parquet"
    postmatch.to_parquet(states_path, index=False)

    tensor_dir = output_dir / "player_gameweek_inference_tensors"
    tensor_report_path = output_dir / "player_gameweek_inference_report.json"
    tensor_report = build_player_gameweek_sequence_tensors(
        states_path,
        target_queries,
        schema_path,
        tensor_dir,
        tensor_report_path,
        target_season=str(target_season),
        target_gameweek=int(target_gameweek),
        target_mode="inference",
        label_grain=None,
        shard_size=shard_size,
    )

    report = {
        "status": "ACTIVE_POSTMATCH_INFERENCE_TENSORS_BUILT",
        "admission_status": "NOT_ADMITTED",
        "training_authorized": False,
        "target_season": str(target_season),
        "target_gameweek": int(target_gameweek),
        "feature_count": len(features),
        "feature_order_sha256": feature_hash,
        "target_query_player_fixture_rows": int(len(target_queries)),
        "target_fixture_count": int(target_queries["fixture"].nunique()),
        "postmatch_state_rows": int(len(postmatch)),
        "postmatch_state_report": postmatch_report,
        "inference_tensor_report": tensor_report,
        "postmatch_states_file": states_path.name,
        "inference_tensor_directory": tensor_dir.name,
        "limitations": [
            "Only TARGET_QUERY rows for the selected season/Gameweek are emitted as inference samples.",
            "Five history tokens are actual played fixtures with conservative post-match availability timestamps.",
            "The 286-feature candidate and active-season historical source vintages remain NOT_ADMITTED.",
            "No model training, point forecast, or M3/M4 recommendation is performed by this builder.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dastan-root", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--player-matches", type=Path, required=True)
    parser.add_argument("--team-matches", type=Path, required=True)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).parents[1] / "config" / "2pm_dastan_286_schema.json",
    )
    parser.add_argument("--target-season", required=True)
    parser.add_argument("--target-gameweek", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--shard-size", type=int, default=10000)
    args = parser.parse_args()
    report = build_active_postmatch_inference(
        args.dastan_root,
        args.candidate,
        args.player_matches,
        args.team_matches,
        args.schema,
        args.output_dir,
        args.report,
        target_season=args.target_season,
        target_gameweek=args.target_gameweek,
        shard_size=args.shard_size,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
