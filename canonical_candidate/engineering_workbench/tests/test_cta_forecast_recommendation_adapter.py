from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cta_forecast_recommendation_adapter import (
    CTAForecastAdapterError,
    build_cta_forecast_provider_snapshot,
)


GAMEWEEKS = [12, 13, 14, 15, 16]
SNAPSHOT_ID = "candidate-snapshot-123"


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build_bundle(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    source_manifest = {"feature_source_mode": "FPL_PLAYER_UNDERSTAT", "source": "pinned"}
    write_json(root / "source_download_manifest.json", source_manifest)
    model_manifest = {
        "status": "CANDIDATE_TRAINED_M2_VALIDATION_PENDING",
        "feature_source_mode": "FPL_PLAYER_UNDERSTAT",
        "validation": {"status": "NOT_RUN_M2_DEFERRED"},
        "production_eligible": False,
        "decision_weight": 0,
    }
    write_json(root / "models" / "cta_points_model_manifest.json", model_manifest)
    model_sha = hashlib.sha256((root / "models" / "cta_points_model_manifest.json").read_bytes()).hexdigest()
    source_sha = hashlib.sha256((root / "source_download_manifest.json").read_bytes()).hexdigest()

    bootstrap = {
        "elements": [
            {"id": 101, "code": 1001, "team": 1, "element_type": 2, "now_cost": 55, "web_name": "Defender A"},
            {"id": 202, "code": 1002, "team": 2, "element_type": 3, "now_cost": 70, "web_name": "Midfielder B"},
        ]
    }
    write_json(root / "snapshots" / "bootstrap-static.json", bootstrap)
    source_report = {
        "season": "2026-27",
        "feature_source_mode": "FPL_PLAYER_UNDERSTAT",
        "understat_player_metric_coverage": {
            "us_xG": 0.75, "us_xA": 0.75, "us_shots": 0.75, "us_key_passes": 0.75,
        },
        "understat_player_coverage": {
            "appearance_rows": 100, "nonappearance_rows": 200, "unknown_minutes_rows": 0,
        },
        "current_bootstrap_snapshot": {
            "captured_at_utc": "2026-11-22T11:59:00Z",
            "deadline_time": "2026-11-27T18:30:00Z",
            "safety_buffer_minutes": 5,
            "gameweek": 12,
        },
    }
    write_json(root / "source_preparation_report.json", source_report)

    five_rows = []
    gw_rows = []
    for code, position, total_points, total_minutes in (
        (1001, "DEF", 20.5, 350.0),
        (1002, "MID", 27.0, 410.0),
    ):
        five_rows.append({
            "season": "2026-27",
            "fpl_code": code,
            "position": position,
            "expected_points_5gw": total_points,
            "expected_minutes_5gw": total_minutes,
            "fixture_count_5gw": 5,
            "gameweeks_with_fixtures": 5,
            "gameweeks": "12,13,14,15,16",
            "forecast_snapshot_id": SNAPSHOT_ID,
            "model_status": "CANDIDATE_NOT_VALIDATED",
            "production_eligible": False,
            "decision_weight": 0.0,
        })
        for index, gw in enumerate(GAMEWEEKS):
            gw_rows.append({
                "season": "2026-27",
                "gameweek": gw,
                "fpl_code": code,
                "position": position,
                "expected_points": round(total_points / 5 + index * 0.01, 6),
                "expected_minutes": total_minutes / 5,
                "fixture_count": 1,
                "fixture_ids": 100 + index,
                "team_names": "Arsenal",
                "forecast_snapshot_id": SNAPSHOT_ID,
                "model_status": "CANDIDATE_NOT_VALIDATED",
                "production_eligible": False,
                "decision_weight": 0.0,
            })
    write_csv(root / "forecasts" / "player_five_gw_forecasts.csv", five_rows)
    write_csv(root / "forecasts" / "player_gameweek_forecasts.csv", gw_rows)

    forecast_report = {
        "status": "PASS_CTA_FIVE_GW_CANDIDATE_FORECAST",
        "forecast_snapshot_id": SNAPSHOT_ID,
        "generated_at_utc": "2026-11-22T12:00:00Z",
        "season": "2026-27",
        "gameweeks": GAMEWEEKS,
        "fixture_player_rows": 10,
        "player_gameweek_rows": 10,
        "five_gameweek_player_rows": 2,
        "feature_source_mode": "FPL_PLAYER_UNDERSTAT",
        "masked_unavailable_feature_count": 80,
        "provenance": {
            "source_manifest_sha256": source_sha,
            "points_model_manifest_sha256": model_sha,
            "feature_matrix_sha256": "feature-hash",
            "minutes_predictions_sha256": "minutes-hash",
        },
        "decision_safeguards": {
            "production_eligible": False,
            "decision_weight": 0,
            "covar_used": False,
        },
        "model_hashes": {"GKP": "a", "DEF": "b", "MID": "c", "FWD": "d"},
    }
    write_json(root / "forecasts" / "forecast_report.json", forecast_report)
    write_json(root / "forecasts" / "bundle_validation_report.json", {
        "status": "PASS_CTA_FORECAST_BUNDLE_INTEGRITY",
        "forecast_snapshot_id": SNAPSHOT_ID,
        "production_eligible": False,
        "decision_weight": 0,
        "covar_used": False,
    })
    return root


def test_adapter_builds_candidate_only_shared_forecast_and_five_gameweek_panels(tmp_path: Path):
    bundle = build_bundle(tmp_path / "bundle")
    result = build_cta_forecast_provider_snapshot(
        bundle, now_utc="2026-11-22T12:05:00Z",
    )
    shared = result["shared_forecast"]
    assert shared["forecast_snapshot_id"] == SNAPSHOT_ID
    assert shared["forecast_horizon_gameweeks"] == 5
    assert shared["forecast_quality"]["validation_status"] == "EXPLORATORY_ONLY"
    assert shared["forecast_quality"]["point_in_time_status"] == "VERIFIED"
    assert shared["forecast_quality"]["data_coverage"]["freshness_status"] == "FRESH_WITHIN_24H"
    assert len(shared["player_forecasts"]) == 2
    assert shared["player_forecasts"][0]["fpl_element_id"] == 101
    assert shared["player_forecasts"][0]["price"] == 5.5
    assert shared["player_forecasts"][0]["team_id"] == 1
    assert len(result["provider_snapshot"]["gameweek_panels"]) == 5
    assert [panel["gameweek"] for panel in result["provider_snapshot"]["gameweek_panels"]] == GAMEWEEKS
    assert len(result["provider_snapshot"]["gameweek_panels"][0]["player_forecasts"]) == 2
    assert result["recommendation_products"]["cta_informed_personal_squad"]["enabled"] is False
    assert result["recommendation_products"]["general_cta_player_rankings"]["squad_independent"] is True
    assert result["guardrails"]["recommendations_emitted"] is False
    assert result["guardrails"]["covar_used"] is False


def test_adapter_accepts_only_provenance_matched_post_lock_eo(tmp_path: Path):
    bundle = build_bundle(tmp_path / "bundle")
    eo = {
        "forecast_snapshot_id": SNAPSHOT_ID,
        "target_deadline_utc": "2026-11-27T18:30:00Z",
        "eo_cohort": "overall top-10k sample",
        "eo_sample_managers": 250,
        "eo_rank_cohort_captured_at_utc": "2026-11-27T18:20:00Z",
        "eo_deadline_time_utc": "2026-11-27T18:30:00Z",
        "eo_picks_captured_at_utc": "2026-11-27T18:31:00Z",
        "eo_picks_lock_verified": True,
        "players": [{"fpl_element_id": 101, "effective_ownership_pct": 82.5}],
    }
    result = build_cta_forecast_provider_snapshot(
        bundle, eo_snapshot=eo, now_utc="2026-11-27T18:32:00Z",
    )
    coverage = result["shared_forecast"]["forecast_quality"]["data_coverage"]
    assert coverage["eo_cohort"] == "overall top-10k sample"
    assert coverage["eo_sample_managers"] == 250
    assert coverage["eo_players_with_coverage"] == 1
    player = next(p for p in result["shared_forecast"]["player_forecasts"] if p["fpl_element_id"] == 101)
    assert player["effective_ownership_pct"] == 82.5


def test_adapter_rejects_production_enabled_candidate_model(tmp_path: Path):
    bundle = build_bundle(tmp_path / "bundle")
    path = bundle / "models" / "cta_points_model_manifest.json"
    model = json.loads(path.read_text())
    model["production_eligible"] = True
    write_json(path, model)
    with pytest.raises(CTAForecastAdapterError, match="production-ineligible"):
        build_cta_forecast_provider_snapshot(bundle, now_utc="2026-11-22T12:05:00Z")


def test_adapter_rejects_forecast_snapshot_mismatch(tmp_path: Path):
    bundle = build_bundle(tmp_path / "bundle")
    path = bundle / "forecasts" / "player_five_gw_forecasts.csv"
    rows = list(csv.DictReader(path.open()))
    rows[0]["forecast_snapshot_id"] = "wrong-snapshot"
    write_csv(path, rows)
    with pytest.raises(CTAForecastAdapterError, match="forecast snapshot mismatch"):
        build_cta_forecast_provider_snapshot(bundle, now_utc="2026-11-22T12:05:00Z")


def test_adapter_rejects_eo_for_another_deadline(tmp_path: Path):
    bundle = build_bundle(tmp_path / "bundle")
    eo = {
        "forecast_snapshot_id": SNAPSHOT_ID,
        "target_deadline_utc": "2026-11-28T18:30:00Z",
        "eo_cohort": "overall top-10k sample",
        "eo_sample_managers": 250,
        "eo_rank_cohort_captured_at_utc": "2026-11-27T18:20:00Z",
        "eo_deadline_time_utc": "2026-11-28T18:30:00Z",
        "eo_picks_captured_at_utc": "2026-11-28T18:31:00Z",
        "eo_picks_lock_verified": True,
        "players": [],
    }
    with pytest.raises(CTAForecastAdapterError, match="EO deadline does not match"):
        build_cta_forecast_provider_snapshot(
            bundle, eo_snapshot=eo, now_utc="2026-11-22T12:05:00Z",
        )


def test_adapter_marks_old_bundle_stale_without_claiming_validation(tmp_path: Path):
    bundle = build_bundle(tmp_path / "bundle")
    result = build_cta_forecast_provider_snapshot(
        bundle, now_utc="2026-11-24T12:00:00Z",
    )
    quality = result["shared_forecast"]["forecast_quality"]
    assert quality["validation_status"] == "EXPLORATORY_ONLY"
    assert quality["data_coverage"]["freshness_status"] == "STALE_OVER_24H"
