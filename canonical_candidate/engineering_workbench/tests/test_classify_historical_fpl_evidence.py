import pytest

from classify_historical_fpl_evidence import (
    EvidenceAdmissionError,
    classify_batch,
)


def _batch(chip=None):
    record = {
        "manager_team_id": 421025,
        "target_gameweek": 5,
        "event_finalized": True,
        "historical_evidence_admitted": False,
        "active_chip": chip,
        "reconciliation": {
            "status": "RECONCILED",
            "historical_evidence_admitted": False,
        },
    }
    return {
        "manager_team_id": 421025,
        "historical_evidence_admitted": False,
        "results": [{"gameweek": 5, "status": "RECONCILED", "result": record}],
    }


def _audit_report(manifest=None):
    manifest = manifest or _manifest()
    archives = []
    for source in manifest["sources"]:
        archives.append({
            "source_type": source["source_type"],
            "raw_snapshot_id": source["raw_snapshot_id"],
            "raw_sha256": source["raw_sha256"],
            "captured_at_utc": source["captured_at_utc"],
            "source_url": source["source_url"],
            "bytes": 100,
        })
    return {
        "status": "PASSED",
        "manager_team_id": 421025,
        "events": [{"gameweek": 5, "status": "RECONCILED", "archives": [],\n                    "decision_sources": archives}],
    }


def _manifest():
    squad = list(range(1, 16))
    prices = {str(player_id): 5.0 for player_id in squad}
    return {
        "target_gameweek": 5,
        "evidence_is_point_in_time": True,
        "deadline_utc": "2026-10-01T11:00:00Z",
        "decision_as_of_utc": "2026-10-01T10:30:00Z",
        "sources": [
            {
                "source_type": "provider_forecast",
                "raw_snapshot_id": "provider-5",
                "raw_sha256": "a" * 64,
                "generated_at_utc": "2026-10-01T09:00:00Z",
                "captured_at_utc": "2026-10-01T09:30:00Z",
                "source_url": "https://provider.example/forecast/gw5",
            },
            {
                "source_type": "player_metadata",
                "raw_snapshot_id": "metadata-5",
                "raw_sha256": "b" * 64,
                "captured_at_utc": "2026-10-01T09:35:00Z",
                "source_url": "https://fantasy.premierleague.com/api/bootstrap-static/",
            },
            {
                "source_type": "manager_deadline_state",
                "raw_snapshot_id": "manager-5",
                "raw_sha256": "c" * 64,
                "captured_at_utc": "2026-10-01T09:40:00Z",
                "source_url": "https://fantasy.premierleague.com/api/entry/421025/event/5/picks/",
            },
        ],
        "manager_state": {
            "squad_15": squad,
            "bank": 0.5,
            "free_transfers": 1,
            "purchase_prices": prices,
            "selling_prices": prices,
            "chip_state": "NONE",
            "starting_xi": list(range(1, 12)),
            "bench_order": [13, 14, 15],
            "reserve_goalkeeper_id": 12,
            "captain_id": 1,
            "vice_captain_id": 2,
        },
    }


def test_reconciled_history_without_deadline_evidence_is_scoring_only():
    result = classify_batch(_batch())
    event = result["events"][0]
    assert event["classification"] == "SCORING_RECONCILIATION_ONLY"
    assert event["official_score_reconciled"] is True
    assert event["historical_evidence_admitted"] is False
    assert result["historical_evidence_admitted"] is False


def test_complete_timestamp_valid_manifest_is_decision_eligible():
    manifest = _manifest()
    result = classify_batch(_batch(), {"5": manifest}, _audit_report(manifest))
    assert result["events"][0]["classification"] == "DECISION_BACKTEST_ELIGIBLE"
    assert result["historical_evidence_admitted"] is True


def test_post_deadline_manager_capture_fails_closed():
    manifest = _manifest()
    manifest["sources"][2]["captured_at_utc"] = "2026-10-01T11:00:00Z"
    result = classify_batch(_batch(), {"5": manifest}, _audit_report())
    event = result["events"][0]
    assert event["classification"] == "SCORING_RECONCILIATION_ONLY"
    assert any("captured at/after deadline" in reason for reason in event["reasons"])


def test_missing_purchase_prices_prevents_decision_admission():
    manifest = _manifest()
    manifest["manager_state"]["purchase_prices"].pop("7")
    result = classify_batch(_batch(), {"5": manifest}, _audit_report(manifest))
    assert result["events"][0]["classification"] == "SCORING_RECONCILIATION_ONLY"
    assert any("purchase_prices" in reason for reason in result["events"][0]["reasons"])


def test_chip_gameweek_is_excluded():
    manifest = _manifest()
    result = classify_batch(_batch(chip="BENCH_BOOST"), {"5": manifest}, _audit_report(manifest))
    assert result["events"][0]["classification"] == "EXCLUDED"


def test_rejects_batch_that_claims_prior_admission():
    batch = _batch()
    batch["historical_evidence_admitted"] = True
    with pytest.raises(EvidenceAdmissionError, match="must retain"):
        classify_batch(batch)



def test_boolean_archive_attestation_without_matching_audit_report_is_not_enough():
    manifest = _manifest()
    result = classify_batch(_batch(), {"5": manifest})
    event = result["events"][0]
    assert event["classification"] == "SCORING_RECONCILIATION_ONLY"
    assert any("Independent archive audit report" in reason for reason in event["reasons"])


def test_manifest_hash_mismatch_against_audited_bytes_fails_closed():
    manifest = _manifest()
    manifest["sources"][0]["raw_sha256"] = "f" * 64
    result = classify_batch(_batch(), {"5": manifest}, _audit_report())
    event = result["events"][0]
    assert event["classification"] == "SCORING_RECONCILIATION_ONLY"
    assert any("raw_sha256 does not match" in reason for reason in event["reasons"])


def test_audit_report_manager_identity_mismatch_fails_closed():
    manifest = _manifest()
    audit = _audit_report(manifest)
    audit["manager_team_id"] = 999
    result = classify_batch(_batch(), {"5": manifest}, audit)
    assert result["events"][0]["classification"] == "SCORING_RECONCILIATION_ONLY"
