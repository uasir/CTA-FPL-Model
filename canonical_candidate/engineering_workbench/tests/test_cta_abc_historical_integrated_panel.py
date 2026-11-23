import json

import pytest

from build_cta_abc_historical_integrated_panel import enrich_panel


def _wys(**overrides):
    row = {
        "season": "2017/18", "fpl_element_id": "10", "gameweek": "4",
        "fixture_id": "104", "target_fpl_total_points": "6",
        "research_eligible_for_analysis": "True",
        "abc_player_key_pass_rate": "0.8",
        "abc_progressive_passes": "2.5",
        "abc_duel_success_rate": "0.6",
    }
    row.update(overrides)
    return row


def _footy(gw, fixture, **overrides):
    row = {
        "join_status": "VERIFIED_IDENTITY_AND_FIXTURE",
        "fpl_element_id": "10", "fpl_fixture_id": str(fixture),
        "gameweek": str(gw), "match_kickoff_utc": f"2017-08-{gw:02d}T15:00:00Z",
        "minutes_played": "90", "key_passes": "2", "tracked_xg_sum": "0.2",
        "shots": "3", "attempts_inside_box": "2", "goals": "1",
        "fouls_committed": "1",
    }
    row.update(overrides)
    return row


def test_11footy_is_primary_and_wyscout_fills_unavailable_features():
    rows, report = enrich_panel([_wys()], [_footy(1, 101), _footy(2, 102), _footy(3, 103)])
    row = rows[0]
    assert row["abc_player_key_pass_rate"] == pytest.approx(2.0)
    assert row["abc_player_tracked_xg_rate"] == pytest.approx(0.2)
    assert row["abc_progressive_passes"] == pytest.approx(2.5)
    assert row["abc_duel_success_rate"] == pytest.approx(0.6)
    sources = json.loads(row["abc_feature_sources"])
    assert sources["player_key_pass_rate"] == "11footy"
    assert sources["progressive_passes"] == "wyscout"
    assert report["feature_values_from_11footy"]["player_key_pass_rate"] == 1
    assert report["feature_values_fallback_to_wyscout"]["progressive_passes"] == 1


def test_same_gameweek_features_are_never_used():
    rows, _ = enrich_panel([_wys(gameweek="3")], [_footy(1, 101), _footy(2, 102), _footy(3, 103)])
    assert rows[0]["abc_player_key_pass_rate"] == pytest.approx(2.0)
    rows, _ = enrich_panel([_wys(gameweek="2")], [_footy(1, 101), _footy(2, 102)])
    # One prior match is insufficient to expose an empty 11footy statistic window?
    assert rows[0]["abc_player_key_pass_rate"] == pytest.approx(2.0)


def test_unverified_11footy_rows_never_contribute():
    bad = _footy(1, 101, join_status="PENDING_RESEARCH_ONLY")
    rows, report = enrich_panel([_wys()], [bad, _footy(2, 102), _footy(3, 103)])
    assert rows[0]["abc_player_key_pass_rate"] == pytest.approx(0.8)
    assert report["verified_11footy_player_match_rows"] == 2


def test_duplicate_verified_player_fixture_is_rejected():
    with pytest.raises(ValueError, match="Duplicate verified"):
        enrich_panel([_wys()], [_footy(1, 101), _footy(1, 101)])


def test_output_marks_research_only_and_preserves_wyscout_values():
    rows, report = enrich_panel([_wys()], [_footy(1, 101)])
    assert rows[0]["research_eligible_for_model"] is True
    assert rows[0]["abc_primary_feature_source"] == "11footy"
    assert rows[0]["abc_supplementary_feature_source"] == "Wyscout"
    assert report["point_in_time_status"] == "RETROSPECTIVE_SOURCE_VINTAGES_NOT_VERIFIED"
    assert rows[0]["abc_progressive_passes"] == pytest.approx(2.5)
