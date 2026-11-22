import copy
import pytest

from provider_capability_registry import (
    ProviderCapabilityError,
    get_provider_capability,
    list_provider_capabilities,
    require_multi_gameweek_capture,
    validate_capture_against_registry,
)


def test_registry_distinguishes_player_gw_and_fixture_gw_sources():
    fpl = get_provider_capability("fpl_cat_public_projections")
    sideline = get_provider_capability("sideline_quant_public_next_gw")
    assert fpl["capture_grain"] == "player_gameweek"
    assert sideline["capture_grain"] == "player_fixture"
    assert sideline["fixture_ids"] is True
    assert fpl["explicit_multi_gameweek_panels"] is False
    assert sideline["explicit_multi_gameweek_panels"] is False


@pytest.mark.parametrize("source_id", [
    "fpl_cat_public_projections",
    "sideline_quant_public_next_gw",
])
def test_current_sources_fail_closed_for_five_gameweek_capture(source_id):
    with pytest.raises(ProviderCapabilityError, match="not registered as eligible"):
        require_multi_gameweek_capture(source_id)


def test_unknown_source_fails_closed():
    with pytest.raises(ProviderCapabilityError, match="unknown provider"):
        get_provider_capability("unreviewed_source")


def test_registry_returns_defensive_copies():
    result = get_provider_capability("fpl_cat_public_projections")
    result["capture_grain"] = "player_fixture"
    assert get_provider_capability("fpl_cat_public_projections")["capture_grain"] == "player_gameweek"


def test_capture_identity_and_grain_are_checked():
    capture = {
        "provider": {"name": "FPL Cat", "product": "projections", "variant": "provider_native_xp", "version": "api/v1"},
        "grain": "player_gameweek",
        "multi_gameweek_capability": {"decision_eligible_for_multi_gameweek": False},
    }
    validate_capture_against_registry("fpl_cat_public_projections", capture)
    bad = copy.deepcopy(capture)
    bad["grain"] = "player_fixture"
    with pytest.raises(ProviderCapabilityError, match="grain"):
        validate_capture_against_registry("fpl_cat_public_projections", bad)


def test_single_gw_source_cannot_self_assert_multi_gw_eligibility():
    capture = {
        "provider": {"name": "FPL Cat", "product": "projections", "variant": "provider_native_xp", "version": "api/v1"},
        "grain": "player_gameweek",
        "multi_gameweek_capability": {"decision_eligible_for_multi_gameweek": True},
    }
    with pytest.raises(ProviderCapabilityError, match="cannot claim"):
        validate_capture_against_registry("fpl_cat_public_projections", capture)


def test_list_is_stable_and_complete_for_current_sources():
    rows = list_provider_capabilities()
    assert [row["source_id"] for row in rows] == [
        "fpl_cat_public_projections", "sideline_quant_public_next_gw"
    ]


def test_minimum_horizon_cannot_be_lowered_to_bypass_policy():
    with pytest.raises(ProviderCapabilityError, match="at least five"):
        require_multi_gameweek_capture("sideline_quant_public_next_gw", required_horizon=1)
