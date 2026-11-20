import base64
import hashlib
import json

import pytest

import capture_predeadline_decision_bundle as capture


def _encoded(value):
    return base64.b64encode(json.dumps(value, sort_keys=True).encode()).decode()


def _state():
    return {
        "squad_15": list(range(1, 16)),
        "bank": 0.9,
        "free_transfers": 1,
        "formation": "4-3-3",
        "starting_xi": list(range(1, 12)),
        "bench_order": [13, 14, 15],
        "reserve_goalkeeper_id": 12,
        "captain_id": 10,
        "vice_captain_id": 11,
        "chip_state": "NONE",
    }


def _fixtures(monkeypatch, *, fallback=False, manager_capture_time="2026-11-20T10:00:00Z",
              missing_current_price=False):
    provider_payload = {
        "gameweek": 12,
        "deadline": "2026-11-21T11:00:00Z",
        "computed_at": "2026-11-20T09:00:00Z",
        "players": [],
    }
    bootstrap = {
        "elements": [
            {"id": player_id, "element_type": element_type,
             "now_cost": 50 if not (missing_current_price and player_id == 1) else None}
            for player_id, element_type in {
                1: 1, 2: 2, 3: 2, 4: 2, 5: 2,
                6: 3, 7: 3, 8: 3, 9: 4, 10: 4, 11: 4,
                12: 1, 13: 2, 14: 3, 15: 4,
            }.items()
        ]
    }
    provider_raw = json.dumps(provider_payload, sort_keys=True).encode()
    metadata_raw = json.dumps(bootstrap, sort_keys=True).encode()
    provider_hash = hashlib.sha256(provider_raw).hexdigest()
    metadata_hash = hashlib.sha256(metadata_raw).hexdigest()
    provider_capture = {
        "provider_snapshot": {
            "snapshot_id": "fplcat-gw12-test",
            "season": "2026-27",
            "target_gameweek": 12,
            "provider": {"name": "FPL Cat", "product": "published xP",
                         "variant": "public next-gameweek JSON API", "version": "api/v1"},
            "grain": "player_gameweek",
            "records": [
                {"fpl_element_id": player_id, "expected_points": 2.0,
                 "expected_minutes": 75}
                for player_id in range(1, 16)
            ],
            "timing": {
                "deadline_utc": "2026-11-21T11:00:00Z",
                "generated_at_utc": "2026-11-20T09:00:00Z",
                "captured_at_utc": "2026-11-20T09:30:00Z",
            },
            "source": {"raw_sha256": provider_hash},
        },
        "raw_archives": {
            "provider_response_base64": base64.b64encode(provider_raw).decode(),
            "fpl_bootstrap_response_base64": base64.b64encode(metadata_raw).decode(),
        },
        "player_metadata_provenance": {
            "captured_at_utc": "2026-11-20T09:35:00Z",
            "raw_sha256": metadata_hash,
        },
    }
    picks = []
    for position, player_id in enumerate(range(1, 16), 1):
        picks.append({
            "position": position,
            "element": player_id,
            "purchase_price": 50,
            "selling_price": 50,
            "is_captain": player_id == 10,
            "is_vice_captain": player_id == 11,
        })
    manager_payload = {
        "active_chip": None,
        "entry_history": {"event": 12, "bank": 9},
        "picks": picks,
    }
    manager_raw = json.dumps(manager_payload, sort_keys=True).encode()
    manager_capture = {
        "manager_context_capture": {
            "captured_at_utc": manager_capture_time,
            "source_url": "https://fantasy.premierleague.com/api/entry/421025/event/12/picks/",
            "raw_sha256": hashlib.sha256(manager_raw).hexdigest(),
            "raw_response_base64": base64.b64encode(manager_raw).decode(),
        },
        "manager_context": {
            "bank": 0.9,
            "squad_snapshot": [
                {"fpl_element_id": player_id, "purchase_price": 5.0}
                for player_id in range(1, 16)
            ],
        },
    }
    if fallback:
        previous = {"entry_history": {"event": 11}, "picks": []}
        gw1 = {"entry_history": {"event": 1}, "picks": []}
        history = {"chips": []}
        manager_archive = {
            "source_type": "FPL_SEASON_HISTORY_RECONSTRUCTION",
            "previous_gameweek_picks": _encoded(previous),
            "gw1_picks": _encoded(gw1),
            "transfers": _encoded([]),
            "history": _encoded(history),
            "bootstrap": _encoded(bootstrap),
        }
        archive_raw = json.dumps(manager_archive, sort_keys=True, separators=(",", ":")).encode()
        manager_capture["manager_context_capture"] = {
            "captured_at_utc": manager_capture_time,
            "source_url": "https://fantasy.premierleague.com/api/entry/421025/event/12/picks/",
            "source_urls": [
                "https://fantasy.premierleague.com/api/entry/421025/event/11/picks/",
                "https://fantasy.premierleague.com/api/entry/421025/event/1/picks/",
                "https://fantasy.premierleague.com/api/entry/421025/transfers/",
                "https://fantasy.premierleague.com/api/entry/421025/history/",
                "https://fantasy.premierleague.com/api/bootstrap-static/",
            ],
            "source_type": "USER_CONFIRMED_SQUAD_WITH_FPL_HISTORY_PRICES",
            "price_source_type": "FPL_SEASON_HISTORY_RECONSTRUCTION",
            "raw_sha256": hashlib.sha256(archive_raw).hexdigest(),
            "raw_response_base64": base64.b64encode(archive_raw).decode(),
            "row_count": 15,
            "identity_verified": True,
        }
    monkeypatch.setattr(capture, "capture_fpl_cat_snapshot", lambda **kwargs: provider_capture)
    monkeypatch.setattr(capture, "capture_manager_context", lambda *args, **kwargs: manager_capture)


def test_captures_three_raw_predeadline_sources_from_official_picks(monkeypatch):
    _fixtures(monkeypatch)
    result = capture.capture_predeadline_decision_bundle(
        team_id=421025, gameweek=12, season="2026-27", manager_state=_state(),
    )
    manifest = result["12"]
    assert {row["source_type"] for row in manifest["sources"]} == {
        "provider_forecast", "player_metadata", "manager_deadline_state"
    }
    assert all(len(row["raw_sha256"]) == 64 for row in manifest["sources"])
    state = manifest["manager_state"]
    assert state["squad_15"] == list(range(1, 16))
    assert state["starting_xi"] == list(range(1, 12))
    assert state["bench_order"] == [13, 14, 15]
    assert state["reserve_goalkeeper_id"] == 12
    assert state["captain_id"] == 10
    assert state["vice_captain_id"] == 11
    assert state["bank"] == 0.9
    assert state["free_transfers"] == 1


def test_supports_user_confirmed_state_with_official_history_archive(monkeypatch):
    _fixtures(monkeypatch, fallback=True)
    result = capture.capture_predeadline_decision_bundle(
        team_id=421025, gameweek=12, season="2026-27", manager_state=_state(),
    )
    envelope = json.loads(base64.b64decode(result["12"]["sources"][2]["raw_payload_base64"]))
    assert envelope["capture_method"] == "USER_CONFIRMED_WITH_OFFICIAL_HISTORY"
    assert envelope["history_archive_base64"]
    assert result["12"]["manager_state"]["purchase_prices"]["1"] == 5.0


def test_rejects_manager_capture_at_deadline(monkeypatch):
    _fixtures(monkeypatch, manager_capture_time="2026-11-21T11:00:00Z")
    with pytest.raises(capture.DecisionCaptureError, match="must precede"):
        capture.capture_predeadline_decision_bundle(
            team_id=421025, gameweek=12, season="2026-27", manager_state=_state(),
        )


def test_rejects_chip_state(monkeypatch):
    _fixtures(monkeypatch)
    state = _state()
    state["chip_state"] = "WILDCARD"
    with pytest.raises(capture.DecisionCaptureError, match="Only chip_state NONE"):
        capture.capture_predeadline_decision_bundle(
            team_id=421025, gameweek=12, season="2026-27", manager_state=state,
        )


def test_rejects_missing_current_player_price(monkeypatch):
    _fixtures(monkeypatch, missing_current_price=True)
    with pytest.raises(capture.DecisionCaptureError, match="current price"):
        capture.capture_predeadline_decision_bundle(
            team_id=421025, gameweek=12, season="2026-27", manager_state=_state(),
        )
