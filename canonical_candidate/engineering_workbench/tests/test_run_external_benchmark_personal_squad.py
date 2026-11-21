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
            "coverage": {"row_count": len(forecasts), "identity_mapped_count": len(forecasts), "identity_resolution_status": "VERIFIED"},
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



def _write_predeadline_field_capture(tmp_path, *, picks_at="2026-11-20T09:30:00Z", omit_player=None):
    import csv

    payload = run_input()
    csv_path = tmp_path / "field.csv"
    report_path = tmp_path / "field-report.json"
    fields = [
        "gameweek", "fpl_element_id", "sample_managers", "sample_weight",
        "owned_by_pct", "starting_pct", "captain_pct", "triple_captain_pct",
        "effective_ownership_pct", "scoring_exposure_pct",
        "effective_ownership_pct_ci95_low", "effective_ownership_pct_ci95_high",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for player_id in range(1, 19):
            if player_id == omit_player:
                continue
            writer.writerow({
                "gameweek": 11, "fpl_element_id": player_id, "sample_managers": 100,
                "sample_weight": 100, "owned_by_pct": 50, "starting_pct": 40,
                "captain_pct": 10, "triple_captain_pct": 0,
                "effective_ownership_pct": 60, "scoring_exposure_pct": 45,
                "effective_ownership_pct_ci95_low": 55,
                "effective_ownership_pct_ci95_high": 65,
            })
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    report = {
        "status": "CAPTURED_PRE_DEADLINE_CURRENT_PICKS",
        "evidence_role": "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE",
        "picks_lock_verified": False, "provisional_picks": True,
        "gameweek": 11, "deadline_time_utc": "2026-11-21T11:00:00Z",
        "capture_started_at_utc": "2026-11-20T09:00:00Z",
        "rank_cohort_captured_at_utc": "2026-11-20T09:10:00Z",
        "picks_captured_at_utc": picks_at,
        "sample_size_captured": 100, "sample_managers": 100,
        "effective_sample_size": 98.5, "rank_limit": 10000,
        "rank_min": 1, "rank_max": 9999, "rank_strata_count": 200,
        "cohort": "overall global rank", "sample_weight": 100,
        "csv_sha256": digest,
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")
    payload["predeadline_field_capture"] = {
        "csv_path": str(csv_path), "report_path": str(report_path),
        "season": "2026-27", "source_url": "https://github.com/example/actions/runs/123",
    }
    return payload, csv_path, report_path


def test_predeadline_field_capture_attaches_inside_same_m3_recommendation(tmp_path):
    payload, _, _ = _write_predeadline_field_capture(tmp_path)
    baseline = run_external_benchmark_personal_squad(run_input())
    result = run_external_benchmark_personal_squad(payload)
    recommendation = result["recommendation"]
    context = recommendation["predeadline_field_analysis"]
    assert context["status"] == "ATTACHED_PROVISIONAL_FIELD_CONTEXT"
    assert context["evidence_role"] == "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE"
    assert context["scenarios"][0]["scenario"] == "HOLD"
    assert context["scenarios"][1]["scenario"] == "TRANSFER"
    assert context["coverage"]["candidate_squad_covered"] is True
    assert context["release_eligible"] is False
    assert context["covar"] == "SEPARATE_RESEARCH_ONLY_CONTEXT"
    for key in ("transfer_recommendation", "current_squad_plan", "squad_plan", "squad_plan_state"):
        assert recommendation[key] == baseline["recommendation"][key]


def test_predeadline_field_capture_after_deadline_is_rejected(tmp_path):
    payload, _, _ = _write_predeadline_field_capture(
        tmp_path, picks_at="2026-11-21T11:00:01Z"
    )
    with pytest.raises(ValueError, match="strictly pre-deadline"):
        run_external_benchmark_personal_squad(payload)


def test_predeadline_field_capture_missing_selected_incoming_player_is_rejected(tmp_path):
    payload, _, _ = _write_predeadline_field_capture(tmp_path, omit_player=17)
    with pytest.raises(ValueError, match="lacks candidate squad players"):
        run_external_benchmark_personal_squad(payload)


def test_predeadline_field_capture_csv_hash_mismatch_is_rejected(tmp_path):
    payload, csv_path, _ = _write_predeadline_field_capture(tmp_path)
    csv_path.write_text(csv_path.read_text() + "\\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        run_external_benchmark_personal_squad(payload)



def test_predeadline_field_context_applies_verified_triple_captain_exposure(tmp_path):
    payload, _, _ = _write_predeadline_field_capture(tmp_path)
    payload["manager_context"]["active_chip"] = "3xc"
    payload["manager_context"]["active_chip_status"] = "VERIFIED_FROM_OFFICIAL_PICKS"
    result = run_external_benchmark_personal_squad(payload)
    context = result["recommendation"]["predeadline_field_analysis"]
    assert context["personal_chip_context"]["captain_multiplier"] == 3
    assert context["personal_chip_context"]["captain_multiplier_status"] == "VERIFIED"
    hold = context["scenarios"][0]
    captain = next(row for row in hold["players"] if row["is_captain"])
    assert captain["personal_effective_ownership_pct"] == 300


def test_predeadline_field_context_does_not_guess_unavailable_chip_state(tmp_path):
    payload, _, _ = _write_predeadline_field_capture(tmp_path)
    result = run_external_benchmark_personal_squad(payload)
    context = result["recommendation"]["predeadline_field_analysis"]
    assert context["personal_chip_context"]["captain_multiplier"] is None
    assert context["personal_chip_context"]["captain_multiplier_status"] == "UNKNOWN_ACTIVE_CHIP_STATE"
    hold = context["scenarios"][0]
    captain = next(row for row in hold["players"] if row["is_captain"])
    assert captain["personal_effective_ownership_pct"] is None


def test_predeadline_field_context_rejects_percentages_above_100(tmp_path):
    payload, csv_path, report_path = _write_predeadline_field_capture(tmp_path)
    csv_text = csv_path.read_text()
    csv_text = csv_text.replace("50,40,10,0,60,45,55,65", "150,40,10,0,60,45,55,65", 1)
    csv_path.write_text(csv_text)
    report = json.loads(report_path.read_text())
    report["csv_sha256"] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    report_path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="must not exceed 100 percent"):
        run_external_benchmark_personal_squad(payload)



def test_predeadline_field_context_allows_weighted_scoring_exposure_above_100(tmp_path):
    payload, csv_path, report_path = _write_predeadline_field_capture(tmp_path)
    csv_text = csv_path.read_text()
    csv_text = csv_text.replace("50,40,10,0,60,45,55,65", "50,40,10,0,60,150,55,65", 1)
    csv_path.write_text(csv_text)
    report = json.loads(report_path.read_text())
    report["csv_sha256"] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    report_path.write_text(json.dumps(report))
    result = run_external_benchmark_personal_squad(payload)
    context = result["recommendation"]["predeadline_field_analysis"]
    assert context["status"] == "ATTACHED_PROVISIONAL_FIELD_CONTEXT"
    assert context["coverage"]["candidate_squad_covered"] is True


def test_predeadline_field_context_rejects_weighted_scoring_exposure_above_300(tmp_path):
    payload, csv_path, report_path = _write_predeadline_field_capture(tmp_path)
    csv_text = csv_path.read_text()
    csv_text = csv_text.replace("50,40,10,0,60,45,55,65", "50,40,10,0,60,301,55,65", 1)
    csv_path.write_text(csv_text)
    report = json.loads(report_path.read_text())
    report["csv_sha256"] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    report_path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="must not exceed 300 percent"):
        run_external_benchmark_personal_squad(payload)
