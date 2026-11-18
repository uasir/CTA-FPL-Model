import copy
import json
from pathlib import Path

from run_fpl_general_market_baseline import run
from compare_fpl_general_market_outputs import compare


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "recommendation_requests.json").read_text(encoding="utf-8")
)


def test_runs_general_market_on_shared_official_baseline_contract():
    snapshot = copy.deepcopy(FIXTURE["general_market"])
    snapshot["forecast_quality"]["data_coverage"]["target_gameweek"] = 11
    result, report = run(snapshot)
    assert report["status"] == "PASS_EXPLORATORY_GENERAL_MARKET"
    assert report["system"] == "general_market"
    assert report["target_gameweek"] == 11
    assert report["recommendation_status"] == "EXPLORATORY_ONLY"
    assert report["players_ranked"] == 15
    assert report["players_with_eo"] == 0
    assert report["differential_status"] == "EO_THRESHOLD_NOT_SET"
    assert report["covar_used"] is False
    assert len(report["top_overall"]) == 10
    assert len(report["captaincy_shortlist"]) == 5
    assert "squad_snapshot" not in result



def test_live_parity_comparator_reports_exact_match_and_first_difference():
    snapshot = copy.deepcopy(FIXTURE["general_market"])
    python_result, _ = run(snapshot)
    assert compare(python_result, copy.deepcopy(python_result))["status"] == "PASS_PYTHON_JAVASCRIPT_PARITY"
    changed = copy.deepcopy(python_result)
    changed["categories"]["overall"][0]["expected_points"] += 0.1
    report = compare(python_result, changed)
    assert report["status"] == "FAIL_PYTHON_JAVASCRIPT_PARITY"
    assert report["first_difference"]["path"].endswith("expected_points")



def test_parity_comparator_treats_equal_json_integer_and_float_as_equal():
    assert compare({"availability_probability": 1.0}, {"availability_probability": 1})["status"] == "PASS_PYTHON_JAVASCRIPT_PARITY"


def test_parity_comparator_does_not_conflate_booleans_with_numbers():
    report = compare({"flag": True}, {"flag": 1})
    assert report["status"] == "FAIL_PYTHON_JAVASCRIPT_PARITY"
