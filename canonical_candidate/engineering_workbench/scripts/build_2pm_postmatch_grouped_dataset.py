"""Build the selected 2PM post-match-history, player-Gameweek tensor dataset.

This is candidate construction only. It does not admit features or authorize training.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from build_2pm_dastan_sequence_dataset import load_schema
from build_2pm_player_gameweek_sequence_tensors import (
    build_player_gameweek_sequence_tensors,
)
from two_pm_feature_masks import build_feature_masks
from build_2pm_postmatch_state_vectors import build_postmatch_state_vectors
from rebuild_2pm_dastan_286_candidate import load_dastan_package


def backfill_cached_shard_masks(
    shard_dir: Path,
    declared_shards: list[dict],
    season: str,
    features: list[str],
    feature_manifest: dict,
) -> list[dict]:
    """Add current mask artifacts to reusable tensors without rebuilding features."""
    for shard in declared_shards:
        tensor_path = shard_dir / shard["tensor"]
        fixture_mask_path = shard_dir / shard["fixture_mask"]
        x = np.load(tensor_path, allow_pickle=False)
        fixture_mask = np.load(fixture_mask_path, allow_pickle=False)
        if x.ndim != 4 or x.shape[2:] != (6, len(features)):
            raise ValueError(f"Cached tensor shape mismatch: {tensor_path}")
        if fixture_mask.shape != x.shape[:2]:
            raise ValueError(f"Cached fixture mask shape mismatch: {fixture_mask_path}")
        availability, observed = build_feature_masks(x, season, features, feature_manifest)
        padded = ~fixture_mask.astype(bool)
        availability[padded, :, :] = 0
        observed[padded, :, :] = 0
        suffix = Path(shard["tensor"]).stem.removeprefix("X_player_gw_")
        availability_name = shard.get("source_availability_state") or f"source_availability_state_{suffix}.npy"
        observed_name = shard.get("observed_value_mask") or f"observed_value_mask_{suffix}.npy"
        np.save(shard_dir / availability_name, availability)
        np.save(shard_dir / observed_name, observed)
        shard["source_availability_state"] = availability_name
        shard["observed_value_mask"] = observed_name
    return declared_shards


def build_dataset(
    dastan_root: Path,
    candidate_path: Path,
    player_matches_path: Path,
    team_matches_path: Path,
    schema_path: Path,
    output_dir: Path,
) -> dict:
    features, feature_hash = load_schema(schema_path)
    feature_manifest_path = Path(__file__).resolve().parents[1] / "config" / "2pm_feature_group_manifest.json"
    feature_manifest = json.loads(feature_manifest_path.read_text(encoding="utf-8"))
    _, _, features_module, _, _ = load_dastan_package(dastan_root)

    candidate = pd.read_parquet(candidate_path)
    player_matches = pd.read_parquet(player_matches_path)
    team_matches = pd.read_parquet(team_matches_path)
    if "forecast_target_eligible" not in candidate:
        raise ValueError(
            "Candidate frame lacks forecast_target_eligible; rebuild with the "
            "deadline-aware target/history split"
        )
    target_candidate = candidate[
        candidate["forecast_target_eligible"].fillna(False).astype(bool)
    ].copy()
    if target_candidate.empty:
        raise ValueError("No forecast-eligible historical player-fixture targets remain")

    # Build historical post-match states from the complete fixture archive,
    # not just fixtures eligible as targets at their original FPL deadline.
    postmatch, postmatch_report = build_postmatch_state_vectors(
        candidate, player_matches, team_matches, features_module, features
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    states_path = output_dir / "postmatch_states.parquet"
    postmatch.to_parquet(states_path, index=False)

    group_keys = (
        target_candidate[["season", "gameweek"]]
        .drop_duplicates()
        .sort_values(["season", "gameweek"], kind="mergesort")
    )
    gameweek_reports = []
    total_emitted = 0
    total_player_gameweek_groups = 0
    total_exclusions = {
        "insufficient_previous_played_matches": 0,
        "postmatch_state_not_available_by_deadline": 0,
        "gap_over_21_days": 0,
    }
    for row in group_keys.itertuples(index=False):
        season = str(row.season)
        gameweek = int(row.gameweek)
        key = f"{season.replace('/', '-')}_gw{gameweek:02d}"
        shard_dir = output_dir / "player_gameweek_tensors" / key
        report_path = output_dir / "reports" / f"{key}.json"
        target_subset = target_candidate[
            target_candidate["season"].astype(str).eq(season)
            & pd.to_numeric(target_candidate["gameweek"], errors="coerce").eq(gameweek)
        ].copy()
        player_codes = set(pd.to_numeric(target_subset["fpl_code"], errors="raise").astype("int64"))
        history_subset = postmatch[
            postmatch["season"].astype(str).eq(season)
            & pd.to_numeric(postmatch["fpl_code"], errors="raise").astype("int64").isin(player_codes)
        ].copy()
        # Completed Gameweeks are reusable across interrupted workflow runs.
        # A report is the completion marker: every declared shard must exist and
        # be non-empty before the Gameweek can be skipped. Incomplete directories
        # are discarded and rebuilt so partial shard writes cannot be mistaken
        # for a completed sample set.
        report = None
        if report_path.exists():
            try:
                cached_report = json.loads(report_path.read_text(encoding="utf-8"))
                declared_shards = cached_report.get("shards", [])
                core_shard_files = ("tensor", "fixture_mask", "labels", "metadata")
                shards_valid = (
                    all(
                        all(
                            shard.get(field)
                            and (shard_dir / shard[field]).is_file()
                            and (shard_dir / shard[field]).stat().st_size > 0
                            for field in core_shard_files
                        )
                        for shard in declared_shards
                    )
                    if declared_shards
                    else int(cached_report.get("counts", {}).get("emitted", -1)) == 0
                )
                report_valid = (
                    cached_report.get("status") == "PLAYER_GAMEWEEK_SEQUENCE_TENSORS_BUILT"
                    and cached_report.get("target_mode") == "historical"
                    and cached_report.get("target_season") == season
                    and int(cached_report.get("target_gameweek", -1)) == gameweek
                    and shards_valid
                )
                if report_valid:
                    cached_report["feature_order"] = features
                    cached_report["snapshot_missing_sentinel_features"] = feature_manifest.get(
                        "snapshot_missing_sentinel_features", []
                    )
                    cached_report["feature_availability_state_codes"] = {
                        "UNAVAILABLE": 0, "AVAILABLE": 1, "UNKNOWN": 2
                    }
                    # Backfill masks on reusable tensors without reacquiring sources
                    # or repeating post-match feature reconstruction.
                    backfill_cached_shard_masks(
                        shard_dir, declared_shards, season, features, feature_manifest
                    )
                    report_path.write_text(
                        json.dumps(cached_report, indent=2) + "\n", encoding="utf-8"
                    )
                    report = cached_report
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                report = None
        if report is None:
            if shard_dir.exists():
                shutil.rmtree(shard_dir)
            report_path.unlink(missing_ok=True)
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
        total_player_gameweek_groups += int(counts["player_gameweek_groups"])
        for reason in total_exclusions:
            total_exclusions[reason] += int(counts[reason])
        gameweek_reports.append({
            "player_gameweek_groups": int(counts["player_gameweek_groups"]),
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
        "feature_order": features,
        "snapshot_missing_sentinel_features": feature_manifest.get(
            "snapshot_missing_sentinel_features", []
        ),
        "feature_availability_state_codes": {
            "UNAVAILABLE": 0, "AVAILABLE": 1, "UNKNOWN": 2
        },
        "feature_order_sha256": feature_hash,
        "sequence_definition": "five_same_season_postmatch_played_fixture_states_plus_one_prematch_query_per_target_fixture",
        "sample_grain": "player_gameweek",
        "target_label_grain": "player_fixture_summed_once_to_player_gameweek",
        "postmatch_state_report": postmatch_report,
        "postmatch_state_rows": int(len(postmatch)),
        "season_gameweek_groups_processed": int(len(group_keys)),
        "player_gameweek_candidate_groups_considered": total_player_gameweek_groups,
        "player_gameweek_samples_emitted": total_emitted,
        "player_gameweek_exclusions": total_exclusions,
        "gameweeks": gameweek_reports,
        "limitations": [
            "All played historical fixtures are retained for post-match tokens, including fixtures not eligible as targets at their original FPL deadline.",
            "Only fixtures kicking off strictly after their official Gameweek deadline are used as forecast targets.",
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
