import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from extract_statsbomb_contextual_threat import (
    contextual_event_features,
    extract_contextual_threat,
)


def test_360_context_measures_defensive_pressure_and_support_geometry():
    event = {
        "id": "event-1",
        "type": {"name": "Pass"},
        "player": {"id": 10, "name": "Attacker"},
        "team": {"id": 1, "name": "Home"},
        "location": [60, 40],
        "under_pressure": True,
        "period": 1,
        "minute": 30,
        "second": 12,
    }
    frame = {
        "event_uuid": "event-1",
        "freeze_frame": [
            {"teammate": True, "actor": True, "keeper": False, "location": [60, 40]},
            {"teammate": False, "actor": False, "keeper": False, "location": [65, 40]},
            {"teammate": False, "actor": False, "keeper": False, "location": [80, 40]},
            {"teammate": False, "actor": False, "keeper": True, "location": [115, 40]},
            {"teammate": True, "actor": False, "keeper": False, "location": [70, 30]},
            {"teammate": False, "actor": False, "keeper": False, "location": [130, 40]},
        ],
    }

    row = contextual_event_features(event, frame)

    assert row["player_id"] == "10"
    assert row["under_pressure"] is True
    assert row["visible_opponents"] == 3
    assert row["opponents_within_5"] == 1
    assert row["opponents_within_10"] == 1
    assert row["nearest_opponent_distance"] == 5.0
    assert row["goalkeeper_distance"] == 55.0
    assert row["goal_corridor_opponents_5m"] == 2
    assert row["goal_side_opponents_12m"] == 2
    assert row["teammates_ahead_within_20"] == 1
    assert row["excluded_out_of_bounds_frame_players"] == 1


def test_missing_360_frame_is_not_imputed_as_zero_context():
    event = {
        "id": "event-2",
        "type": {"name": "Carry"},
        "player": {"id": 11, "name": "Carrier"},
        "team": {"id": 1, "name": "Home"},
        "location": [40, 40],
    }
    event_rows, player_rows, report = extract_contextual_threat([event], [], "match-1")

    assert event_rows == []
    assert player_rows == []
    assert report["supported_events"] == 1
    assert report["unmatched_supported_events_without_frame"] == 1
    assert report["event_context_coverage"] == 0.0


def test_player_match_aggregation_is_scoped_to_sampled_360_events():
    events = [
        {
            "id": "pass-1", "type": {"name": "Pass"},
            "player": {"id": 10, "name": "Attacker"},
            "team": {"id": 1, "name": "Home"}, "location": [60, 40],
            "under_pressure": True,
        },
        {
            "id": "shot-1", "type": {"name": "Shot"},
            "player": {"id": 10, "name": "Attacker"},
            "team": {"id": 1, "name": "Home"}, "location": [100, 40],
        },
    ]
    frames = [
        {
            "event_uuid": "pass-1",
            "freeze_frame": [
                {"teammate": True, "actor": True, "keeper": False, "location": [60, 40]},
                {"teammate": False, "actor": False, "keeper": False, "location": [66, 40]},
            ],
        },
        {
            "event_uuid": "shot-1",
            "freeze_frame": [
                {"teammate": True, "actor": True, "keeper": False, "location": [100, 40]},
                {"teammate": False, "actor": False, "keeper": True, "location": [115, 40]},
            ],
        },
    ]

    event_rows, player_rows, report = extract_contextual_threat(events, frames, "match-1")

    assert len(event_rows) == 2
    assert len(player_rows) == 1
    assert player_rows[0]["contextual_events"] == 2
    assert player_rows[0]["pressured_contextual_events"] == 1
    assert player_rows[0]["shot_context_events"] == 1
    assert player_rows[0]["pass_context_events"] == 1
    assert player_rows[0]["feature_scope"] == "360_sampled_events_only_not_full_match_totals"
    assert report["player_match_rows"] == 1
    assert report["prediction_validation"] == "NOT_EVALUATED"


def test_duplicate_frame_uuid_is_reported_and_only_one_is_used():
    event = {
        "id": "event-1", "type": {"name": "Pass"},
        "player": {"id": 10, "name": "Attacker"},
        "team": {"id": 1, "name": "Home"}, "location": [60, 40],
    }
    frame = {
        "event_uuid": "event-1",
        "freeze_frame": [
            {"teammate": True, "actor": True, "keeper": False, "location": [60, 40]},
        ],
    }
    event_rows, _, report = extract_contextual_threat([event], [frame, frame], "match-1")

    assert len(event_rows) == 1
    assert report["duplicate_360_event_uuids"] == 1
