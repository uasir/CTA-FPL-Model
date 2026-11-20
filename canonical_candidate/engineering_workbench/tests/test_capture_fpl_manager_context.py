import hashlib
import json

import pytest

import capture_fpl_manager_context as manager_capture


TEAM_ID = 421025
GAMEWEEK = 11


def picks_payload():
    return {
        "picks": [
            {"element": element, "purchase_price": 50 + element}
            for element in range(1, 16)
        ],
        "entry_history": {"bank": 9, "event": GAMEWEEK, "event_transfers": 1},
    }


def test_captures_fifteen_players_purchase_prices_and_raw_hash(monkeypatch):
    raw = json.dumps(picks_payload()).encode()
    monkeypatch.setattr(manager_capture, "fetch", lambda url: raw)
    monkeypatch.setattr(manager_capture, "utc_now", lambda: "2026-11-20T14:50:00Z")
    result = manager_capture.capture_manager_context(
        TEAM_ID, GAMEWEEK, expected_element_ids=set(range(1, 16)),
        expected_bank=0.9, free_transfers=1,
    )
    assert result["manager_context_capture"]["identity_verified"] is True
    assert result["manager_context_capture"]["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    assert len(result["manager_context"]["squad_snapshot"]) == 15
    assert result["manager_context"]["squad_snapshot"][0] == {
        "fpl_element_id": 1, "purchase_price": 5.1,
    }
    assert result["manager_context"]["bank"] == 0.9
    assert result["manager_context"]["free_transfers"] == 1
    assert result["manager_context"]["formation"] == "4-3-3"


def test_rejects_squad_identity_mismatch(monkeypatch):
    monkeypatch.setattr(manager_capture, "fetch", lambda url: json.dumps(picks_payload()).encode())
    with pytest.raises(manager_capture.CaptureError, match="squad identity mismatch"):
        manager_capture.capture_manager_context(
            TEAM_ID, GAMEWEEK, expected_element_ids=set(range(2, 17)), free_transfers=1,
        )


def test_rejects_bank_mismatch(monkeypatch):
    monkeypatch.setattr(manager_capture, "fetch", lambda url: json.dumps(picks_payload()).encode())
    with pytest.raises(manager_capture.CaptureError, match="bank mismatch"):
        manager_capture.capture_manager_context(
            TEAM_ID, GAMEWEEK, expected_bank=1.0, free_transfers=1,
        )


def test_rejects_non_fifteen_player_squad(monkeypatch):
    payload = picks_payload()
    payload["picks"].pop()
    monkeypatch.setattr(manager_capture, "fetch", lambda url: json.dumps(payload).encode())
    with pytest.raises(manager_capture.CaptureError, match="expected 15"):
        manager_capture.capture_manager_context(TEAM_ID, GAMEWEEK, free_transfers=1)


def test_rejects_invalid_purchase_price(monkeypatch):
    payload = picks_payload()
    payload["picks"][0]["purchase_price"] = 0
    monkeypatch.setattr(manager_capture, "fetch", lambda url: json.dumps(payload).encode())
    with pytest.raises(manager_capture.CaptureError, match="purchase_price"):
        manager_capture.capture_manager_context(TEAM_ID, GAMEWEEK, free_transfers=1)


def test_rejects_wrong_gameweek_response(monkeypatch):
    payload = picks_payload()
    payload["entry_history"]["event"] = 10
    monkeypatch.setattr(manager_capture, "fetch", lambda url: json.dumps(payload).encode())
    with pytest.raises(manager_capture.CaptureError, match="does not match requested"):
        manager_capture.capture_manager_context(TEAM_ID, GAMEWEEK, free_transfers=1)


def test_uses_user_confirmed_squad_when_pre_deadline_picks_return_404(monkeypatch):
    from urllib.error import HTTPError

    def unavailable(url):
        raise HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(manager_capture, "fetch", unavailable)
    monkeypatch.setattr(manager_capture, "utc_now", lambda: "2026-11-20T15:10:00Z")
    result = manager_capture.capture_manager_context(
        TEAM_ID, GAMEWEEK,
        expected_element_ids=set(range(1, 16)),
        expected_bank=0.9,
        free_transfers=1,
        allow_user_confirmed_fallback=True,
    )
    provenance = result["manager_context_capture"]
    assert provenance["source_type"] == "USER_CONFIRMED_CONTEXT"
    assert provenance["identity_verification_method"] == "user-confirmed squad IDs"
    assert provenance["identity_verified"] is True
    assert provenance["row_count"] == 15
    assert len(result["manager_context"]["squad_snapshot"]) == 15
    assert "purchase_price" not in result["manager_context"]["squad_snapshot"][0]
    assert result["manager_context"]["bank"] == 0.9
