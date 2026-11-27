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
    assert manifest["manifest_version"] == "1.6.0"
    assert manifest["source_pins"]["dastan"]["commit"] == "758db9247e8b3a9a870c991064f74d8339d61cd0"
    assert manifest["source_pins"]["vaastav"]["commit"] == "8c97b2adb123863c3dd581e730f1360e89815ac2"
    assert manifest["source_pins"]["fplcache"]["commit"] == "6c364bfbd9914649dc5dec016e544be3ae4fe767"
    assert manifest["source_vintage_policies"]["understat"]["status"] == "HOLD"
    assert manifest["source_vintage_policies"]["understat"]["mask_action"] == "FORCE_UNOBSERVED"
    assert len(manifest["source_vintage_policies"]["understat"]["feature_order"]) == 100
    assert len(manifest["source_availability_groups"]["understat_player_history"]["feature_order"]) == 20
    assert len(manifest["source_availability_groups"]["understat_team_context"]["feature_order"]) == 80
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


def test_manifest_keeps_unverified_2026_27_availability_unknown():
    schema, manifest, _ = load_feature_group_manifest(ROOT)
    policy = manifest["feature_source_availability"]
    assert policy["default_state"] == "UNKNOWN"
    assert policy["groups"]["defensive_regime_dependent"]["2025-26"] == "AVAILABLE"
    assert policy["groups"]["defensive_regime_dependent"].get("2026-27", "UNKNOWN") == "UNKNOWN"


def test_manifest_rejects_promoting_unverified_current_season_to_available():
    schema, manifest, _ = load_feature_group_manifest(ROOT)
    broken = json.loads(json.dumps(manifest))
    broken["feature_source_availability"]["groups"]["defensive_regime_dependent"]["2026-27"] = "AVAILABLE"
    with pytest.raises(ValueError, match="2026/27 defensive source availability"):
        validate_feature_group_manifest(schema, broken)


def test_feature_family_and_reconstruction_treatment_registers_cover_286_once():
    schema, manifest, _ = load_feature_group_manifest(ROOT)
    family = manifest["feature_family_register"]
    assert {name: item["count"] for name, item in family["families"].items()} == {
        "Player rolling": 115,
        "Own-team rolling": 60,
        "Opponent rolling": 60,
        "Flat context": 6,
        "Availability history": 9,
        "Dastan engineered/context": 33,
        "Pre-deadline availability": 3,
    }
    assert sum(item["count"] for item in family["reconstruction_treatments"].values()) == 286
    assert family["admission_status_counts"] == {"HOLD": 286}
    features = [
        feature for item in family["families"].values()
        for feature in item["feature_order"]
    ]
    assert len(features) == 286
    assert set(features) == set(schema["feature_order"])


def test_feature_family_register_rejects_missing_or_duplicated_feature():
    schema, manifest, _ = load_feature_group_manifest(ROOT)
    broken = json.loads(json.dumps(manifest))
    broken["feature_family_register"]["families"]["Player rolling"]["feature_order"].pop()
    with pytest.raises(ValueError, match="partition all 286 schema columns"):
        validate_feature_group_manifest(schema, broken)


def test_manifest_source_pins_must_match_the_feature_schema():
    schema, manifest, _ = load_feature_group_manifest(ROOT)
    broken = json.loads(json.dumps(manifest))
    broken["source_pins"]["dastan"]["commit"] = "wrong-commit"
    with pytest.raises(ValueError, match="Dastan pin"):
        validate_feature_group_manifest(schema, broken)


def test_scoring_regime_contract_encodes_the_official_2025_26_boundary_and_2026_27_continuation():
    _, manifest, _ = load_feature_group_manifest(ROOT)
    scoring = manifest["scoring_regime_contract"]
    assert scoring["regime_by_season"]["legacy_no_defensive_contribution_points"] == [
        "2020-21", "2021-22", "2022-23", "2023-24", "2024-25"
    ]
    assert scoring["regime_by_season"]["defensive_contribution_v1"] == ["2025-26", "2026-27"]
    current = scoring["regimes"]["defensive_contribution_v1"]
    assert current["defender"]["action_fields"] == [
        "clearances_blocks_interceptions", "tackles"
    ]
    assert current["defender"]["threshold"] == 10
    assert current["midfielder_forward"]["action_fields"] == [
        "clearances_blocks_interceptions", "tackles", "recoveries"
    ]
    assert current["midfielder_forward"]["threshold"] == 12
    assert current["defender"]["award_points"] == 2
    assert current["defender"]["maximum_award_points_per_match"] == 2


def test_scoring_regime_contract_rejects_wrong_midfielder_threshold():
    schema, manifest, _ = load_feature_group_manifest(ROOT)
    broken = json.loads(json.dumps(manifest))
    broken["scoring_regime_contract"]["regimes"]["defensive_contribution_v1"][
        "midfielder_forward"
    ]["threshold"] = 10
    with pytest.raises(ValueError, match="midfielder_forward"):
        validate_feature_group_manifest(schema, broken)
