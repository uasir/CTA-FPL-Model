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
