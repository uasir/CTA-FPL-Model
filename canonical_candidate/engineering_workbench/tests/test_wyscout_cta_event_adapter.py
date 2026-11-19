from build_wyscout_cta_event_adapter import normalize_wyscout_events


def test_adapter_scales_attacking_relative_coordinates_and_namespaces_ids():
    events = [
        {"id": 1, "matchPeriod": "1H", "eventSec": 10, "teamId": 1,
         "playerId": 10, "eventName": "Pass", "positions": [
             {"x": 20, "y": 50}, {"x": 80, "y": 40}],
         "tags": [{"id": 1801}]},
        {"id": 2, "matchPeriod": "1H", "eventSec": 12, "teamId": 1,
         "playerId": 10, "eventName": "Shot", "positions": [
             {"x": 90, "y": 50}], "tags": []},
        {"id": 3, "matchPeriod": "1H", "eventSec": 15, "teamId": 2,
         "playerId": 20, "eventName": "Pass", "positions": [
             {"x": 30, "y": 50}, {"x": 40, "y": 50}], "tags": [{"id": 1802}]},
    ]
    rows, report = normalize_wyscout_events(
        events,
        [{"wyId": 10, "shortName": "A"}, {"wyId": 20, "shortName": "B"}],
        [{"wyId": 1, "name": "Home"}, {"wyId": 2, "name": "Away"}],
        "match-1",
    )
    assert rows[0]["location"] == [24.0, 40.0]
    assert rows[0]["pass"]["end_location"] == [96.0, 32.0]
    assert rows[0]["player"]["id"] == "wyscout:10"
    assert rows[0]["possession"] == rows[1]["possession"]
    assert rows[2]["possession"] != rows[1]["possession"]
    assert rows[2]["pass"]["outcome"]["name"] == "Inaccurate"
    assert report["possession_method"] == "INFERRED_CONTIGUOUS_TEAM_BLOCK"


def test_adapter_does_not_invent_recipient_pressure_or_xg():
    events = [{
        "id": 1, "matchPeriod": "2H", "eventSec": 5, "teamId": 1,
        "playerId": 10, "eventName": "Pass", "positions": [
            {"x": 10, "y": 20}, {"x": 20, "y": 30}], "tags": [],
    }]
    rows, _ = normalize_wyscout_events(
        events, [{"wyId": 10, "shortName": "A"}], [{"wyId": 1, "name": "Home"}], 99
    )
    assert "recipient" not in rows[0]["pass"]
    assert "under_pressure" not in rows[0]
    assert "statsbomb_xg" not in rows[0].get("shot", {})
    assert rows[0]["pass"]["outcome"]["name"] == "Unknown"


def test_adapter_preserves_goal_tag_for_cta_xg_fit():
    events = [{
        "id": 8, "matchPeriod": "1H", "eventSec": 30, "teamId": 1,
        "playerId": 10, "eventName": "Shot", "positions": [
            {"x": 95, "y": 50}], "tags": [{"id": 101}],
    }]
    rows, _ = normalize_wyscout_events(
        events, [{"wyId": 10, "shortName": "Scorer"}],
        [{"wyId": 1, "name": "Home"}], 101
    )
    assert rows[0]["shot"]["outcome"]["name"] == "Goal"


def test_adapter_preserves_events_without_a_player_actor():
    events = [{
        "id": 9, "matchPeriod": "1H", "eventSec": 20, "teamId": 1,
        "playerId": 0, "eventName": "Duel", "positions": [
            {"x": 40, "y": 50}], "tags": [],
    }]
    rows, report = normalize_wyscout_events(
        events, [{"wyId": 10, "shortName": "A"}],
        [{"wyId": 1, "name": "Home"}], 99
    )
    assert len(rows) == 1
    assert "player" not in rows[0]
    assert report["actor_quality_counts"]["missing_player_id"] == 1


def test_adapter_preserves_unresolved_provider_id_without_fabricating_name():
    events = [{
        "id": 10, "matchPeriod": "1H", "eventSec": 25, "teamId": 1,
        "playerId": 999, "eventName": "Pass", "positions": [
            {"x": 20, "y": 50}, {"x": 30, "y": 50}], "tags": [{"id": 1801}],
    }]
    rows, report = normalize_wyscout_events(
        events, [{"wyId": 10, "shortName": "A"}],
        [{"wyId": 1, "name": "Home"}], 99
    )
    assert rows[0]["player"] == {"id": "wyscout:999", "name": ""}
    assert report["actor_quality_counts"]["unresolved_player_metadata"] == 1


def test_adapter_maps_direct_free_kick_shots_to_shots():
    events = [{
        "id": 11, "matchPeriod": "2H", "eventSec": 45, "teamId": 1,
        "playerId": 10, "eventName": "Free Kick", "subEventName": "Free kick shot",
        "positions": [{"x": 90, "y": 50}], "tags": [{"id": 101}],
    }]
    rows, report = normalize_wyscout_events(
        events, [{"wyId": 10, "shortName": "A"}],
        [{"wyId": 1, "name": "Home"}], 99
    )
    assert rows[0]["type"]["name"] == "Shot"
    assert rows[0]["shot"]["outcome"]["name"] == "Goal"
    assert report["free_kick_shots_mapped_to_shot"] == 1


def test_duel_outcome_tags_prevent_false_possession_switches():
    events = [
        {"id": 1, "matchPeriod": "1H", "eventSec": 1, "teamId": 1,
         "playerId": 10, "eventName": "Pass", "positions": [
             {"x": 20, "y": 50}, {"x": 30, "y": 50}], "tags": [{"id": 1801}]},
        {"id": 2, "matchPeriod": "1H", "eventSec": 2, "teamId": 2,
         "playerId": 20, "eventName": "Duel", "subEventName": "Ground defending duel",
         "positions": [{"x": 30, "y": 50}, {"x": 31, "y": 50}], "tags": [{"id": 701}]},
        {"id": 3, "matchPeriod": "1H", "eventSec": 2, "teamId": 1,
         "playerId": 10, "eventName": "Duel", "subEventName": "Ground attacking duel",
         "positions": [{"x": 31, "y": 50}, {"x": 32, "y": 50}], "tags": [{"id": 703}]},
        {"id": 4, "matchPeriod": "1H", "eventSec": 3, "teamId": 1,
         "playerId": 10, "eventName": "Duel", "subEventName": "Ground attacking duel",
         "positions": [{"x": 32, "y": 50}, {"x": 33, "y": 50}], "tags": [{"id": 701}]},
        {"id": 5, "matchPeriod": "1H", "eventSec": 4, "teamId": 2,
         "playerId": 20, "eventName": "Pass", "positions": [
             {"x": 33, "y": 50}, {"x": 40, "y": 50}], "tags": [{"id": 1801}]},
    ]
    rows, report = normalize_wyscout_events(
        events, [{"wyId": 10, "shortName": "A"}, {"wyId": 20, "shortName": "B"}],
        [{"wyId": 1, "name": "Home"}, {"wyId": 2, "name": "Away"}], 101
    )
    assert rows[0]["possession"] == rows[1]["possession"] == rows[2]["possession"] == rows[3]["possession"]
    assert rows[1]["possession_team"]["name"] == "Home"
    assert rows[1]["team"]["name"] == "Away"
    assert rows[4]["possession"] != rows[3]["possession"]
    assert report["possession_boundary_reason_counts"]["duel_lost"] == 1


def test_foul_does_not_transfer_possession_to_fouling_team_and_restart_starts_new_one():
    events = [
        {"id": 1, "matchPeriod": "1H", "eventSec": 1, "teamId": 1,
         "playerId": 10, "eventName": "Pass", "positions": [
             {"x": 20, "y": 50}, {"x": 30, "y": 50}], "tags": [{"id": 1801}]},
        {"id": 2, "matchPeriod": "1H", "eventSec": 2, "teamId": 2,
         "playerId": 20, "eventName": "Foul", "subEventName": "Foul",
         "positions": [{"x": 30, "y": 50}], "tags": []},
        {"id": 3, "matchPeriod": "1H", "eventSec": 5, "teamId": 1,
         "playerId": 10, "eventName": "Free Kick", "subEventName": "Free Kick",
         "positions": [{"x": 30, "y": 50}, {"x": 35, "y": 50}], "tags": [{"id": 1801}]},
    ]
    rows, _ = normalize_wyscout_events(
        events, [{"wyId": 10, "shortName": "A"}, {"wyId": 20, "shortName": "B"}],
        [{"wyId": 1, "name": "Home"}, {"wyId": 2, "name": "Away"}], 102
    )
    assert rows[0]["possession"] == rows[1]["possession"]
    assert rows[1]["possession_team"]["name"] == "Home"
    assert rows[2]["possession"] != rows[1]["possession"]
    assert rows[2]["possession_team"]["name"] == "Home"


def test_neutral_duel_does_not_create_a_new_possession():
    events = [
        {"id": 1, "matchPeriod": "1H", "eventSec": 1, "teamId": 1,
         "playerId": 10, "eventName": "Pass", "positions": [
             {"x": 20, "y": 50}, {"x": 30, "y": 50}], "tags": [{"id": 1801}]},
        {"id": 2, "matchPeriod": "1H", "eventSec": 2, "teamId": 2,
         "playerId": 20, "eventName": "Duel", "subEventName": "Ground loose ball duel",
         "positions": [{"x": 30, "y": 50}, {"x": 31, "y": 50}], "tags": [{"id": 702}]},
        {"id": 3, "matchPeriod": "1H", "eventSec": 3, "teamId": 1,
         "playerId": 10, "eventName": "Pass", "positions": [
             {"x": 31, "y": 50}, {"x": 40, "y": 50}], "tags": [{"id": 1801}]},
    ]
    rows, _ = normalize_wyscout_events(
        events, [{"wyId": 10, "shortName": "A"}, {"wyId": 20, "shortName": "B"}],
        [{"wyId": 1, "name": "Home"}, {"wyId": 2, "name": "Away"}], 103
    )
    assert rows[0]["possession"] == rows[1]["possession"] == rows[2]["possession"]
    assert rows[1]["possession_team"]["name"] == "Home"
