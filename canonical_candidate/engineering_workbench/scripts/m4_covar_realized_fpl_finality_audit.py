#!/usr/bin/env python3
"""Reconcile retrospective FPL player-GW history against official event-live totals.

This is a final-scoring audit, not a point-in-time reconstruction. It compares
fixture-history aggregates with the official event/{event_id}/live endpoint and
never fills missing history rows with zero.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence


class RealizedFplFinalityAuditError(ValueError):
    """Official finality evidence is incomplete or inconsistent."""


COMPARE_FIELDS = (
    "minutes", "total_points", "goals_scored", "assists", "clean_sheets",
    "goals_conceded", "own_goals", "penalties_saved", "penalties_missed",
    "yellow_cards", "red_cards", "saves", "bonus", "bps",
)
_SHA256 = set("0123456789abcdef")


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise RealizedFplFinalityAuditError(f"{label} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RealizedFplFinalityAuditError(f"{label} must be an integer") from exc
    if str(value).strip() not in (str(parsed), f"{parsed}.0"):
        raise RealizedFplFinalityAuditError(f"{label} must be an integer")
    return parsed


def audit_player_gameweek_finality(
    player_gameweek_rows: Sequence[Mapping[str, Any]],
    event_live_payload: Mapping[str, Any],
    *,
    season: str,
    event_id: int,
    source_provenance: Mapping[str, Any],
    raw_source_bytes: bytes,
) -> dict[str, Any]:
    if not isinstance(player_gameweek_rows, Sequence) or not player_gameweek_rows:
        raise RealizedFplFinalityAuditError("player_gameweek_rows must be non-empty")
    if not isinstance(event_live_payload, Mapping):
        raise RealizedFplFinalityAuditError("event_live_payload must be an object")
    if not isinstance(season, str) or not season.strip():
        raise RealizedFplFinalityAuditError("season must be explicit")
    event = _integer(event_id, "event_id")
    if event < 1:
        raise RealizedFplFinalityAuditError("event_id must be positive")
    if not isinstance(source_provenance, Mapping):
        raise RealizedFplFinalityAuditError("source_provenance must be an object")
    required_provenance = ("source_url", "captured_at_utc", "raw_sha256")
    if any(not isinstance(source_provenance.get(k), str) or not source_provenance[k].strip()
           for k in required_provenance):
        raise RealizedFplFinalityAuditError("source provenance requires URL, capture timestamp and SHA-256")
    if source_provenance["source_url"].rstrip("/") != (
        f"https://fantasy.premierleague.com/api/event/{event}/live"
    ):
        raise RealizedFplFinalityAuditError("source URL must be the official requested event-live endpoint")
    digest = source_provenance["raw_sha256"].lower()
    if len(digest) != 64 or any(ch not in _SHA256 for ch in digest):
        raise RealizedFplFinalityAuditError("raw_sha256 must be a 64-character hexadecimal SHA-256")
    if not isinstance(raw_source_bytes, bytes) or not raw_source_bytes:
        raise RealizedFplFinalityAuditError("raw_source_bytes must contain the exact captured response bytes")
    actual_digest = hashlib.sha256(raw_source_bytes).hexdigest()
    if actual_digest != digest:
        raise RealizedFplFinalityAuditError("event-live raw source bytes do not match source provenance SHA-256")
    try:
        parsed_raw = json.loads(raw_source_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RealizedFplFinalityAuditError("event-live raw source bytes are not valid JSON") from exc
    if parsed_raw != event_live_payload:
        raise RealizedFplFinalityAuditError("parsed event-live payload does not match exact captured response bytes")
    try:
        from datetime import datetime
        captured = datetime.fromisoformat(source_provenance["captured_at_utc"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise RealizedFplFinalityAuditError("captured_at_utc must be ISO-8601") from exc
    if captured.tzinfo is None:
        raise RealizedFplFinalityAuditError("captured_at_utc must include a timezone")

    live_rows = event_live_payload.get("elements")
    if not isinstance(live_rows, list) or not live_rows:
        raise RealizedFplFinalityAuditError("event-live elements must be a non-empty list")
    live_by_id = {}
    for index, item in enumerate(live_rows):
        if not isinstance(item, Mapping):
            raise RealizedFplFinalityAuditError(f"event-live elements[{index}] must be an object")
        pid = _integer(item.get("id"), f"event-live elements[{index}].id")
        if pid in live_by_id:
            raise RealizedFplFinalityAuditError(f"duplicate event-live player ID {pid}")
        stats = item.get("stats")
        if not isinstance(stats, Mapping):
            raise RealizedFplFinalityAuditError(f"event-live player {pid} stats must be an object")
        live_by_id[pid] = stats

    seen = set()
    mismatches = []
    compared = 0
    for index, row in enumerate(player_gameweek_rows):
        if not isinstance(row, Mapping):
            raise RealizedFplFinalityAuditError(f"player_gameweek_rows[{index}] must be an object")
        if row.get("season") != season or _integer(row.get("gameweek"), "row.gameweek") != event:
            raise RealizedFplFinalityAuditError("all realized rows must match requested season and event")
        pid = _integer(row.get("fpl_element_id"), "row.fpl_element_id")
        if pid in seen:
            raise RealizedFplFinalityAuditError(f"duplicate player-Gameweek key {(season, pid, event)}")
        seen.add(pid)
        if pid not in live_by_id:
            raise RealizedFplFinalityAuditError(f"player {pid} missing from official event-live response")
        live = live_by_id[pid]
        for field in COMPARE_FIELDS:
            if field not in live or live[field] is None:
                raise RealizedFplFinalityAuditError(f"event-live player {pid} missing required stat {field}")
            historical = _integer(row.get(field), f"history player {pid}.{field}")
            official = _integer(live[field], f"event-live player {pid}.{field}")
            compared += 1
            if historical != official:
                mismatches.append({
                    "fpl_element_id": pid, "field": field,
                    "history_value": historical, "official_event_live_value": official,
                    "delta": historical - official,
                })

    return {
        "schema_version": "1.0.0",
        "season": season,
        "event_id": event,
        "status": "PASS_EXACT_MATCH" if not mismatches else "FAIL_MISMATCH",
        "finality_reconciled": not mismatches,
        "point_in_time_status": "NOT_VERIFIED_RETROSPECTIVE_FINAL_SCORING_AUDIT",
        "player_gameweek_rows_compared": len(seen),
        "official_event_live_players": len(live_by_id),
        "stat_values_compared": compared,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:100],
        "source_provenance": {
            "source_url": source_provenance["source_url"],
            "captured_at_utc": source_provenance["captured_at_utc"],
            "raw_sha256": digest,
        },
        "missing_history_rows_zero_filled": 0,
        "limitations": [
            "This confirms agreement with the captured official event-live scoring response only for supplied player-Gameweek rows.",
            "Players absent from the historical panel are not synthesized or assumed to have zero points.",
            "A retrospective event-live response does not establish what was available at the original Gameweek deadline.",
            "Exact player-Gameweek reconciliation does not validate fixture-level joint dependence or a forecast model.",
        ],
    }
