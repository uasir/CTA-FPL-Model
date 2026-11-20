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
        archive["provider_id"] = "fpl-cat"
        archive["provider_variant"] = "public-xp"
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


def _decision_manifest_with_attested_manager_state(batch):
    gw = 5
    squad = list(range(1, 16))
    element_types = {
        1: 1, 2: 2, 3: 2, 4: 2, 5: 2,
        6: 3, 7: 3, 8: 3, 9: 4, 10: 4, 11: 4,
        12: 1, 13: 2, 14: 3, 15: 4,
    }
    bootstrap = {
        "elements": [
            {"id": player_id, "element_type": element_type,
             "now_cost": 50, "cost_change_start": 0}
            for player_id, element_type in element_types.items()
        ],
        "events": [{"id": gw, "deadline_time": "2026-10-01T11:00:00Z"}],
    }
    gw1 = {
        "entry_history": {"event": 1},
        "picks": [
            {"element": player_id, "purchase_price": 50}
            for player_id in squad
        ],
    }
    previous = {"entry_history": {"event": 4}, "picks": []}
    history = {"chips": []}
    wrapper = {
        "source_type": "FPL_SEASON_HISTORY_RECONSTRUCTION",
        "previous_gameweek_picks": _encoded_archive(previous),
        "gw1_picks": _encoded_archive(gw1),
        "transfers": _encoded_archive([]),
        "history": _encoded_archive(history),
        "bootstrap": _encoded_archive(bootstrap),
    }
    state = {
        "squad_15": squad,
        "bank": 0.9,
        "free_transfers": 1,
        "purchase_prices": {str(player_id): 5.0 for player_id in squad},
        "selling_prices": {str(player_id): 5.0 for player_id in squad},
        "chip_state": "NONE",
        "starting_xi": list(range(1, 12)),
        "bench_order": [13, 14, 15],
        "reserve_goalkeeper_id": 12,
        "captain_id": 10,
        "vice_captain_id": 11,
        "formation": "4-3-3",
    }
    captured = "2026-10-01T09:30:00Z"
    envelope = {
        "capture_kind": "USER_ATTESTED_PREDEADLINE_MANAGER_STATE",
        "capture_method": "USER_CONFIRMED_WITH_OFFICIAL_HISTORY",
        "manager_team_id": 421025,
        "target_gameweek": gw,
        "captured_at_utc": captured,
        "source_urls": [
            "https://fantasy.premierleague.com/api/entry/421025/event/4/picks/",
            "https://fantasy.premierleague.com/api/entry/421025/event/1/picks/",
            "https://fantasy.premierleague.com/api/entry/421025/transfers/",
            "https://fantasy.premierleague.com/api/entry/421025/history/",
            "https://fantasy.premierleague.com/api/bootstrap-static/",
        ],
        "history_archive_base64": _encoded_archive(wrapper),
        "raw_manager_picks_base64": None,
        "manager_state": state,
    }
    official_picks = {
        "active_chip": None,
        "automatic_subs": [],
        "entry_history": {"event": gw, "bank": 9},
        "picks": [
            {
                "element": player_id,
                "position": player_id,
                "element_type": element_types[player_id],
                "is_captain": player_id == 10,
                "is_vice_captain": player_id == 11,
            }
            for player_id in squad
        ],
    }
    record = batch["results"][0]["result"]
    manager_archive = next(row for row in record["source_archives"]
                           if row["source_type"] == "manager_picks")
    raw_official = json.dumps(official_picks).encode()
    manager_archive["raw_payload_base64"] = base64.b64encode(raw_official).decode()
    manager_archive["raw_sha256"] = hashlib.sha256(raw_official).hexdigest()
    envelope_raw = json.dumps(envelope, sort_keys=True).encode()
    sources = [
        _decision_archive("provider_forecast"),
        _decision_archive("player_metadata"),
        {
            "source_type": "manager_deadline_state",
            "source_url": "https://fantasy.premierleague.com/entry/421025",
            "captured_at_utc": captured,
            "raw_snapshot_id": "manager-attestation-gw5",
            "raw_payload_base64": base64.b64encode(envelope_raw).decode(),
            "raw_sha256": hashlib.sha256(envelope_raw).hexdigest(),
        },
    ]
    # Keep the player-metadata archive byte-identical to the bootstrap used in the attested price chain.
    metadata_raw = base64.b64decode(wrapper["bootstrap"])
    metadata = sources[1]
    metadata["raw_payload_base64"] = base64.b64encode(metadata_raw).decode()
    metadata["raw_sha256"] = hashlib.sha256(metadata_raw).hexdigest()
    metadata["source_url"] = "https://fantasy.premierleague.com/api/bootstrap-static/"
    return {"5": {"sources": sources}}


def _encoded_archive(value):
    return base64.b64encode(json.dumps(value, sort_keys=True).encode()).decode()


def test_audits_user_attested_state_and_replays_official_purchase_prices():
    batch = _batch()
    manifests = _decision_manifest_with_attested_manager_state(batch)
    result = audit_batch(batch, manifests)
    assert result["status"] == "PASSED"
    assert len(result["events"][0]["decision_sources"]) == 3


def test_rejects_attested_lineup_that_differs_from_finalized_official_picks():
    batch = _batch()
    manifests = _decision_manifest_with_attested_manager_state(batch)
    archive = next(row for row in batch["results"][0]["result"]["source_archives"]
                   if row["source_type"] == "manager_picks")
    payload = json.loads(base64.b64decode(archive["raw_payload_base64"]))
    payload["picks"][0]["position"] = 12
    payload["picks"][11]["position"] = 1
    raw = json.dumps(payload).encode()
    archive["raw_payload_base64"] = base64.b64encode(raw).decode()
    archive["raw_sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(BatchAuditError, match="starting XI differs"):
        audit_batch(batch, manifests)


def test_rejects_manager_price_reconstruction_from_different_bootstrap_snapshot():
    batch = _batch()
    manifests = _decision_manifest_with_attested_manager_state(batch)
    metadata = next(row for row in manifests["5"]["sources"]
                    if row["source_type"] == "player_metadata")
    changed = {"elements": [{"id": 1, "now_cost": 51, "element_type": 1}]}
    raw = json.dumps(changed).encode()
    metadata["raw_payload_base64"] = base64.b64encode(raw).decode()
    metadata["raw_sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(BatchAuditError, match="bootstrap differs"):
        audit_batch(batch, manifests)
