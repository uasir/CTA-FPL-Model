"""Build the selected 2PM post-match-history, player-Gameweek tensor dataset.

This is candidate construction only. It does not admit features or authorize training.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from build_2pm_dastan_sequence_dataset import load_schema
from build_2pm_player_gameweek_sequence_tensors import (
    build_player_gameweek_sequence_tensors,
)
from build_2pm_postmatch_state_vectors import build_postmatch_state_vectors
from rebuild_2pm_dastan_286_candidate import load_dastan_package


def build_dataset(
    dastan_root: Path,
    candidate_path: Path,
    player_matches_path: Path,
    team_matches_path: Path,
    schema_path: Path,
    output_dir: Path,
) -> dict:
    features, feature_hash = load_schema(schema_path)
    _, _, features_module, _, _ = load_dastan_package(dastan_root)

    candidate = pd.read_parquet(candidate_path)
    player_matches = pd.read_parquet(player_matches_path)
    team_matches = pd.read_parquet(team_matches_path)

    postmatch, postmatch_report = build_postmatch_state_vectors(
        candidate, player_matches, team_matches, features_module, features
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    states_path = output_dir / "postmatch_states.parquet"
    postmatch.to_parquet(states_path, index=False)

    group_keys = (
        candidate[["season", "gameweek"]]
        .drop_duplicates()
        .sort_values(["season", "gameweek"], kind="mergesort")
    )
    gameweek_reports = []
    total_emitted = 0
    for row in group_keys.itertuples(index=False):
        season = str(row.season)
        gameweek = int(row.gameweek)
        key = f"{season.replace('/', '-')}_gw{gameweek:02d}"
        shard_dir = output_dir / "player_gameweek_tensors" / key
        report_path = output_dir / "reports" / f"{key}.json"
        target_subset = candidate[
            candidate["season"].astype(str).eq(season)
            & pd.to_numeric(candidate["gameweek"], errors="coerce").eq(gameweek)
        ].copy()
        player_codes = set(pd.to_numeric(target_subset["fpl_code"], errors="raise").astype("int64"))
        history_subset = postmatch[
            postmatch["season"].astype(str).eq(season)
            & pd.to_numeric(postmatch["fpl_code"], errors="raise").astype("int64").isin(player_codes)
        ].copy()
        report = build_player_gameweek_sequence_tensors(
            history_subset,
            target_subset,
            schema_path,
            shard_dir,
            report_path,
            target_season=season,
            target_gameweek=gameweek,
            target_mode="historical",
            label_grain="player_fixture",
        )
        counts = report["counts"]
        total_emitted += int(counts["emitted"])
        gameweek_reports.append({
            "season": season,
            "gameweek": gameweek,
            "emitted": int(counts["emitted"]),
            "insufficient_previous_played_matches": int(
                counts["insufficient_previous_played_matches"]
            ),
            "postmatch_state_not_available_by_deadline": int(
                counts["postmatch_state_not_available_by_deadline"]
            ),
            "gap_over_21_days": int(counts["gap_over_21_days"]),
            "tensor_shards": len(report["shards"]),
            "tensor_directory": str(shard_dir.relative_to(output_dir)),
            "report": str(report_path.relative_to(output_dir)),
        })

    result = {
        "status": "POSTMATCH_PLAYER_GAMEWEEK_CANDIDATE_DATASET_BUILT",
        "admission_status": "NOT_ADMITTED",
        "training_authorized": False,
        "feature_count": len(features),
        "feature_order_sha256": feature_hash,
        "sequence_definition": "five_same_season_postmatch_played_fixture_states_plus_one_prematch_query_per_target_fixture",
        "sample_grain": "player_gameweek",
        "target_label_grain": "player_fixture_summed_once_to_player_gameweek",
        "postmatch_state_report": postmatch_report,
        "postmatch_state_rows": int(len(postmatch)),
        "player_gameweek_groups_considered": int(len(group_keys)),
        "player_gameweek_samples_emitted": total_emitted,
        "gameweeks": gameweek_reports,
        "limitations": [
            "Candidate source vintages and all 286 feature semantics remain NOT_ADMITTED.",
            "The 21-day sequence eligibility rule is enforced by the grouped tensor builder.",
            "No model training, inference, or M3/M4 integration is performed.",
        ],
    }
    report_path = output_dir / "postmatch_grouped_dataset_report.json"
    report_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


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
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = build_dataset(
        args.dastan_root,
        args.candidate,
        args.player_matches,
        args.team_matches,
        args.schema,
        args.output_dir,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
