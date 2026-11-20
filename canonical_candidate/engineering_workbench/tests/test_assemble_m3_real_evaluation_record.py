import base64
import copy
import hashlib
import json

import pytest

from assemble_m3_real_evaluation_record import (
    EvaluationAssemblyError,
    assemble_evaluation_record,
)


def _archive(source_type, payload, captured, url):
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {
        "source_type": source_type,
        "source_url": url,
        "raw_snapshot_id": f"snapshot-{source_type}",
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "captured_at_utc": captured,
        "raw_payload_base64": base64.b64encode(raw).decode(),
    }


def _fixture(action="TRANSFER"):
    manager_id, gameweek = 421025, 11
    deadline = "2026-11-21T11:00:00Z"
    as_of = "2026-11-20T19:00:00Z"
    software_commit = "a" * 40
    roster = []
    for player_id in range(1, 16):
        position = ("GKP" if player_id <= 2 else "DEF" if player_id <= 7
                    else "MID" if player_id <= 12 else "FWD")
        roster.append({
            "fpl_element_id": player_id,
            "position": position,
            "team_id": (player_id - 1) // 3 + 1,
            "purchase_price": 5.0,
            "current_price": 5.0,
        })
    xi = [1, 3, 4, 5, 6, 8, 9, 10, 13, 14, 15]
    hold_plan = {
        "squad_ids": list(range(1, 16)),
        "starting_xi": xi,
        "bench_order": [7, 11, 12],
        "reserve_goalkeeper_id": 2,
        "captain_id": 15,
        "vice_captain_id": 14,
        "formation": "4-3-3",
    }
    incoming = {
        "fpl_element_id": 16,
        "position": "DEF",
        "team_id": 6,
        "purchase_price": 5.1,
        "current_price": 5.1,
    }
    if action == "TRANSFER":
        decision_body = {
            "action": "TRANSFER",
            "transfer_out_id": 7,
            "transfer_in_id": 16,
            "incoming_player": incoming,
            "transfer_hit_points": 0,
            "squad_plan": {
                **hold_plan,
                "squad_ids": [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16],
                "starting_xi": [1, 3, 4, 5, 16, 8, 9, 10, 13, 14, 15],
                "bench_order": [6, 11, 12],
            },
        }
        expected_ids = list(range(1, 17))
    else:
        decision_body = {
            "action": "HOLD",
            "transfer_out_id": None,
            "transfer_in_id": None,
            "incoming_player": None,
            "transfer_hit_points": 0,
            "squad_plan": hold_plan,
        }
        expected_ids = list(range(1, 16))
    decision_hash = hashlib.sha256(
        json.dumps(decision_body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    decision = {**decision_body, "decision_sha256": decision_hash}

    provider = {
        "name": "FPL Cat",
        "product": "Expected Points",
        "variant": "api/v1",
    }
    predeadline_archives = [
        _archive("provider", {"provider": provider}, as_of, "https://provider.example/forecast"),
        _archive("player_metadata", {"players": 15}, as_of, "https://fpl.example/bootstrap"),
        _archive("manager_state", {"manager": manager_id}, as_of, f"https://fpl.example/entry/{manager_id}"),
    ]
    candidate = {
        "evidence_class": "REAL_CANDIDATE",
        "manager_team_id": manager_id,
        "target_gameweek": gameweek,
        "deadline_utc": deadline,
        "as_of_utc": as_of,
        "season": "2026-27",
        "provider_snapshot_id": "provider-gw11",
        "provider_identity": provider,
        "decision_contract_version": "1.0.0",
        "software_commit": software_commit,
        "source_archives": predeadline_archives,
        "manager_state": {
            "squad_snapshot": roster,
            "bank": 0.9,
            "free_transfers": 1,
            "personal_risk_profile": "aggressive",
            "formation": "4-3-3",
            "chip": "NONE",
            "hold_plan": hold_plan,
        },
        "frozen_decision": decision,
    }
    recommendation = {
        "manager_team_id": manager_id,
        "target_gameweek": gameweek,
        "release_eligible": False,
        "frozen_decision": decision,
        "evaluation_candidate": candidate,
    }

    bootstrap = {
        "events": [{"id": gameweek, "finished": True, "data_checked": True}],
    }
    live_elements = [
        {"id": player_id, "stats": {
            "total_points": player_id % 8,
            "minutes": 90,
            "yellow_cards": 0,
            "red_cards": 0,
        }}
        for player_id in range(1, 18)
    ]
    official_archives = [
        _archive("bootstrap_static", bootstrap, "2026-11-22T12:00:00Z",
                 "https://fantasy.premierleague.com/api/bootstrap-static/"),
        _archive("manager_picks", {"entry_history": {"event": gameweek}},
                 "2026-11-22T12:00:01Z",
                 f"https://fantasy.premierleague.com/api/entry/{manager_id}/event/{gameweek}/picks/"),
        _archive("event_live", {"elements": live_elements}, "2026-11-22T12:00:02Z",
                 f"https://fantasy.premierleague.com/api/event/{gameweek}/live/"),
    ]
    source_record = {
        "manager_team_id": manager_id,
        "target_gameweek": gameweek,
        "event_finalized": True,
        "active_chip": None,
        "historical_evidence_admitted": False,
        "source_archives": official_archives,
    }
    batch = {
        "manager_team_id": manager_id,
        "historical_evidence_admitted": False,
        "results": [{"gameweek": gameweek, "status": "RECONCILED", "result": source_record}],
    }
    audit = {
        "status": "PASSED",
        "manager_team_id": manager_id,
        "historical_evidence_admitted": False,
        "events": [{
            "gameweek": gameweek,
            "status": "RECONCILED",
            "predeadline_recommendation": {
                "status": "VERIFIED",
                "action": action,
                "decision_sha256": decision_hash,
                "execution_match": "RECOMMENDATION_MATCHED",
            },
            "predeadline_replay": {
                "status": "VERIFIED",
                "replay_type": "DETERMINISTIC_RAW_AND_CANONICAL_INPUT_REEXECUTION",
                "software_commit": software_commit,
                "decision_sha256": decision_hash,
                "raw_archive_hashes_verified": True,
            },
            "archives": [{
                "source_type": row["source_type"],
                "raw_snapshot_id": row["raw_snapshot_id"],
                "raw_sha256": row["raw_sha256"],
                "captured_at_utc": row["captured_at_utc"],
                "source_url": row["source_url"],
            } for row in official_archives],
        }],
    }
    admission = {
        "manager_team_id": manager_id,
        "events": [{
            "gameweek": gameweek,
            "classification": "DECISION_BACKTEST_ELIGIBLE",
            "historical_evidence_admitted": True,
            "official_score_reconciled": True,
        }],
    }
    return recommendation, batch, audit, admission, expected_ids


def test_assembles_transfer_record_with_16_player_decision_cohort():
    recommendation, batch, audit, admission, expected_ids = _fixture()
    record = assemble_evaluation_record(recommendation, batch, audit, admission)
    assert record["evidence_class"] == "REAL_CANDIDATE"
    assert {row["fpl_element_id"] for row in record["realised_player_points"]} == set(expected_ids)
    assert len(record["realised_player_points"]) == 16
    assert record["source_archives"][-1]["source_type"] == "realised_points"
    assert record["source_archives"][-1]["finalization_basis"] == (
        "OFFICIAL_BOOTSTRAP_FINISHED_AND_DATA_CHECKED_OBSERVED"
    )
    assert record["assembly_provenance"]["frozen_replay_status"] == "VERIFIED"


def test_assembles_hold_record_with_15_player_cohort():
    recommendation, batch, audit, admission, expected_ids = _fixture("HOLD")
    record = assemble_evaluation_record(recommendation, batch, audit, admission)
    assert len(record["realised_player_points"]) == 15
    assert {row["fpl_element_id"] for row in record["realised_player_points"]} == set(expected_ids)


def test_rejects_event_without_admission():
    recommendation, batch, audit, admission, _ = _fixture()
    admission["events"][0]["classification"] = "SCORING_RECONCILIATION_ONLY"
    admission["events"][0]["historical_evidence_admitted"] = False
    with pytest.raises(EvaluationAssemblyError, match="DECISION_BACKTEST_ELIGIBLE"):
        assemble_evaluation_record(recommendation, batch, audit, admission)


def test_rejects_missing_replay_verification():
    recommendation, batch, audit, admission, _ = _fixture()
    audit["events"][0]["predeadline_replay"]["status"] = "MISSING"
    with pytest.raises(EvaluationAssemblyError, match="replay"):
        assemble_evaluation_record(recommendation, batch, audit, admission)


def test_rejects_decision_hash_mismatch():
    recommendation, batch, audit, admission, _ = _fixture()
    audit["events"][0]["predeadline_recommendation"]["decision_sha256"] = "f" * 64
    with pytest.raises(EvaluationAssemblyError, match="exact frozen decision"):
        assemble_evaluation_record(recommendation, batch, audit, admission)


def test_rejects_tampered_event_live_archive():
    recommendation, batch, audit, admission, _ = _fixture()
    batch["results"][0]["result"]["source_archives"][2]["raw_payload_base64"] = (
        base64.b64encode(b'{"elements": []}').decode()
    )
    with pytest.raises(EvaluationAssemblyError, match="SHA-256 mismatch"):
        assemble_evaluation_record(recommendation, batch, audit, admission)


def test_rejects_missing_incoming_player_points():
    recommendation, batch, audit, admission, _ = _fixture()
    archive = batch["results"][0]["result"]["source_archives"][2]
    raw = json.loads(base64.b64decode(archive["raw_payload_base64"]))
    raw["elements"] = [row for row in raw["elements"] if row["id"] != 16]
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
    archive["raw_payload_base64"] = base64.b64encode(encoded).decode()
    archive["raw_sha256"] = hashlib.sha256(encoded).hexdigest()
    audit["events"][0]["archives"][2]["raw_sha256"] = archive["raw_sha256"]
    with pytest.raises(EvaluationAssemblyError, match="missing decision-cohort"):
        assemble_evaluation_record(recommendation, batch, audit, admission)


def test_rejects_manager_identity_mismatch():
    recommendation, batch, audit, admission, _ = _fixture()
    recommendation["manager_team_id"] = 421026
    with pytest.raises(EvaluationAssemblyError, match="identity"):
        assemble_evaluation_record(recommendation, batch, audit, admission)


def test_rejects_unfinalized_bootstrap():
    recommendation, batch, audit, admission, _ = _fixture()
    archive = batch["results"][0]["result"]["source_archives"][0]
    raw = json.loads(base64.b64decode(archive["raw_payload_base64"]))
    raw["events"][0]["data_checked"] = False
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
    archive["raw_payload_base64"] = base64.b64encode(encoded).decode()
    archive["raw_sha256"] = hashlib.sha256(encoded).hexdigest()
    audit["events"][0]["archives"][0]["raw_sha256"] = archive["raw_sha256"]
    with pytest.raises(EvaluationAssemblyError, match="finalized"):
        assemble_evaluation_record(recommendation, batch, audit, admission)


def test_rejects_official_scoring_archive_not_bound_to_audit():
    recommendation, batch, audit, admission, _ = _fixture()
    audit["events"][0]["archives"][2]["raw_sha256"] = "f" * 64
    with pytest.raises(EvaluationAssemblyError, match="does not match the independent audit"):
        assemble_evaluation_record(recommendation, batch, audit, admission)


def test_rejects_finalized_observation_after_event_live_capture():
    recommendation, batch, audit, admission, _ = _fixture()
    bootstrap_archive = batch["results"][0]["result"]["source_archives"][0]
    bootstrap_archive["captured_at_utc"] = "2026-11-22T12:00:03Z"
    audit["events"][0]["archives"][0]["captured_at_utc"] = bootstrap_archive["captured_at_utc"]
    with pytest.raises(EvaluationAssemblyError, match="captured before finalized"):
        assemble_evaluation_record(recommendation, batch, audit, admission)
