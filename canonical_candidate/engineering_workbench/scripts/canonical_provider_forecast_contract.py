#!/usr/bin/env python3
"""Canonical, provider-neutral contract for external FPL benchmark forecasts.

This boundary preserves source identity, timing, grain and missingness. It
never converts provider outputs, invents forecasts, or aggregates fixtures.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
import re
from typing import Any, Mapping

CONTRACT_VERSION = "1.0.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_GRAINS = {"player_gameweek", "player_fixture"}


class ForecastContractError(ValueError):
    """Raised when a provider snapshot cannot be safely normalized."""


def _utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ForecastContractError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ForecastContractError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ForecastContractError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _finite(value: Any, field: str, *, minimum: float | None = None,
            maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ForecastContractError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ForecastContractError(f"{field} must be finite")
    if minimum is not None and result < minimum:
        raise ForecastContractError(f"{field} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise ForecastContractError(f"{field} must be <= {maximum}")
    return result


def normalize_provider_snapshot(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one immutable external-provider snapshot.

    Snapshots without a disclosed provider-generation timestamp are retained
    as diagnostic-only and are never marked deadline-eligible.
    """
    if not isinstance(payload, Mapping):
        raise ForecastContractError("snapshot must be an object")

    required = ("snapshot_id", "season", "target_gameweek", "provider",
                "timing", "source", "grain", "records", "coverage")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ForecastContractError("missing snapshot fields: " + ", ".join(missing))

    for key in ("snapshot_id", "season"):
        if not isinstance(payload[key], str) or not payload[key].strip():
            raise ForecastContractError(f"{key} must be a non-empty string")
    gw = payload["target_gameweek"]
    if isinstance(gw, bool) or not isinstance(gw, int) or gw < 1:
        raise ForecastContractError("target_gameweek must be a positive integer")

    provider = payload["provider"]
    if not isinstance(provider, Mapping):
        raise ForecastContractError("provider must be an object")
    for key in ("name", "product", "variant"):
        if not isinstance(provider.get(key), str) or not provider[key].strip():
            raise ForecastContractError(f"provider.{key} must be explicit and non-empty")
    if provider["name"].strip().lower() == "fpl lucho" and "served" in provider["variant"].lower():
        # Preserve exact product identity; served xP must not be silently relabelled Odds xP.
        pass

    timing = payload["timing"]
    if not isinstance(timing, Mapping):
        raise ForecastContractError("timing must be an object")
    deadline = _utc(timing.get("deadline_utc"), "timing.deadline_utc")
    captured = _utc(timing.get("captured_at_utc"), "timing.captured_at_utc")
    if captured >= deadline:
        raise ForecastContractError("snapshot capture must be strictly before deadline")
    generated_raw = timing.get("generated_at_utc")
    generated = _utc(generated_raw, "timing.generated_at_utc") if generated_raw else None
    if generated is not None and generated >= deadline:
        raise ForecastContractError("provider generation timestamp is at or after deadline")
    pit_status = "VERIFIED_PRE_DEADLINE" if generated is not None else "UNVERIFIED_PROVIDER_GENERATION_TIME"
    eligible = generated is not None

    source = payload["source"]
    if not isinstance(source, Mapping):
        raise ForecastContractError("source must be an object")
    if not isinstance(source.get("url"), str) or not source["url"].strip():
        raise ForecastContractError("source.url must be non-empty")
    raw_hash = source.get("raw_sha256")
    if not isinstance(raw_hash, str) or not _SHA256.fullmatch(raw_hash.lower()):
        raise ForecastContractError("source.raw_sha256 must be a 64-character SHA-256")
    if not isinstance(source.get("raw_snapshot_id"), str) or not source["raw_snapshot_id"].strip():
        raise ForecastContractError("source.raw_snapshot_id must be non-empty")

    grain = payload["grain"]
    if grain not in _ALLOWED_GRAINS:
        raise ForecastContractError("grain must be player_gameweek or player_fixture")
    records = payload["records"]
    if not isinstance(records, list) or not records:
        raise ForecastContractError("records must be a non-empty list")
    seen: set[tuple[int, int | None]] = set()
    normalized_records = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ForecastContractError(f"records[{index}] must be an object")
        player_id = record.get("fpl_element_id")
        if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id < 1:
            raise ForecastContractError(f"records[{index}].fpl_element_id must be a positive integer")
        fixture_id = record.get("fixture_id")
        if grain == "player_fixture":
            if isinstance(fixture_id, bool) or not isinstance(fixture_id, int) or fixture_id < 1:
                raise ForecastContractError(f"records[{index}].fixture_id is required for player_fixture grain")
        elif fixture_id is not None:
            raise ForecastContractError("player_gameweek records must not carry fixture_id")
        key = (player_id, fixture_id)
        if key in seen:
            raise ForecastContractError(f"duplicate forecast key: {key}")
        seen.add(key)
        item = {
            "fpl_element_id": player_id,
            "expected_points": _finite(record.get("expected_points"), f"records[{index}].expected_points"),
        }
        if fixture_id is not None:
            item["fixture_id"] = fixture_id
        for field in ("expected_minutes", "appearance_probability", "points_variance",
                      "q10", "q50", "q90"):
            if field in record and record[field] is not None:
                minimum = 0 if field in {"expected_minutes", "points_variance"} else None
                maximum = 1 if field == "appearance_probability" else None
                item[field] = _finite(record[field], f"records[{index}].{field}",
                                      minimum=minimum, maximum=maximum)
        normalized_records.append(item)

    coverage = payload["coverage"]
    if not isinstance(coverage, Mapping):
        raise ForecastContractError("coverage must be an object")
    row_count = coverage.get("row_count")
    if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count != len(records):
        raise ForecastContractError("coverage.row_count must equal the raw record count")
    expected_universe = coverage.get("expected_player_universe")
    if expected_universe is not None and (
        isinstance(expected_universe, bool) or not isinstance(expected_universe, int) or expected_universe < 1
    ):
        raise ForecastContractError("coverage.expected_player_universe must be a positive integer")
    mapped = coverage.get("identity_mapped_count")
    if mapped is not None and (
        isinstance(mapped, bool) or not isinstance(mapped, int) or not 0 <= mapped <= row_count
    ):
        raise ForecastContractError("coverage.identity_mapped_count must be between zero and row_count")

    return {
        "contract_version": CONTRACT_VERSION,
        "snapshot_id": payload["snapshot_id"],
        "season": payload["season"],
        "target_gameweek": gw,
        "provider": {
            "name": provider["name"].strip(),
            "product": provider["product"].strip(),
            "variant": provider["variant"].strip(),
            "version": provider.get("version"),
        },
        "timing": {
            "generated_at_utc": generated.isoformat() if generated else None,
            "captured_at_utc": captured.isoformat(),
            "deadline_utc": deadline.isoformat(),
            "point_in_time_status": pit_status,
        },
        "source": {
            "url": source["url"],
            "raw_snapshot_id": source["raw_snapshot_id"],
            "raw_sha256": raw_hash.lower(),
        },
        "grain": grain,
        "records": normalized_records,
        "coverage": dict(coverage),
        "decision_eligible": eligible,
        "eligibility_reason": (
            "PROVIDER_GENERATED_AND_CAPTURED_BEFORE_DEADLINE"
            if eligible else "PROVIDER_GENERATION_TIME_NOT_DISCLOSED"
        ),
    }
