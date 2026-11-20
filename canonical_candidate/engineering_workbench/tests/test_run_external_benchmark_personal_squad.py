import copy
import hashlib
import json
from pathlib import Path

import pytest

from run_external_benchmark_personal_squad import (
    BenchmarkDecisionRunError,
    run_external_benchmark_personal_squad,
)


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "recommendation_requests.json").read_text(encoding="utf-8")
)


def run_input():
    manager = copy.deepcopy(FIXTURE["personal_squad"])
    forecasts = copy.deepcopy(manager["player_forecasts"])
    forecasts[2]["price"] = 5.2
    forecasts.extend([
        {"fpl_element_id": 16, "expected_points": 7.0, "expected_minutes": 85,
         "price": 5.0, "position": "DEF", "team_id": 6},
        {"fpl_element_id": 17, "expected_points": 8.0, "expected_minutes": 90,
         "price": 5.0, "position": "DEF", "team_id": 1},
        {"fpl_element_id": 18, "expected_points": 9.0, "expected_minutes": 90,
         "price": 20.0, "position": "DEF", "team_id": 7},
    ])
    raw = b"immutable external benchmark response for M3 integration test"
    return {
        "provider_snapshot": {
            "snapshot_id": "gw11-fplcat-frozen-0900z",
            "season": "2026-27",
            "target_gameweek": 11,
            "provider": {"name": "FPL Cat", "product": "published xP", "variant": "xP API", "version": "v1"},
            "timing": {
                "generated_at_utc": "2026-11-20T08:30:00Z",
                "captured_at_utc": "2026-11-20T09:00:00Z",
                "deadline_utc": "2026-11-21T11:00:00Z",
            },
            "source": {
                "url": "https://provider.example/forecast.json",
                "raw_snapshot_id": "raw-gw11-0900z",
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
            },
            "grain": "player_gameweek",
            "records": [
                {"fpl_element_id": row["fpl_element_id"], "expected_points": row["expected_points"]}
                for row in forecasts
            ],
            "coverage": {"row_count": len(forecasts), "identity_mapped_count": len(forecasts)},
        },
        "player_metadata": [
            {key: row[key] for key in ("fpl_element_id", "price", "position", "team_id", "expected_minutes")}
            for row in forecasts
        ],
        "manager_context": {
            "squad_snapshot": manager["squad_snapshot"],
            "bank": manager["bank"],
            "free_transfers": manager["free_transfers"],
            "personal_risk_profile": manager["personal_risk_profile"],
            "formation": manager["formation"],
        },
        "player_metadata_provenance": {
            "source_url": "https://fantasy.premierleague.com/api/bootstrap-static/",
            "raw_snapshot_id": "sha256:" + hashlib.sha256(b"frozen bootstrap").hexdigest(),
            "raw_sha256": hashlib.sha256(b"frozen bootstrap").hexdigest(),
            "captured_at_utc": "2026-11-20T09:05:00Z",
            "row_count": len(forecasts),
        },
        "as_of_utc": "2026-11-20T10:00:00Z",
    }


def test_external_benchmark_snapshot_runs_through_personal_squad_engine():
    result = run_external_benchmark_personal_squad(run_input())
    recommendation = result["recommendation"]
    assert result["run_type"] == "EXTERNAL_BENCHMARK_PERSONAL_SQUAD"
    assert result["provider_identity"]["name"] == "FPL Cat"
    assert result["source_provenance"]["raw_sha256"] == run_input()["provider_snapshot"]["source"]["raw_sha256"]
    assert recommendation["model_version"].startswith("external:FPL Cat:")
    assert recommendation["recommendation_status"] == "EXPLORATORY_ONLY"
    assert recommendation["squad_plan"]["formation"] == "4-3-3"
    assert len(recommendation["squad_plan"]["starting_xi"]) == 11
    assert recommendation["transfer_recommendation"]["best_candidate"]["transfer_in_id"] == 17
    assert result["release_eligible"] is False


def test_diagnostic_only_provider_snapshot_cannot_run_decisions():
    payload = run_input()
    payload["provider_snapshot"]["timing"]["generated_at_utc"] = None
    with pytest.raises(BenchmarkDecisionRunError, match="diagnostic-only"):
        run_external_benchmark_personal_squad(payload)


def test_player_fixture_forecasts_cannot_be_silently_aggregated():
    payload = run_input()
    payload["provider_snapshot"]["grain"] = "player_fixture"
    payload["provider_snapshot"]["records"][0]["fixture_id"] = 101
    with pytest.raises(Exception, match="fixture_id"):
        run_external_benchmark_personal_squad(payload)


def test_run_requires_complete_manager_context():
    payload = run_input()
    del payload["manager_context"]["bank"]
    with pytest.raises(BenchmarkDecisionRunError, match="manager_context fields"):
        run_external_benchmark_personal_squad(payload)


def test_run_is_deterministic_for_identical_frozen_inputs():
    payload = run_input()
    first = run_external_benchmark_personal_squad(payload)
    second = run_external_benchmark_personal_squad(payload)
    assert first == second
def test_metadata_snapshot_must_be_pre_deadline():
    payload = run_input()
    payload["player_metadata_provenance"]["captured_at_utc"] = "2026-11-21T11:00:00Z"
    with pytest.raises(BenchmarkDecisionRunError, match="metadata capture must be strictly before"):
        run_external_benchmark_personal_squad(payload)
