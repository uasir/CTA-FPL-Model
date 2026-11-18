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

    row = contextual_event_features(event, frame, attacks_right=True)

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



def test_directional_features_are_withheld_without_explicit_attack_direction():
    event = {
        "id": "event-direction-unknown",
        "type": {"name": "Pass"},
        "player": {"id": 10, "name": "Attacker"},
        "team": {"id": 1, "name": "Home"},
        "location": [60, 40],
    }
    frame = {
        "event_uuid": "event-direction-unknown",
        "freeze_frame": [
            {"teammate": True, "actor": True, "keeper": False, "location": [60, 40]},
            {"teammate": True, "actor": False, "keeper": False, "location": [90, 40]},
            {"teammate": False, "actor": False, "keeper": False, "location": [70, 50]},
        ],
    }

    row = contextual_event_features(event, frame)

    assert row["direction_known"] is False
    assert row["goal_corridor_opponents_5m"] == ""
    assert row["teammates_ahead_within_20"] == ""
    assert row["dangerous_receiving_options_open"] == ""
    assert row["threat_creation_pass_attempt"] == ""


def test_statsbomb_action_executing_team_orientation_needs_no_direction_map():
    event = {
        "id": "event-source-oriented",
        "type": {"name": "Pass"},
        "player": {"id": 10, "name": "Attacker"},
        "team": {"id": 1, "name": "Home"},
        "period": 1,
        "location": [60, 40],
        "pass": {"end_location": [90, 40]},
    }
    frame = {
        "event_uuid": "event-source-oriented",
        "freeze_frame": [
            {"teammate": True, "actor": True, "keeper": False, "location": [60, 40]},
            {"teammate": True, "actor": False, "keeper": False, "location": [90, 40]},
            {"teammate": False, "actor": False, "keeper": False, "location": [70, 50]},
            {"teammate": False, "actor": False, "keeper": True, "location": [115, 40]},
        ],
    }

    event_rows, _, report = extract_contextual_threat([event], [frame], "match-1")
    row = event_rows[0]

    assert row["direction_known"] is True
    assert row["attacks_right"] is True
    assert row["attack_direction_source"] == "statsbomb_action_executing_team_orientation"
    assert row["attack_direction_confidence"] == "source_specification"
    assert row["threat_creation_pass_attempt"] == 1
    assert report["direction_coverage"] == 1.0
    assert report["direction_sources"] == ["statsbomb_action_executing_team_orientation"]
    assert report["direction_confidence_counts"] == {"source_specification": 1}


def test_direction_can_be_required_when_source_orientation_is_not_known():
    event = {
        "id": "event-global-frame",
        "type": {"name": "Pass"},
        "player": {"id": 10, "name": "Attacker"},
        "team": {"id": 1, "name": "Home"},
        "period": 1,
        "location": [60, 40],
    }
    frame = {
        "event_uuid": "event-global-frame",
        "freeze_frame": [
            {"teammate": True, "actor": True, "keeper": False, "location": [60, 40]},
            {"teammate": False, "actor": False, "keeper": False, "location": [70, 50]},
        ],
    }

    event_rows, _, report = extract_contextual_threat(
        [event], [frame], "match-1", coordinate_orientation="requires_direction_map"
    )

    assert event_rows[0]["direction_known"] is False
    assert event_rows[0]["goal_corridor_opponents_5m"] == ""
    assert report["direction_coverage"] == 0.0


def test_receiving_lane_and_threat_creation_features_respect_attack_direction():
    event = {
        "id": "event-forward-pass",
        "type": {"name": "Pass"},
        "player": {"id": 10, "name": "Passer"},
        "team": {"id": 1, "name": "Home"},
        "location": [60, 40],
        "pass": {
            "recipient": {"id": 11, "name": "Receiver"},
            "end_location": [90, 40],
        },
    }
    frame = {
        "event_uuid": "event-forward-pass",
        "freeze_frame": [
            {"teammate": True, "actor": True, "keeper": False, "location": [60, 40]},
            {"teammate": True, "actor": False, "keeper": False, "location": [90, 40]},
            {"teammate": False, "actor": False, "keeper": False, "location": [70, 50]},
            {"teammate": False, "actor": False, "keeper": True, "location": [115, 40]},
        ],
    }

    attacks_right = contextual_event_features(event, frame, attacks_right=True)
    attacks_left = contextual_event_features(event, frame, attacks_right=False)

    assert attacks_right["pass_recipient_id"] == "11"
    assert attacks_right["receiving_options_observed_ahead"] == 1
    assert attacks_right["open_receiving_options_ahead"] == 1
    assert attacks_right["dangerous_receiving_options_open"] == 1
    assert attacks_right["threat_creation_pass_attempt"] == 1
    assert attacks_right["threat_creation_pass_completed"] == 1
    assert attacks_right["progressive_pass_attempt"] == 1
    assert attacks_left["receiving_options_observed_ahead"] == 0
    assert attacks_left["dangerous_receiving_options_open"] == 0
    assert attacks_left["threat_creation_pass_attempt"] == 0


def test_creation_reception_and_realisation_remain_separate_player_dimensions():
    common_frame = [
        {"teammate": True, "actor": True, "keeper": False, "location": [90, 40]},
        {"teammate": False, "actor": False, "keeper": False, "location": [96, 45]},
        {"teammate": False, "actor": False, "keeper": True, "location": [115, 40]},
    ]
    events = [
        {
            "id": "pass", "type": {"name": "Pass"},
            "player": {"id": 10, "name": "Creator"},
            "team": {"id": 1, "name": "Home"}, "period": 1, "location": [60, 40],
            "pass": {"recipient": {"id": 11, "name": "Receiver"}, "end_location": [90, 40]},
        },
        {
            "id": "receipt", "type": {"name": "Ball Receipt*"},
            "player": {"id": 11, "name": "Receiver"},
            "team": {"id": 1, "name": "Home"}, "period": 1, "location": [90, 40],
        },
        {
            "id": "shot", "type": {"name": "Shot"},
            "player": {"id": 11, "name": "Receiver"},
            "team": {"id": 1, "name": "Home"}, "period": 1, "location": [100, 40],
            "shot": {"statsbomb_xg": 0.2, "outcome": {"name": "Goal"}},
        },
    ]
    frames = [
        {"event_uuid": "pass", "freeze_frame": [
            {"teammate": True, "actor": True, "keeper": False, "location": [60, 40]},
            {"teammate": True, "actor": False, "keeper": False, "location": [90, 40]},
            {"teammate": False, "actor": False, "keeper": False, "location": [70, 50]},
            {"teammate": False, "actor": False, "keeper": True, "location": [115, 40]},
        ]},
        {"event_uuid": "receipt", "freeze_frame": common_frame},
        {"event_uuid": "shot", "freeze_frame": common_frame},
    ]
    directions = {("match-1", "1", "1"): True}

    event_rows, player_rows, report = extract_contextual_threat(
        events, frames, "match-1", direction_map=directions
    )
    by_player = {row["player_id"]: row for row in player_rows}

    assert by_player["10"]["threat_creation_pass_attempts"] == 1
    assert by_player["10"]["threat_involvement_dangerous_receipts"] == 0
    assert by_player["10"]["threat_realisation_shots"] == 0
    assert by_player["11"]["threat_creation_pass_attempts"] == 0
    assert by_player["11"]["threat_involvement_dangerous_receipts"] == 1
    assert by_player["11"]["threat_realisation_shots"] == 1
    assert by_player["11"]["threat_realisation_xg"] == 0.2
    assert by_player["11"]["threat_realisation_goals"] == 1
    assert report["events_with_known_attack_direction"] == 3
    assert report["direction_coverage"] == 1.0
    assert report["threat_creation_pass_attempts"] == 1
    assert report["threat_creation_pass_completions"] == 1
    assert report["receiving_options_observed_ahead"] == 1
    assert report["receiving_options_assessed_ahead"] == 1
    assert report["open_receiving_options_ahead"] == 1
    assert report["dangerous_receiving_options_open"] == 1
    assert report["events_with_dangerous_open_receiving_options"] == 1
    assert report["threat_involvement_dangerous_receipts"] == 1
    assert report["threat_realisation_shots"] == 1
    assert report["threat_realisation_xg"] == 0.2
    assert report["threat_realisation_goals"] == 1
    assert report["aggregation_policy"].startswith("Creation, involvement, receiving opportunity")


def test_direction_map_is_match_period_and_team_scoped(tmp_path):
    direction_file = tmp_path / "direction_map.csv"
    direction_file.write_text(
        "match_id,period,team,attacks_right\nmatch-1,1,1,true\nmatch-1,1,Away,false\n",
        encoding="utf-8",
    )

    from extract_statsbomb_contextual_threat import read_direction_map

    directions = read_direction_map(direction_file)

    assert directions[("match-1", "1", "1")] is True
    assert directions[("match-1", "1", "Away")] is False


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



def test_real_statsbomb_360_fixture_subset_extracts_context_without_fpl_join():
    import json

    fixture_root = Path(__file__).resolve().parent / "fixtures" / "3895320"
    events = json.loads((fixture_root / "events" / "3895320.json").read_text())
    frames = json.loads((fixture_root / "three-sixty" / "3895320.json").read_text())

    event_rows, player_rows, report = extract_contextual_threat(events, frames, "3895320")

    assert report["status"] == "PASS_STRUCTURAL_ONLY"
    assert report["prediction_validation"] == "NOT_EVALUATED"
    assert report["duplicate_360_event_uuids"] == 0
    assert report["events_with_usable_360_context"] > 0
    assert len(player_rows) > 0
    assert all(row["match_id"] == "3895320" for row in player_rows)
    assert all(row["feature_scope"] == "360_sampled_events_only_not_full_match_totals" for row in player_rows)
