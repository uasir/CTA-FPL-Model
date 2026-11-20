import base64
import hashlib
import json
from urllib.error import HTTPError

import pytest

import capture_fpl_manager_context as manager_capture


TEAM_ID = 421025
GAMEWEEK = 11


def picks_payload(event=GAMEWEEK, bank=9):
    return {
        "picks": [
            {"element": element, "purchase_price": 50 + element}
            for element in range(1, 16)
        ],
        "entry_history": {"bank": bank, "event": event, "event_transfers": 1},
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
    payload = picks_payload(event=10)
    monkeypatch.setattr(manager_capture, "fetch", lambda url: json.dumps(payload).encode())
    with pytest.raises(manager_capture.CaptureError, match="does not match requested"):
        manager_capture.capture_manager_context(TEAM_ID, GAMEWEEK, free_transfers=1)


def _history(chips=None):
    return {"chips": chips or []}


def _bootstrap(ids=range(1, 17)):
    return {"elements": [
        {"id": element, "now_cost": 60 + element, "cost_change_start": 10}
        for element in ids
    ]}


def test_uses_bootstrap_season_start_price_when_gw1_pick_price_is_missing():
    gw1 = picks_payload(event=1)
    gw1["picks"][0].pop("purchase_price")
    squad = manager_capture.reconstruct_purchase_prices(
        gw1, [], _history(), 11, set(range(1, 16)), _bootstrap()
    )
    prices = {row["fpl_element_id"]: row["purchase_price"] for row in squad}
    assert prices[1] == 5.1


def test_reconstructs_unchanged_and_transferred_players_from_season_history():
    gw1 = picks_payload(event=1)
    # Sell player 1 for player 16 in GW4; incoming price is £6.2m.
    transfers = [{
        "event": 4, "time": "2026-09-20T10:00:00Z",
        "element_out": 1, "element_out_cost": 51,
        "element_in": 16, "element_in_cost": 62,
    }]
    expected = set(range(2, 17))
    squad = manager_capture.reconstruct_purchase_prices(gw1, transfers, _history(), 11, expected)
    prices = {row["fpl_element_id"]: row["purchase_price"] for row in squad}
    assert prices[2] == 5.2
    assert prices[16] == 6.2
    assert len(prices) == 15


def test_reconstructs_rebuy_using_latest_transfer_in_cost():
    gw1 = picks_payload(event=1)
    transfers = [
        {"event": 3, "time": "2026-09-01T10:00:00Z", "element_out": 1, "element_out_cost": 51,
         "element_in": 16, "element_in_cost": 60},
        {"event": 5, "time": "2026-09-15T10:00:00Z", "element_out": 16, "element_out_cost": 60,
         "element_in": 1, "element_in_cost": 55},
    ]
    squad = manager_capture.reconstruct_purchase_prices(
        gw1, transfers, _history(), 11, set(range(1, 16))
    )
    prices = {row["fpl_element_id"]: row["purchase_price"] for row in squad}
    assert prices[1] == 5.5
    assert 16 not in prices


def test_excludes_free_hit_event_transfers():
    gw1 = picks_payload(event=1)
    transfers = [{
        "event": 4, "time": "2026-09-20T10:00:00Z",
        "element_out": 1, "element_out_cost": 51,
        "element_in": 16, "element_in_cost": 62,
    }]
    squad = manager_capture.reconstruct_purchase_prices(
        gw1, transfers, _history([{"name": "freehit", "event": 4}]),
        11, set(range(1, 16)),
    )
    assert {row["fpl_element_id"] for row in squad} == set(range(1, 16))


def test_rejects_missing_transfer_price_and_unexplained_squad():
    gw1 = picks_payload(event=1)
    transfers = [{
        "event": 4, "time": "2026-09-20T10:00:00Z",
        "element_out": 1, "element_out_cost": 51,
        "element_in": 16, "element_in_cost": None,
    }]
    with pytest.raises(manager_capture.CaptureError, match="element_in_cost"):
        manager_capture.reconstruct_purchase_prices(
            gw1, transfers, _history(), 11, set(range(2, 17))
        )
    with pytest.raises(manager_capture.CaptureError, match="identity mismatch"):
        manager_capture.reconstruct_purchase_prices(
            gw1, [], _history(), 11, set(range(2, 17))
        )


def test_pre_deadline_fallback_uses_season_history_and_archives_all_sources(monkeypatch):
    from urllib.error import HTTPError

    gw1_raw = json.dumps(picks_payload(event=1)).encode()
    transfers_raw = json.dumps([{
        "event": 4, "time": "2026-09-20T10:00:00Z",
        "element_out": 1, "element_out_cost": 51,
        "element_in": 16, "element_in_cost": 62,
    }]).encode()
    history_raw = json.dumps(_history()).encode()
    bootstrap_raw = json.dumps(_bootstrap()).encode()
    calls = []

    def fake_fetch(url):
        calls.append(url)
        if url.endswith("/event/11/picks/"):
            raise HTTPError(url, 404, "Not Found", {}, None)
        if url.endswith("/event/1/picks/"):
            return gw1_raw
        if url.endswith("/transfers/"):
            return transfers_raw
        if url.endswith("/history/"):
            return history_raw
        if url.endswith("/bootstrap-static/"):
            return bootstrap_raw
        raise AssertionError(url)

    monkeypatch.setattr(manager_capture, "fetch", fake_fetch)
    monkeypatch.setattr(manager_capture, "utc_now", lambda: "2026-11-20T15:10:00Z")
    expected = set(range(2, 17))
    result = manager_capture.capture_manager_context(
        TEAM_ID, GAMEWEEK, expected_element_ids=expected, expected_bank=0.9,
        free_transfers=1, allow_user_confirmed_fallback=True,
    )
    provenance = result["manager_context_capture"]
    assert provenance["source_type"] == "USER_CONFIRMED_SQUAD_WITH_FPL_HISTORY_PRICES"
    assert provenance["identity_verified"] is True
    assert provenance["row_count"] == 15
    assert set(calls) == {
        f"https://fantasy.premierleague.com/api/entry/{TEAM_ID}/event/11/picks/",
        f"https://fantasy.premierleague.com/api/entry/{TEAM_ID}/event/1/picks/",
        f"https://fantasy.premierleague.com/api/entry/{TEAM_ID}/transfers/",
        f"https://fantasy.premierleague.com/api/entry/{TEAM_ID}/history/",
        "https://fantasy.premierleague.com/api/bootstrap-static/",
    }
    archive_raw = base64.b64decode(provenance["raw_response_base64"], validate=True)
    assert hashlib.sha256(archive_raw).hexdigest() == provenance["raw_sha256"]
    prices = {row["fpl_element_id"]: row["purchase_price"]
              for row in result["manager_context"]["squad_snapshot"]}
    assert prices[16] == 6.2
    assert prices[2] == 5.2
    assert "bootstrap" in json.loads(archive_raw)
