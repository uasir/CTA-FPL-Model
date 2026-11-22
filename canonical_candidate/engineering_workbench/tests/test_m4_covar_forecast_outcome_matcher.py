from __future__ import annotations

import copy
import pytest

from m4_covar_forecast_outcome_matcher import (
    ForecastOutcomeMatchError,
    match_forecast_to_realized_outcomes,
)


def inputs():
    forecast = {
        "bundle_type": "M3_CONVENTIONAL_FORECAST_ONLY_COVAR_INPUT",
        "season": "2026-27",
        "target_gameweek": 11,
        "as_of_utc": "2026-11-21T08:01:32Z",
        "deadline_utc": "2026-11-21T11:00:00Z",
        "forecast_snapshot_id": "fplcat-gw11-test",
        "model_version": "conventional-m3-adapter-test",
        "decision_weight": 0.0,
        "production_eligible": False,
        "privacy": {
            "manager_identity_included": False,
            "manager_squad_included": False,
            "bank_or_transfer_state_included": False,
            "frozen_decision_included": False,
        },
        "source_archives": [
            {"source_type": "provider_forecast", "captured_at_utc": "2026-11-21T08:01:32Z", "generated_at_utc": "2026-11-21T07:30:00Z"},
            {"source_type": "player_metadata", "captured_at_utc": "2026-11-21T08:01:32Z"},
        ],
        "player_forecasts": [
            {"fpl_element_id": 10, "expected_points": 4.5, "expected_minutes": 80},
            {"fpl_element_id": 11, "expected_points": 2.0, "expected_minutes": 25},
            {"fpl_element_id": 12, "expected_points": 1.0, "expected_minutes": 10},
        ],
    }
    realized_gw = [
        {"season": "2026-27", "gameweek": 11, "fpl_element_id": 10, "total_points": 8, "minutes": 90},
        {"season": "2026-27", "gameweek": 11, "fpl_element_id": 11, "total_points": 0, "minutes": 0},
        {"season": "2026-27", "gameweek": 11, "fpl_element_id": 13, "total_points": 2, "minutes": 60},
    ]
    fixtures = [
        {"season": "2026-27", "gameweek": 11, "kickoff_time": "2026-11-21T11:30:00Z"}
    ]
    finality = {
        "status": "PASS_ALL_EVENTS",
        "season": "2026-27",
        "events_checked": [1, 2, 11],
        "reports": [
            {"event_id": 11, "status": "PASS_EXACT_MATCH", "finality_reconciled": True, "outcome_available_at_utc": "2026-11-22T12:00:00Z"}
        ],
    }
    return forecast, realized_gw, fixtures, finality


def test_matches_only_observed_intersection_and_reports_unmatched_without_zero_fill():
    forecast, realized, fixtures, finality = inputs()
    result = match_forecast_to_realized_outcomes(forecast, realized, fixtures, finality)
    assert result["matched_player_count"] == 2
    assert result["forecast_players_without_observed_realized_row"] == 1
    assert result["realized_rows_without_forecast"] == 1
    assert result["missing_observations_zero_filled"] == 0
    assert result["outcome_available_at_utc"] == "2026-11-22T12:00:00Z"
    assert result["matched_rows"][0]["points_error_actual_minus_expected"] == 3.5


def test_uses_observed_capture_timestamp_when_finality_has_no_explicit_availability_field():
    forecast, realized, fixtures, finality = inputs()
    finality["reports"][0].pop("outcome_available_at_utc")
    finality["reports"][0]["source_provenance"] = {
        "captured_at_utc": "2026-11-22T12:00:00Z",
        "raw_sha256": "a" * 64,
        "source_url": "https://fantasy.premierleague.com/api/event/11/live/",
    }
    result = match_forecast_to_realized_outcomes(forecast, realized, fixtures, finality)
    assert result["outcome_available_at_utc"] == "2026-11-22T12:00:00Z"


def test_rejects_finality_without_any_observed_availability_timestamp():
    forecast, realized, fixtures, finality = inputs()
    finality["reports"][0].pop("outcome_available_at_utc")
    with pytest.raises(ForecastOutcomeMatchError, match="observed outcome availability timestamp"):
        match_forecast_to_realized_outcomes(forecast, realized, fixtures, finality)


def test_rejects_finality_not_passed():
    forecast, realized, fixtures, finality = inputs()
    finality["status"] = "FAIL_MISMATCH"
    with pytest.raises(ForecastOutcomeMatchError, match="PASS_ALL_EVENTS"):
        match_forecast_to_realized_outcomes(forecast, realized, fixtures, finality)


def test_rejects_target_gw_without_exact_finality_report():
    forecast, realized, fixtures, finality = inputs()
    finality["reports"][0]["status"] = "FAIL_MISMATCH"
    with pytest.raises(ForecastOutcomeMatchError, match="exact official event-live"):
        match_forecast_to_realized_outcomes(forecast, realized, fixtures, finality)


def test_rejects_asof_after_kickoff():
    forecast, realized, fixtures, finality = inputs()
    forecast["as_of_utc"] = "2026-11-21T12:00:00Z"
    with pytest.raises(ForecastOutcomeMatchError, match="as-of must precede deadline"):
        match_forecast_to_realized_outcomes(forecast, realized, fixtures, finality)


def test_rejects_source_capture_after_asof():
    forecast, realized, fixtures, finality = inputs()
    forecast["source_archives"][0]["captured_at_utc"] = "2026-11-21T08:02:00Z"
    with pytest.raises(ForecastOutcomeMatchError, match="after forecast as-of"):
        match_forecast_to_realized_outcomes(forecast, realized, fixtures, finality)


def test_rejects_duplicate_forecast_player_ids():
    forecast, realized, fixtures, finality = inputs()
    forecast["player_forecasts"].append(copy.deepcopy(forecast["player_forecasts"][0]))
    with pytest.raises(ForecastOutcomeMatchError, match="unique positive"):
        match_forecast_to_realized_outcomes(forecast, realized, fixtures, finality)


def test_rejects_manager_data_privacy_declaration():
    forecast, realized, fixtures, finality = inputs()
    forecast["privacy"]["manager_squad_included"] = True
    with pytest.raises(ForecastOutcomeMatchError, match="exclude manager data"):
        match_forecast_to_realized_outcomes(forecast, realized, fixtures, finality)


def test_rejects_duplicate_realized_ids():
    forecast, realized, fixtures, finality = inputs()
    realized.append(copy.deepcopy(realized[0]))
    with pytest.raises(ForecastOutcomeMatchError, match="unique positive"):
        match_forecast_to_realized_outcomes(forecast, realized, fixtures, finality)


def test_private_match_archive_cli_accepts_csv_gameweek_strings_and_hashes_inputs(tmp_path):
    import csv
    import json
    from m4_covar_forecast_outcome_matcher import build_match_archive

    forecast, realized, fixtures, finality = inputs()
    forecast_path = tmp_path / "forecast.json"
    gw_path = tmp_path / "realized_gw.csv"
    fixture_path = tmp_path / "fixtures.csv"
    finality_path = tmp_path / "finality.json"
    output = tmp_path / "archive"
    forecast_path.write_text(json.dumps(forecast))
    finality_path.write_text(json.dumps(finality))
    with gw_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(realized[0]))
        writer.writeheader()
        writer.writerows(realized)
    with fixture_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fixtures[0]))
        writer.writeheader()
        writer.writerows(fixtures)

    manifest = build_match_archive(forecast_path, gw_path, fixture_path, finality_path, output)
    assert manifest["status"] == "MATCHED_RESEARCH_PANEL_CREATED"
    assert manifest["matched_player_count"] == 2
    assert len(manifest["input_sha256"]) == 4
    assert (output / "matched_forecast_outcomes.json").is_file()
    assert (output / "match_manifest.json").is_file()
    assert not (output / "MATCH_INCOMPLETE").exists()
