import base64
import copy
import hashlib
import json

import pytest

from evaluate_external_benchmark_decisions import (
    DecisionEvaluationError,
    evaluate_decision_record,
)


def _archive(source_type, generated=False):
    raw = json.dumps({"synthetic": source_type}, sort_keys=True).encode()
    result = {
        "source_type": source_type,
        "source_url": f"https://synthetic.invalid/{source_type}",
        "raw_snapshot_id": f"synthetic-{source_type}-1",
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "captured_at_utc": (
            "2026-10-03T10:00:00Z" if source_type == "realised_points"
            else "2026-10-01T10:00:00Z"
        ),
        "raw_payload_base64": base64.b64encode(raw).decode(),
    }
    if generated:
        result["generated_at_utc"] = "2026-10-01T09:00:00Z"
    if source_type == "realised_points":
        result["finalized_at_utc"] = "2026-10-03T09:00:00Z"
    return result


def _player(player_id, position=None):
    if position is None:
        if player_id <= 2:
            position = "GKP"
        elif player_id <= 7:
            position = "DEF"
        elif player_id <= 12:
            position = "MID"
        else:
            position = "FWD"
    return {
        "fpl_element_id": player_id,
        "position": position,
        "team_id": (player_id - 1) // 3 + 1,
        "purchase_price": 5.0,
        "current_price": 5.0,
    }


def _plan(squad_ids, xi, bench, reserve=2, captain=15, vice=14):
    return {
        "squad_ids": list(squad_ids),
        "starting_xi": list(xi),
        "bench_order": list(bench),
        "reserve_goalkeeper_id": reserve,
        "captain_id": captain,
        "vice_captain_id": vice,
        "formation": "4-3-3",
    }


def _seal(decision):
    body = {key: value for key, value in decision.items() if key != "decision_sha256"}
    decision["decision_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return decision


def _record():
    roster = [_player(i) for i in range(1, 16)]
    xi = [1, 3, 4, 5, 6, 8, 9, 10, 13, 14, 15]
    hold_plan = _plan(range(1, 16), xi, [7, 11, 12])
    incoming = _player(16, "DEF")
    post_roster_ids = [i for i in range(1, 16) if i != 7] + [16]
    post_xi = [1, 3, 4, 5, 16, 8, 9, 10, 13, 14, 15]
    post_plan = _plan(post_roster_ids, post_xi, [6, 11, 12])
    decision = _seal({
        "action": "TRANSFER",
        "transfer_out_id": 7,
        "transfer_in_id": 16,
        "incoming_player": incoming,
        "transfer_hit_points": 0,
        "squad_plan": post_plan,
    })
    realised = []
    for player_id in [*range(1, 16), 16]:
        minutes = 90
        points = 2
        if player_id in {3, 15}:
            minutes = 0
        if player_id == 7:
            points = 5
        if player_id == 6:
            points = 3
        if player_id == 14:
            points = 6
        if player_id == 16:
            points = 8
        realised.append({
            "fpl_element_id": player_id,
            "minutes": minutes,
            "yellow_cards": 0,
            "red_cards": 0,
            "total_points": points,
        })
    return {
        "evidence_class": "SYNTHETIC_TEST",
        "manager_team_id": 421025,
        "season": "2026-27",
        "provider_snapshot_id": "synthetic-fplcat-gw11",
        "decision_contract_version": "m3-decision-v0.1",
        "target_gameweek": 11,
        "deadline_utc": "2026-10-01T11:00:00Z",
        "as_of_utc": "2026-10-01T10:30:00Z",
        "provider_identity": {"name": "Synthetic Provider", "product": "xP", "variant": "fixture"},
        "software_commit": "a" * 40,
        "source_archives": [
            _archive("provider", generated=True),
            _archive("player_metadata"),
            _archive("manager_state"),
            _archive("realised_points"),
        ],
        "manager_state": {
            "bank": 0.5,
            "free_transfers": 1,
            "personal_risk_profile": "aggressive",
            "formation": "4-3-3",
            "chip": "NONE",
            "squad_snapshot": roster,
            "hold_plan": hold_plan,
        },
        "frozen_decision": decision,
        "realised_player_points": realised,
    }


def test_scores_transfer_against_hold_with_autosubs_captain_fallback_and_incoming_points():
    result = evaluate_decision_record(_record())
    assert result["evidence_class"] == "SYNTHETIC_TEST"
    assert result["evaluation_status"] == "SYNTHETIC_ONLY_NOT_HISTORICAL_EVIDENCE"
    assert result["recommended"]["outfield_substitutions"] == [
        {"player_out_id": 3, "player_in_id": 6},
        {"player_out_id": 15, "player_in_id": 11},
    ]
    assert result["recommended"]["effective_captain_id"] == 14
    assert result["recommended"]["captain_bonus_points"] == 6
    assert result["recommended"]["transfer_hit_points"] == 0
    assert result["hold"]["outfield_substitutions"] == [
        {"player_out_id": 3, "player_in_id": 7},
        {"player_out_id": 15, "player_in_id": 11},
    ]
    assert result["historical_performance_validated"] is False


def test_transfer_with_no_free_transfer_must_charge_four_points():
    record = _record()
    record["manager_state"]["free_transfers"] = 0
    record["frozen_decision"]["transfer_hit_points"] = 4
    _seal(record["frozen_decision"])
    result = evaluate_decision_record(record)
    assert result["recommended"]["transfer_hit_points"] == 4
    assert result["recommended"]["net_points"] == result["recommended"]["gross_points"] - 4


def test_rejects_provider_hash_mismatch():
    record = _record()
    record["source_archives"][0]["raw_sha256"] = "0" * 64
    with pytest.raises(DecisionEvaluationError, match="SHA-256 mismatch"):
        evaluate_decision_record(record)


def test_rejects_source_captured_after_deadline():
    record = _record()
    record["source_archives"][1]["captured_at_utc"] = "2026-10-01T11:00:00Z"
    with pytest.raises(DecisionEvaluationError, match="at or after the deadline"):
        evaluate_decision_record(record)


def test_rejects_decision_timestamp_at_deadline():
    record = _record()
    record["as_of_utc"] = record["deadline_utc"]
    with pytest.raises(DecisionEvaluationError, match="strictly before"):
        evaluate_decision_record(record)


def test_rejects_missing_realised_player_points():
    record = _record()
    record["realised_player_points"].pop()
    with pytest.raises(DecisionEvaluationError, match="exactly 16 player rows"):
        evaluate_decision_record(record)


def test_rejects_duplicate_realised_player_ids():
    record = _record()
    record["realised_player_points"][-1]["fpl_element_id"] = 15
    with pytest.raises(DecisionEvaluationError, match="duplicate player ID"):
        evaluate_decision_record(record)


def test_rejects_corrupted_frozen_decision_hash():
    record = _record()
    record["frozen_decision"]["transfer_hit_points"] = 1
    with pytest.raises(DecisionEvaluationError, match="decision_sha256 mismatch"):
        evaluate_decision_record(record)


def test_rejects_incoherent_post_transfer_roster():
    record = _record()
    record["frozen_decision"]["squad_plan"]["squad_ids"] = list(range(1, 16))
    _seal(record["frozen_decision"])
    with pytest.raises(DecisionEvaluationError, match="squad_ids must exactly match"):
        evaluate_decision_record(record)


def test_rejects_bench_transfer_that_does_not_promote_incoming_player():
    record = _record()
    record["frozen_decision"]["squad_plan"]["starting_xi"] = [1, 3, 4, 5, 6, 8, 9, 10, 13, 14, 15]
    record["frozen_decision"]["squad_plan"]["bench_order"] = [16, 11, 12]
    _seal(record["frozen_decision"])
    with pytest.raises(DecisionEvaluationError, match="must improve the starting XI"):
        evaluate_decision_record(record)


def test_rejects_incoming_player_with_wrong_position():
    record = _record()
    record["frozen_decision"]["incoming_player"]["position"] = "MID"
    _seal(record["frozen_decision"])
    with pytest.raises(DecisionEvaluationError, match="formation does not match"):
        evaluate_decision_record(record)


def test_rejects_changed_starting_goalkeeper():
    record = _record()
    record["frozen_decision"]["squad_plan"]["starting_xi"][0] = 2
    record["frozen_decision"]["squad_plan"]["reserve_goalkeeper_id"] = 1
    _seal(record["frozen_decision"])
    with pytest.raises(DecisionEvaluationError, match="designated reserve goalkeeper cannot change"):
        evaluate_decision_record(record)


def test_rejects_chip_scoring_outside_initial_scope():
    record = _record()
    record["manager_state"]["chip"] = "BENCH_BOOST"
    with pytest.raises(DecisionEvaluationError, match="chip scoring is outside"):
        evaluate_decision_record(record)


def test_identical_frozen_record_produces_identical_scores():
    record = _record()
    assert evaluate_decision_record(copy.deepcopy(record)) == evaluate_decision_record(copy.deepcopy(record))


def _real_admission_inputs(record):
    gameweek = record["target_gameweek"]
    manager_id = record["manager_team_id"]
    decision = record["frozen_decision"]
    manager_archive = next(
        row for row in record["source_archives"] if row["source_type"] == "manager_state"
    )
    metadata_archive = next(
        row for row in record["source_archives"] if row["source_type"] == "player_metadata"
    )
    roster_for_metadata = record["manager_state"]["squad_snapshot"]
    incoming_for_metadata = record["frozen_decision"].get("incoming_player")
    metadata_cohort = list(roster_for_metadata)
    if isinstance(incoming_for_metadata, dict):
        metadata_cohort.append(incoming_for_metadata)
    element_type_by_position = {"GKP": 1, "DEF": 2, "MID": 3, "FWD": 4}
    bootstrap = {
        "elements": [
            {
                "id": row["fpl_element_id"],
                "element_type": element_type_by_position[row["position"]],
                "team": row["team_id"],
                "now_cost": round(row["current_price"] * 10),
            }
            for row in metadata_cohort
        ]
    }
    metadata_raw = json.dumps(bootstrap, sort_keys=True, separators=(",", ":")).encode()
    metadata_archive.update({
        "raw_snapshot_id": "official-bootstrap-gw11",
        "raw_sha256": hashlib.sha256(metadata_raw).hexdigest(),
        "raw_payload_base64": base64.b64encode(metadata_raw).decode(),
    })
    manager_state = record["manager_state"]
    roster = manager_state["squad_snapshot"]
    purchase_prices = {str(row["fpl_element_id"]): row["purchase_price"] for row in roster}
    selling_prices = {}
    for row in roster:
        current_tenths = round(row["current_price"] * 10)
        purchase_tenths = round(row["purchase_price"] * 10)
        selling_prices[str(row["fpl_element_id"])] = (
            current_tenths if current_tenths <= purchase_tenths
            else purchase_tenths + (current_tenths - purchase_tenths) // 2
        ) / 10
    hold = manager_state["hold_plan"]
    manager_envelope = {
        "capture_kind": "USER_ATTESTED_PREDEADLINE_MANAGER_STATE",
        "manager_team_id": manager_id,
        "target_gameweek": gameweek,
        "captured_at_utc": manager_archive["captured_at_utc"],
        "manager_state": {
            "squad_15": sorted(manager_state["hold_plan"]["squad_ids"]),
            "bank": manager_state["bank"],
            "free_transfers": manager_state["free_transfers"],
            "formation": manager_state["formation"],
            "starting_xi": hold["starting_xi"],
            "bench_order": hold["bench_order"],
            "reserve_goalkeeper_id": hold["reserve_goalkeeper_id"],
            "captain_id": hold["captain_id"],
            "vice_captain_id": hold["vice_captain_id"],
            "chip_state": "NONE",
            "purchase_prices": purchase_prices,
            "selling_prices": selling_prices,
        },
    }
    manager_raw = json.dumps(manager_envelope, sort_keys=True, separators=(",", ":")).encode()
    manager_archive.update({
        "raw_snapshot_id": "official-manager-state-gw11",
        "raw_sha256": hashlib.sha256(manager_raw).hexdigest(),
        "raw_payload_base64": base64.b64encode(manager_raw).decode(),
    })
    source_type_map = {
        "provider": "provider_forecast",
        "player_metadata": "player_metadata",
        "manager_state": "manager_deadline_state",
    }
    decision_sources = []
    for archive in record["source_archives"]:
        if archive["source_type"] not in source_type_map:
            continue
        source = {
            "source_type": source_type_map[archive["source_type"]],
            "raw_snapshot_id": archive["raw_snapshot_id"],
            "raw_sha256": archive["raw_sha256"],
            "captured_at_utc": archive["captured_at_utc"],
            "source_url": archive["source_url"],
        }
        if archive["source_type"] == "provider":
            source.update({
                "generated_at_utc": archive["generated_at_utc"],
                "provider_id": record["provider_identity"]["name"],
                "provider_variant": record["provider_identity"]["variant"],
            })
        decision_sources.append(source)
    realised_archive = next(
        row for row in record["source_archives"] if row["source_type"] == "realised_points"
    )
    live_payload = {
        "elements": [
            {
                "id": row["fpl_element_id"],
                "stats": {
                    "minutes": row["minutes"],
                    "yellow_cards": row["yellow_cards"],
                    "red_cards": row["red_cards"],
                    "total_points": row["total_points"],
                },
            }
            for row in record["realised_player_points"]
        ]
    }
    live_raw = json.dumps(live_payload, sort_keys=True).encode()
    realised_archive.update({
        "source_url": f"https://fantasy.premierleague.com/api/event/{gameweek}/live/",
        "raw_snapshot_id": f"official-event-live-gw{gameweek}",
        "raw_sha256": hashlib.sha256(live_raw).hexdigest(),
        "raw_payload_base64": base64.b64encode(live_raw).decode(),
    })
    audit = {
        "status": "PASSED",
        "manager_team_id": manager_id,
        "events": [{
            "gameweek": gameweek,
            "status": "RECONCILED",
            "archives": [{
                "source_type": "event_live",
                "raw_snapshot_id": realised_archive["raw_snapshot_id"],
                "raw_sha256": realised_archive["raw_sha256"],
                "captured_at_utc": realised_archive["captured_at_utc"],
                "source_url": realised_archive["source_url"],
            }],
            "decision_sources": decision_sources,
            "predeadline_recommendation": {
                "status": "VERIFIED",
                "action": decision["action"],
                "execution_match": "RECOMMENDATION_MATCHED",
                "decision_sha256": decision["decision_sha256"],
            },
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
    batch = {
        "manager_team_id": manager_id,
        "historical_evidence_admitted": False,
        "results": [{
            "gameweek": gameweek,
            "status": "RECONCILED",
            "result": {
                "manager_team_id": manager_id,
                "target_gameweek": gameweek,
                "event_finalized": True,
                "historical_evidence_admitted": False,
                "active_chip": None,
            },
        }],
    }
    return admission, audit, batch


def test_real_candidate_requires_and_accepts_matching_independent_admission_chain():
    record = _record()
    record["evidence_class"] = "REAL_CANDIDATE"
    admission, audit, batch = _real_admission_inputs(record)
    result = evaluate_decision_record(
        record, admission_report=admission, audit_report=audit, batch=batch
    )
    assert result["evidence_class"] == "REAL_CANDIDATE"
    assert result["evaluation_status"] == "REAL_DECISION_BACKTEST_EVENT_SCORED_NOT_PROMOTION_EVIDENCE"
    assert result["historical_performance_validated"] is False


def test_real_candidate_rejects_missing_audited_decision_sources():
    record = _record()
    record["evidence_class"] = "REAL_CANDIDATE"
    admission, audit, batch = _real_admission_inputs(record)
    audit["events"][0]["decision_sources"] = []
    with pytest.raises(DecisionEvaluationError, match="not bound to an independently audited"):
        evaluate_decision_record(record, admission_report=admission, audit_report=audit, batch=batch)


def test_real_candidate_rejects_valid_but_unrelated_provider_archive():
    record = _record()
    record["evidence_class"] = "REAL_CANDIDATE"
    admission, audit, batch = _real_admission_inputs(record)
    audit["events"][0]["decision_sources"][0]["raw_sha256"] = "f" * 64
    with pytest.raises(DecisionEvaluationError, match="does not match the independent decision-source audit"):
        evaluate_decision_record(record, admission_report=admission, audit_report=audit, batch=batch)


def test_real_candidate_rejects_provider_snapshot_substitution():
    record = _record()
    record["evidence_class"] = "REAL_CANDIDATE"
    admission, audit, batch = _real_admission_inputs(record)
    provider_source = next(
        row for row in audit["events"][0]["decision_sources"]
        if row["source_type"] == "provider_forecast"
    )
    provider_source["raw_snapshot_id"] = "different-provider-snapshot"
    with pytest.raises(DecisionEvaluationError, match="raw_snapshot_id does not match"):
        evaluate_decision_record(record, admission_report=admission, audit_report=audit, batch=batch)



def test_real_candidate_rejects_unrelated_realised_points_archive():
    record = _record()
    record["evidence_class"] = "REAL_CANDIDATE"
    admission, audit, batch = _real_admission_inputs(record)
    audit["events"][0]["archives"][0]["raw_sha256"] = "f" * 64
    with pytest.raises(DecisionEvaluationError, match="does not match the audited official event-live archive"):
        evaluate_decision_record(record, admission_report=admission, audit_report=audit, batch=batch)


def test_real_candidate_rejects_realised_points_detached_from_official_live_rows():
    record = _record()
    record["evidence_class"] = "REAL_CANDIDATE"
    admission, audit, batch = _real_admission_inputs(record)
    record["realised_player_points"][0]["total_points"] += 1
    with pytest.raises(DecisionEvaluationError, match="does not match official event-live scoring"):
        evaluate_decision_record(record, admission_report=admission, audit_report=audit, batch=batch)


def test_real_candidate_rejects_current_price_detached_from_official_metadata():
    record = _record()
    record["evidence_class"] = "REAL_CANDIDATE"
    admission, audit, batch = _real_admission_inputs(record)
    record["manager_state"]["squad_snapshot"][0]["current_price"] += 0.1
    with pytest.raises(DecisionEvaluationError, match="does not match official bootstrap metadata"):
        evaluate_decision_record(record, admission_report=admission, audit_report=audit, batch=batch)


def test_real_candidate_rejects_incoming_player_club_detached_from_official_metadata():
    record = _record()
    record["evidence_class"] = "REAL_CANDIDATE"
    admission, audit, batch = _real_admission_inputs(record)
    record["frozen_decision"]["incoming_player"]["team_id"] += 1
    _seal(record["frozen_decision"])
    audit["events"][0]["predeadline_recommendation"]["decision_sha256"] = record["frozen_decision"]["decision_sha256"]
    with pytest.raises(DecisionEvaluationError, match="does not match official bootstrap metadata"):
        evaluate_decision_record(record, admission_report=admission, audit_report=audit, batch=batch)


def test_real_candidate_rejects_detached_manager_roster():
    record = _record()
    record["evidence_class"] = "REAL_CANDIDATE"
    admission, audit, batch = _real_admission_inputs(record)
    record["manager_state"]["squad_snapshot"][-1]["fpl_element_id"] = 99
    with pytest.raises(DecisionEvaluationError, match="does not match the archived 15-player"):
        evaluate_decision_record(record, admission_report=admission, audit_report=audit, batch=batch)


def test_real_candidate_rejects_detached_manager_bank():
    record = _record()
    record["evidence_class"] = "REAL_CANDIDATE"
    admission, audit, batch = _real_admission_inputs(record)
    record["manager_state"]["bank"] += 0.1
    with pytest.raises(DecisionEvaluationError, match="bank does not match the archived"):
        evaluate_decision_record(record, admission_report=admission, audit_report=audit, batch=batch)


def test_real_candidate_rejects_detached_hold_bench_order():
    record = _record()
    record["evidence_class"] = "REAL_CANDIDATE"
    admission, audit, batch = _real_admission_inputs(record)
    record["manager_state"]["hold_plan"]["bench_order"] = [11, 7, 12]
    with pytest.raises(DecisionEvaluationError, match="bench_order does not match the archived"):
        evaluate_decision_record(record, admission_report=admission, audit_report=audit, batch=batch)


def test_real_candidate_rejects_purchase_price_detached_from_manager_archive():
    record = _record()
    record["evidence_class"] = "REAL_CANDIDATE"
    admission, audit, batch = _real_admission_inputs(record)
    record["manager_state"]["squad_snapshot"][0]["purchase_price"] += 0.1
    with pytest.raises(DecisionEvaluationError, match="purchase price .* does not match archived"):
        evaluate_decision_record(record, admission_report=admission, audit_report=audit, batch=batch)


def test_real_candidate_rejects_missing_audited_event_live_archive():
    record = _record()
    record["evidence_class"] = "REAL_CANDIDATE"
    admission, audit, batch = _real_admission_inputs(record)
    audit["events"][0]["archives"] = []
    with pytest.raises(DecisionEvaluationError, match="missing the official event-live scoring archive"):
        evaluate_decision_record(record, admission_report=admission, audit_report=audit, batch=batch)

def test_real_candidate_rejects_missing_admission_chain():
    record = _record()
    record["evidence_class"] = "REAL_CANDIDATE"
    with pytest.raises(DecisionEvaluationError, match="requires admission report"):
        evaluate_decision_record(record)


def test_real_candidate_rejects_decision_hash_mismatch_in_audit():
    record = _record()
    record["evidence_class"] = "REAL_CANDIDATE"
    admission, audit, batch = _real_admission_inputs(record)
    audit["events"][0]["predeadline_recommendation"]["decision_sha256"] = "0" * 64
    with pytest.raises(DecisionEvaluationError, match="frozen decision hash/action/execution"):
        evaluate_decision_record(record, admission_report=admission, audit_report=audit, batch=batch)


def test_real_candidate_rejects_non_admitted_event_even_if_admission_report_is_tampered():
    record = _record()
    record["evidence_class"] = "REAL_CANDIDATE"
    admission, audit, batch = _real_admission_inputs(record)
    batch["results"][0]["result"]["event_finalized"] = False
    with pytest.raises(DecisionEvaluationError, match="matching finalized"):
        evaluate_decision_record(record, admission_report=admission, audit_report=audit, batch=batch)


def test_hold_scores_the_manager_lineup_without_transfer_hit():
    record = _record()
    record["frozen_decision"] = _seal({
        "action": "HOLD",
        "transfer_out_id": None,
        "transfer_in_id": None,
        "transfer_hit_points": 0,
        "squad_plan": copy.deepcopy(record["manager_state"]["hold_plan"]),
    })
    record["realised_player_points"] = record["realised_player_points"][:15]
    result = evaluate_decision_record(record)
    assert result["recommended"]["gross_points"] == result["hold"]["gross_points"]
    assert result["net_points_delta_vs_hold"] == 0
    assert result["recommended"]["transfer_hit_points"] == 0


def test_uses_reserve_goalkeeper_when_starting_goalkeeper_does_not_play():
    record = _record()
    record["realised_player_points"][0]["minutes"] = 0
    result = evaluate_decision_record(record)
    assert result["recommended"]["goalkeeper_substitution"] == {
        "player_out_id": 1, "player_in_id": 2
    }
    assert 2 in result["recommended"]["on_pitch_ids_after_substitutions"]


def test_rejects_realised_points_archive_captured_before_deadline():
    record = _record()
    record["source_archives"][3]["captured_at_utc"] = "2026-10-01T10:45:00Z"
    with pytest.raises(DecisionEvaluationError, match="realised_points archive must be captured after"):
        evaluate_decision_record(record)


def test_zero_minute_carded_bench_player_is_eligible_for_autosub():
    record = _record()
    bench_player = next(row for row in record["realised_player_points"] if row["fpl_element_id"] == 6)
    bench_player["minutes"] = 0
    bench_player["yellow_cards"] = 1
    bench_player["total_points"] = -1
    result = evaluate_decision_record(record)
    assert {"player_out_id": 3, "player_in_id": 6} in result["recommended"]["outfield_substitutions"]


def test_zero_minute_carded_starting_goalkeeper_is_not_replaced():
    record = _record()
    starting_keeper = next(row for row in record["realised_player_points"] if row["fpl_element_id"] == 1)
    starting_keeper["minutes"] = 0
    starting_keeper["yellow_cards"] = 1
    starting_keeper["total_points"] = -1
    result = evaluate_decision_record(record)
    assert result["recommended"]["goalkeeper_substitution"] is None


def test_rejects_unaffordable_transfer_using_fpl_sell_price():
    record = _record()
    record["frozen_decision"]["incoming_player"]["current_price"] = 6.0
    record["frozen_decision"]["incoming_player"]["purchase_price"] = 6.0
    _seal(record["frozen_decision"])
    with pytest.raises(DecisionEvaluationError, match="unaffordable"):
        evaluate_decision_record(record)


def test_rejects_goalkeeper_transfer_under_fixed_keeper_strategy():
    record = _record()
    decision = record["frozen_decision"]
    decision["transfer_out_id"] = 1
    decision["transfer_in_id"] = 16
    decision["incoming_player"] = _player(16, "GKP")
    decision["squad_plan"] = _plan([2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 7, 16],
                                   [16, 3, 4, 5, 6, 8, 9, 10, 13, 14, 15], [7, 11, 12])
    _seal(decision)
    with pytest.raises(DecisionEvaluationError, match="goalkeeper transfers are excluded"):
        evaluate_decision_record(record)


def test_output_retains_input_and_raw_source_hashes():
    result = evaluate_decision_record(_record())
    assert len(result["evaluation_input_sha256"]) == 64
    assert len(result["frozen_decision_sha256"]) == 64
    assert {item["source_type"] for item in result["source_provenance"]} == {
        "provider", "player_metadata", "manager_state", "realised_points"
    }

def test_rejects_malformed_transfer_identifiers_without_uncaught_type_errors():
    record = _record()
    record["frozen_decision"]["transfer_out_id"] = [7]
    _seal(record["frozen_decision"])
    with pytest.raises(DecisionEvaluationError, match="transfer_out_id must identify an owned player"):
        evaluate_decision_record(record)

def test_output_retains_manager_provider_identity_and_does_not_apply_risk_profile():
    result = evaluate_decision_record(_record())
    assert result["manager_team_id"] == 421025
    assert result["provider_snapshot_id"] == "synthetic-fplcat-gw11"
    assert result["personal_risk_profile"] == "aggressive"
    assert result["risk_profile_applied"] is False


def test_rejects_invalid_manager_risk_profile_and_formation():
    record = _record()
    record["manager_state"]["personal_risk_profile"] = "extreme"
    with pytest.raises(DecisionEvaluationError, match="personal_risk_profile is invalid"):
        evaluate_decision_record(record)
    record = _record()
    record["manager_state"]["formation"] = "2-5-3"
    with pytest.raises(DecisionEvaluationError, match="legal FPL formation"):
        evaluate_decision_record(record)