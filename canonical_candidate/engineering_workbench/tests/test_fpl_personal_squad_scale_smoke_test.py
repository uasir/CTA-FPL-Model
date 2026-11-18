import copy
import json
from pathlib import Path

from run_fpl_personal_squad_scale_smoke_test import run


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "recommendation_requests.json").read_text(encoding="utf-8")
)


def test_personal_squad_engine_scales_over_full_forecast_pool_with_synthetic_roster():
    snapshot = copy.deepcopy(FIXTURE["general_market"])
    result, report = run(snapshot)
    assert report["status"] == "PASS_SYNTHETIC_PERSONAL_SQUAD_SCALE_SMOKE_TEST"
    assert report["scope"].startswith("synthetic squad only")
    assert report["forecast_players"] == 15
    assert report["synthetic_squad_players"] == 15
    assert report["maximum_players_per_team"] == 3
    assert report["formation"] == "4-3-3"
    assert report["starting_xi_count"] == 11
    assert report["covar_used"] is False
    assert result["system"] == "personal_squad"
