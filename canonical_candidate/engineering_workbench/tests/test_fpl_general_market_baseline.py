import copy
import json
from pathlib import Path

from run_fpl_general_market_baseline import run


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
