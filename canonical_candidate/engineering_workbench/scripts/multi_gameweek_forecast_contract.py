#!/usr/bin/env python3
"""Provenance-controlled fixture-level multi-Gameweek forecast bundles.

The contract only normalizes explicit provider fixture forecasts. It never
extrapolates a single-GW projection, invents player rows, or silently blends
providers. Blank Gameweeks are represented as zero only when the supplied
fixture schedule confirms that the player's club has no fixture.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping

from provider_capability_registry import (
    ProviderCapabilityError,
    require_multi_gameweek_capture,
    validate_capture_against_registry,
)


class MultiGameweekForecastError(ValueError):
    """Raised when a forecast bundle is incomplete or provenance-inconsistent."""


def _utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise MultiGameweekForecastError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MultiGameweekForecastError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise MultiGameweekForecastError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _id(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise MultiGameweekForecastError(f"{field} must be a positive integer")
    return value


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise MultiGameweekForecastError(f"{field} must be finite and numeric")
    if value < 0:
        raise MultiGameweekForecastError(f"{field} cannot be negative")
    return float(value)


def build_multi_gameweek_forecast_bundle(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and aggregate a five-plus-GW provider fixture forecast bundle.

    Required top-level keys:
      forecast_bundle_id, season, provider, model_version, decision_as_of_utc,
      required_player_ids, panels.

    Each panel contains one normalized provider snapshot (player_fixture
    grain), fixture metadata, and player metadata for that target Gameweek.
    """
    if not isinstance(payload, Mapping):
        raise MultiGameweekForecastError("payload must be an object")
    for key in ("forecast_bundle_id", "season", "model_version"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise MultiGameweekForecastError(f"{key} must be a non-empty string")
    provider = payload.get("provider")
    if not isinstance(provider, Mapping) or any(
        not isinstance(provider.get(key), str) or not provider[key].strip()
        for key in ("name", "product", "variant", "version")
    ):
        raise MultiGameweekForecastError("provider identity must include name, product, variant and version")
    as_of = _utc(payload.get("decision_as_of_utc"), "decision_as_of_utc")
    minimum = payload.get("minimum_horizon_gameweeks", 5)
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 5:
        raise MultiGameweekForecastError("minimum_horizon_gameweeks must be an integer of at least 5")
    source_id = payload.get("provider_source_id")
    if not isinstance(source_id, str) or not source_id.strip():
        raise MultiGameweekForecastError("provider_source_id must identify a registered capture source")
    try:
        require_multi_gameweek_capture(source_id, required_horizon=minimum)
    except ProviderCapabilityError as exc:
        raise MultiGameweekForecastError(f"provider capability gate rejected bundle: {exc}") from exc
    required_ids = payload.get("required_player_ids")
    if not isinstance(required_ids, list) or not required_ids:
        raise MultiGameweekForecastError("required_player_ids must be a non-empty list")
    player_ids = [_id(value, "required_player_ids item") for value in required_ids]
    if len(player_ids) != len(set(player_ids)):
        raise MultiGameweekForecastError("required_player_ids must be unique")

    panels = payload.get("panels")
    if not isinstance(panels, list) or len(panels) < minimum:
        raise MultiGameweekForecastError(f"at least {minimum} explicit Gameweek panels are required")
    parsed_panels = []
    seen_snapshots = set()
    for index, panel in enumerate(panels):
        if not isinstance(panel, Mapping):
            raise MultiGameweekForecastError(f"panels[{index}] must be an object")
        snapshot = panel.get("snapshot")
        if not isinstance(snapshot, Mapping):
            raise MultiGameweekForecastError(f"panels[{index}].snapshot must be a normalized provider snapshot")
        if snapshot.get("season") != payload["season"]:
            raise MultiGameweekForecastError(f"panels[{index}] season does not match bundle")
        if snapshot.get("provider") != dict(provider):
            raise MultiGameweekForecastError(f"panels[{index}] provider identity/version does not match bundle")
        try:
            validate_capture_against_registry(
                source_id,
                {
                    "provider": snapshot.get("provider"),
                    "grain": snapshot.get("grain"),
                    "multi_gameweek_capability": snapshot.get("multi_gameweek_capability", {}),
                },
            )
        except ProviderCapabilityError as exc:
            raise MultiGameweekForecastError(
                f"panels[{index}] provider capability registry rejected snapshot: {exc}"
            ) from exc
        if snapshot.get("grain") != "player_fixture":
            raise MultiGameweekForecastError("fixture-by-fixture transfer evaluation requires player_fixture forecast grain")
        if snapshot.get("decision_eligible") is not True:
            raise MultiGameweekForecastError(f"panels[{index}] provider snapshot is not point-in-time eligible")
        snapshot_id = snapshot.get("snapshot_id")
        if not isinstance(snapshot_id, str) or not snapshot_id.strip() or snapshot_id in seen_snapshots:
            raise MultiGameweekForecastError("each Gameweek must have a unique non-empty provider snapshot_id")
        seen_snapshots.add(snapshot_id)
        timing = snapshot.get("timing")
        if not isinstance(timing, Mapping):
            raise MultiGameweekForecastError(f"panels[{index}] timing is missing")
        captured = _utc(timing.get("captured_at_utc"), f"panels[{index}].captured_at_utc")
        generated = _utc(timing.get("generated_at_utc"), f"panels[{index}].generated_at_utc")
        deadline = _utc(timing.get("deadline_utc"), f"panels[{index}].deadline_utc")
        if generated > captured or captured > as_of or as_of >= deadline:
            raise MultiGameweekForecastError(f"panels[{index}] timing is not valid at decision_as_of_utc")
        age_hours = (as_of - captured).total_seconds() / 3600
        if age_hours > float(payload.get("maximum_snapshot_age_hours", 24)):
            raise MultiGameweekForecastError(f"panels[{index}] forecast snapshot is stale at decision time")
        gw = _id(snapshot.get("target_gameweek"), f"panels[{index}].target_gameweek")

        fixtures = panel.get("fixtures")
        if not isinstance(fixtures, list) or not fixtures:
            raise MultiGameweekForecastError(f"panels[{index}].fixtures must be a non-empty fixture schedule")
        fixture_by_id = {}
        for fixture_index, fixture in enumerate(fixtures):
            if not isinstance(fixture, Mapping):
                raise MultiGameweekForecastError(f"panels[{index}].fixtures[{fixture_index}] must be an object")
            fixture_id = _id(fixture.get("fixture_id"), "fixture_id")
            if fixture_id in fixture_by_id:
                raise MultiGameweekForecastError(f"duplicate fixture_id {fixture_id} in GW{gw}")
            if _id(fixture.get("gameweek"), "fixture.gameweek") != gw:
                raise MultiGameweekForecastError(f"fixture {fixture_id} Gameweek does not match provider panel")
            home = _id(fixture.get("home_team_id"), "fixture.home_team_id")
            away = _id(fixture.get("away_team_id"), "fixture.away_team_id")
            if home == away:
                raise MultiGameweekForecastError(f"fixture {fixture_id} has identical home and away teams")
            kickoff = _utc(fixture.get("kickoff_time"), f"fixture {fixture_id}.kickoff_time")
            fixture_by_id[fixture_id] = {
                "fixture_id": fixture_id, "gameweek": gw,
                "home_team_id": home, "away_team_id": away,
                "kickoff_time": kickoff.isoformat(),
            }

        metadata = panel.get("player_metadata")
        if not isinstance(metadata, list) or not metadata:
            raise MultiGameweekForecastError(f"panels[{index}].player_metadata must be a non-empty list")
        meta_by_id = {}
        for row in metadata:
            if not isinstance(row, Mapping):
                raise MultiGameweekForecastError("player metadata rows must be objects")
            pid = _id(row.get("fpl_element_id"), "player_metadata.fpl_element_id")
            if pid in meta_by_id:
                raise MultiGameweekForecastError(f"duplicate player metadata for {pid} in GW{gw}")
            team = _id(row.get("team_id"), f"player {pid}.team_id")
            position = row.get("position")
            if position not in {"GKP", "DEF", "MID", "FWD"}:
                raise MultiGameweekForecastError(f"player {pid} has invalid position")
            meta_by_id[pid] = {"team_id": team, "position": position}
        missing_meta = sorted(set(player_ids) - set(meta_by_id))
        if missing_meta:
            raise MultiGameweekForecastError(f"missing player metadata in GW{gw}: {missing_meta[:20]}")

        records = snapshot.get("records")
        if not isinstance(records, list) or not records:
            raise MultiGameweekForecastError(f"GW{gw} provider fixture records are missing")
        records_by_key = {}
        for record in records:
            if not isinstance(record, Mapping):
                raise MultiGameweekForecastError(f"GW{gw} provider record must be an object")
            pid = _id(record.get("fpl_element_id"), "record.fpl_element_id")
            fixture_id = _id(record.get("fixture_id"), "record.fixture_id")
            if pid not in player_ids:
                continue
            if fixture_id not in fixture_by_id:
                raise MultiGameweekForecastError(f"player {pid} forecast references unknown fixture {fixture_id}")
            if pid not in meta_by_id:
                raise MultiGameweekForecastError(f"missing metadata for forecast player {pid}")
            team_id = meta_by_id[pid]["team_id"]
            fixture = fixture_by_id[fixture_id]
            if team_id not in {fixture["home_team_id"], fixture["away_team_id"]}:
                raise MultiGameweekForecastError(f"player {pid} team does not participate in fixture {fixture_id}")
            key = (pid, fixture_id)
            if key in records_by_key:
                raise MultiGameweekForecastError(f"duplicate player-fixture forecast {key}")
            if record.get("expected_minutes") is None:
                raise MultiGameweekForecastError(f"player {pid} fixture {fixture_id} is missing expected_minutes")
            records_by_key[key] = {
                "fpl_element_id": pid, "fixture_id": fixture_id, "gameweek": gw,
                "team_id": team_id, "position": meta_by_id[pid]["position"],
                "expected_points": _number(record.get("expected_points"), "expected_points"),
                "expected_minutes": _number(record.get("expected_minutes"), "expected_minutes"),
                "opponent_team_id": fixture["away_team_id"] if team_id == fixture["home_team_id"] else fixture["home_team_id"],
                "kickoff_time": fixture["kickoff_time"],
            }

        for pid in player_ids:
            team_id = meta_by_id[pid]["team_id"]
            expected_fixture_ids = {
                fid for fid, fixture in fixture_by_id.items()
                if team_id in {fixture["home_team_id"], fixture["away_team_id"]}
            }
            actual_fixture_ids = {fid for (record_pid, fid) in records_by_key if record_pid == pid}
            missing_fixtures = expected_fixture_ids - actual_fixture_ids
            if missing_fixtures:
                raise MultiGameweekForecastError(
                    f"missing fixture forecasts for player {pid} in GW{gw}: {sorted(missing_fixtures)}"
                )

        parsed_panels.append({
            "gameweek": gw, "snapshot_id": snapshot_id,
            "fixture_forecasts": list(records_by_key.values()),
            "metadata": meta_by_id, "fixtures": fixture_by_id,
        })

    weeks = [panel["gameweek"] for panel in parsed_panels]
    if weeks != list(range(weeks[0], weeks[0] + len(weeks))):
        raise MultiGameweekForecastError("forecast panels must be consecutive and ordered")

    player_gameweek = []
    fixture_rows = []
    for panel in parsed_panels:
        gw = panel["gameweek"]
        for pid in player_ids:
            meta = panel["metadata"][pid]
            rows = [row for row in panel["fixture_forecasts"] if row["fpl_element_id"] == pid]
            player_gameweek.append({
                "fpl_element_id": pid, "gameweek": gw,
                "team_id": meta["team_id"], "position": meta["position"],
                "expected_points": round(sum(row["expected_points"] for row in rows), 6),
                "expected_minutes": round(sum(row["expected_minutes"] for row in rows), 6),
                "fixture_count": len(rows),
            })
            fixture_rows.extend(rows)

    return {
        "contract_version": "1.0.0",
        "forecast_bundle_id": payload["forecast_bundle_id"],
        "forecast_snapshot_id": payload["forecast_bundle_id"],
        "season": payload["season"],
        "provider": dict(provider),
        "provider_source_id": source_id,
        "model_version": payload["model_version"],
        "decision_as_of_utc": as_of.isoformat(),
        "horizon_gameweeks": weeks,
        "horizon_size": len(weeks),
        "source_snapshot_ids": [panel["snapshot_id"] for panel in parsed_panels],
        "fixture_forecasts": fixture_rows,
        "player_gameweek_forecasts": player_gameweek,
        "forecast_coverage": {
            "required_player_count": len(player_ids),
            "complete_player_gameweek_rows": len(player_gameweek),
            "fixture_forecast_rows": len(fixture_rows),
            "blank_gameweeks_inferred_from_schedule": [
                {"fpl_element_id": row["fpl_element_id"], "gameweek": row["gameweek"]}
                for row in player_gameweek if row["fixture_count"] == 0
            ],
        },
        "limitations": [
            "Only explicit player-fixture forecasts are accepted; one-Gameweek values are never extrapolated.",
            "Each target Gameweek retains its own immutable provider snapshot ID under one bundle ID.",
            "Blank Gameweeks contribute zero only where the supplied fixture schedule confirms no club fixture.",
            "This contract does not itself validate forecast accuracy or make a recommendation release-eligible.",
        ],
    }
