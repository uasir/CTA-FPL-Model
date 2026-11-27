import hashlib

import numpy as np
import pandas as pd
import pytest

import augment_2pm_candidate_observation_sidecars as augmenter


FEATURES = [f"feature_{i:03d}" for i in range(286)]
RETAINED = [
    "is_home_num", "value", "selected", "transfers_balance",
    "ar_ep_next", "sig_status_risk", "sig_chance_playing", "sig_has_news",
]
for index, name in enumerate(RETAINED):
    FEATURES[index] = name


def candidate_frame():
    frame = pd.DataFrame(
        {name: np.ones(2, dtype=np.float64) for name in FEATURES}
    )
    frame["is_home_num"] = 0
    frame["value"] = -1
    frame["selected"] = 0
    frame["transfers_balance"] = 10
    frame["ar_ep_next"] = -1
    frame["sig_status_risk"] = -1
    frame["sig_chance_playing"] = 0.9
    frame["sig_has_news"] = 0
    return frame


def install_fake_rebuilders(monkeypatch, *, mismatch=False, missing=None):
    def add_partition(frame, names, base_value):
        out = frame.copy()
        for name in names:
            out[name] = base_value
            out[f"__observed__{name}"] = np.ones(len(out), dtype=np.uint8)
        return out, {"status": "TEST"}

    first = FEATURES[:100]
    second = FEATURES[100:200]
    third = FEATURES[200:]

    def player(frame, matches, features):
        value = frame.copy()
        if mismatch:
            value[first[0]] = value[first[0]] + 1
        names = [name for name in first if name != missing]
        for name in names:
            value[f"__observed__{name}"] = 1
        return value, {"status": "TEST"}

    def team(frame, matches, features):
        value = frame.copy()
        names = [name for name in second if name != missing]
        for name in names:
            value[f"__observed__{name}"] = 1
        return value, {"status": "TEST"}

    def fixture(frame, matches):
        value = frame.copy()
        names = [name for name in third if name != missing]
        for name in names:
            value[f"__observed__{name}"] = 1
        return value, {"status": "TEST"}

    monkeypatch.setattr(augmenter, "rebuild_player_history_features", player)
    monkeypatch.setattr(augmenter, "rebuild_deadline_team_context", team)
    monkeypatch.setattr(augmenter, "rebuild_fixture_context", fixture)


def test_candidate_sidecar_migration_preserves_all_feature_values(monkeypatch):
    install_fake_rebuilders(monkeypatch)
    original = candidate_frame()
    augmented, report = augmenter.augment_candidate_frame(
        original,
        pd.DataFrame(),
        pd.DataFrame(),
        object(),
        FEATURES,
        ["value", "ar_ep_next", "sig_status_risk"],
    )
    assert report["status"] == "AUGMENTED_FROM_PINNED_RAW_MATCHES"
    assert report["feature_value_parity"]["status"] == "PASS"
    assert report["sidecar_count"] == 286
    assert len([c for c in augmented if c.startswith("__observed__")]) == 286
    pd.testing.assert_frame_equal(augmented[FEATURES], original[FEATURES])
    assert (augmented["__observed__value"] == 0).all()
    assert (augmented["__observed__selected"] == 1).all()
    assert (augmented["__observed__ar_ep_next"] == 0).all()
    assert (augmented["__observed__sig_chance_playing"] == 1).all()


def test_candidate_sidecar_migration_fails_if_reconstruction_changes_values(monkeypatch):
    install_fake_rebuilders(monkeypatch, mismatch=True)
    with pytest.raises(ValueError, match="changed cached feature values"):
        augmenter.augment_candidate_frame(
            candidate_frame(),
            pd.DataFrame(),
            pd.DataFrame(),
            object(),
            FEATURES,
            ["value", "ar_ep_next", "sig_status_risk"],
        )


def test_candidate_sidecar_migration_fails_if_any_feature_sidecar_is_missing(monkeypatch):
    missing = FEATURES[150]
    install_fake_rebuilders(monkeypatch, missing=missing)
    with pytest.raises(ValueError, match="did not produce all 286 sidecars"):
        augmenter.augment_candidate_frame(
            candidate_frame(),
            pd.DataFrame(),
            pd.DataFrame(),
            object(),
            FEATURES,
            ["value", "ar_ep_next", "sig_status_risk"],
        )


def test_candidate_migration_requires_exact_dastan_vaastav_and_fplcache_pins(tmp_path):
    raw_manifest = tmp_path / "downloads.json"
    raw_manifest.write_text('{"source": "pinned"}')
    manifest = {
        "source_pins": {
            "dastan": {"repository": "dastan/repo", "commit": "dastan-sha"},
            "vaastav": {"repository": "vaastav/repo", "commit": "vaastav-sha"},
            "fplcache": {"repository": "fplcache/repo", "commit": "cache-sha"},
        }
    }
    report = {
        "upstream_commit": "dastan-sha",
        "upstream_repository": "dastan/repo",
        "source_pins": {
            "vaastav": {"repository": "vaastav/repo", "commit": "vaastav-sha"},
            "fplcache": {"repository": "fplcache/repo", "commit": "cache-sha"},
        },
        "source_manifest_sha256": hashlib.sha256(raw_manifest.read_bytes()).hexdigest(),
    }
    assert augmenter.validate_candidate_source_pins(
        report, manifest, "dastan-sha", raw_manifest
    ) == report["source_manifest_sha256"]

    report["source_pins"]["fplcache"]["commit"] = "wrong"
    with pytest.raises(ValueError, match="fplcache source pin"):
        augmenter.validate_candidate_source_pins(
            report, manifest, "dastan-sha", raw_manifest
        )
