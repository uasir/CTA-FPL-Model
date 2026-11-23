import json

import numpy as np
import pandas as pd

from prepare_2pm_candidate_tensors import prepare_candidate_tensors


FEATURES = [f"feature_{index:03d}" for index in range(286)]


def candidate_frame():
    rows = []
    kickoffs = pd.date_range("2026-07-01T12:00:00Z", periods=6, freq="7D")
    for index, kickoff in enumerate(kickoffs):
        deadline = kickoff - pd.Timedelta(hours=3)
        values = {feature: float(index + 1) for feature in FEATURES}
        if index == 0:
            values[FEATURES[0]] = np.nan
            values[FEATURES[1]] = -1.0
        is_target = index == 5
        rows.append({
            "season": "2026-27",
            "gameweek": index + 1,
            "fixture": 700 + index,
            "fpl_code": 12345,
            "kickoff_time": kickoff,
            "match_available_at": (
                pd.NaT if is_target else kickoff + pd.Timedelta(hours=24)
            ),
            "deadline_time": deadline,
            "feature_cutoff_time": deadline,
            "minutes": 0 if is_target else 90,
            "completion_time_quality": (
                "NOT_FINISHED" if is_target else "CONSERVATIVE_24H_UPPER_BOUND"
            ),
            "source_vintage_status": (
                "CURRENT_TARGET_QUERY_FROM_PREDEADLINE_SNAPSHOT"
                if is_target else "RETROSPECTIVE_SOURCE_VINTAGE_NOT_VERIFIED"
            ),
            "target_points": 0 if is_target else index + 1,
            **values,
        })
    return pd.DataFrame(rows)


def test_candidate_tensor_preparation_audits_nan_and_preserves_minus_one(tmp_path):
    frame = candidate_frame()
    input_path = tmp_path / "candidate.parquet"
    frame.to_parquet(input_path, index=False)
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps({
        "feature_count": 286,
        "feature_order": FEATURES,
    }))
    tensor_dir = tmp_path / "tensors"
    report_path = tmp_path / "report.json"

    report = prepare_candidate_tensors(
        input_path, schema_path, tensor_dir, report_path, shard_size=10
    )
    assert report["residual_nan_values_imputed_to_zero"] == 1
    assert report["preserved_minus_one_snapshot_sentinels"] == 1
    assert report["raw_nan_counts_by_feature"][FEATURES[0]] == 1
    tensor = np.load(tensor_dir / "X_00000.npy")
    assert tensor.shape == (1, 6, 286)
    assert np.isfinite(tensor).all()
    assert tensor[0, 0, 0] == 0.0
    assert tensor[0, 0, 1] == -1.0
    assert report_path.exists()


def test_candidate_tensor_preparation_fails_on_infinity(tmp_path):
    frame = candidate_frame()
    frame.loc[0, FEATURES[0]] = np.inf
    input_path = tmp_path / "candidate.parquet"
    frame.to_parquet(input_path, index=False)
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps({
        "feature_count": 286,
        "feature_order": FEATURES,
    }))
    import pytest
    with pytest.raises(ValueError, match="infinite values"):
        prepare_candidate_tensors(
            input_path,
            schema_path,
            tmp_path / "tensors",
            tmp_path / "report.json",
        )
