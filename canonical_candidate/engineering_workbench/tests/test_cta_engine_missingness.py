from cta_engine import build_features


def _shot_event(xg_marker=None):
    event = {
        "_match_id": "match-1",
        "_event_index": 0,
        "period": 1,
        "possession": 1,
        "team": {"name": "Home"},
        "possession_team": {"name": "Home"},
        "type": {"name": "Shot"},
        "player": {"id": "wyscout:10", "name": "Player A"},
        "minute": 1,
        "second": 5,
        "location": [105.0, 40.0],
        "shot": {"outcome": {"name": "Unknown"}},
    }
    if xg_marker is not None:
        event["shot"]["statsbomb_xg"] = xg_marker
    return event


def test_missing_provider_xg_is_not_encoded_as_zero():
    sequences, players = build_features(
        [_shot_event()], {("match-1", 1, "Home"): True}, None
    )

    assert sequences[0]["shot_count"] == 1
    assert sequences[0]["shot_xg_observed_count"] == 0
    assert sequences[0]["shot_xg_reference_only"] == ""
    assert "shot_xg_reference_only" not in players["wyscout:10"]
    assert "shot_xg_observed_count" not in players["wyscout:10"]


def test_observed_xg_is_retained_and_counted():
    sequences, players = build_features(
        [_shot_event(0.17)], {("match-1", 1, "Home"): True}, None
    )

    assert sequences[0]["shot_xg_observed_count"] == 1
    assert sequences[0]["shot_xg_reference_only"] == 0.17
    assert players["wyscout:10"]["shot_xg_reference_only"] == 0.17
    assert players["wyscout:10"]["shot_xg_observed_count"] == 1
