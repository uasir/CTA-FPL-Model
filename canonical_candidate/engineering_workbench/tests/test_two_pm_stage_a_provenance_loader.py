from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("torch")
import train_two_pm_poisson_transformer as trainer


FEATURES = [f"feature_{i}" for i in range(286)]
COMMON = FEATURES[:259]
DEFENSIVE = FEATURES[259:]


def build_artifact(tmp_path: Path, *, include_masks: bool = True):
    root = tmp_path / "artifact"
    tensor_dir = root / "postmatch-grouped-dataset" / "player_gameweek_tensors" / "2024-25_gw01"
    tensor_dir.mkdir(parents=True)
    schema_path = tmp_path / "schema.json"
    manifest_path = tmp_path / "manifest.json"
    schema_path.write_text(json.dumps({"feature_order": FEATURES}))
    manifest_path.write_text(json.dumps({
        "feature_groups": {
            "common_candidate": {"feature_order": COMMON},
            "defensive_regime_dependent": {"feature_order": DEFENSIVE},
        }
    }))
    metadata_path = tensor_dir / "metadata_player_gw_00000.csv"
    with metadata_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["season", "gameweek", "fpl_code", "fixture_ids"])
        writer.writeheader()
        writer.writerow({"season": "2024-25", "gameweek": "1", "fpl_code": "100", "fixture_ids": "1"})
    x = np.zeros((1, 1, 6, 286), dtype=np.float32)
    x[0, 0, 0, 3] = 123.0
    fixture = np.ones((1, 1), dtype=np.uint8)
    y = np.asarray([2], dtype=np.float32)
    np.save(tensor_dir / "X_player_gw_00000.npy", x)
    np.save(tensor_dir / "fixture_mask_00000.npy", fixture)
    np.save(tensor_dir / "y_player_gw_00000.npy", y)
    if include_masks:
        observed = np.zeros_like(x, dtype=np.uint8)
        observed[0, 0, 0, 3] = 1
        availability = np.ones_like(x, dtype=np.uint8)
        availability[0, 0, 0, 3] = 2
        np.save(tensor_dir / "observed_value_mask_00000.npy", observed)
        np.save(tensor_dir / "source_availability_state_00000.npy", availability)
    return root, schema_path, manifest_path, tensor_dir


def test_loader_requires_both_provenance_arrays(tmp_path):
    root, schema, manifest, _ = build_artifact(tmp_path, include_masks=False)
    with pytest.raises(FileNotFoundError, match="required provenance arrays"):
        trainer.load_grouped_dataset(root, schema, manifest)


def test_loader_preserves_feature_axis_and_observed_zero_semantics(tmp_path):
    root, schema, manifest, _ = build_artifact(tmp_path)
    samples, feature_order = trainer.load_grouped_dataset(root, schema, manifest)
    values, fixture_mask, observed, metadata = samples[0]
    assert feature_order == COMMON
    assert values.shape == (1, 6, 259)
    assert values[0, 0, 3] == 123.0
    assert observed[0, 0, 3]
    assert metadata["availability"][0, 0, 3] == 2
    assert fixture_mask.tolist() == [True]


def test_loader_enforces_manifest_source_vintage_hold_over_stored_mask(tmp_path):
    root, schema, manifest, _ = build_artifact(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["source_vintage_policies"] = {
        "understat": {
            "status": "HOLD",
            "mask_action": "FORCE_UNOBSERVED",
            "feature_count": 1,
            "feature_order": ["feature_3"],
        }
    }
    manifest.write_text(json.dumps(payload))

    samples, _ = trainer.load_grouped_dataset(root, schema, manifest)
    values, _, observed, metadata = samples[0]

    # The stale artifact says this finite value is observed; the current
    # manifest HOLD decision must win without rebuilding the tensor artifact.
    assert values[0, 0, 3] == 123.0
    assert not observed[0, 0, 3]
    assert metadata["availability"][0, 0, 3] == 2


def test_loader_fails_closed_on_unsupported_source_vintage_policy(tmp_path):
    root, schema, manifest, _ = build_artifact(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["source_vintage_policies"] = {
        "understat": {
            "status": "VERIFIED",
            "mask_action": "APPLY_ROW_LEVEL_MASK",
            "feature_count": 1,
            "feature_order": ["feature_3"],
        }
    }
    manifest.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="Unsupported source-vintage policy"):
        trainer.load_grouped_dataset(root, schema, manifest)


def test_loader_rejects_observed_value_from_unavailable_source(tmp_path):
    root, schema, manifest, tensor_dir = build_artifact(tmp_path)
    availability = np.load(tensor_dir / "source_availability_state_00000.npy")
    availability[0, 0, 0, 3] = 0
    np.save(tensor_dir / "source_availability_state_00000.npy", availability)
    with pytest.raises(ValueError, match="marked observed"):
        trainer.load_grouped_dataset(root, schema, manifest)


def test_loader_rejects_nonbinary_observed_mask(tmp_path):
    root, schema, manifest, tensor_dir = build_artifact(tmp_path)
    observed = np.load(tensor_dir / "observed_value_mask_00000.npy")
    observed[0, 0, 0, 3] = 3
    np.save(tensor_dir / "observed_value_mask_00000.npy", observed)
    with pytest.raises(ValueError, match="must be binary"):
        trainer.load_grouped_dataset(root, schema, manifest)
