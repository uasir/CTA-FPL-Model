from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from recommendation_contracts import (
    RecommendationContractError,
    validate_general_market_request,
    validate_personal_squad_request,
)


_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "recommendation_requests.json").read_text(
        encoding="utf-8"
    )
)


def shared():
    return copy.deepcopy(_FIXTURE["general_market"])


def personal():
    return copy.deepcopy(_FIXTURE["personal_squad"])


def test_general_market_is_valid_without_any_squad_context():
    result = validate_general_market_request(shared())
    assert result["system"] == "general_market"
    assert "squad_snapshot" not in result
    assert result["forecast_snapshot_id"] == shared()["forecast_snapshot_id"]


@pytest.mark.parametrize(
    "field",
    [
        "squad", "squad_snapshot", "bank", "free_transfers", "chips",
        "formation", "starting_xi", "bench_order", "manager_rank",
        "rank_target", "personal_risk_profile", "personal_preferences",
        "manager_id", "manager_entry_id", "team_id_for_manager",
    ],
)
def test_general_market_rejects_personal_context(field):
    payload = shared()
    payload[field] = "must-not-cross-boundary"
    with pytest.raises(RecommendationContractError, match="must not receive personal fields"):
        validate_general_market_request(payload)


def test_personal_squad_requires_and_preserves_explicit_manager_context():
    payload = personal()
    result = validate_personal_squad_request(payload)
    assert result["system"] == "personal_squad"
    assert len(result["squad_snapshot"]) == 15
    assert result["bank"] == 4.6
    assert result["free_transfers"] == 1
    assert result["formation"] == "4-3-3"
    assert result["forecast_quality"]["point_in_time_status"] == "NOT_VERIFIED"


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda p: p.update(squad_snapshot=p["squad_snapshot"][:-1]), "exactly 15"),
        (lambda p: p["squad_snapshot"].__setitem__(1, p["squad_snapshot"][0]), "Duplicate squad"),
        (lambda p: p.update(bank=-0.1), "bank must be"),
        (lambda p: p.update(free_transfers=-1), "free_transfers must be"),
        (lambda p: p.pop("personal_risk_profile"), "Missing personal squad fields"),
    ],
)
def test_personal_squad_rejects_invalid_constraints(mutation, message):
    payload = personal()
    mutation(payload)
    with pytest.raises(RecommendationContractError, match=message):
        validate_personal_squad_request(payload)


def test_both_systems_reject_duplicate_forecast_player_ids():
    payload = shared()
    payload["player_forecasts"].append({"fpl_element_id": 1, "expected_points": 4.2, "expected_minutes": 80, "price": 5.0, "position": "MID", "team_id": 1})
    with pytest.raises(RecommendationContractError, match="Duplicate forecast"):
        validate_general_market_request(payload)
    personal_payload = personal()
    personal_payload["player_forecasts"].append({"fpl_element_id": 1})
    with pytest.raises(RecommendationContractError, match="Duplicate forecast"):
        validate_personal_squad_request(personal_payload)


def test_personal_squad_requires_purchase_price_per_player():
    payload = personal()
    payload["squad_snapshot"][0].pop("purchase_price")
    with pytest.raises(RecommendationContractError, match="purchase_price"):
        validate_personal_squad_request(payload)


def test_general_market_rejects_personal_context_nested_in_filters_or_forecasts():
    payload = shared()
    payload["filters"] = {"position": "MID", "squad_snapshot": [{"fpl_element_id": 1}]}
    with pytest.raises(RecommendationContractError, match="must not receive personal fields"):
        validate_general_market_request(payload)

    payload = shared()
    payload["player_forecasts"][0]["personal_risk_profile"] = "aggressive"
    with pytest.raises(RecommendationContractError, match="must not receive personal fields"):
        validate_general_market_request(payload)


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_personal_squad_rejects_non_finite_money_values(bad_value):
    payload = personal()
    payload["bank"] = bad_value
    with pytest.raises(RecommendationContractError, match="bank must be"):
        validate_personal_squad_request(payload)

    payload = personal()
    payload["squad_snapshot"][0]["purchase_price"] = bad_value
    with pytest.raises(RecommendationContractError, match="purchase_price"):
        validate_personal_squad_request(payload)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(forecast_quality=None),
        lambda p: p["forecast_quality"].update(validation_status="PRODUCTION_READY"),
        lambda p: p["forecast_quality"].update(point_in_time_status="UNKNOWN"),
        lambda p: p["forecast_quality"].update(data_coverage=[]),
        lambda p: p["forecast_quality"].update(limitations="not-a-list"),
        lambda p: p["forecast_quality"].pop("limitations"),
    ],
)
def test_both_request_types_reject_invalid_forecast_quality(mutation):
    for factory, validator in [
        (shared, validate_general_market_request),
        (personal, validate_personal_squad_request),
    ]:
        payload = factory()
        mutation(payload)
        with pytest.raises(RecommendationContractError, match="forecast_quality"):
            validator(payload)


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("expected_minutes", -1, "expected_minutes cannot be negative"),
        ("price", 0, "price must be positive"),
        ("position", "WING", "position is invalid"),
        ("team_id", 0, "team_id must be a positive integer"),
        ("availability_probability", 1.1, "availability_probability must be between 0 and 1"),
        ("points_variance", -0.1, "points_variance must be non-negative"),
    ],
)
def test_player_forecast_record_rejects_invalid_fields(field, value, message):
    payload = shared()
    payload["player_forecasts"][0][field] = value
    with pytest.raises(RecommendationContractError, match=message):
        validate_general_market_request(payload)


def test_player_forecast_record_requires_core_fields():
    payload = shared()
    del payload["player_forecasts"][0]["expected_minutes"]
    with pytest.raises(RecommendationContractError, match="expected_minutes"):
        validate_general_market_request(payload)


def test_python_contract_rejects_non_numeric_ids_and_unhashable_position():
    payload = shared()
    payload["player_forecasts"][0]["fpl_element_id"] = "1"
    with pytest.raises(RecommendationContractError, match="positive integer"):
        validate_general_market_request(payload)

    payload = shared()
    payload["player_forecasts"][0]["position"] = ["MID"]
    with pytest.raises(RecommendationContractError, match="position is invalid"):
        validate_general_market_request(payload)


def test_personal_squad_enforces_fpl_position_and_team_composition():
    payload = personal()
    payload["player_forecasts"][0]["position"] = "DEF"
    with pytest.raises(RecommendationContractError, match="position composition"):
        validate_personal_squad_request(payload)

    payload = personal()
    for player in payload["player_forecasts"][:4]:
        player["team_id"] = 1
    with pytest.raises(RecommendationContractError, match="more than 3 players"):
        validate_personal_squad_request(payload)


def test_personal_squad_requires_forecast_for_every_owned_player():
    payload = personal()
    payload["player_forecasts"] = payload["player_forecasts"][:-1]
    with pytest.raises(RecommendationContractError, match="Missing forecast for owned"):
        validate_personal_squad_request(payload)
