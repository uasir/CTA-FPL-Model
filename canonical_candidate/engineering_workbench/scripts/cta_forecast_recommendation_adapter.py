#!/usr/bin/env python3
"""Adapt a CTA five-GW candidate bundle to the shared recommendation forecast contract.

This adapter is intentionally a provider/contract boundary only. It does not
call either recommendation engine while CTA M2 validation is pending.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class CTAForecastAdapterError(ValueError):
    """Raised when a CTA candidate bundle cannot safely enter the shared contract."""


POSITION_BY_ELEMENT_TYPE = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CTAForecastAdapterError(f"{label} is missing or invalid JSON") from exc
    if not isinstance(value, dict):
        raise CTAForecastAdapterError(f"{label} must be a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise CTAForecastAdapterError(f"{label} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CTAForecastAdapterError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CTAForecastAdapterError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _finite(value: Any, label: str, *, non_negative: bool = False) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise CTAForecastAdapterError(f"{label} must be a finite number") from exc
    if isinstance(value, bool) or not math.isfinite(result):
        raise CTAForecastAdapterError(f"{label} must be a finite number")
    if non_negative and result < 0:
        raise CTAForecastAdapterError(f"{label} cannot be negative")
    return result


def _optional_eo(
    players: list[dict[str, Any]],
    eo_snapshot: Mapping[str, Any] | None,
    snapshot_id: str,
    deadline: datetime,
) -> dict[str, Any] | None:
    if eo_snapshot is None:
        return None
    if not isinstance(eo_snapshot, Mapping):
        raise CTAForecastAdapterError("EO snapshot must be an object")
    required = (
        "forecast_snapshot_id", "target_deadline_utc", "eo_cohort",
        "eo_sample_managers", "eo_rank_cohort_captured_at_utc",
        "eo_deadline_time_utc", "eo_picks_captured_at_utc",
        "eo_picks_lock_verified", "players",
    )
    missing = [key for key in required if key not in eo_snapshot]
    if missing:
        raise CTAForecastAdapterError(f"EO snapshot is missing required fields: {missing}")
    if eo_snapshot["forecast_snapshot_id"] != snapshot_id:
        raise CTAForecastAdapterError("EO snapshot belongs to a different CTA forecast snapshot")
    if not isinstance(eo_snapshot["eo_cohort"], str) or not eo_snapshot["eo_cohort"].strip():
        raise CTAForecastAdapterError("EO cohort must be a non-empty string")
    sample = eo_snapshot["eo_sample_managers"]
    if isinstance(sample, bool) or not isinstance(sample, int) or sample < 1:
        raise CTAForecastAdapterError("EO sample managers must be a positive integer")
    rank_at = _time(eo_snapshot["eo_rank_cohort_captured_at_utc"], "EO rank cohort capture time")
    eo_deadline = _time(eo_snapshot["eo_deadline_time_utc"], "EO deadline")
    target_deadline = _time(eo_snapshot["target_deadline_utc"], "EO target deadline")
    picks_at = _time(eo_snapshot["eo_picks_captured_at_utc"], "EO picks capture time")
    if eo_deadline != deadline or target_deadline != deadline:
        raise CTAForecastAdapterError("EO deadline does not match the CTA target deadline")
    if not rank_at < deadline < picks_at:
        raise CTAForecastAdapterError("EO rank cohort must predate deadline and picks must be post-deadline")
    if eo_snapshot["eo_picks_lock_verified"] is not True:
        raise CTAForecastAdapterError("EO picks must have verified post-lock provenance")
    values = eo_snapshot["players"]
    if not isinstance(values, list):
        raise CTAForecastAdapterError("EO players must be a list")
    by_id: dict[int, float] = {}
    known_ids = {row["fpl_element_id"] for row in players}
    for index, row in enumerate(values):
        if not isinstance(row, Mapping):
            raise CTAForecastAdapterError(f"EO players[{index}] must be an object")
        player_id = row.get("fpl_element_id")
        if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id not in known_ids:
            raise CTAForecastAdapterError(f"EO players[{index}] has an unknown FPL element ID")
        if player_id in by_id:
            raise CTAForecastAdapterError(f"EO snapshot has duplicate player {player_id}")
        by_id[player_id] = _finite(
            row.get("effective_ownership_pct"),
            f"EO player {player_id} effective_ownership_pct",
            non_negative=True,
        )
    for row in players:
        if row["fpl_element_id"] in by_id:
            row["effective_ownership_pct"] = by_id[row["fpl_element_id"]]
    return {
        "eo_cohort": eo_snapshot["eo_cohort"],
        "eo_sample_managers": sample,
        "eo_rank_cohort_captured_at_utc": rank_at.isoformat(),
        "eo_deadline_time_utc": eo_deadline.isoformat(),
        "eo_picks_captured_at_utc": picks_at.isoformat(),
        "eo_picks_lock_verified": True,
        "players_with_eo": len(by_id),
    }


def build_cta_forecast_provider_snapshot(
    bundle_dir: str | Path,
    *,
    eo_snapshot: Mapping[str, Any] | None = None,
    now_utc: str | datetime | None = None,
) -> dict[str, Any]:
    """Verify a candidate bundle and map it to the shared player forecast contract.

    The output is always exploratory. It cannot release recommendations or
    enter the conventional FPL Cat/Sideline Quant product path.
    """
    root = Path(bundle_dir)
    forecast_report = _read_json(root / "forecasts" / "forecast_report.json", "forecast report")
    bundle_report = _read_json(root / "forecasts" / "bundle_validation_report.json", "bundle validation report")
    model_manifest = _read_json(root / "models" / "cta_points_model_manifest.json", "CTA points model manifest")
    source_report = _read_json(root / "source_preparation_report.json", "source preparation report")
    bootstrap = _read_json(root / "snapshots" / "bootstrap-static.json", "official FPL bootstrap")
    snapshot_manifest = source_report.get("current_bootstrap_snapshot")
    if not isinstance(snapshot_manifest, Mapping):
        raise CTAForecastAdapterError("source report lacks current official bootstrap snapshot metadata")

    if forecast_report.get("status") != "PASS_CTA_FIVE_GW_CANDIDATE_FORECAST":
        raise CTAForecastAdapterError("CTA forecast report is not a passed five-GW candidate")
    if bundle_report.get("status") != "PASS_CTA_FORECAST_BUNDLE_INTEGRITY":
        raise CTAForecastAdapterError("CTA forecast bundle integrity did not pass")
    if model_manifest.get("status") != "CANDIDATE_TRAINED_M2_VALIDATION_PENDING":
        raise CTAForecastAdapterError("CTA points model is not in the expected M2-pending candidate state")
    if model_manifest.get("validation", {}).get("status") != "NOT_RUN_M2_DEFERRED":
        raise CTAForecastAdapterError("CTA M2 validation state is not explicitly deferred")
    if model_manifest.get("production_eligible") is not False or model_manifest.get("decision_weight") != 0:
        raise CTAForecastAdapterError("CTA points model must remain production-ineligible with zero decision weight")
    if forecast_report.get("decision_safeguards", {}).get("production_eligible") is not False:
        raise CTAForecastAdapterError("forecast report does not preserve production-ineligible safeguard")
    if forecast_report.get("decision_safeguards", {}).get("decision_weight") != 0:
        raise CTAForecastAdapterError("forecast report decision weight must remain zero")
    if forecast_report.get("decision_safeguards", {}).get("covar_used") is not False:
        raise CTAForecastAdapterError("CTA candidate must not use CoVar")
    if bundle_report.get("production_eligible") is not False or bundle_report.get("decision_weight") != 0:
        raise CTAForecastAdapterError("bundle validation report does not preserve candidate safeguards")
    if bundle_report.get("covar_used") is not False:
        raise CTAForecastAdapterError("bundle validation report must explicitly exclude CoVar")

    snapshot_id = forecast_report.get("forecast_snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id:
        raise CTAForecastAdapterError("forecast snapshot ID is missing")
    if bundle_report.get("forecast_snapshot_id") != snapshot_id:
        raise CTAForecastAdapterError("bundle validation snapshot ID differs from forecast report")
    gameweeks = forecast_report.get("gameweeks")
    if (not isinstance(gameweeks, list) or len(gameweeks) != 5
            or any(isinstance(gw, bool) or not isinstance(gw, int) for gw in gameweeks)
            or any(right != left + 1 for left, right in zip(gameweeks, gameweeks[1:]))):
        raise CTAForecastAdapterError("CTA candidate must cover five consecutive ordered Gameweeks")
    season = forecast_report.get("season")
    if source_report.get("season") != season:
        raise CTAForecastAdapterError("source and forecast seasons do not match")
    if source_report.get("feature_source_mode") != forecast_report.get("feature_source_mode"):
        raise CTAForecastAdapterError("source and forecast feature-source modes do not match")
    if model_manifest.get("feature_source_mode") != forecast_report.get("feature_source_mode"):
        raise CTAForecastAdapterError("CTA model and forecast feature-source modes do not match")

    provenance = forecast_report.get("provenance")
    if not isinstance(provenance, Mapping):
        raise CTAForecastAdapterError("forecast provenance is missing")
    source_manifest_path = root / "source_download_manifest.json"
    model_manifest_path = root / "models" / "cta_points_model_manifest.json"
    if provenance.get("source_manifest_sha256") != _sha256(source_manifest_path):
        raise CTAForecastAdapterError("source manifest SHA-256 does not match forecast provenance")
    if provenance.get("points_model_manifest_sha256") != _sha256(model_manifest_path):
        raise CTAForecastAdapterError("CTA model manifest SHA-256 does not match forecast provenance")

    generated_at = _time(forecast_report.get("generated_at_utc"), "forecast generated_at_utc")
    captured_at = _time(snapshot_manifest.get("captured_at_utc"), "bootstrap captured_at_utc")
    deadline = _time(snapshot_manifest.get("deadline_time"), "target deadline")
    safety_minutes = snapshot_manifest.get("safety_buffer_minutes", 5)
    if isinstance(safety_minutes, bool) or not isinstance(safety_minutes, int) or safety_minutes < 5:
        raise CTAForecastAdapterError("official bootstrap safety buffer must be at least five minutes")
    if snapshot_manifest.get("gameweek") != gameweeks[0]:
        raise CTAForecastAdapterError("official bootstrap snapshot is not for the first target Gameweek")
    if (deadline - captured_at).total_seconds() < safety_minutes * 60:
        raise CTAForecastAdapterError("official bootstrap snapshot violates the pre-deadline safety buffer")
    if not generated_at < deadline:
        raise CTAForecastAdapterError("CTA forecast was generated at or after the first target deadline")

    if now_utc is None:
        now = datetime.now(timezone.utc)
    elif isinstance(now_utc, datetime):
        if now_utc.tzinfo is None or now_utc.utcoffset() is None:
            raise CTAForecastAdapterError("now_utc datetime must be timezone-aware")
        now = now_utc.astimezone(timezone.utc)
    else:
        now = _time(now_utc, "now_utc")
    age_seconds = (now - generated_at).total_seconds()
    freshness = "FRESH_WITHIN_24H" if 0 <= age_seconds <= 24 * 60 * 60 else "STALE_OVER_24H"

    elements = bootstrap.get("elements")
    if not isinstance(elements, list) or not elements:
        raise CTAForecastAdapterError("official bootstrap elements are missing")
    by_code: dict[int, Mapping[str, Any]] = {}
    for element in elements:
        if not isinstance(element, Mapping):
            raise CTAForecastAdapterError("official bootstrap contains a malformed player element")
        code = element.get("code")
        if isinstance(code, bool) or not isinstance(code, int) or code < 1:
            raise CTAForecastAdapterError("official bootstrap player code must be a positive integer")
        if code in by_code:
            raise CTAForecastAdapterError(f"official bootstrap has duplicate stable player code {code}")
        by_code[code] = element

    csv_path = root / "forecasts" / "player_five_gw_forecasts.csv"
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except OSError as exc:
        raise CTAForecastAdapterError("five-GW player forecast CSV is missing") from exc
    if not rows:
        raise CTAForecastAdapterError("five-GW player forecast CSV is empty")
    if len(rows) != forecast_report.get("five_gameweek_player_rows"):
        raise CTAForecastAdapterError("five-GW player forecast row count differs from forecast report")

    players: list[dict[str, Any]] = []
    seen_codes: set[int] = set()
    for index, row in enumerate(rows):
        try:
            code = int(row["fpl_code"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CTAForecastAdapterError(f"five-GW forecast row {index} has an invalid FPL stable code") from exc
        if code in seen_codes:
            raise CTAForecastAdapterError(f"five-GW forecast has duplicate FPL stable code {code}")
        seen_codes.add(code)
        element = by_code.get(code)
        if element is None:
            raise CTAForecastAdapterError(f"FPL stable code {code} is absent from the official bootstrap")
        element_id = element.get("id")
        team_id = element.get("team")
        position = POSITION_BY_ELEMENT_TYPE.get(element.get("element_type"))
        if isinstance(element_id, bool) or not isinstance(element_id, int) or element_id < 1:
            raise CTAForecastAdapterError(f"bootstrap element for code {code} has invalid FPL element ID")
        if isinstance(team_id, bool) or not isinstance(team_id, int) or team_id < 1:
            raise CTAForecastAdapterError(f"bootstrap element for code {code} has invalid team ID")
        if row.get("season") != season:
            raise CTAForecastAdapterError(f"season mismatch for FPL stable code {code}")
        if position is None or row.get("position") != position:
            raise CTAForecastAdapterError(f"position mismatch for FPL stable code {code}")
        if row.get("forecast_snapshot_id") != snapshot_id:
            raise CTAForecastAdapterError(f"forecast snapshot mismatch for FPL stable code {code}")
        if row.get("model_status") != "CANDIDATE_NOT_VALIDATED":
            raise CTAForecastAdapterError(f"player {element_id} does not carry candidate-only status")
        if row.get("production_eligible", "").strip().lower() != "false":
            raise CTAForecastAdapterError(f"player {element_id} is not explicitly production-ineligible")
        if _finite(row.get("decision_weight"), f"player {element_id} decision_weight") != 0:
            raise CTAForecastAdapterError(f"player {element_id} decision weight must be zero")
        if row.get("gameweeks") != ",".join(str(gw) for gw in gameweeks):
            raise CTAForecastAdapterError(f"player {element_id} has a different forecast horizon")
        now_cost = element.get("now_cost")
        if isinstance(now_cost, bool) or not isinstance(now_cost, int) or now_cost <= 0:
            raise CTAForecastAdapterError(f"bootstrap element for player {element_id} has invalid price")
        players.append({
            "fpl_element_id": element_id,
            "expected_points": _finite(row.get("expected_points_5gw"), f"player {element_id} expected_points_5gw"),
            "expected_minutes": _finite(row.get("expected_minutes_5gw"), f"player {element_id} expected_minutes_5gw", non_negative=True),
            "price": now_cost / 10.0,
            "team_id": team_id,
            "position": position,
            "display_name": str(element.get("web_name") or element.get("second_name") or element_id),
            "fpl_stable_code": code,
        })
    if len({row["fpl_element_id"] for row in players}) != len(players):
        raise CTAForecastAdapterError("five-GW forecast maps multiple stable codes to one FPL element ID")

    gameweek_csv = root / "forecasts" / "player_gameweek_forecasts.csv"
    try:
        with gameweek_csv.open("r", encoding="utf-8", newline="") as stream:
            gameweek_rows = list(csv.DictReader(stream))
    except OSError as exc:
        raise CTAForecastAdapterError("player-Gameweek forecast CSV is missing") from exc
    if len(gameweek_rows) != forecast_report.get("player_gameweek_rows"):
        raise CTAForecastAdapterError("player-Gameweek row count differs from forecast report")
    panels_by_gw: dict[int, list[dict[str, Any]]] = {gw: [] for gw in gameweeks}
    seen_by_gw: dict[int, set[int]] = {gw: set() for gw in gameweeks}
    for index, row in enumerate(gameweek_rows):
        try:
            gw = int(row["gameweek"])
            code = int(row["fpl_code"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CTAForecastAdapterError(f"player-Gameweek row {index} has invalid keys") from exc
        if gw not in panels_by_gw:
            raise CTAForecastAdapterError(f"player-Gameweek row {index} is outside the five-GW horizon")
        if row.get("season") != season:
            raise CTAForecastAdapterError(f"season mismatch for player-Gameweek row {index}")
        if code not in seen_codes:
            raise CTAForecastAdapterError(f"player-Gameweek row {index} has no matching five-GW player total")
        if code in seen_by_gw[gw]:
            raise CTAForecastAdapterError(f"duplicate player {code} in GW{gw} forecast")
        seen_by_gw[gw].add(code)
        element = by_code[code]
        element_id = element["id"]
        position = POSITION_BY_ELEMENT_TYPE.get(element.get("element_type"))
        if row.get("position") != position:
            raise CTAForecastAdapterError(f"position mismatch for player {element_id} in GW{gw}")
        if row.get("forecast_snapshot_id") != snapshot_id:
            raise CTAForecastAdapterError(f"player-Gameweek snapshot mismatch for player {element_id}")
        if row.get("model_status") != "CANDIDATE_NOT_VALIDATED":
            raise CTAForecastAdapterError(f"player {element_id} GW{gw} is not candidate-only")
        if row.get("production_eligible", "").strip().lower() != "false":
            raise CTAForecastAdapterError(f"player {element_id} GW{gw} is not production-ineligible")
        if _finite(row.get("decision_weight"), f"player {element_id} GW{gw} decision_weight") != 0:
            raise CTAForecastAdapterError(f"player {element_id} GW{gw} decision weight must be zero")
        panels_by_gw[gw].append({
            "fpl_element_id": element_id,
            "expected_points": _finite(row.get("expected_points"), f"player {element_id} GW{gw} expected_points"),
            "expected_minutes": _finite(row.get("expected_minutes"), f"player {element_id} GW{gw} expected_minutes", non_negative=True),
            "price": element["now_cost"] / 10.0,
            "team_id": element["team"],
            "position": position,
            "display_name": str(element.get("web_name") or element.get("second_name") or element_id),
        })
    if any(not panels_by_gw[gw] for gw in gameweeks):
        raise CTAForecastAdapterError("one or more target Gameweeks have no player forecasts")
    gameweek_panels = [
        {"gameweek": gw, "player_forecasts": panels_by_gw[gw]}
        for gw in gameweeks
    ]

    # Reconcile the cumulative five-GW product against its five individual
    # player-GW panels. This prevents a stale/mismatched aggregate from feeding
    # general rankings while a different panel feeds the personal optimiser.
    panel_totals: dict[int, dict[str, float]] = {}
    for panel in gameweek_panels:
        for player in panel["player_forecasts"]:
            totals = panel_totals.setdefault(
                player["fpl_element_id"], {"expected_points": 0.0, "expected_minutes": 0.0},
            )
            totals["expected_points"] += player["expected_points"]
            totals["expected_minutes"] += player["expected_minutes"]
    for player in players:
        totals = panel_totals.get(player["fpl_element_id"])
        if totals is None:
            raise CTAForecastAdapterError(
                f"player {player['fpl_element_id']} has no individual Gameweek forecast panel"
            )
        for field in ("expected_points", "expected_minutes"):
            if not math.isclose(
                totals[field], player[field], rel_tol=1e-7, abs_tol=1e-6,
            ):
                raise CTAForecastAdapterError(
                    f"five-GW {field} does not reconcile to individual Gameweek panels "
                    f"for player {player['fpl_element_id']}"
                )
    if set(panel_totals) != {player["fpl_element_id"] for player in players}:
        raise CTAForecastAdapterError("individual Gameweek panels and five-GW player universe differ")

    eo_provenance = _optional_eo(players, eo_snapshot, snapshot_id, deadline)
    data_coverage = {
        "freshness_status": freshness,
        "target_deadline_utc": deadline.isoformat(),
        "bootstrap_captured_at_utc": captured_at.isoformat(),
        "feature_source_mode": forecast_report["feature_source_mode"],
        "understat_player_metric_coverage": source_report.get("understat_player_metric_coverage", {}),
        "understat_player_coverage_counts": {
            key: source_report.get("understat_player_coverage", {}).get(key)
            for key in ("appearance_rows", "nonappearance_rows", "unknown_minutes_rows")
        },
        "masked_unavailable_feature_count": forecast_report.get("masked_unavailable_feature_count"),
        "forecast_player_count": len(players),
        "forecast_fixture_rows": forecast_report.get("fixture_player_rows"),
        "forecast_player_gameweek_rows": forecast_report.get("player_gameweek_rows"),
        "forecast_five_gameweek_player_rows": forecast_report.get("five_gameweek_player_rows"),
        "production_eligible": False,
        "decision_weight": 0,
        "covar_used": False,
    }
    if eo_provenance:
        data_coverage.update({
            key: value for key, value in eo_provenance.items() if key != "players_with_eo"
        })
        data_coverage["eo_players_with_coverage"] = eo_provenance["players_with_eo"]

    model_version = "cta-owned-xgboost:" + str(provenance["points_model_manifest_sha256"])
    shared_forecast = {
        "forecast_snapshot_id": snapshot_id,
        "model_version": model_version,
        "forecast_horizon_gameweeks": len(gameweeks),
        "forecast_quality": {
            "validation_status": "EXPLORATORY_ONLY",
            "point_in_time_status": "VERIFIED",
            "data_coverage": data_coverage,
            "limitations": [
                "CTA points model remains M2-validation-pending and cannot drive recommendations.",
                "CTA candidate has zero decision weight and is not production eligible.",
                "No player-point variance or CoVar is produced or inferred.",
                "Team/opponent Understat feature families remain masked under the current source policy.",
                "Current price and team metadata come from the captured official FPL bootstrap.",
            ],
        },
        "player_forecasts": players,
    }
    provider_snapshot = {
        "provider": {"name": "CTA-FPL", "product": "CTA-owned points", "variant": "five-gw-candidate"},
        "forecast_snapshot_id": snapshot_id,
        "season": season,
        "gameweeks": gameweeks,
        "gameweek_panels": gameweek_panels,
        "timing": {
            "generated_at_utc": generated_at.isoformat(),
            "bootstrap_captured_at_utc": captured_at.isoformat(),
            "deadline_utc": deadline.isoformat(),
            "freshness_status": freshness,
        },
        "provenance": {
            "source_manifest_sha256": provenance["source_manifest_sha256"],
            "points_model_manifest_sha256": provenance["points_model_manifest_sha256"],
            "feature_matrix_sha256": provenance["feature_matrix_sha256"],
            "minutes_predictions_sha256": provenance["minutes_predictions_sha256"],
            "points_model_hashes": forecast_report.get("model_hashes", {}),
            "feature_source_mode": forecast_report["feature_source_mode"],
        },
    }
    return {
        "schema_version": "cta_forecast_provider_snapshot/1.0.0",
        "provider_snapshot": provider_snapshot,
        "shared_forecast": shared_forecast,
        "recommendation_products": {
            "conventional_personal_squad": {
                "status": "SEPARATE_CONVENTIONAL_PROVIDER_PATH",
                "enabled": True,
                "cta_points_used": False,
                "providers": ["FPL Cat", "Sideline Quant"],
            },
            "cta_informed_personal_squad": {
                "status": "WITHHELD_M2_VALIDATION_PENDING",
                "enabled": False,
                "squad_independent": False,
                "requires": ["M2 forecast validation", "fresh explicit manager squad snapshot", "verified LiveFPL EO/coverage"],
            },
            "general_cta_player_rankings": {
                "status": "WITHHELD_M2_VALIDATION_PENDING",
                "enabled": False,
                "squad_independent": True,
                "requires": ["M2 forecast validation"],
            },
        },
        "guardrails": {
            "recommendations_emitted": False,
            "candidate_only": True,
            "production_eligible": False,
            "decision_weight": 0,
            "covar_used": False,
            "effective_ownership_blended_into_expected_points": False,
            "personal_squad_context_consumed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--eo-snapshot", type=Path)
    parser.add_argument("--now-utc")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    eo = _read_json(args.eo_snapshot, "EO snapshot") if args.eo_snapshot else None
    result = build_cta_forecast_provider_snapshot(
        args.bundle_dir, eo_snapshot=eo, now_utc=args.now_utc,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "PASS_CTA_FORECAST_PROVIDER_ADAPTER",
        "forecast_snapshot_id": result["provider_snapshot"]["forecast_snapshot_id"],
        "forecast_horizon_gameweeks": result["shared_forecast"]["forecast_horizon_gameweeks"],
        "player_forecasts": len(result["shared_forecast"]["player_forecasts"]),
        "recommendations_emitted": result["guardrails"]["recommendations_emitted"],
        "production_eligible": result["guardrails"]["production_eligible"],
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
