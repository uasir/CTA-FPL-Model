from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest
from aggregate_abc_player_gameweeks import aggregate_player_gameweeks


def row(fixture_id, **overrides):
    base = {
        "season": "2017/18",
        "fpl_element_id": "10",
        "gameweek": "7",
        "fixture_id": fixture_id,
        "identity_verified": "True",
        "research_eligible_for_analysis": "True",
        "target_fpl_total_points": "3",
        "target_fpl_minutes": "90",
        "abc_progressive_passes": "1.5",
        "abc_defensive_actions": "2.0",
        "abc_defensive_exposure": "55",
        "fpl_total_points_prior_3_avg": "4.2",
        "fpl_total_points_prior_5_avg": "3.8",
        "fpl_minutes_prior_3_avg": "75",
        "fpl_minutes_prior_5_avg": "70",
        "feature_cutoff_time_utc": "2017-09-01T00:00:00Z",
        "feature_cutoff_policy": "CONSERVATIVE_EARLIEST_GAMEWEEK_KICKOFF",
        "abc_provenance": "pinned-source-hash",
    }
    base.update(overrides)
    return base


def test_single_fixture_player_gameweek_retains_consistent_snapshots_and_labels():
    result = aggregate_player_gameweeks(
        [row("101")],
        {("2017/18", "10", 7): {"101"}},
    )[0]
    assert result["fixture_count_observed"] == 1
    assert result["fixture_completeness_status"] == "PASS"
    assert result["target_fpl_total_points"] == 3.0
    assert result["target_fpl_minutes"] == 90.0
    assert result["abc_progressive_passes"] == 1.5
    assert result["research_eligible_for_model"] is True


def test_double_gameweek_sums_labels_but_does_not_sum_rolling_features():
    result = aggregate_player_gameweeks(
        [row("101"), row("102")],
        {("2017/18", "10", 7): {"101", "102"}},
    )[0]
    assert result["target_fpl_total_points"] == 6.0
    assert result["target_fpl_minutes"] == 180.0
    assert result["abc_progressive_passes"] == 1.5
    assert result["fpl_total_points_prior_3_avg"] == 4.2
    assert result["research_eligible_for_model"] is True


def test_double_gameweek_conflicting_opponent_context_is_null_not_averaged():
    result = aggregate_player_gameweeks(
        [row("101"), row("102", abc_defensive_exposure="61")],
        {("2017/18", "10", 7): {"101", "102"}},
    )[0]
    assert result["abc_defensive_exposure"] is None
    assert result["abc_feature_aggregation_status"]["abc_defensive_exposure"] == "CONFLICT"
    assert result["research_eligible_for_model"] is True


def test_partial_feature_coverage_stays_null_and_explicit():
    result = aggregate_player_gameweeks(
        [row("101"), row("102", abc_progressive_passes="")],
        {("2017/18", "10", 7): {"101", "102"}},
    )[0]
    assert result["abc_progressive_passes"] is None
    assert result["abc_feature_aggregation_status"]["abc_progressive_passes"] == "PARTIAL"


def test_missing_expected_fixture_count_blocks_model_eligibility():
    result = aggregate_player_gameweeks([row("101")])[0]
    assert result["fixture_completeness_status"] == "NOT_CHECKED"
    assert result["research_eligible_for_model"] is False
    assert "REFERENCE_FIXTURE_IDS_NOT_SUPPLIED" in result["exclusion_reasons"]


def test_incomplete_double_gameweek_blocks_model_eligibility():
    result = aggregate_player_gameweeks(
        [row("101")],
        {("2017/18", "10", 7): {"101", "102"}},
    )[0]
    assert result["fixture_completeness_status"] == "MISMATCH"
    assert result["research_eligible_for_model"] is False


def test_duplicate_player_fixture_rows_fail_closed():
    with pytest.raises(ValueError, match="Duplicate player-fixture"):
        aggregate_player_gameweeks(
            [row("101"), row("101")],
            {("2017/18", "10", 7): {"101"}},
        )


def test_inconsistent_predeadline_snapshot_cutoff_blocks_eligibility():
    result = aggregate_player_gameweeks(
        [row("101"), row("102", feature_cutoff_time_utc="2017-09-02T00:00:00Z")],
        {("2017/18", "10", 7): {"101", "102"}},
    )[0]
    assert result["research_eligible_for_model"] is False
    assert "CONFLICTING_FEATURE_CUTOFF_TIME_UTC" in result["exclusion_reasons"]
