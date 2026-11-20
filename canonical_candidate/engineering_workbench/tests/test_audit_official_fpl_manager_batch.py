import base64
import hashlib
import json

import pytest

from audit_official_fpl_manager_batch import BatchAuditError, audit_batch


def _archive(source_type, manager=421025, gw=5):
    if source_type == "bootstrap_static":
        payload = {"events": [{"id": gw, "finished": True, "data_checked": True}]}
        url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    elif source_type == "manager_picks":
        payload = {"entry_history": {"event": gw}}
        url = f"https://fantasy.premierleague.com/api/entry/{manager}/event/{gw}/picks/"
    else:
        payload = {"elements": []}
        url = f"https://fantasy.premierleague.com/api/event/{gw}/live/"
    raw = json.dumps(payload).encode()
    return {
        "source_type": source_type, "source_url": url,
        "captured_at_utc": "2026-11-20T16:00:00Z",
        "raw_snapshot_id": f"snapshot-{source_type}",
        "raw_payload_base64": base64.b64encode(raw).decode(),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
    }


def _batch():
    archives = [_archive(kind) for kind in ("bootstrap_static", "manager_picks", "event_live")]
    record = {
        "manager_team_id": 421025, "target_gameweek": 5, "event_finalized": True,
        "historical_evidence_admitted": False, "source_archives": archives,
        "reconciliation": {
            "status": "RECONCILED", "historical_evidence_admitted": False,
            "automatic_substitutions": [{"player_in_id": 110, "player_out_id": 497}],
            "official_transfer_cost": 4,
        },
    }
    return {
        "batch_contract_version": "0.1.0", "manager_team_id": 421025,
        "requested_gameweeks": [5], "reconciled_count": 1, "excluded_count": 0,
        "reconciled_gameweeks": [5], "excluded_gameweeks": [],
        "gameweeks_with_automatic_substitutions": [5], "gameweeks_with_transfer_hits": [5],
        "historical_evidence_admitted": False,
        "results": [{"gameweek": 5, "status": "RECONCILED", "result": record}],
    }


def test_audits_archives_and_reconciliation_coverage():
    result = audit_batch(_batch())
    assert result["status"] == "PASSED"
    assert result["gameweeks_with_automatic_substitutions"] == [5]
    assert result["gameweeks_with_transfer_hits"] == [5]
    assert len(result["events"][0]["archives"]) == 3
    assert result["historical_evidence_admitted"] is False


def test_rejects_raw_archive_hash_mismatch():
    batch = _batch()
    batch["results"][0]["result"]["source_archives"][0]["raw_sha256"] = "0" * 64
    with pytest.raises(BatchAuditError, match="SHA-256 mismatch"):
        audit_batch(batch)


def test_rejects_inconsistent_batch_summary():
    batch = _batch()
    batch["gameweeks_with_transfer_hits"] = []
    with pytest.raises(BatchAuditError, match="transfer-hit Gameweek summary"):
        audit_batch(batch)


def _decision_archive(source_type, manager=421025, gw=5):
    if source_type == "provider_forecast":
        payload = {"provider": "example", "gameweek": gw, "rows": []}
        url = "https://provider.example/forecast/gw5"
    elif source_type == "player_metadata":
        payload = {"elements": []}
        url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    else:
        payload = {"entry_history": {"event": gw}, "picks": []}
        url = f"https://fantasy.premierleague.com/api/entry/{manager}/event/{gw}/picks/"
    raw = json.dumps(payload).encode()
    archive = {
        "source_type": source_type,
        "source_url": url,
        "captured_at_utc": "2026-10-01T09:30:00Z",
        "raw_snapshot_id": f"decision-{source_type}-{gw}",
        "raw_payload_base64": base64.b64encode(raw).decode(),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
    }
    if source_type == "provider_forecast":
        archive["generated_at_utc"] = "2026-10-01T09:00:00Z"
    return archive


def test_audits_decision_archives_separately_from_postdeadline_scoring_archives():
    batch = _batch()
    sources = [
        _decision_archive(kind)
        for kind in ("provider_forecast", "player_metadata", "manager_deadline_state")
    ]
    result = audit_batch(batch, {"5": {"sources": sources}})
    audited = result["events"][0]["decision_sources"]
    assert {row["source_type"] for row in audited} == {
        "provider_forecast", "player_metadata", "manager_deadline_state"
    }
    assert all(row["captured_at_utc"] == "2026-10-01T09:30:00Z" for row in audited)


def test_rejects_decision_archive_hash_mismatch():
    batch = _batch()
    sources = [
        _decision_archive(kind)
        for kind in ("provider_forecast", "player_metadata", "manager_deadline_state")
    ]
    sources[0]["raw_sha256"] = "0" * 64
    with pytest.raises(BatchAuditError, match="SHA-256 mismatch"):
        audit_batch(batch, {"5": {"sources": sources}})


def test_rejects_incomplete_decision_archive_set():
    batch = _batch()
    sources = [_decision_archive("provider_forecast")]
    with pytest.raises(BatchAuditError, match="all three unique source archives"):
        audit_batch(batch, {"5": {"sources": sources}})
