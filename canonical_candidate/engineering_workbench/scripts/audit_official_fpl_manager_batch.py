#!/usr/bin/env python3
"""Verify integrity and coverage of a multi-Gameweek official FPL reconciliation batch."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


class BatchAuditError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BatchAuditError(message)


def _audit_archives(record: dict[str, Any], manager_team_id: int, gameweek: int) -> list[dict[str, Any]]:
    archives = record.get("source_archives")
    _require(isinstance(archives, list), f"GW{gameweek}: source_archives must be a list")
    by_type = {row.get("source_type"): row for row in archives if isinstance(row, dict)}
    expected = {"bootstrap_static", "manager_picks", "event_live"}
    _require(set(by_type) == expected and len(archives) == 3,
             f"GW{gameweek}: expected exactly three unique official source archives")
    audited = []
    for source_type in sorted(expected):
        archive = by_type[source_type]
        raw_b64 = archive.get("raw_payload_base64")
        _require(isinstance(raw_b64, str) and raw_b64, f"GW{gameweek}/{source_type}: raw payload missing")
        try:
            raw = base64.b64decode(raw_b64, validate=True)
        except Exception as exc:
            raise BatchAuditError(f"GW{gameweek}/{source_type}: invalid base64 payload") from exc
        digest = hashlib.sha256(raw).hexdigest()
        _require(digest == archive.get("raw_sha256"),
                 f"GW{gameweek}/{source_type}: SHA-256 mismatch")
        try:
            payload = json.loads(raw)
        except Exception as exc:
            raise BatchAuditError(f"GW{gameweek}/{source_type}: archived payload is not valid JSON") from exc
        _require(isinstance(payload, dict), f"GW{gameweek}/{source_type}: archived payload must be an object")
        captured = archive.get("captured_at_utc")
        _require(isinstance(captured, str), f"GW{gameweek}/{source_type}: capture timestamp missing")
        try:
            parsed = datetime.fromisoformat(captured.replace("Z", "+00:00"))
        except ValueError as exc:
            raise BatchAuditError(f"GW{gameweek}/{source_type}: invalid capture timestamp") from exc
        _require(parsed.tzinfo is not None, f"GW{gameweek}/{source_type}: capture timestamp must be timezone-aware")
        url = archive.get("source_url", "")
        if source_type == "manager_picks":
            _require(url.endswith(f"/entry/{manager_team_id}/event/{gameweek}/picks/"),
                     f"GW{gameweek}: manager picks archive URL does not match manager/event")
            _require(payload.get("entry_history", {}).get("event") == gameweek,
                     f"GW{gameweek}: archived manager picks event mismatch")
        elif source_type == "event_live":
            _require(url.endswith(f"/event/{gameweek}/live/"),
                     f"GW{gameweek}: event-live archive URL mismatch")
            _require(isinstance(payload.get("elements"), list),
                     f"GW{gameweek}: event-live archive has no elements")
        else:
            _require(url.endswith("/bootstrap-static/"),
                     f"GW{gameweek}: bootstrap archive URL mismatch")
            events = payload.get("events")
            matches = [row for row in events or [] if isinstance(row, dict) and row.get("id") == gameweek]
            _require(len(matches) == 1 and matches[0].get("finished") is True
                     and matches[0].get("data_checked") is True,
                     f"GW{gameweek}: bootstrap does not confirm finalized event")
        _require(archive.get("raw_snapshot_id"), f"GW{gameweek}/{source_type}: snapshot ID missing")
        audited.append({
            "source_type": source_type,
            "raw_snapshot_id": archive["raw_snapshot_id"],
            "raw_sha256": digest,
            "captured_at_utc": captured,
            "source_url": url,
            "bytes": len(raw),
        })

    # Optional provider archives are decision evidence, not official scoring
    # sources. Audit their bytes independently and expose exact references.
    decision_archives = record.get("decision_source_archives", [])
    _require(isinstance(decision_archives, list),
             f"GW{gameweek}: decision_source_archives must be a list")
    for archive in decision_archives:
        _require(isinstance(archive, dict)
                 and archive.get("source_type") == "provider_forecast",
                 f"GW{gameweek}: unsupported decision evidence archive type")
        raw_b64 = archive.get("raw_payload_base64")
        _require(isinstance(raw_b64, str) and raw_b64,
                 f"GW{gameweek}/provider_forecast: raw payload missing")
        try:
            raw = base64.b64decode(raw_b64, validate=True)
            payload = json.loads(raw)
        except Exception as exc:
            raise BatchAuditError(
                f"GW{gameweek}/provider_forecast: invalid base64 or JSON payload"
            ) from exc
        _require(isinstance(payload, (dict, list)),
                 f"GW{gameweek}/provider_forecast: payload must be JSON")
        digest = hashlib.sha256(raw).hexdigest()
        _require(digest == archive.get("raw_sha256"),
                 f"GW{gameweek}/provider_forecast: SHA-256 mismatch")
        captured = archive.get("captured_at_utc")
        try:
            parsed = datetime.fromisoformat(captured.replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise BatchAuditError(
                f"GW{gameweek}/provider_forecast: invalid capture timestamp"
            ) from exc
        _require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
                 f"GW{gameweek}/provider_forecast: capture timestamp must be timezone-aware")
        url = archive.get("source_url")
        _require(isinstance(url, str) and url.startswith("https://"),
                 f"GW{gameweek}/provider_forecast: HTTPS source URL missing")
        _require(isinstance(archive.get("raw_snapshot_id"), str)
                 and archive["raw_snapshot_id"],
                 f"GW{gameweek}/provider_forecast: snapshot ID missing")
        audited.append({
            "source_type": "provider_forecast",
            "raw_snapshot_id": archive["raw_snapshot_id"],
            "raw_sha256": digest,
            "captured_at_utc": captured,
            "source_url": url,
            "bytes": len(raw),
        })
    _require(len([item for item in audited
                  if item["source_type"] == "provider_forecast"]) <= 1,
             f"GW{gameweek}: duplicate provider forecast archives")
    return audited


def audit_batch(batch: dict[str, Any]) -> dict[str, Any]:
    _require(batch.get("batch_contract_version") == "0.1.0", "unsupported batch contract version")
    manager_id = batch.get("manager_team_id")
    _require(isinstance(manager_id, int) and manager_id > 0, "invalid manager_team_id")
    requested = batch.get("requested_gameweeks")
    results = batch.get("results")
    _require(isinstance(requested, list) and requested and len(set(requested)) == len(requested),
             "requested_gameweeks must be unique and non-empty")
    _require(isinstance(results, list), "batch results must be a list")
    _require([row.get("gameweek") for row in results] == requested,
             "batch results must cover requested Gameweeks in order")

    audited_events = []
    reconciled_gws, excluded_gws, autosub_gws, hit_gws = [], [], [], []
    for row in results:
        gw, status = row.get("gameweek"), row.get("status")
        _require(isinstance(gw, int) and gw > 0, "invalid result Gameweek")
        record = row.get("result") if status == "RECONCILED" else row.get("diagnostic_record")
        if status == "RECONCILED":
            _require(isinstance(record, dict), f"GW{gw}: reconciled result missing")
            _require(record.get("manager_team_id") == manager_id and record.get("target_gameweek") == gw,
                     f"GW{gw}: child record identity mismatch")
            _require(record.get("event_finalized") is True, f"GW{gw}: event not marked finalized")
            _require(record.get("historical_evidence_admitted") is False,
                     f"GW{gw}: historical evidence admission must remain false")
            reconciliation = record.get("reconciliation", {})
            _require(reconciliation.get("status") == "RECONCILED",
                     f"GW{gw}: child reconciliation status mismatch")
            _require(reconciliation.get("historical_evidence_admitted") is False,
                     f"GW{gw}: reconciliation evidence admission must remain false")
            reconciled_gws.append(gw)
            if reconciliation.get("automatic_substitutions"):
                autosub_gws.append(gw)
            if reconciliation.get("official_transfer_cost", 0) > 0:
                hit_gws.append(gw)
        else:
            _require(status == "EXCLUDED", f"GW{gw}: unknown batch status")
            excluded_gws.append(gw)
            if record is None:
                audited_events.append({"gameweek": gw, "status": "EXCLUDED", "archives": []})
                continue
            _require(record.get("historical_evidence_admitted") is False,
                     f"GW{gw}: diagnostic evidence admission must remain false")
        archives = _audit_archives(record, manager_id, gw)
        audited_events.append({"gameweek": gw, "status": status, "archives": archives})

    _require(batch.get("reconciled_count") == len(reconciled_gws), "reconciled Gameweek count mismatch")
    _require(batch.get("excluded_count") == len(excluded_gws), "excluded Gameweek count mismatch")
    _require(batch.get("reconciled_gameweeks") == reconciled_gws, "reconciled Gameweek summary mismatch")
    _require(batch.get("excluded_gameweeks") == excluded_gws, "excluded Gameweek summary mismatch")
    _require(batch.get("gameweeks_with_automatic_substitutions") == autosub_gws,
             "automatic-substitution Gameweek summary mismatch")
    _require(batch.get("gameweeks_with_transfer_hits") == hit_gws,
             "transfer-hit Gameweek summary mismatch")
    _require(batch.get("historical_evidence_admitted") is False,
             "batch historical evidence admission must remain false")
    return {
        "audit_contract_version": "0.1.0",
        "status": "PASSED",
        "manager_team_id": manager_id,
        "requested_gameweeks": requested,
        "reconciled_gameweeks": reconciled_gws,
        "excluded_gameweeks": excluded_gws,
        "gameweeks_with_automatic_substitutions": autosub_gws,
        "gameweeks_with_transfer_hits": hit_gws,
        "historical_evidence_admitted": False,
        "events": audited_events,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    batch = json.loads(args.batch.read_text(encoding="utf-8"))
    audit = audit_batch(batch)
    args.output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "
", encoding="utf-8")
    print(json.dumps({key: value for key, value in audit.items() if key != "events"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
