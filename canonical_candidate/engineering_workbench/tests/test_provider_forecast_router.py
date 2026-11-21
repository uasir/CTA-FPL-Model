import copy

import pytest

from provider_forecast_router import ProviderForecastRoutingError, route_provider_forecast


def payload():
    return {
        "snapshot_id": "sq-gw11-001",
        "season": "2026-27",
        "target_gameweek": 11,
        "provider": {
            "name": "FPL Cat",
            "product": "projections",
            "variant": "provider_native_xp",
            "version": "v1",
        },
        "timing": {
            "generated_at_utc": "2026-11-20T08:00:00Z",
            "captured_at_utc": "2026-11-20T08:05:00Z",
            "deadline_utc": "2026-11-21T11:00:00Z",
        },
        "source": {
            "url": "https://example.test/projections",
            "raw_snapshot_id": "raw-001",
            "raw_sha256": "a" * 64,
        },
        "grain": "player_gameweek",
        "records": [{"fpl_element_id": 1, "expected_points": 5.2, "expected_minutes": 80}],
        "coverage": {"row_count": 1, "identity_mapped_count": 1, "identity_resolution_status": "VERIFIED"},
    }


def test_routes_registered_player_gameweek_snapshot_without_blending():
    result = route_provider_forecast(payload())
    assert result["provider_id"] == "fpl_cat"
    assert result["routing_status"] == "READY_FOR_RECOMMENDATION_ADAPTER"
    assert result["decision_eligible"] is True
    assert result["canonical_snapshot"]["records"][0]["expected_points"] == 5.2
    assert result["recommendation_payload"] is None




@pytest.mark.parametrize(
    "coverage",
    [
        {"row_count": 1, "identity_mapped_count": 1},
        {"row_count": 1, "identity_mapped_count": 0, "identity_resolution_status": "VERIFIED"},
        {"row_count": 1, "identity_mapped_count": 1, "identity_resolution_status": "UNVERIFIED_NAME_CLUB_MATCH"},
    ],
)
def test_player_gameweek_snapshot_without_verified_identity_is_diagnostic_only(coverage):
    source = payload()
    source["coverage"] = coverage
    result = route_provider_forecast(source)
    assert result["routing_status"] == "DIAGNOSTIC_ONLY"
    assert result["decision_eligible"] is False
    assert result["routing_reason"] == "IDENTITY_PROVENANCE_NOT_VERIFIED"

def test_routes_unverified_generation_time_as_diagnostic_only():
    source = payload()
    source["timing"]["generated_at_utc"] = None
    result = route_provider_forecast(source)
    assert result["routing_status"] == "DIAGNOSTIC_ONLY"
    assert result["decision_eligible"] is False


def test_preserves_fixture_grain_without_implicit_aggregation():
    source = payload()
    source["provider"] = {
        "name": "Sideline Quant",
        "product": "gameweek_projections",
        "variant": "provider_native_xp",
    }
    source["grain"] = "player_fixture"
    source["records"] = [
        {"fpl_element_id": 1, "fixture_id": 101, "expected_points": 2.1},
        {"fpl_element_id": 1, "fixture_id": 102, "expected_points": 3.1},
    ]
    source["coverage"] = {"row_count": 2}
    result = route_provider_forecast(source)
    assert result["routing_status"] == "EXPLICIT_PLAYER_GAMEWEEK_TRANSFORM_REQUIRED"
    assert result["canonical_snapshot"]["grain"] == "player_fixture"
    assert len(result["canonical_snapshot"]["records"]) == 2


@pytest.mark.parametrize("name", ["FPL Forecaster", "FPL Review", "FPLWise", "RotoWire"])
def test_rejects_sources_outside_active_five(name):
    source = payload()
    source["provider"]["name"] = name
    with pytest.raises(ProviderForecastRoutingError, match="not in the active"):
        route_provider_forecast(source)


def test_rejects_unregistered_provider_product():
    source = payload()
    source["provider"]["product"] = "other-product"
    with pytest.raises(ProviderForecastRoutingError, match="product mismatch"):
        route_provider_forecast(source)


def test_rejects_unregistered_lucho_variant():
    source = payload()
    source["provider"] = {
        "name": "FPL Lucho",
        "product": "forecast_csv",
        "variant": "blended_xp",
    }
    with pytest.raises(ProviderForecastRoutingError, match="unregistered forecast variant"):
        route_provider_forecast(source)


def test_lucho_variants_are_kept_as_distinct_registered_routes():
    for variant in ("served_odds_anchored_xp", "raw_model_xp", "odds_xp"):
        source = payload()
        source["provider"] = {
            "name": "FPL Lucho",
            "product": "forecast_csv",
            "variant": variant,
        }
        result = route_provider_forecast(source)
        assert result["provider"]["variant"] == variant
        assert result["routing_status"] == "READY_FOR_RECOMMENDATION_ADAPTER"


def test_builds_recommendation_payload_only_with_explicit_metadata_and_as_of():
    metadata = [{"fpl_element_id": 1, "price": 7.0, "position": 3, "team_id": 1}]
    result = route_provider_forecast(
        payload(), player_metadata=metadata, as_of_utc="2026-11-20T09:00:00Z"
    )
    assert result["routing_status"] == "RECOMMENDATION_PAYLOAD_READY"
    player = result["recommendation_payload"]["player_forecasts"][0]
    assert player["expected_points"] == 5.2
    assert player["fpl_element_id"] == 1


def test_requires_metadata_and_as_of_together():
    with pytest.raises(ProviderForecastRoutingError, match="must be supplied together"):
        route_provider_forecast(payload(), player_metadata=[{"fpl_element_id": 1}])


def test_does_not_mutate_input_payload():
    source = payload()
    original = copy.deepcopy(source)
    route_provider_forecast(source)
    assert source == original



def test_sideline_quant_derived_player_gameweek_snapshot_routes_to_recommendation_boundary():
    from parse_sideline_quant_snapshot import parse_sideline_quant_capture
    from test_parse_sideline_quant_snapshot import make_capture

    parsed = parse_sideline_quant_capture(make_capture())
    derived = parsed["player_gameweek_snapshot"]
    result = route_provider_forecast(derived)
    assert result["provider_id"] == "sideline_quant"
    assert result["routing_status"] == "READY_FOR_RECOMMENDATION_ADAPTER"
    assert result["grain"] == "player_gameweek"
    assert result["canonical_snapshot"]["records"][0]["expected_points"] == pytest.approx(5.5)
    assert result["canonical_snapshot"]["records"][0]["points_variance"] == pytest.approx(3.4 ** 2)


def test_fpl_cat_capture_identity_provenance_reaches_recommendation_boundary():
    from capture_fpl_cat_snapshot import capture_fpl_cat_snapshot, FPL_CAT_URL, FPL_BOOTSTRAP_URL
    from test_capture_fpl_cat_snapshot import fixture_bytes

    provider_raw, bootstrap_raw = fixture_bytes()
    responses = {FPL_CAT_URL: provider_raw, FPL_BOOTSTRAP_URL: bootstrap_raw}
    times = iter(["2026-11-20T09:00:00Z", "2026-11-20T09:01:00Z"])
    captured = capture_fpl_cat_snapshot(
        season="2026-27",
        fetch_bytes=lambda url: responses[url],
        clock=lambda: next(times),
    )
    result = route_provider_forecast(
        captured["provider_snapshot"],
        player_metadata=captured["player_metadata"],
        as_of_utc="2026-11-20T10:00:00Z",
    )
    assert result["routing_status"] == "RECOMMENDATION_PAYLOAD_READY"
    assert result["recommendation_payload"]["player_forecasts"][0]["fpl_element_id"] == 1
