import copy
import pytest

from assemble_external_benchmark_decision_input import (
    DecisionInputError,
    assemble_decision_input,
)


def captures():
    provider = {
        "provider_snapshot": {
            "target_gameweek": 11,
            "timing": {
                "captured_at_utc": "2026-11-20T14:48:00Z",
                "deadline_utc": "2026-11-21T11:00:00Z",
            },
            "records": [{"fpl_element_id": i} for i in range(1, 673)],
        },
        "player_metadata": [{"fpl_element_id": i} for i in range(1, 673)],
        "player_metadata_provenance": {"row_count": 672},
    }
    manager = {
        "manager_context_capture": {
            "gameweek": 11,
            "team_id": 421025,
            "identity_verified": True,
            "row_count": 15,
            "raw_sha256": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
            "raw_response_base64": "e30=",
            "captured_at_utc": "2026-11-20T14:49:00Z",
        },
        "manager_context": {
            "squad_snapshot": [
                {"fpl_element_id": i, "purchase_price": 5.0}
                for i in range(1, 16)
            ],
            "bank": 0.9,
            "free_transfers": 1,
            "personal_risk_profile": "aggressive",
            "formation": "4-3-3",
        },
    }
    return provider, manager


def test_assembles_verified_captures_without_changing_manager_inputs():
    provider, manager = captures()
    result = assemble_decision_input(
        provider, manager, as_of_utc="2026-11-20T15:00:00Z"
    )
    assert len(result["provider_snapshot"]["records"]) == 672
    assert len(result["player_metadata"]) == 672
    assert len(result["manager_context"]["squad_snapshot"]) == 15
    assert result["manager_context"]["free_transfers"] == 1
    assert result["manager_context"]["bank"] == 0.9
    assert result["manager_context"]["formation"] == "4-3-3"


def test_rejects_gameweek_mismatch():
    provider, manager = captures()
    manager["manager_context_capture"]["gameweek"] = 10
    with pytest.raises(DecisionInputError, match="does not match"):
        assemble_decision_input(provider, manager, as_of_utc="2026-11-20T15:00:00Z")


def test_rejects_unverified_manager_identity():
    provider, manager = captures()
    manager["manager_context_capture"]["identity_verified"] = False
    with pytest.raises(DecisionInputError, match="identity"):
        assemble_decision_input(provider, manager, as_of_utc="2026-11-20T15:00:00Z")


def test_rejects_squad_player_missing_from_metadata():
    provider, manager = captures()
    provider["player_metadata"] = [
        row for row in provider["player_metadata"]
        if row["fpl_element_id"] != 3
    ]
    with pytest.raises(DecisionInputError, match="missing from FPL metadata"):
        assemble_decision_input(provider, manager, as_of_utc="2026-11-20T15:00:00Z")


def test_rejects_as_of_at_or_after_deadline():
    provider, manager = captures()
    with pytest.raises(DecisionInputError, match="strictly before deadline"):
        assemble_decision_input(provider, manager, as_of_utc="2026-11-21T11:00:00Z")


def test_rejects_duplicate_squad_ids():
    provider, manager = captures()
    manager["manager_context"]["squad_snapshot"][1]["fpl_element_id"] = 1
    with pytest.raises(DecisionInputError, match="15 unique"):
        assemble_decision_input(provider, manager, as_of_utc="2026-11-20T15:00:00Z")



def test_rejects_manager_raw_response_hash_mismatch():
    provider, manager = captures()
    manager["manager_context_capture"]["raw_sha256"] = "0" * 64
    with pytest.raises(DecisionInputError, match="SHA-256 mismatch"):
        assemble_decision_input(provider, manager, as_of_utc="2026-11-20T15:00:00Z")


def test_rejects_manager_capture_row_count_mismatch():
    provider, manager = captures()
    manager["manager_context_capture"]["row_count"] = 14
    with pytest.raises(DecisionInputError, match="exactly 15 rows"):
        assemble_decision_input(provider, manager, as_of_utc="2026-11-20T15:00:00Z")


def test_adds_conservative_selling_price_floor_when_purchase_price_is_unknown():
    provider, manager = captures()
    for row in manager["manager_context"]["squad_snapshot"]:
        row.pop("purchase_price")
    result = assemble_decision_input(
        provider, manager, as_of_utc="2026-11-20T15:00:00Z"
    )
    squad = result["manager_context"]["squad_snapshot"]
    assert len(squad) == 15
    assert all("purchase_price" not in row for row in squad)
    assert all(row["selling_price_floor"] == 5.0 for row in squad)
