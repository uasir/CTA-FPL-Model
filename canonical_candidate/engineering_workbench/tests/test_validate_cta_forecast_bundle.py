import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_cta_forecast_bundle import validate_bundle


def _write_valid_bundle(forecast_dir: Path):
    forecast_dir.mkdir()
    snapshot = "a" * 64
    fixture_rows = []
    for gw, fixture_id, points, minutes in [
        (12, 1001, 2.0, 70.0),
        (14, 1002, 3.0, 80.0),
        (15, 1003, 1.0, 60.0),
        (16, 1004, 4.0, 90.0),
    ]:
        fixture_rows.append({
            "season": "2026-27", "gameweek": gw, "fpl_code": 123,
            "position": "MID", "fixture_id": fixture_id,
            "p60": 0.2, "p_any": 0.4, "expected_minutes": minutes,
            "cta_expected_points_per_90": (points - 0.6) * 90.0 / minutes,
            "cta_expected_points": points,
            "forecast_snapshot_id": snapshot, "production_eligible": False,
            "decision_weight": 0.0, "covar_used": False,
        })
    fixture = pd.DataFrame(fixture_rows)
    fixture.to_csv(forecast_dir / "fixture_forecasts.csv", index=False)

    gw = fixture.groupby(
        ["season", "gameweek", "fpl_code", "position"], as_index=False
    ).agg(
        expected_points=("cta_expected_points", "sum"),
        expected_minutes=("expected_minutes", "sum"),
        fixture_count=("fixture_id", "nunique"),
    )
    gw["forecast_snapshot_id"] = snapshot
    gw["model_status"] = "CANDIDATE_NOT_VALIDATED"
    gw["production_eligible"] = False
    gw["decision_weight"] = 0.0
    gw.to_csv(forecast_dir / "player_gameweek_forecasts.csv", index=False)

    horizon = gw.groupby(["season", "fpl_code", "position"], as_index=False).agg(
        expected_points_5gw=("expected_points", "sum"),
        expected_minutes_5gw=("expected_minutes", "sum"),
        fixture_count_5gw=("fixture_count", "sum"),
        gameweeks_with_fixtures=("gameweek", "nunique"),
    )
    horizon["forecast_snapshot_id"] = snapshot
    horizon["model_status"] = "CANDIDATE_NOT_VALIDATED"
    horizon["production_eligible"] = False
    horizon["decision_weight"] = 0.0
    horizon.to_csv(forecast_dir / "player_five_gw_forecasts.csv", index=False)

    (forecast_dir / "forecast_report.json").write_text(json.dumps({
        "forecast_snapshot_id": snapshot,
        "gameweeks": [12, 13, 14, 15, 16],
        "decision_safeguards": {"production_eligible": False},
    }))


def test_bundle_accepts_blank_fixture_gameweek_inside_declared_horizon(tmp_path: Path):
    forecast_dir = tmp_path / "forecasts"
    _write_valid_bundle(forecast_dir)
    report = validate_bundle(forecast_dir, forecast_dir / "validation.json")
    assert report["status"] == "PASS_CTA_FORECAST_BUNDLE_INTEGRITY"
    assert report["gameweeks"] == [12, 13, 14, 15, 16]
    assert report["fixture_rows"] == 4


def test_bundle_rejects_invalid_appearance_probability_order(tmp_path: Path):
    import pytest
    forecast_dir = tmp_path / "forecasts"
    _write_valid_bundle(forecast_dir)
    fixture_path = forecast_dir / "fixture_forecasts.csv"
    fixture = pd.read_csv(fixture_path)
    fixture.loc[0, "p60"] = 0.6
    fixture.loc[0, "p_any"] = 0.4
    fixture.to_csv(fixture_path, index=False)
    with pytest.raises(ValueError, match="p60 probability cannot exceed p_any"):
        validate_bundle(forecast_dir, forecast_dir / "validation.json")


def test_bundle_rejects_points_component_mismatch(tmp_path: Path):
    import pytest
    forecast_dir = tmp_path / "forecasts"
    _write_valid_bundle(forecast_dir)
    fixture_path = forecast_dir / "fixture_forecasts.csv"
    fixture = pd.read_csv(fixture_path)
    fixture.loc[0, "cta_expected_points"] += 0.25
    fixture.to_csv(fixture_path, index=False)
    with pytest.raises(ValueError, match="do not match appearance"):
        validate_bundle(forecast_dir, forecast_dir / "validation.json")
