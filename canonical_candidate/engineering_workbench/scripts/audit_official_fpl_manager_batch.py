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


def _audit_archives(record: dict[str, Any], manager_team_id: int, gameweek: int,
                    decision_sources_out: list[dict[str, Any]]) -> list[dict[str, Any]]:
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

    # Decision-input archives are distinct from post-deadline scoring archives.
    # Each must carry its own raw bytes and exact point-in-time provenance.
    decision_archives = record.get("decision_source_archives", [])
    _require(isinstance(decision_archives, list),
             f"GW{gameweek}: decision_source_archives must be a list")
    allowed_decision_types = {
        "provider_forecast", "player_metadata", "manager_deadline_state"
    }
    seen_decision_types = set()
    for archive in decision_archives:
        _require(isinstance(archive, dict),
                 f"GW{gameweek}: malformed decision evidence archive")
        source_type = archive.get("source_type")
        _require(source_type in allowed_decision_types and source_type not in seen_decision_types,
                 f"GW{gameweek}: unsupported or duplicate decision evidence archive type")
        seen_decision_types.add(source_type)
        raw_b64 = archive.get("raw_payload_base64")
        _require(isinstance(raw_b64, str) and raw_b64,
                 f"GW{gameweek}/{source_type}: raw payload missing")
        try:
            raw = base64.b64decode(raw_b64, validate=True)
            payload = json.loads(raw)
        except Exception as exc:
            raise BatchAuditError(
                f"GW{gameweek}/{source_type}: invalid base64 or JSON payload"
            ) from exc
        _require(isinstance(payload, (dict, list)),
                 f"GW{gameweek}/{source_type}: payload must be a JSON object or array")
        digest = hashlib.sha256(raw).hexdigest()
        _require(digest == archive.get("raw_sha256"),
                 f"GW{gameweek}/{source_type}: SHA-256 mismatch")
        captured = archive.get("captured_at_utc")
        try:
            parsed = datetime.fromisoformat(captured.replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise BatchAuditError(
                f"GW{gameweek}/{source_type}: invalid capture timestamp"
            ) from exc
        _require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
                 f"GW{gameweek}/{source_type}: capture timestamp must be timezone-aware")
        url = archive.get("source_url")
        _require(isinstance(url, str) and url.startswith("https://"),
                 f"GW{gameweek}/{source_type}: HTTPS source URL missing")
        snapshot_id = archive.get("raw_snapshot_id")
        _require(isinstance(snapshot_id, str) and snapshot_id,
                 f"GW{gameweek}/{source_type}: snapshot ID missing")
        if source_type == "player_metadata":
            _require(url.endswith("/bootstrap-static/"),
                     f"GW{gameweek}: player metadata source URL mismatch")
        elif source_type == "manager_deadline_state":
            _require(url.endswith(f"/entry/{manager_team_id}/event/{gameweek}/picks/"),
                     f"GW{gameweek}: manager deadline-state source URL mismatch")
            _require(payload.get("entry_history", {}).get("event") == gameweek,
                     f"GW{gameweek}: manager deadline-state payload Gameweek mismatch")
        generated = archive.get("generated_at_utc")
        if source_type == "provider_forecast":
            try:
                generated_time = datetime.fromisoformat(generated.replace("Z", "+00:00"))
            except (TypeError, ValueError) as exc:
                raise BatchAuditError(
                    f"GW{gameweek}: provider forecast generation timestamp missing or invalid"
                ) from exc
            _require(generated_time.tzinfo is not None and generated_time.utcoffset() is not None,
                     f"GW{gameweek}: provider generation timestamp must be timezone-aware")
        decision_sources_out.append({
            "source_type": source_type,
            "raw_snapshot_id": snapshot_id,
            "raw_sha256": digest,
            "captured_at_utc": captured,
            "source_url": url,
            "generated_at_utc": generated,
            "bytes": len(raw),
        })
    _require(not decision_archives or seen_decision_types == allowed_decision_types,
             f"GW{gameweek}: decision evidence archive set must contain all three required sources")
    return audited


def audit_batch(batch: dict[str, Any],
                decision_manifests: dict[str, Any] | None = None) -> dict[str, Any]:
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

    manifests = decision_manifests or {}
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
                audited_events.append({"gameweek": gw, "status": "EXCLUDED", "archives": [], "decision_sources": []})
                continue
            _require(record.get("historical_evidence_admitted") is False,
                     f"GW{gw}: diagnostic evidence admission must remain false")
        decision_sources = []
        manifest = manifests.get(str(gw), manifests.get(gw))
        record_for_audit = record
        if manifest is not None:
            _require(isinstance(manifest, dict),
                     f"GW{gw}: decision evidence manifest must be an object")
            source_rows = manifest.get("sources")
            _require(isinstance(source_rows, list)
                     and len(source_rows) == 3
                     and {source.get("source_type") for source in source_rows
                          if isinstance(source, dict)} == {
                              "provider_forecast", "player_metadata", "manager_deadline_state"
                          },
                     f"GW{gw}: decision manifest must contain all three unique source archives")
            record_for_audit = dict(record)
            record_for_audit["decision_source_archives"] = source_rows
        archives = _audit_archives(record_for_audit, manager_id, gw, decision_sources)
        audited_events.append({
            "gameweek": gw, "status": status, "archives": archives,
            "decision_sources": decision_sources,
        })

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
    parser.add_argument("--decision-manifests", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    batch = json.loads(args.batch.read_text(encoding="utf-8"))
    manifests = (json.loads(args.decision_manifests.read_text(encoding="utf-8"))
                 if args.decision_manifests else None)
    audit = audit_batch(batch, manifests)
    args.output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "
", encoding="utf-8")
    print(json.dumps({key: value for key, value in audit.items() if key != "events"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
