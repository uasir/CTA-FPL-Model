from build_wyscout_cta_player_match_features import build_player_match_features


def test_wyscout_cta_player_match_features_separate_attempts_and_realisation():
    events = [
        {
            "id": 1, "matchId": 10, "playerId": 100, "teamId": 1,
            "eventName": "Pass", "subEventName": "Smart pass",
            "positions": [{"x": 60, "y": 50}, {"x": 75, "y": 50}],
            "tags": [{"id": 1801}, {"id": 302}, {"id": 901}],
        },
        {
            "id": 2, "matchId": 10, "playerId": 100, "teamId": 1,
            "eventName": "Pass", "subEventName": "Simple pass",
            "positions": [{"x": 60, "y": 40}, {"x": 70, "y": 40}],
            "tags": [{"id": 1802}, {"id": 201}],
        },
        {
            "id": 3, "matchId": 10, "playerId": 100, "teamId": 1,
            "eventName": "Shot", "subEventName": "Shot",
            "positions": [{"x": 88, "y": 50}],
            "tags": [{"id": 1801}, {"id": 101}, {"id": 201}],
        },
        {
            "id": 4, "matchId": 10, "playerId": 100, "teamId": 1,
            "eventName": "Others on the ball", "subEventName": "Acceleration",
            "positions": [{"x": 40, "y": 50}, {"x": 55, "y": 50}],
            "tags": [],
        },
        {
            "id": 5, "matchId": 10, "playerId": 100, "teamId": 1,
            "eventName": "Duel", "subEventName": "Ground attacking duel",
            "positions": [{"x": 55, "y": 50}],
            "tags": [{"id": 703}, {"id": 2001}],
        },
    ]
    matches = [{
        "wyId": 10, "dateutc": "2018-04-01 15:00:00",
        "gameweek": 32,
        "teamsData": {
            "1": {"teamId": 1, "side": "home"},
            "2": {"teamId": 2, "side": "away"},
        },
    }]
    players = [{"wyId": 100, "shortName": "Player A"}]
    teams = [
        {"wyId": 1, "name": "Home FC"},
        {"wyId": 2, "name": "Away FC"},
    ]

    rows, report = build_player_match_features(events, matches, players, teams)

    assert len(rows) == 1
    row = rows[0]
    assert row["provider_player_id"] == 100
    assert row["provider_player_name"] == "Player A"
    assert row["provider_team_name"] == "Home FC"
    assert row["opponent_team_name"] == "Away FC"
    assert row["home_away"] == "home"
    assert row["pass_attempts"] == 2
    assert row["pass_completions"] == 1
    assert row["key_pass_attempts"] == 1
    assert row["smart_pass_attempts"] == 1
    assert row["through_pass_attempts"] == 1
    assert row["opportunity_pass_attempts"] == 1
    assert row["progressive_pass_attempts"] == 2
    assert row["progressive_pass_completions"] == 1
    assert row["final_third_entry_pass_attempts"] == 2
    assert row["threat_creation_pass_attempts"] == 2
    assert row["threat_creation_pass_completions"] == 1
    assert row["shot_attempts"] == 1
    assert row["accurate_shot_attempts"] == 1
    assert row["goals"] == 1
    assert row["shot_opportunity_attempts"] == 1
    assert row["progressive_carry_attempts"] == 1
    assert row["dangerous_ball_losses"] == 1
    assert row["duel_events"] == 1
    assert row["duels_won"] == 1
    assert row["receiver_identity_status"] == "NOT_AVAILABLE_IN_PUBLIC_WYSCOUT_EVENT_SCHEMA"
    assert row["xg_status"] == "NOT_AVAILABLE_IN_PUBLIC_WYSCOUT_EVENT_SCHEMA"
    assert report["identity_mapping_status"] == "NOT_MAPPED_TO_FPL"
    assert report["prediction_validation"] == "NOT_EVALUATED"


def test_wyscout_cta_counts_pass_attempt_without_inventing_spatial_progression():
    events = [{
        "id": 1, "matchId": 10, "playerId": 100, "teamId": 1,
        "eventName": "Pass", "subEventName": "Simple pass",
        "positions": [], "tags": [{"id": 1802}],
    }]
    matches = [{
        "wyId": 10, "dateutc": "2018-04-01 15:00:00",
        "teamsData": {"1": {"teamId": 1, "side": "home"}},
    }]

    rows, report = build_player_match_features(
        events, matches, [{"wyId": 100, "shortName": "Player A"}],
        [{"wyId": 1, "name": "Home FC"}],
    )

    assert rows[0]["pass_attempts"] == 1
    assert rows[0]["pass_completions"] == 0
    assert rows[0]["progressive_pass_attempts"] == 0
    assert rows[0]["threat_creation_pass_attempts"] == 0
    assert report["player_match_rows"] == 1


def test_wyscout_goal_and_own_goal_tags_reconcile_to_match_score():
    events = [
        {
            "id": 1, "matchId": 10, "playerId": 100, "teamId": 1,
            "eventName": "Shot", "subEventName": "Shot",
            "positions": [{"x": 90, "y": 50}],
            "tags": [{"id": 101}, {"id": 1801}],
        },
        {
            "id": 2, "matchId": 10, "playerId": 101, "teamId": 1,
            "eventName": "Free Kick", "subEventName": "Free Kick",
            "positions": [{"x": 90, "y": 50}],
            "tags": [{"id": 101}],
        },
    ]
    events.insert(2, {"id":3,"matchId":10,"playerId":200,"teamId":2,"eventName":"Others on the ball","subEventName":"Touch","positions":[{"x":10,"y":50}],"tags":[{"id":102}]})
    events.insert(3, {"id":4,"matchId":10,"playerId":300,"teamId":2,"eventName":"Save attempt","subEventName":"Save attempt","positions":[{"x":10,"y":50}],"tags":[{"id":101}]})
    matches = [{
        "wyId": 10, "dateutc": "2018-04-01 15:00:00",
        "teamsData": {
            "1": {"teamId": 1, "side": "home", "score": 2},
            "2": {"teamId": 2, "side": "away", "score": 1},
        },
    }]
    rows, report = build_player_match_features(
        events, matches,
        [{"wyId": 100, "shortName": "Scorer"}, {"wyId": 101, "shortName": "Free kick scorer"}, {"wyId": 200, "shortName": "Own goal"}, {"wyId": 300, "shortName": "Goalkeeper"}],
        [{"wyId": 1, "name": "Home FC"}, {"wyId": 2, "name": "Away FC"}],
    )

    by_player = {row["provider_player_id"]: row for row in rows}
    assert by_player[100]["goals"] == 1
    assert by_player[101]["goals"] == 1
    assert by_player[200]["own_goals"] == 1
    assert by_player[300]["goals"] == 0
    assert report["goal_reconciliation"]["match_metadata_goals"] == 3
    assert report["goal_reconciliation"]["player_attributed_goal_total"] == 3
    assert report["goal_reconciliation"]["player_attributed_minus_metadata_goal_delta"] == 0
    assert report["goal_reconciliation"]["status"] == "PASS_EXACT"
