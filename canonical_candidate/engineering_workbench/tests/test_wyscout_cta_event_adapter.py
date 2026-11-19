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
