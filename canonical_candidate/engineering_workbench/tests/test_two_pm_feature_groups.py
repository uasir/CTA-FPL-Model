import json
from pathlib import Path

import pytest

from two_pm_feature_groups import (
    EXPECTED_DEFENSIVE_COLUMNS,
    load_feature_group_manifest,
    validate_feature_group_manifest,
)


ROOT = Path(__file__).resolve().parents[1]


def test_versioned_manifest_partitions_all_286_schema_features_in_order():
    schema, manifest, groups = load_feature_group_manifest(ROOT)
    assert manifest["manifest_version"] == "1.0.0"
    assert len(groups["common_candidate"]) == 259
    assert len(groups["defensive_regime_dependent"]) == 27
    assert groups["defensive_regime_dependent"] == EXPECTED_DEFENSIVE_COLUMNS
    assert len(set(groups["common_candidate"]) | set(groups["defensive_regime_dependent"])) == 286
    assert not set(groups["common_candidate"]) & set(groups["defensive_regime_dependent"])
    defensive = set(groups["defensive_regime_dependent"])
    assert groups["common_candidate"] == tuple(
        name for name in schema["feature_order"] if name not in defensive
    )


def test_reconstruction_family_counts_are_reconciled_without_double_counting():
    _, _, groups = load_feature_group_manifest(ROOT)
    player = set(groups["defensive_player_history"])
    fixture = set(groups["fixture_context"])
    defensive = set(groups["defensive_regime_dependent"])
    assert len(player) == 26
    assert len(fixture) == 6
    assert len(defensive) == 27
    assert len(player | fixture) == 32
    assert not player & fixture
    assert len(defensive & player) == 23
    assert len(defensive & fixture) == 4
    assert {"ar_starts_3", "ar_starts_5", "ar_starts_10"} <= player
    assert {"ar_rest_days", "ar_team_matches_14d"} <= fixture


def test_manifest_fails_closed_when_a_defensive_feature_is_missing():
    schema, manifest, _ = load_feature_group_manifest(ROOT)
    broken = json.loads(json.dumps(manifest))
    broken["feature_groups"]["defensive_regime_dependent"]["feature_order"].remove(
        "ar_dc_ppg_5"
    )
    with pytest.raises(ValueError, match="Expected 259 common and 27"):
        validate_feature_group_manifest(schema, broken)


def test_manifest_fails_closed_when_schema_order_changes():
    schema, manifest, _ = load_feature_group_manifest(ROOT)
    broken_schema = json.loads(json.dumps(schema))
    broken_schema["feature_order"][0], broken_schema["feature_order"][1] = (
        broken_schema["feature_order"][1], broken_schema["feature_order"][0]
    )
    with pytest.raises(ValueError, match="Common feature order"):
        validate_feature_group_manifest(broken_schema, manifest)
