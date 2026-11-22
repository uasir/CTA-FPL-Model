import base64
import hashlib
import json

import pytest

from capture_fpl_cat_snapshot import (
    CaptureError,
    FPL_BOOTSTRAP_URL,
    FPL_CAT_URL,
    capture_fpl_cat_snapshot,
)


DEADLINE = "2026-11-21T11:00:00Z"


def fixture_bytes():
    provider = {
        "gameweek": 11,
        "deadline": DEADLINE,
        "computed_at": "2026-11-20T08:30:00Z",
        "players": [
            {"id": 1, "xp": 5.25, "expected_minutes": 88},
            {"id": 2, "xp": 3.75, "expected_minutes": 72},
        ],
    }
    bootstrap = {
        "events": [{"id": 11, "deadline_time": DEADLINE}],
        "element_types": [
            {"id": 1, "singular_name_short": "GKP"},
            {"id": 2, "singular_name_short": "DEF"},
        ],
        "elements": [
            {"id": 1, "element_type": 1, "now_cost": 55, "team": 1},
            {"id": 2, "element_type": 2, "now_cost": 48, "team": 2},
        ],
    }
    return json.dumps(provider).encode(), json.dumps(bootstrap).encode()


def test_captures_provider_and_metadata_with_independent_hashes():
    provider_raw, bootstrap_raw = fixture_bytes()
    responses = {FPL_CAT_URL: provider_raw, FPL_BOOTSTRAP_URL: bootstrap_raw}
    times = iter(["2026-11-20T09:00:00Z", "2026-11-20T09:01:00Z"])
    result = capture_fpl_cat_snapshot(
        season="2026-27",
        fetch_bytes=lambda url: responses[url],
        clock=lambda: next(times),
    )
    snapshot = result["provider_snapshot"]
    assert snapshot["provider"]["name"] == "FPL Cat"
    assert snapshot["target_gameweek"] == 11
    assert snapshot["coverage"]["identity_resolution_status"] == "VERIFIED"
    assert snapshot["coverage"]["identity_resolution_method"] == "PROVIDER_PLAYER_ID_EQUALS_OFFICIAL_FPL_ELEMENT_ID"
    assert snapshot["records"][0] == {
        "fpl_element_id": 1, "expected_points": 5.25, "expected_minutes": 88
    }
    assert snapshot["source"]["raw_sha256"] == hashlib.sha256(provider_raw).hexdigest()
    assert result["player_metadata_provenance"]["raw_sha256"] == hashlib.sha256(bootstrap_raw).hexdigest()
    assert base64.b64decode(result["raw_archives"]["provider_response_base64"]) == provider_raw
    assert base64.b64decode(result["raw_archives"]["fpl_bootstrap_response_base64"]) == bootstrap_raw
    assert result["player_metadata"][0] == {
        "fpl_element_id": 1, "price": 5.5, "position": "GKP", "team_id": 1
    }


def test_rejects_provider_capture_at_or_after_deadline():
    provider_raw, bootstrap_raw = fixture_bytes()
    responses = {FPL_CAT_URL: provider_raw, FPL_BOOTSTRAP_URL: bootstrap_raw}
    times = iter(["2026-11-21T11:00:00Z", "2026-11-21T11:01:00Z"])
    with pytest.raises(CaptureError, match="at or after its deadline"):
        capture_fpl_cat_snapshot(
            season="2026-27",
            fetch_bytes=lambda url: responses[url],
            clock=lambda: next(times),
        )


def test_rejects_mismatch_with_official_fpl_deadline():
    provider_raw, bootstrap_raw = fixture_bytes()
    bootstrap = json.loads(bootstrap_raw)
    bootstrap["events"][0]["deadline_time"] = "2026-11-21T12:00:00Z"
    responses = {
        FPL_CAT_URL: provider_raw,
        FPL_BOOTSTRAP_URL: json.dumps(bootstrap).encode(),
    }
    times = iter(["2026-11-20T09:00:00Z", "2026-11-20T09:01:00Z"])
    with pytest.raises(CaptureError, match="does not match"):
        capture_fpl_cat_snapshot(
            season="2026-27",
            fetch_bytes=lambda url: responses[url],
            clock=lambda: next(times),
        )


def test_rejects_missing_player_minutes_and_unmapped_identity():
    provider_raw, bootstrap_raw = fixture_bytes()
    provider = json.loads(provider_raw)
    provider["players"][0]["expected_minutes"] = None
    responses = {
        FPL_CAT_URL: json.dumps(provider).encode(),
        FPL_BOOTSTRAP_URL: bootstrap_raw,
    }
    times = iter(["2026-11-20T09:00:00Z", "2026-11-20T09:01:00Z"])
    with pytest.raises(CaptureError, match="expected_minutes"):
        capture_fpl_cat_snapshot(
            season="2026-27",
            fetch_bytes=lambda url: responses[url],
            clock=lambda: next(times),
        )

    provider["players"][0]["expected_minutes"] = 88
    provider["players"][0]["id"] = 999
    responses[FPL_CAT_URL] = json.dumps(provider).encode()
    times = iter(["2026-11-20T09:00:00Z", "2026-11-20T09:01:00Z"])
    with pytest.raises(CaptureError, match="absent from FPL bootstrap"):
        capture_fpl_cat_snapshot(
            season="2026-27",
            fetch_bytes=lambda url: responses[url],
            clock=lambda: next(times),
        )



def test_missing_provider_generation_time_is_preserved_as_diagnostic_only():
    provider_raw, bootstrap_raw = fixture_bytes()
    provider = json.loads(provider_raw)
    provider.pop("computed_at")
    responses = {
        FPL_CAT_URL: json.dumps(provider).encode(),
        FPL_BOOTSTRAP_URL: bootstrap_raw,
    }
    times = iter(["2026-11-20T09:00:00Z", "2026-11-20T09:01:00Z"])
    result = capture_fpl_cat_snapshot(
        season="2026-27",
        fetch_bytes=lambda url: responses[url],
        clock=lambda: next(times),
    )
    assert result["provider_snapshot"]["timing"]["generated_at_utc"] is None
    assert result["capture_status"]["provider_generated_before_capture"] is False
    assert result["capture_status"]["provider_generation_time_status"] == "NOT_DISCLOSED_DIAGNOSTIC_ONLY"


def test_rejects_metadata_capture_at_or_after_deadline():
    provider_raw, bootstrap_raw = fixture_bytes()
    responses = {FPL_CAT_URL: provider_raw, FPL_BOOTSTRAP_URL: bootstrap_raw}
    times = iter(["2026-11-20T09:00:00Z", "2026-11-21T11:00:00Z"])
    with pytest.raises(CaptureError, match="metadata was retrieved at or after"):
        capture_fpl_cat_snapshot(
            season="2026-27",
            fetch_bytes=lambda url: responses[url],
            clock=lambda: next(times),
        )



def test_single_gameweek_player_level_capture_is_explicitly_not_multi_gameweek_eligible():
    provider_raw, bootstrap_raw = fixture_bytes()
    responses = {FPL_CAT_URL: provider_raw, FPL_BOOTSTRAP_URL: bootstrap_raw}
    times = iter(["2026-11-20T09:00:00Z", "2026-11-20T09:01:00Z"])
    result = capture_fpl_cat_snapshot(
        season="2026-27",
        fetch_bytes=lambda url: responses[url],
        clock=lambda: next(times),
    )
    capability = result["provider_snapshot"]["multi_gameweek_capability"]
    assert capability["status"] == "NOT_SUPPORTED_BY_CAPTURE_SCHEMA"
    assert capability["decision_eligible_for_multi_gameweek"] is False
    assert capability["available_gameweeks"] == [11]
    assert capability["available_grain"] == "player_gameweek"
    assert capability["required_grain"] == "player_fixture"
    assert "fixture_id" in capability["missing_fields"]
    assert "explicit_future_gameweek_forecast_panel" in capability["missing_fields"]
