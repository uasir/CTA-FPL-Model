from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from understat_apish_provider import (
    normalize_player_matches,
    normalize_team_histories,
    _valid_meta,
    _persist_response,
)


def test_player_history_normalizes_understat_season_and_required_fields():
    rows = normalize_player_matches([{
        "season": "2025-26", "date": "2025-08-15 15:00:00",
        "h_team": "Arsenal", "a_team": "Chelsea", "time": "90", "xG": "0.7",
    }], 76)
    assert rows[0]["season"] == "2025"
    assert rows[0]["h_team"] == "Arsenal"


def test_player_history_rejects_missing_identity_fields():
    with pytest.raises(ValueError, match="lacks"):
        normalize_player_matches([{"xG": 0.5}], 76)


def test_team_histories_require_full_epl_team_set_and_normalize_venue():
    payload = {"raw": {"teams": {
        f"id-{i}": {"title": f"Team {i}", "history": [{
            "date": "2025-08-15 15:00:00", "is_home": True, "xG": 1.2,
        }]} for i in range(20)
    }}}
    teams = normalize_team_histories(payload, "2025-26")
    assert len(teams) == 20
    assert teams["Team 0"]["history"][0]["h_a"] == "h"


def test_team_histories_reject_partial_team_list():
    with pytest.raises(ValueError, match="only 1 usable teams"):
        normalize_team_histories({"raw": {"teams": {
            "1": {"title": "Arsenal", "history": [{"date": "2025-08-15"}]}
        }}}, "2025-26")


def test_provider_cache_requires_matching_provenance_and_checksum(tmp_path):
    from understat_apish_provider import ApiShUnderstatClient
    path = tmp_path / "players" / "76.json"
    client = type("Client", (), {"last_meta": {"request_id": "test", "credits_used": 1}})()
    _persist_response(path, [{"season": "2025", "date": "2025-08-15", "h_team": "A", "a_team": "B"}],
                      kind="player", key="76", client=client)
    assert _valid_meta(path, kind="player", key="76")
    assert not _valid_meta(path, kind="player", key="87")
