#!/usr/bin/env python3
"""Score fixture-level CTA points/minutes and aggregate player-GW/five-GW forecasts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from feature_availability import mask_unavailable_features, unavailable_feature_names

IDENTITY = ["season", "gameweek", "fpl_code", "fpl_element_id", "fixture_id", "position"]
POSITIONS = ("GKP", "DEF", "MID", "FWD")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scale_points_per_90(points_per_90, expected_minutes) -> np.ndarray:
    """Convert conditional points-per-90 into fixture expected points."""
    rate = np.asarray(points_per_90, dtype=np.float64)
    minutes = np.asarray(expected_minutes, dtype=np.float64)
    if rate.shape != minutes.shape:
        raise ValueError("points-per-90 and expected-minutes arrays must have matching shapes")
    if not np.isfinite(rate).all():
        raise ValueError("points-per-90 predictions must be finite")
    if not np.isfinite(minutes).all() or (minutes < 0).any() or (minutes > 90).any():
        raise ValueError("expected minutes must be finite and within [0, 90]")
    return rate * minutes / 90.0


def expected_appearance_points(p_any, p60) -> np.ndarray:
    """Expected FPL appearance points from probabilities of any/60+ minutes."""
    any_probability = np.asarray(p_any, dtype=np.float64)
    sixty_probability = np.asarray(p60, dtype=np.float64)
    if any_probability.shape != sixty_probability.shape:
        raise ValueError("p_any and p60 arrays must have matching shapes")
    if (
        not np.isfinite(any_probability).all()
        or not np.isfinite(sixty_probability).all()
        or (any_probability < 0).any()
        or (any_probability > 1).any()
        or (sixty_probability < 0).any()
        or (sixty_probability > any_probability).any()
    ):
        raise ValueError("minutes probabilities must satisfy 0 <= p60 <= p_any <= 1")
    # 2 points for 60+ minutes; 1 point for 1-59 minutes.
    return any_probability + sixty_probability


def score(matrix_path: Path, minutes_path: Path, schema_path: Path,
          source_report_path: Path, feature_report_path: Path,
          minutes_report_path: Path, model_dir: Path, output_dir: Path) -> dict:
    matrix = pd.read_csv(matrix_path, low_memory=False)
    minutes = pd.read_csv(minutes_path, low_memory=False)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    features = schema.get("feature_order", [])
    if len(features) != 286 or len(set(features)) != 286:
        raise ValueError("Expected the pinned ordered 286-feature schema")
    for label, frame in (("feature matrix", matrix), ("minutes forecast", minutes)):
        missing = sorted((set(IDENTITY) if label == "minutes forecast" else set(IDENTITY)) - set(frame.columns))
        if missing:
            raise ValueError(f"{label} missing identity fields: {missing}")
    missing_features = sorted(set(features) - set(matrix.columns))
    if missing_features:
        raise ValueError(f"feature matrix missing model inputs: {missing_features[:20]}")
    key = ["season", "gameweek", "fpl_code", "fixture_id"]
    if matrix.duplicated(key).any() or minutes.duplicated(key).any():
        raise ValueError("Duplicate player-fixture keys in feature/minutes inputs")
    if len(matrix) != len(minutes):
        raise ValueError(f"Feature/minutes row count mismatch: {len(matrix)} != {len(minutes)}")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = model_dir / "cta_points_model_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_report = json.loads(source_report_path.read_text(encoding="utf-8"))
    feature_report = json.loads(feature_report_path.read_text(encoding="utf-8"))
    minutes_report = json.loads(minutes_report_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "CANDIDATE_TRAINED_M2_VALIDATION_PENDING":
        raise ValueError("CTA points model manifest is not a candidate awaiting M2 validation")
    if manifest.get("feature_source_mode") != "FPL_NATIVE_NO_UNDERSTAT":
        raise ValueError("CTA points model was not trained for the FPL-native feature mode")
    expected_mask = unavailable_feature_names(features)
    if manifest.get("masked_unavailable_features") != expected_mask:
        raise ValueError("CTA points model unavailable-feature mask differs from scoring policy")
    feature_order_hash = hashlib.sha256("\n".join(features).encode()).hexdigest()
    if manifest.get("feature_order_sha256") != feature_order_hash:
        raise ValueError("CTA points model feature order differs from forecast schema")

    merged = matrix.merge(minutes[IDENTITY + ["p60", "p_any", "expected_minutes"]],
                           on=IDENTITY, how="left", validate="one_to_one")
    if merged["expected_minutes"].isna().any():
        raise ValueError("Some fixture rows have no matching Dastan minutes prediction")
    merged["cta_expected_points_per_90"] = np.nan
    merged["cta_expected_points"] = np.nan
    model_hashes = {}
    for position in POSITIONS:
        subset = merged["position"].astype(str).eq(position)
        if not subset.any():
            continue
        model_path = model_dir / f"cta_points_{position}.json"
        expected_hash = manifest["positions"][position]["model_sha256"]
        if sha256(model_path) != expected_hash:
            raise ValueError(f"CTA points model hash mismatch: {model_path.name}")
        model = xgb.XGBRegressor()
        model.load_model(str(model_path))
        scoring_features, applied_mask = mask_unavailable_features(
            merged.loc[subset, features], features,
        )
        if applied_mask != expected_mask:
            raise RuntimeError("Unavailable feature mask changed during scoring")
        X = scoring_features.apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy(dtype=np.float32)
        points_per_90 = model.predict(X)
        if not np.isfinite(points_per_90).all():
            raise ValueError(f"{position}: non-finite CTA points-per-90 predictions")
        expected_minutes = pd.to_numeric(
            merged.loc[subset, "expected_minutes"], errors="coerce"
        ).to_numpy(dtype=np.float64)
        any_probability = pd.to_numeric(
            merged.loc[subset, "p_any"], errors="coerce"
        ).to_numpy(dtype=np.float64)
        sixty_probability = pd.to_numeric(
            merged.loc[subset, "p60"], errors="coerce"
        ).to_numpy(dtype=np.float64)
        appearance_points = expected_appearance_points(
            any_probability, sixty_probability,
        )
        merged.loc[subset, "cta_expected_points_per_90"] = points_per_90
        merged.loc[subset, "cta_expected_points"] = (
            scale_points_per_90(points_per_90, expected_minutes)
            + appearance_points
        )
        model_hashes[position] = expected_hash
    if merged["cta_expected_points"].isna().any():
        raise ValueError("Some fixture rows did not receive a CTA points prediction")

    provenance = {
        "source_manifest_sha256": source_report["source_manifest_sha256"],
        "feature_matrix_sha256": sha256(matrix_path),
        "feature_report_sha256": sha256(feature_report_path),
        "minutes_predictions_sha256": sha256(minutes_path),
        "minutes_report_sha256": sha256(minutes_report_path),
        "points_model_manifest_sha256": sha256(manifest_path),
        "feature_schema_sha256": sha256(schema_path),
        "points_model_hashes": model_hashes,
        "minutes_artifact_hashes": minutes_report.get("verified_artifacts", {}),
    }
    snapshot_id = hashlib.sha256(
        json.dumps(provenance, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    merged["forecast_snapshot_id"] = snapshot_id
    merged["expected_points_model_status"] = "CANDIDATE_NOT_VALIDATED"
    merged["production_eligible"] = False
    merged["decision_weight"] = 0.0
    merged["covar_used"] = False
    fixture_fields = [
        "season", "gameweek", "fpl_code", "fpl_element_id", "fixture_id",
        "position", "team_name", "opponent_team_name", "kickoff_time",
        "forecast_snapshot_id", "p60", "p_any", "expected_minutes",
        "cta_expected_points_per_90", "cta_expected_points",
        "expected_points_model_status", "production_eligible", "decision_weight", "covar_used",
    ]
    fixture_out = merged[fixture_fields].sort_values(
        ["season", "gameweek", "fpl_code", "kickoff_time"], kind="mergesort"
    )
    gw_out = (
        fixture_out.groupby(["season", "gameweek", "fpl_code", "position"], as_index=False)
        .agg(
            expected_points=("cta_expected_points", "sum"),
            expected_minutes=("expected_minutes", "sum"),
            fixture_count=("fixture_id", "nunique"),
            fixture_ids=("fixture_id", lambda values: ",".join(map(str, sorted(set(values))))),
            team_names=("team_name", lambda values: " | ".join(sorted(set(map(str, values))))),
        )
    )
    horizon_out = (
        gw_out.groupby(["season", "fpl_code", "position"], as_index=False)
        .agg(
            expected_points_5gw=("expected_points", "sum"),
            expected_minutes_5gw=("expected_minutes", "sum"),
            fixture_count_5gw=("fixture_count", "sum"),
            gameweeks_with_fixtures=("gameweek", "nunique"),
            gameweeks=("gameweek", lambda values: ",".join(map(str, sorted(set(values.astype(int)))))),
        )
    )
    for frame in (gw_out, horizon_out):
        frame["forecast_snapshot_id"] = snapshot_id
        frame["model_status"] = "CANDIDATE_NOT_VALIDATED"
        frame["production_eligible"] = False
        frame["decision_weight"] = 0.0

    fixture_path = output_dir / "fixture_forecasts.csv"
    gw_path = output_dir / "player_gameweek_forecasts.csv"
    horizon_path = output_dir / "player_five_gw_forecasts.csv"
    fixture_out.to_csv(fixture_path, index=False, lineterminator="\n")
    gw_out.to_csv(gw_path, index=False, lineterminator="\n")
    horizon_out.to_csv(horizon_path, index=False, lineterminator="\n")
    observed_gameweeks = sorted(pd.to_numeric(merged["gameweek"], errors="raise").astype(int).unique().tolist())
    gameweeks = [int(value) for value in feature_report.get("target_gameweeks", [])]
    if len(gameweeks) != 5 or gameweeks != list(range(gameweeks[0], gameweeks[0] + 5)):
        raise ValueError(f"Feature report does not declare five consecutive target gameweeks: {gameweeks}")
    if not set(observed_gameweeks).issubset(set(gameweeks)):
        raise ValueError(f"Forecast rows contain gameweeks outside the declared horizon: {observed_gameweeks}")
    if merged["season"].astype(str).nunique() != 1:
        raise ValueError("Forecast matrix contains more than one season")
    report = {
        "status": "PASS_CTA_FIVE_GW_CANDIDATE_FORECAST",
        "forecast_snapshot_id": snapshot_id,
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "provenance": provenance,
        "season": str(merged["season"].iloc[0]),
        "gameweeks": gameweeks,
        "fixture_player_rows": len(fixture_out),
        "player_gameweek_rows": len(gw_out),
        "five_gameweek_player_rows": len(horizon_out),
        "points_model": "CTA-owned position-specific XGBoost candidate",
        "minutes_model": "Dastan 1.1.0 p60-only heads plus minutes calibration",
        "dastan_points_heads_used": False,
        "model_hashes": model_hashes,
        "feature_matrix_sha256": sha256(matrix_path),
        "minutes_predictions_sha256": sha256(minutes_path),
        "outputs": {
            "fixture_forecasts": {"path": str(fixture_path), "sha256": sha256(fixture_path)},
            "player_gameweek_forecasts": {"path": str(gw_path), "sha256": sha256(gw_path)},
            "player_five_gw_forecasts": {"path": str(horizon_path), "sha256": sha256(horizon_path)},
        },
        "decision_safeguards": {
            "status": "EXPLORATORY_NOT_PRODUCTION",
            "decision_weight": 0.0,
            "production_eligible": False,
            "covar_used": False,
            "reason": "M2 validation remains deferred; do not route candidate forecasts into recommendations",
        },
        "aggregation": "player-GW and five-GW expected points/minutes are sums of fixture-level forecasts; no aggregate forecast is split across fixtures",
        "uncertainty": "No calibrated player-point variance or joint scenario covariance is produced",
    }
    (output_dir / "forecast_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-matrix", type=Path, required=True)
    parser.add_argument("--minutes-predictions", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--feature-report", type=Path, required=True)
    parser.add_argument("--minutes-report", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    score(args.feature_matrix, args.minutes_predictions, args.schema,
          args.source_report, args.feature_report, args.minutes_report,
          args.model_dir, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
