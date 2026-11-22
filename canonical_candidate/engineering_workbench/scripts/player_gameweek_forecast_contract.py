#!/usr/bin/env python3
"""Validate FPL Cat's licensed five-plus-GW player-Gameweek forecast panel.

This is intentionally separate from the fixture-level contract. It preserves
one provider snapshot and the provider's native player_gameweek rows; no
fixture-level xP or per-fixture split is inferred.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping


class PlayerGameweekForecastError(ValueError):
    """Raised when a player-Gameweek forecast panel is incomplete or invalid."""


def _utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise PlayerGameweekForecastError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PlayerGameweekForecastError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise PlayerGameweekForecastError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _positive_id(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PlayerGameweekForecastError(f"{field} must be a positive integer")
    return value


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value < 0:
        raise PlayerGameweekForecastError(f"{field} must be finite and non-negative")
    return float(value)


def build_player_gameweek_forecast_bundle(
    capture: Mapping[str, Any],
    *,
    decision_as_of_utc: str,
    required_player_ids: list[int],
    minimum_horizon_gameweeks: int = 5,
    maximum_snapshot_age_hours: float = 24,
) -> dict[str, Any]:
    """Build an M4-ready aggregate-grain bundle from one licensed partner capture."""
    if not isinstance(capture, Mapping):
        raise PlayerGameweekForecastError("capture must be an object")
    if capture.get("provider_source_id") != "fpl_cat_partner_projections":
        raise PlayerGameweekForecastError("capture is not from the registered FPL Cat partner source")
    snapshot = capture.get("provider_snapshot")
    if not isinstance(snapshot, Mapping):
        raise PlayerGameweekForecastError("provider_snapshot is required")
    if snapshot.get("grain") != "player_gameweek":
        raise PlayerGameweekForecastError("FPL Cat partner bundle must retain player_gameweek grain")
    if snapshot.get("decision_eligible") is not True:
        raise PlayerGameweekForecastError("provider snapshot is not marked decision eligible")
    provider = snapshot.get("provider")
    expected_provider = {
        "name": "FPL Cat",
        "product": "partner_projections",
        "variant": "provider_native_xp",
        "version": "partner-api-v1",
    }
    if provider != expected_provider:
        raise PlayerGameweekForecastError("provider identity/version does not match the partner contract")
    snapshot_id = snapshot.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id.strip():
        raise PlayerGameweekForecastError("immutable provider snapshot_id is required")
    source = snapshot.get("source")
    if not isinstance(source, Mapping) or not isinstance(source.get("raw_sha256"), str) or len(source["raw_sha256"]) != 64:
        raise PlayerGameweekForecastError("raw provider SHA-256 provenance is required")

    weeks = snapshot.get("gameweeks")
    if (not isinstance(weeks, list) or len(weeks) < minimum_horizon_gameweeks
            or any(isinstance(gw, bool) or not isinstance(gw, int) or gw < 1 for gw in weeks)
            or weeks != list(range(weeks[0], weeks[0] + len(weeks)))):
        raise PlayerGameweekForecastError("at least five consecutive provider Gameweeks are required")
    if isinstance(minimum_horizon_gameweeks, bool) or not isinstance(minimum_horizon_gameweeks, int) or minimum_horizon_gameweeks < 5:
        raise PlayerGameweekForecastError("minimum_horizon_gameweeks cannot be below five")
    if not isinstance(required_player_ids, list) or not required_player_ids:
        raise PlayerGameweekForecastError("required_player_ids must be a non-empty list")
    player_ids = [_positive_id(pid, "required_player_ids item") for pid in required_player_ids]
    if len(set(player_ids)) != len(player_ids):
        raise PlayerGameweekForecastError("required_player_ids must be unique")

    timing = snapshot.get("timing")
    if not isinstance(timing, Mapping):
        raise PlayerGameweekForecastError("provider timing is required")
    generated = _utc(timing.get("generated_at_utc"), "generated_at_utc")
    captured = _utc(timing.get("captured_at_utc"), "captured_at_utc")
    as_of = _utc(decision_as_of_utc, "decision_as_of_utc")
    deadlines = timing.get("gameweek_deadlines_utc")
    if not isinstance(deadlines, Mapping):
        raise PlayerGameweekForecastError("official per-Gameweek deadlines are required")
    parsed_deadlines = {gw: _utc(deadlines.get(str(gw)), f"GW{gw} deadline") for gw in weeks}
    if generated > captured or captured > as_of:
        raise PlayerGameweekForecastError("provider generation/capture timestamps are inconsistent")
    if any(as_of >= deadline for deadline in parsed_deadlines.values()):
        raise PlayerGameweekForecastError("decision as-of time must precede every forecast Gameweek deadline")
    if (as_of - captured).total_seconds() / 3600 > maximum_snapshot_age_hours:
        raise PlayerGameweekForecastError("provider snapshot is stale at decision time")

    rows = snapshot.get("records")
    if not isinstance(rows, list) or not rows:
        raise PlayerGameweekForecastError("player-Gameweek forecast rows are missing")
    by_key = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise PlayerGameweekForecastError(f"records[{index}] must be an object")
        pid = _positive_id(row.get("fpl_element_id"), f"records[{index}].fpl_element_id")
        gw = _positive_id(row.get("gameweek"), f"records[{index}].gameweek")
        if pid not in player_ids or gw not in weeks:
            continue
        key = (pid, gw)
        if key in by_key:
            raise PlayerGameweekForecastError(f"duplicate player-Gameweek forecast {key}")
        position = row.get("position")
        if position not in {"GKP", "DEF", "MID", "FWD"}:
            raise PlayerGameweekForecastError(f"player {pid} GW{gw} has invalid position")
        fixtures = row.get("fixtures_count")
        if isinstance(fixtures, bool) or not isinstance(fixtures, int) or fixtures < 0:
            raise PlayerGameweekForecastError(f"player {pid} GW{gw} has invalid fixture count")
        opponents = row.get("opponents")
        if not isinstance(opponents, list) or len(opponents) != fixtures:
            raise PlayerGameweekForecastError(f"player {pid} GW{gw} opponent coverage is inconsistent")
        by_key[key] = {
            "fpl_element_id": pid,
            "gameweek": gw,
            "team_id": _positive_id(row.get("team_id"), "team_id"),
            "position": position,
            "expected_points": _number(row.get("expected_points"), "expected_points"),
            "expected_minutes": _number(row.get("expected_minutes"), "expected_minutes"),
            "fixtures_count": fixtures,
            "opponents": opponents,
            "play_chance": row.get("play_chance"),
            "p_return": row.get("p_return"),
            "p_haul": row.get("p_haul"),
            "p_blank": row.get("p_blank"),
            "xp_q10": row.get("xp_q10"),
            "xp_q90": row.get("xp_q90"),
            "breakdown": row.get("breakdown"),
        }
    expected_keys = {(pid, gw) for pid in player_ids for gw in weeks}
    missing = sorted(expected_keys - set(by_key))
    if missing:
        raise PlayerGameweekForecastError(f"missing player-Gameweek forecasts: {missing[:20]}")
    if len(by_key) != len(expected_keys):
        raise PlayerGameweekForecastError("unexpected player-Gameweek row count")

    ordered_rows = [by_key[(pid, gw)] for gw in weeks for pid in player_ids]
    return {
        "forecast_bundle_id": f"{snapshot_id}-asof-{as_of.strftime('%Y%m%dT%H%M%SZ')}",
        "forecast_snapshot_id": snapshot_id,
        "provider_source_id": capture["provider_source_id"],
        "provider": dict(provider),
        "model_version": snapshot.get("model_version", "provider_model_version_not_disclosed"),
        "contract_version": "1.0.0-player-gameweek",
        "forecast_grain": "player_gameweek",
        "decision_as_of_utc": as_of.isoformat().replace("+00:00", "Z"),
        "horizon_gameweeks": weeks[:],
        "source_snapshot_ids": [snapshot_id],
        "player_gameweek_forecasts": ordered_rows,
        "fixture_forecasts": None,
        "capabilities": {
            "five_gameweek_transfer_comparison": True,
            "fixture_level_expected_points": False,
            "double_gameweek_fixture_split": False,
            "provider_native_double_gameweek_total_preserved": True,
            "joint_player_point_scenarios": False,
            "covariance_available": False,
        },
        "provenance": {
            "raw_sha256": source["raw_sha256"],
            "source_url": source.get("url"),
            "generated_at_utc": timing["generated_at_utc"],
            "captured_at_utc": timing["captured_at_utc"],
            "gameweek_deadlines_utc": {str(gw): timing["gameweek_deadlines_utc"][str(gw)] for gw in weeks},
        },
    }
