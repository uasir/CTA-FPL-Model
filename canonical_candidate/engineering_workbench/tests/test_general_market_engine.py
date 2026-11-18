import copy
import json
import subprocess
from pathlib import Path

import pytest

from general_market_engine import recommend_general_market
from recommendation_contracts import RecommendationContractError


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "recommendation_requests.json").read_text(encoding="utf-8")
)


def request():
    return copy.deepcopy(FIXTURE["general_market"])


def add_locked_eo_provenance(payload):
    payload["forecast_quality"]["data_coverage"].update({
        "eo_cohort": "overall top-10k rank-stratified sample",
        "eo_sample_managers": 100,
        "eo_rank_cohort_captured_at_utc": "2026-11-28T10:55:00+00:00",
        "eo_deadline_time_utc": "2026-11-28T11:00:00+00:00",
        "eo_picks_captured_at_utc": "2026-11-28T11:01:00+00:00",
        "eo_picks_lock_verified": True,
    })
    return payload


def test_general_market_ranks_without_any_personal_squad_context():
    result = recommend_general_market(request())
    assert result["system"] == "general_market"
    assert result["covar_used"] is False
    assert len(result["categories"]["overall"]) == 10
    assert set(result["categories"]["by_position"]) == {"GKP", "DEF", "MID", "FWD"}
    assert "squad_snapshot" not in result
    assert result["recommendation_status"] == "EXPLORATORY_ONLY"


def test_general_market_filters_are_public_and_deterministic():
    payload = request()
    payload["filters"] = {"position": "MID", "min_price": 6, "limit": 3}
    result = recommend_general_market(payload)
    rows = result["categories"]["overall"]
    assert len(rows) == 3
    assert all(row["position"] == "MID" and row["price"] >= 6 for row in rows)


def test_differential_category_requires_sampled_eo_and_explicit_threshold():
    payload = add_locked_eo_provenance(request())
    payload["player_forecasts"][0]["effective_ownership_pct"] = 4.5
    payload["player_forecasts"][1]["effective_ownership_pct"] = 55.0
    payload["filters"] = {"differential_eo_max_pct": 10}
    result = recommend_general_market(payload)
    differential = result["categories"]["differentials"]
    assert differential["status"] == "SAMPLED_EO_AVAILABLE"
    assert [row["fpl_element_id"] for row in differential["players"]] == [1]


def test_differential_category_does_not_invent_eo():
    payload = request()
    payload["filters"] = {"differential_eo_max_pct": 10}
    result = recommend_general_market(payload)
    assert result["categories"]["differentials"]["status"] == "EO_UNAVAILABLE"
    assert result["categories"]["differentials"]["players"] == []


@pytest.mark.parametrize(
    "filters",
    [
        {"position": "WING"},
        {"team_id": 0},
        {"limit": 0},
        {"min_price": -1},
        {"min_price": 8, "max_price": 7},
        {"differential_eo_max_pct": -1},
    ],
)
def test_rejects_invalid_public_filters(filters):
    payload = request()
    payload["filters"] = filters
    with pytest.raises(RecommendationContractError):
        recommend_general_market(payload)


def test_python_and_javascript_general_market_outputs_are_identical():
    test_dir = Path(__file__).parent
    runner = test_dir / "js" / "emit_general_market_outputs.mjs"
    completed = subprocess.run(
        ["node", str(runner)],
        check=True,
        capture_output=True,
        text=True,
    )
    javascript = json.loads(completed.stdout)
    python = recommend_general_market(request())
    assert javascript == python



def test_null_filters_are_rejected_consistently():
    payload = request()
    payload["filters"] = None
    with pytest.raises(RecommendationContractError, match="filters must be"):
        recommend_general_market(payload)



def test_eo_values_without_lock_provenance_are_rejected():
    payload = request()
    payload["player_forecasts"][0]["effective_ownership_pct"] = 4.5
    with pytest.raises(RecommendationContractError, match="verified cohort and post-lock provenance"):
        recommend_general_market(payload)
