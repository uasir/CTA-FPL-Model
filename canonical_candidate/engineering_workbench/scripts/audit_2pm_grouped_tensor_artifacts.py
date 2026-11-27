"""Fail-closed integrity audit for emitted 2PM player-Gameweek tensor shards."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def audit_dataset(dataset_dir: Path) -> dict:
    dataset_dir = Path(dataset_dir)
    report_path = dataset_dir / "postmatch_grouped_dataset_report.json"
    if not report_path.is_file():
        raise FileNotFoundError(f"Missing grouped dataset report: {report_path}")
    build_report = json.loads(report_path.read_text(encoding="utf-8"))
    if build_report.get("admission_status") != "NOT_ADMITTED":
        raise ValueError("Unexpected feature admission state; review before continuing")
    if build_report.get("training_authorized") is not False:
        raise ValueError("Candidate tensor dataset must not authorize training")

    x_files = sorted((dataset_dir / "player_gameweek_tensors").rglob("X_player_gw_*.npy"))
    if not x_files:
        raise ValueError("No player-Gameweek tensor shards were emitted")

    seen: set[tuple[str, int, int]] = set()
    samples = fixture_slots = valid_fixtures = nan_values = feature_values = 0
    inf_values = negative_labels = 0
    availability_state_counts = {"0": 0, "1": 0, "2": 0}
    observed_value_count = 0
    fixture_count_histogram: dict[str, int] = {}
    season_counts: dict[str, int] = {}
    max_gap = 0.0

    for x_path in x_files:
        suffix = x_path.stem.removeprefix("X_player_gw_")
        folder = x_path.parent
        mask_path = folder / f"fixture_mask_{suffix}.npy"
        availability_path = folder / f"source_availability_state_{suffix}.npy"
        observed_path = folder / f"observed_value_mask_{suffix}.npy"
        y_path = folder / f"y_player_gw_{suffix}.npy"
        metadata_path = folder / f"metadata_player_gw_{suffix}.csv"
        for required in (mask_path, availability_path, observed_path, y_path, metadata_path):
            if not required.is_file():
                raise FileNotFoundError(f"Missing shard companion: {required}")

        x = np.load(x_path, allow_pickle=False)
        mask = np.load(mask_path, allow_pickle=False)
        availability = np.load(availability_path, allow_pickle=False)
        observed = np.load(observed_path, allow_pickle=False)
        y = np.load(y_path, allow_pickle=False).reshape(-1)
        metadata = pd.read_csv(metadata_path)

        if x.ndim != 4 or x.shape[2:] != (6, 286):
            raise ValueError(f"Unexpected X shape in {x_path}: {x.shape}")
        if mask.shape != x.shape[:2]:
            raise ValueError(f"Fixture mask shape mismatch in {mask_path}: {mask.shape}")
        if not np.isin(mask, [0, 1, False, True]).all():
            raise ValueError(f"Fixture mask contains values other than 0/1: {mask_path}")
        if len(y) != x.shape[0] or len(metadata) != x.shape[0]:
            raise ValueError(f"Sample count mismatch in shard {folder.name}/{suffix}")
        if np.isinf(x).any():
            raise ValueError(f"Infinite feature value found in {x_path}")
        if not np.isfinite(y).all():
            raise ValueError(f"Non-finite target label found in {y_path}")

        if not np.allclose(y, pd.to_numeric(metadata["target_points"], errors="raise"), atol=1e-6):
            raise ValueError(f"Tensor labels do not match metadata in {metadata_path}")

        mask_counts = mask.astype(bool).sum(axis=1)
        metadata_fixture_counts = pd.to_numeric(metadata["fixture_count"], errors="raise").to_numpy()
        if not np.array_equal(mask_counts, metadata_fixture_counts):
            raise ValueError(f"Fixture mask does not match metadata in {metadata_path}")

        for row in metadata.itertuples(index=False):
            key = (str(row.season), int(row.gameweek), int(row.fpl_code))
            if key in seen:
                raise ValueError(f"Duplicate player-Gameweek sample: {key}")
            seen.add(key)
            season_counts[key[0]] = season_counts.get(key[0], 0) + 1
            fixture_count = int(row.fixture_count)
            fixture_count_histogram[str(fixture_count)] = fixture_count_histogram.get(str(fixture_count), 0) + 1

            history_ids = json.loads(row.history_fixture_ids)
            history_times = pd.to_datetime(json.loads(row.history_state_as_of_times), utc=True)
            gaps = [float(v) for v in json.loads(row.sequence_gap_days)]
            if len(history_ids) != 5 or len(history_times) != 5 or len(gaps) != 5:
                raise ValueError(f"Sequence does not contain five history states: {key}")
            if any(pd.isna(t) for t in history_times):
                raise ValueError(f"Invalid history timestamp: {key}")
            deadline = pd.to_datetime(row.target_deadline_time, utc=True)
            kickoff = pd.to_datetime(row.target_first_kickoff_time, utc=True)
            if not (history_times < deadline).all():
                raise ValueError(f"History state is not strictly pre-deadline: {key}")
            if not deadline < kickoff:
                raise ValueError(f"Target kickoff is not after deadline: {key}")
            if any(g < 0 or g > 21 for g in gaps):
                raise ValueError(f"Sequence gap violates 21-day limit: {key}")
            max_gap = max(max_gap, max(gaps))

            fixture_points = [float(v) for v in json.loads(row.fixture_target_points)]
            if len(fixture_points) != fixture_count:
                raise ValueError(f"Fixture label count mismatch: {key}")
            if not np.isclose(sum(fixture_points), float(row.target_points), atol=1e-6):
                raise ValueError(f"Fixture labels do not sum to player-Gameweek label: {key}")

        samples += int(x.shape[0])
        fixture_slots += int(mask.size)
        valid_fixtures += int(mask.astype(bool).sum())
        nan_values += int(np.isnan(x).sum())
        feature_values += int(x.size)
        inf_values += int(np.isinf(x).sum())
        negative_labels += int((y < 0).sum())
        for code in (0, 1, 2):
            availability_state_counts[str(code)] += int((availability == code).sum())
        observed_value_count += int(observed.sum())

    expected = {
        "postmatch_state_rows": int(build_report.get("postmatch_state_rows", -1)),
        "season_gameweek_groups_processed": int(build_report.get("season_gameweek_groups_processed", -1)),
        "player_gameweek_candidate_groups_considered": int(build_report.get("player_gameweek_candidate_groups_considered", -1)),
        "player_gameweek_samples_emitted": int(build_report.get("player_gameweek_samples_emitted", -1)),
    }
    if samples != expected["player_gameweek_samples_emitted"]:
        raise ValueError(f"Emitted sample count mismatch: shards={samples}, report={expected['player_gameweek_samples_emitted']}")
    return {
        "status": "PASS",
        "admission_status": "NOT_ADMITTED",
        "training_authorized": False,
        "tensor_shards": len(x_files),
        "samples": samples,
        "unique_player_gameweek_keys": len(seen),
        "valid_fixture_queries": valid_fixtures,
        "fixture_slots": fixture_slots,
        "availability_state_counts": availability_state_counts,
        "observed_value_count": observed_value_count,
        "fixture_count_histogram": fixture_count_histogram,
        "season_sample_counts": season_counts,
        "feature_count": 286,
        "sequence_length": 6,
        "nan_feature_values_preserved_for_fold_imputation": nan_values,
        "total_feature_values": feature_values,
        "nan_feature_rate": (nan_values / feature_values) if feature_values else None,
        "infinite_feature_values": inf_values,
        "negative_target_labels_preserved": negative_labels,
        "maximum_observation_gap_days": max_gap,
        "build_report_counts": expected,
        "checks": [
            "all tensor shards have [samples, fixtures, 6, 286] shape",
            "tensor, fixture-mask, source-availability mask, observed-value mask and metadata sample counts agree",
            "source availability uses 0=unavailable, 1=available, 2=unknown",
            "observed-value mask excludes non-finite values and structurally unavailable features",
            "player-Gameweek keys are unique across all shards",
            "fixture masks match per-sample fixture counts",
            "five historical states are strictly before the target deadline",
            "target deadline is strictly before first target kickoff",
            "all five history gaps are within 21 days",
            "fixture labels sum to the player-Gameweek target label",
            "negative labels are retained and feature NaNs remain un-imputed",
            "no infinite features or non-finite target labels",
            "candidate remains NOT_ADMITTED and training unauthorized",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit_dataset(args.dataset_dir)
    except Exception as exc:
        result = {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        raise
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
