import json
import pytest

from capture_fpl_cat_partner_snapshot import (
    FPL_CAT_PARTNER_URL,
    FPL_BOOTSTRAP_URL,
    PartnerCaptureError,
    capture_fpl_cat_partner_snapshot,
)


def _fixtures():
    weeks = []
    deadlines = {}
    for gw in range(12, 18):
        deadline = f"2026-11-27T18:30:00Z" if gw == 12 else f"2026-12-{4 + (gw - 13) * 7:02d}T18:30:00Z"
        deadlines[gw] = deadline
        weeks.append({"gameweek": gw, "fixtures": 1, "opponents": [{"team": "ARS", "home": False}],
                      "xp": 4.5, "expected_minutes": 80, "play_chance": 0.9,
                      "p_return": 0.4, "p_haul": 0.1, "p_blank": 0.5,
                      "xp_q10": 1.0, "xp_q90": 8.0, "breakdown": {"appearance": 2.0}})
    provider = {
        "gameweeks": [{"gameweek": gw} for gw in range(12, 18)],
        "deadline": deadlines[12],
        "computed_at": "2026-11-22T05:00:00Z",
        "players": [{"id": 1, "gameweeks": weeks}],
    }
    bootstrap = {
        "events": [{"id": gw, "deadline_time": deadlines[gw]} for gw in deadlines],
        "element_types": [{"id": 3, "singular_name_short": "MID"}],
        "elements": [{"id": 1, "element_type": 3, "team": 1, "now_cost": 100}],
    }
    return json.dumps(provider).encode(), json.dumps(bootstrap).encode()


def test_partner_capture_preserves_native_player_gameweek_grain_and_raw_provenance():
    provider_raw, bootstrap_raw = _fixtures()
    calls = []

    def fetch(url, headers):
        calls.append((url, headers))
        return provider_raw if url == FPL_CAT_PARTNER_URL else bootstrap_raw

    times = iter(["2026-11-22T06:00:00Z", "2026-11-22T06:00:01Z"])
    result = capture_fpl_cat_partner_snapshot(
        season="2026-27", api_key="test-key", fetch_bytes=fetch, clock=lambda: next(times)
    )
    snapshot = result["provider_snapshot"]
    assert calls[0][0] == FPL_CAT_PARTNER_URL
    assert calls[0][1]["Authorization"] == "Bearer test-key"
    assert snapshot["grain"] == "player_gameweek"
    assert snapshot["gameweeks"] == [12, 13, 14, 15, 16, 17]
    assert len(snapshot["records"]) == 6
    assert snapshot["records"][1]["expected_points"] == 4.5
    assert snapshot["records"][1]["fixtures_count"] == 1
    assert result["capture_status"]["fixture_level_xp_available"] is False
    assert result["capture_status"]["double_gameweek_xp_preserved_as_provider_total"] is True
    assert len(result["raw_archives"]["provider_response_base64"]) > 0


def test_partner_capture_requires_partner_key():
    with pytest.raises(PartnerCaptureError, match="FPLCAT_PARTNER_API_KEY is required"):
        capture_fpl_cat_partner_snapshot(season="2026-27", api_key="")


def test_partner_capture_rejects_incomplete_six_gameweek_player_panel():
    provider_raw, bootstrap_raw = _fixtures()
    data = json.loads(provider_raw)
    data["players"][0]["gameweeks"].pop()
    provider_raw = json.dumps(data).encode()

    def fetch(url, headers):
        return provider_raw if url == FPL_CAT_PARTNER_URL else bootstrap_raw

    times = iter(["2026-11-22T06:00:00Z", "2026-11-22T06:00:01Z"])
    with pytest.raises(PartnerCaptureError, match="complete ordered six-GW panel"):
        capture_fpl_cat_partner_snapshot(
            season="2026-27", api_key="test-key", fetch_bytes=fetch, clock=lambda: next(times)
        )


def test_partner_capture_rejects_double_gameweek_opponent_mismatch():
    provider_raw, bootstrap_raw = _fixtures()
    data = json.loads(provider_raw)
    data["players"][0]["gameweeks"][0]["fixtures"] = 2
    provider_raw = json.dumps(data).encode()

    def fetch(url, headers):
        return provider_raw if url == FPL_CAT_PARTNER_URL else bootstrap_raw

    times = iter(["2026-11-22T06:00:00Z", "2026-11-22T06:00:01Z"])
    with pytest.raises(PartnerCaptureError, match="opponent list does not match fixture count"):
        capture_fpl_cat_partner_snapshot(
            season="2026-27", api_key="test-key", fetch_bytes=fetch, clock=lambda: next(times)
        )
