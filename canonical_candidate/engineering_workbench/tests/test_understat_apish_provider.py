from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from understat_apish_provider import (
    ApiShUnderstatClient,
    normalize_player_matches,
    normalize_team_history,
    reserve_monthly_calls,
)


class FakeResponse:
    status_code = 200
    headers = {}

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.headers = {}
        self.payload = payload
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append((url, params, timeout))
        return FakeResponse(self.payload)


def test_player_history_imports_raw_understat_match_rows():
    payload = {
        "success": True,
        "credits_used": 1,
        "raw": {
            "matches": [{
                "id": "9001",
                "season": "2025-26",
                "date": "2025-08-15 15:00:00",
                "h_team": "Arsenal",
                "a_team": "Chelsea",
                "time": "90",
                "xG": "0.7",
                "xA": "0.2",
            }]
        },
    }
    session = FakeSession(payload)
    client = ApiShUnderstatClient(api_key="secret", session=session)
    rows, credits = client.player_history(76)
    assert credits == 1
    assert rows[0]["season"] == "2025"
    assert rows[0]["h_team"] == "Arsenal"
    assert session.headers["x-api-key"] == "secret"
    url, params, timeout = session.calls[0]
    assert url.endswith("/player")
    assert params["id"] == "76"
    assert params["include_shots"] == "false"
    assert params["raw"] == "true"
    assert timeout == 120


def test_league_team_histories_imports_all_raw_understat_team_histories():
    payload = {
        "success": True,
        "credits_used": 1,
        "raw": {
            "teams": {
                "Arsenal": {
                    "title": "Arsenal",
                    "history": [{
                        "date": "2025-08-15 15:00:00",
                        "is_home": True,
                        "scored": 2,
                        "missed": 0,
                        "xG": 1.6,
                        "xGA": 0.4,
                        "deep": 11,
                        "deep_allowed": 3,
                        "ppda": 8.2,
                        "ppda_allowed": 12.1,
                        "pts": 3,
                    }],
                },
                "Chelsea": {
                    "title": "Chelsea",
                    "history": [{
                        "date": "2025-08-15 15:00:00",
                        "is_home": False,
                        "scored": 0,
                        "missed": 2,
                        "xG": 0.4,
                        "xGA": 1.6,
                        "deep": 3,
                        "deep_allowed": 11,
                        "ppda": 12.1,
                        "ppda_allowed": 8.2,
                        "pts": 0,
                    }],
                },
            }
        },
    }
    session = FakeSession(payload)
    client = ApiShUnderstatClient(api_key="secret", session=session)
    teams, credits = client.league_team_histories("2025-26")
    assert credits == 1
    assert set(teams) == {"Arsenal", "Chelsea"}
    assert teams["Arsenal"]["history"][0]["h_a"] == "h"
    assert teams["Arsenal"]["history"][0]["xG"] == 1.6
    _url, params, _timeout = session.calls[0]
    assert params["league"] == "EPL"
    assert params["season"] == 2025


def test_player_and_team_normalizers_reject_incomplete_rows():
    with pytest.raises(ValueError, match="identity fields"):
        normalize_player_matches([{"xG": 0.5}], 76)
    with pytest.raises(ValueError, match="lacks date"):
        normalize_team_history([{"xG": 1.2}], "Arsenal", "2025-26")


def test_missing_api_key_fails_closed(monkeypatch):
    monkeypatch.delenv("APISH_KEY", raising=False)
    with pytest.raises(RuntimeError, match="APISH_KEY is required"):
        ApiShUnderstatClient()


def test_monthly_credit_guard_reserves_and_blocks_over_budget(tmp_path: Path):
    path = tmp_path / "apish_usage.json"
    first = reserve_monthly_calls(path, 3, 5)
    assert first["calls_reserved"] == 3
    with pytest.raises(RuntimeError, match="would exceed 5 calls"):
        reserve_monthly_calls(path, 3, 5)
