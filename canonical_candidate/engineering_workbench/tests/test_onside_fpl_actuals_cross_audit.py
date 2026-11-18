import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from audit_onside_against_fpl_actuals import audit


def test_fpl_double_gameweek_is_aggregated_before_onside_comparison():
    fpl=[
        {"season":"2026-27","fpl_element_id":"1","gameweek":"1","fixture_id":"10","target_total_points":"2"},
        {"season":"2026-27","fpl_element_id":"1","gameweek":"1","fixture_id":"11","target_total_points":"3"},
        {"season":"2026-27","fpl_element_id":"1","gameweek":"2","fixture_id":"12","target_total_points":"4"},
        {"season":"2026-27","fpl_element_id":"2","gameweek":"1","fixture_id":"10","target_total_points":"1"},
    ]
    onside=[
        {"player_id":"1","gw":"1","actual_points":"5","player_name":"One"},
        {"player_id":"1","gw":"2","actual_points":"3","player_name":"One"},
        {"player_id":"2","gw":"1","actual_points":"1","player_name":"Two"},
        {"player_id":"3","gw":"1","actual_points":"2","player_name":"Three"},
    ]
    report=audit(fpl,onside,source_sha256="abc")
    assert report["status"]=="REVIEW_MISMATCHES"
    assert report["matched_player_gameweek_rows"]==3
    assert report["exact_matches"]==2
    assert report["mismatches"]==1
    assert report["fpl_rows_without_onside"]==0
    assert report["onside_rows_without_fpl"]==1
    assert report["mismatch_examples"][0]["fpl_fixture_rows"]==1
    assert report["gameweeks"][0]["matched_player_rows"]==2


def test_audit_never_fills_missing_player_gameweeks_with_zero():
    fpl=[{"season":"2026-27","fpl_element_id":"1","gameweek":"1","target_total_points":"0"}]
    onside=[{"player_id":"2","gw":"1","actual_points":"0"}]
    report=audit(fpl,onside)
    assert report["matched_player_gameweek_rows"]==0
    assert report["fpl_rows_without_onside"]==1
    assert report["onside_rows_without_fpl"]==1
    assert report["status"]=="NO_OVERLAP"


def test_duplicate_onside_player_gameweek_is_rejected():
    fpl=[{"season":"2026-27","fpl_element_id":"1","gameweek":"1","target_total_points":"2"}]
    onside=[
        {"player_id":"1","gw":"1","actual_points":"2"},
        {"player_id":"1","gw":"1","actual_points":"2"},
    ]
    try:
        audit(fpl,onside)
    except ValueError as exc:
        assert "Duplicate Onside" in str(exc)
    else:
        raise AssertionError("Expected duplicate Onside key to fail")


def test_non_finite_actual_points_are_rejected():
    fpl=[{"season":"2026-27","fpl_element_id":"1","gameweek":"1","target_total_points":"2"}]
    onside=[{"player_id":"1","gw":"1","actual_points":"NaN"}]
    try:
        audit(fpl,onside)
    except ValueError as exc:
        assert "finite" in str(exc)
    else:
        raise AssertionError("Expected non-finite actual points to be rejected")
