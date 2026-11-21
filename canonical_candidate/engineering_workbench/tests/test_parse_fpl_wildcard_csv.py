import hashlib
import pytest

from parse_fpl_wildcard_csv import FPLWildcardParseError, parse_fpl_wildcard_csv


CSV = """rank,gameweek,player,profile_url,club,position,price_m,ownership_pct,fixture,xpts,xmins,start_pct,appearance_pct,sixty_plus_pct,blank_pct,haul_pct
1,11,Player One,/player/1/,ARS,MID,8.0,12.3,ARS-BUR,6.4,85,78,90,75,20,18
2,11,Player Two,/player/2/,CHE,FWD,7.0,4.2,CHE-LIV,4.1,72,65,82,60,30,8
"""


def bootstrap():
    return {
        "teams": [{"id": 1, "short_name": "ARS"}, {"id": 2, "short_name": "CHE"}],
        "elements": [
            {"id": 101, "web_name": "Player One", "first_name": "Player", "second_name": "One", "team": 1},
            {"id": 102, "web_name": "Player Two", "first_name": "Player", "second_name": "Two", "team": 2},
        ],
    }


def metadata(csv=CSV):
    return {
        "capture_id": "wildcard-gw11-private-test",
        "season": "2026-27",
        "target_gameweek": 11,
        "captured_at_utc": "2026-11-21T08:50:00Z",
        "deadline_utc": "2026-11-21T11:00:00Z",
        "projection_updated_at_utc": "2026-11-21T08:45:00Z",
        "source_url": "https://fplwildcard.com/data/projections/current.csv",
        "model_version": "Model v11",
        "raw_sha256": hashlib.sha256(csv.encode()).hexdigest(),
    }


def test_parses_documented_schema_and_maps_exact_player_club_identity():
    result = parse_fpl_wildcard_csv(CSV, metadata(), bootstrap())
    snap = result["canonical_snapshot"]
    assert snap["provider"]["name"] == "FPL Wildcard"
    assert snap["grain"] == "player_gameweek"
    assert [r["fpl_element_id"] for r in snap["records"]] == [101, 102]
    assert snap["records"][0]["expected_points"] == 6.4
    assert result["provider_native_rows"][0]["start_pct"] == "78"
    assert snap["timing"]["generated_at_utc"] is None
    assert snap["coverage"]["identity_resolution_status"] == "UNVERIFIED_NAME_CLUB_MATCH"
    assert snap["decision_eligible"] is False
    assert result["source_metadata"]["storage_policy"] == "PRIVATE_RESTRICTED_NO_REDISTRIBUTION"


def test_rejects_wrong_gameweek_and_duplicate_player_keys():
    with pytest.raises(FPLWildcardParseError, match="Gameweek"):
        parse_fpl_wildcard_csv(CSV.replace(",11,", ",10,", 1), metadata(), bootstrap())
    duplicate = CSV.replace("2,11,Player Two,/player/2/,CHE", "2,11,Player One,/player/1/,ARS")
    with pytest.raises(FPLWildcardParseError, match="duplicate player-Gameweek"):
        parse_fpl_wildcard_csv(duplicate, metadata(duplicate), bootstrap())


def test_rejects_ambiguous_identity_and_bad_hash():
    ambiguous = bootstrap()
    ambiguous["elements"].append({"id": 103, "web_name": "Player One", "first_name": "Other", "second_name": "Name", "team": 1})
    with pytest.raises(FPLWildcardParseError, match="not uniquely mapped"):
        parse_fpl_wildcard_csv(CSV, metadata(), ambiguous)
    bad = metadata()
    bad["raw_sha256"] = "0" * 64
    with pytest.raises(FPLWildcardParseError, match="SHA-256"):
        parse_fpl_wildcard_csv(CSV, bad, bootstrap())


def test_rejects_undocumented_or_missing_columns():
    with pytest.raises(FPLWildcardParseError, match="missing required"):
        parse_fpl_wildcard_csv("rank,gameweek\n1,11\n", metadata(""), bootstrap())
    with pytest.raises(FPLWildcardParseError, match="undocumented columns"):
        parse_fpl_wildcard_csv(CSV.replace("rank,gameweek", "extra,rank,gameweek"), metadata(CSV.replace("rank,gameweek", "extra,rank,gameweek")), bootstrap())



def test_wildcard_snapshot_matches_registry_and_routes_as_diagnostic_until_generation_time_is_verified():
    from forecast_provider_registry import get_active_provider
    from provider_forecast_router import route_provider_forecast

    result = parse_fpl_wildcard_csv(CSV, metadata(), bootstrap())
    snapshot = result["canonical_snapshot"]
    spec = get_active_provider("FPL Wildcard")
    assert snapshot["provider"]["product"] == spec["product"]
    assert snapshot["provider"]["variant"] == spec["forecast_variant"]

    routed = route_provider_forecast(snapshot)
    assert routed["provider_id"] == "fpl_wildcard"
    assert routed["routing_status"] == "DIAGNOSTIC_ONLY"
    assert routed["decision_eligible"] is False
    assert routed["routing_reason"] == "PROVIDER_GENERATION_TIME_NOT_DISCLOSED"
