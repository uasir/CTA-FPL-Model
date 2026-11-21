import pytest

from forecast_provider_registry import (
    ACTIVE_PROVIDER_SPECS,
    EXCLUDED_PROVIDERS,
    RESEARCH_ONLY_CANDIDATES,
    ProviderRegistryError,
    get_active_provider,
    list_active_providers,
    require_active_provider,
)


def test_registry_contains_exactly_the_agreed_five_providers():
    assert [item["name"] for item in list_active_providers()] == [
        "FPL Cat", "Sideline Quant", "FPLRogue", "FPL Lucho", "FPL Wildcard"
    ]
    assert len(ACTIVE_PROVIDER_SPECS) == 5


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("fpl_cat", "FPL Cat"),
        ("Sideline Quant", "Sideline Quant"),
        ("FPLRogue", "FPLRogue"),
        ("fpl_lucho", "FPL Lucho"),
        ("FPL Wildcard", "FPL Wildcard"),
    ],
)
def test_active_provider_aliases_resolve_to_canonical_names(key, expected):
    assert require_active_provider(key) == expected


@pytest.mark.parametrize(
    "provider",
    ["FPL Forecaster", "FPL Review", "FPLWise", "RotoWire", "unknown", "", None],
)
def test_excluded_candidates_and_unknown_sources_are_rejected(provider):
    with pytest.raises(ProviderRegistryError):
        get_active_provider(provider)


def test_restricted_provider_policy_is_explicit_and_defensive():
    wildcard = get_active_provider("fpl_wildcard")
    assert "no_redistribution" in wildcard["data_policy"]
    assert "private" in wildcard["data_policy"]
    wildcard["data_policy"] = "public"
    assert "no_redistribution" in get_active_provider("FPL Wildcard")["data_policy"]


def test_lucho_variants_remain_distinct_and_unblended():
    lucho = get_active_provider("FPL Lucho")
    assert lucho["forecast_variant"] == "served_odds_anchored_xp"
    variants = {item["variant_id"]: item for item in lucho["forecast_variants"]}
    assert set(variants) == {"served_odds_anchored_xp", "raw_model_xp", "odds_xp"}
    assert variants["served_odds_anchored_xp"]["availability"] == "public_forecast_csv"
    assert variants["raw_model_xp"]["availability"] == "performance_page_series_export_unverified"
    assert variants["odds_xp"]["availability"] == "performance_page_series_export_unverified"
    assert "bookmaker odds" in variants["odds_xp"]["semantics"]


def test_research_only_sources_are_not_active_providers():
    active = {item["name"] for item in list_active_providers()}
    assert not active.intersection(EXCLUDED_PROVIDERS)
    assert not active.intersection(RESEARCH_ONLY_CANDIDATES)



def test_only_fpl_cat_and_sideline_quant_are_strict_decision_capture_eligible():
    eligible = {
        item["name"] for item in list_active_providers()
        if item.get("decision_capture_eligible") is True
    }
    assert eligible == {"FPL Cat", "Sideline Quant"}
