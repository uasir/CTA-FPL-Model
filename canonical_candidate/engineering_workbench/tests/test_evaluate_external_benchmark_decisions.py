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
        "season": "2026-27",
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


def test_real_candidate_records_remain_blocked_until_admission_gate_exists():
    record = _record()
    record["evidence_class"] = "REAL_CANDIDATE"
    with pytest.raises(DecisionEvaluationError, match="blocked until independent historical-evidence admission"):
        evaluate_decision_record(record)


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