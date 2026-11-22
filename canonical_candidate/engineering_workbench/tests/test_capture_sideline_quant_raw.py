import base64
import hashlib
import json

import pytest

from capture_sideline_quant_raw import (
    FPL_BOOTSTRAP_URL,
    SIDELINE_URL,
    CaptureError,
    capture_sideline_quant_raw,
)


def fixture_bytes():
    provider = {
        "schema_version": "1.0",
        "generated_at": "2026-11-20T08:00:00Z",
        "gameweek": 11,
        "deadline": "2026-11-21T11:00:00Z",
        "n_players": 672,
        "n_rows": 680,
        "produced_by": "Sideline Quant",
        "licence": {"name": "CC BY 4.0"},
        "columns": {"player_id": "FPL element id", "fixture_id": "FPL fixture id", "xP": "fixture xP"},
        "rows": [{"player_id": 1, "fixture_id": 101, "xP": 4.2}],
    }
    bootstrap = {
        "events": [{"id": 11, "deadline_time": "2026-11-21T11:00:00Z"}]
    }
    return json.dumps(provider).encode(), json.dumps(bootstrap).encode()


def run_capture(provider_raw=None, bootstrap_raw=None, times=None):
    default_provider, default_bootstrap = fixture_bytes()
    responses = {
        SIDELINE_URL.format(gameweek=11): provider_raw or default_provider,
        FPL_BOOTSTRAP_URL: bootstrap_raw or default_bootstrap,
    }
    clock_values = iter(times or ["2026-11-20T09:00:00Z", "2026-11-20T09:01:00Z"])
    return capture_sideline_quant_raw(
        season="2026-27",
        gameweek=11,
        fetch=lambda url: responses[url],
        clock=lambda: next(clock_values),
    )


def test_captures_raw_provider_bytes_and_provenance_without_guessing_row_parser():
    provider_raw, bootstrap_raw = fixture_bytes()
    result = run_capture(provider_raw, bootstrap_raw)
    assert result["provider"]["name"] == "Sideline Quant"
    assert result["coverage"]["grain"] == "player_fixture"
    assert result["coverage"]["declared_row_count"] == 680
    assert result["schema_inspection"]["normalization_status"] == "NOT_NORMALIZED"
    assert result["schema_inspection"]["row_parser_status"] == "PENDING_RAW_PAYLOAD_SCHEMA_INSPECTION"
    assert base64.b64decode(result["raw_archives"]["provider_response_base64"]) == provider_raw
    assert base64.b64decode(result["raw_archives"]["official_fpl_bootstrap_base64"]) == bootstrap_raw
    assert result["source"]["raw_sha256"] == hashlib.sha256(provider_raw).hexdigest()


def test_rejects_wrong_gameweek_and_deadline_mismatch():
    provider_raw, bootstrap_raw = fixture_bytes()
    provider = json.loads(provider_raw)
    provider["gameweek"] = 10
    with pytest.raises(CaptureError, match="Gameweek does not match"):
        run_capture(json.dumps(provider).encode(), bootstrap_raw)
    provider["gameweek"] = 11
    provider["deadline"] = "2026-11-21T12:00:00Z"
    with pytest.raises(CaptureError, match="does not match official"):
        run_capture(json.dumps(provider).encode(), bootstrap_raw)


def test_rejects_generation_after_capture_and_post_deadline_capture():
    provider_raw, bootstrap_raw = fixture_bytes()
    with pytest.raises(CaptureError, match="later than retrieval"):
        run_capture(provider_raw, bootstrap_raw, ["2026-11-20T07:59:00Z", "2026-11-20T08:01:00Z"])
    with pytest.raises(CaptureError, match="at or after its deadline"):
        run_capture(provider_raw, bootstrap_raw, ["2026-11-21T11:00:00Z", "2026-11-21T11:01:00Z"])


def test_uses_official_fpl_deadline_when_provider_deadline_is_null():
    provider_raw, bootstrap_raw = fixture_bytes()
    provider = json.loads(provider_raw)
    provider["deadline"] = None
    result = run_capture(
        json.dumps(provider).encode(),
        bootstrap_raw,
        ["2026-11-20T09:00:00Z", "2026-11-20T09:01:00Z"],
    )
    assert result["timing"]["deadline_utc"] == "2026-11-21T11:00:00Z"
    assert result["timing"]["provider_deadline_supplied"] is False
    assert result["timing"]["point_in_time_status"] == "PROVIDER_GENERATED_AND_CAPTURED_BEFORE_DEADLINE"


def test_rejects_invalid_declared_coverage():
    provider_raw, bootstrap_raw = fixture_bytes()
    provider = json.loads(provider_raw)
    provider["n_rows"] = 0
    with pytest.raises(CaptureError, match="n_rows"):
        run_capture(json.dumps(provider).encode(), bootstrap_raw)
