import base64
import hashlib
import json

import pytest

import capture_predeadline_decision_bundle as capture


def _b64(value):
    return base64.b64encode(json.dumps(value, sort_keys=True).encode()).decode()


def _fixtures(monkeypatch, manager_capture_time="2026-11-20T10:00:00Z"):
    provider_payload = {
        "gameweek": 12,
        "deadline": "2026-11-21T11:00:00Z",
        "computed_at": "2026-11-20T09:00:00Z",
        "players": [],
    }
    bootstrap = {
        "elements": [
            {"id": player_id, "element_type": element_type}
            for player_id, element_type in {
                1: 1, 2: 2, 3: 2, 4: 2, 5: 2,
                6: 3, 7: 3, 8: 3, 9: 3, 10: 4, 11: 4,
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
            "target_gameweek": 12,
            "timing": {
                "deadline_utc": "2026-11-21T11:00:00Z",
                "generated_at_utc": "2026-11-20T09:00:00Z",
                "captured_at_utc": "2026-11-20T09:30:00Z",
            },
        },
        "raw_archives": {
            "provider_response_base64": base64.b64encode(provider_raw).decode(),
            "fpl_bootstrap_response_base64": base64.b64encode(metadata_raw).decode(),
        },
        "player_metadata_provenance": {
            "captured_at_utc": "2026-11-20T09:35:00Z",
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
    manager_payload = {"entry_history": {"event": 12, "bank": 9}, "picks": picks}
    manager_raw = json.dumps(manager_payload, sort_keys=True).encode()
    manager_hash = hashlib.sha256(manager_raw).hexdigest()
    manager_capture = {
        "manager_context_capture": {
            "captured_at_utc": manager_capture_time,
            "source_url": "https://fantasy.premierleague.com/api/entry/421025/event/12/picks/",
            "raw_sha256": manager_hash,
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
    monkeypatch.setattr(capture, "capture_fpl_cat_snapshot", lambda **kwargs: provider_capture)
    monkeypatch.setattr(capture, "capture_manager_context", lambda *args, **kwargs: manager_capture)


def test_captures_three_raw_predeadline_sources_and_manager_state(monkeypatch):
    _fixtures(monkeypatch)
    result = capture.capture_predeadline_decision_bundle(
        team_id=421025, gameweek=12, season="2026-27",
        expected_element_ids=set(range(1, 16)), free_transfers=1,
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


def test_rejects_manager_capture_at_deadline(monkeypatch):
    _fixtures(monkeypatch, manager_capture_time="2026-11-21T11:00:00Z")
    with pytest.raises(capture.DecisionCaptureError, match="must precede"):
        capture.capture_predeadline_decision_bundle(
            team_id=421025, gameweek=12, season="2026-27",
            expected_element_ids=set(range(1, 16)), free_transfers=1,
        )


def test_rejects_squad_identity_mismatch(monkeypatch):
    _fixtures(monkeypatch)
    with pytest.raises(capture.DecisionCaptureError, match="do not match"):
        capture.capture_predeadline_decision_bundle(
            team_id=421025, gameweek=12, season="2026-27",
            expected_element_ids=set(range(2, 17)), free_transfers=1,
        )


def test_rejects_chip_state(monkeypatch):
    _fixtures(monkeypatch)
    with pytest.raises(capture.DecisionCaptureError, match="Only chip_state NONE"):
        capture.capture_predeadline_decision_bundle(
            team_id=421025, gameweek=12, season="2026-27",
            expected_element_ids=set(range(1, 16)), free_transfers=1,
            chip_state="WILDCARD",
        )


def test_rejects_missing_selling_price(monkeypatch):
    _fixtures(monkeypatch)
    original = capture.capture_manager_context

    def missing_price(*args, **kwargs):
        result = original(*args, **kwargs)
        raw = base64.b64decode(result["manager_context_capture"]["raw_response_base64"])
        payload = json.loads(raw)
        payload["picks"][0].pop("selling_price")
        changed = json.dumps(payload, sort_keys=True).encode()
        result["manager_context_capture"]["raw_response_base64"] = base64.b64encode(changed).decode()
        return result

    monkeypatch.setattr(capture, "capture_manager_context", missing_price)
    with pytest.raises(capture.DecisionCaptureError, match="selling_price"):
        capture.capture_predeadline_decision_bundle(
            team_id=421025, gameweek=12, season="2026-27",
            expected_element_ids=set(range(1, 16)), free_transfers=1,
        )
