from build_11footy_historical_fpl_identity_candidates import build_identity_review_queue, attach_current_candidates


def _teams():
    names = [
        "Arsenal", "Bournemouth", "Brighton", "Burnley", "Chelsea",
        "Crystal Palace", "Everton", "Huddersfield", "Leicester", "Liverpool",
        "Man City", "Man Utd", "Newcastle", "Southampton", "Stoke",
        "Swansea", "Spurs", "Watford", "West Brom", "West Ham",
    ]
    return [{"season": "2017-18", "team": i + 1, "team_name": name} for i, name in enumerate(names)]


def test_11footy_historical_fpl_candidates_use_minutes_goals_assists_and_team():
    provider_rows = []
    fpl_history = []
    dates = ["2018-04-01", "2018-04-08", "2018-04-15"]
    for index, date in enumerate(dates):
        match_id = 500 + index
        fixture_id = 900 + index
        goals = 1 if index == 0 else 0
        provider_rows.append({
            "match_id": match_id, "kickoff_utc": date + "T15:00:00Z",
            "home_team_name": "Arsenal", "away_team_name": "Bournemouth",
            "player_id": 100, "provider_player_id": 100,
            "team_id": 1, "player_team_name": "Arsenal",
            "minutes_played": 90, "goals": goals, "own_goals": 0, "assists": 0,
        })
        fpl_history.extend([
            {"element": 10, "fixture": fixture_id, "kickoff_time": date + "T15:00:00Z",
             "opponent_team": 2, "was_home": "True", "minutes": 90,
             "goals_scored": goals, "own_goals": 0, "assists": 0},
            {"element": 99, "fixture": fixture_id, "kickoff_time": date + "T15:00:00Z",
             "opponent_team": 1, "was_home": "False", "minutes": 90,
             "goals_scored": 0, "own_goals": 0, "assists": 0},
        ])

    candidates, report = build_identity_review_queue(
        provider_rows,
        {100: "Player A"},
        {100: "1990-01-01"},
        [{"id": 10, "code": 1000, "first_name": "Player", "second_name": "A", "team": 1}],
        [{"id": 10, "first_name": "Player", "second_name": "A"}],
        fpl_history,
        _teams(),
    )

    row = candidates[0]
    assert row["candidate_fpl_element_id"] == 10
    assert row["provider_birth_date"] == "1990-01-01"
    assert row["fixture_mapped_rows"] == 3
    assert row["fpl_history_overlap_rows"] == 3
    assert row["minutes_exact_rows"] == 3
    assert row["full_signature_exact_rows"] == 3
    assert row["review_priority"] == "P1_MULTI_MATCH_TEAM_SIGNATURE"
    assert row["verification_status"] == "PENDING"
    assert report["provider_matches_with_fixture_status"] == {"matched": 3}
    assert report["verification_status"] == "NO_CANDIDATE_AUTO_VERIFIED"


def test_11footy_historical_fpl_candidates_keep_ambiguous_names_unresolved():
    provider_rows = [{
        "match_id": 500, "kickoff_utc": "2018-04-01T15:00:00Z",
        "home_team_name": "Arsenal", "away_team_name": "Bournemouth",
        "player_id": 100, "provider_player_id": 100,
        "team_id": 1, "player_team_name": "Arsenal",
        "minutes_played": 90, "goals": 0, "own_goals": 0, "assists": 0,
    }]
    candidates, report = build_identity_review_queue(
        provider_rows,
        {100: "Alex Smith"},
        {100: "1990-01-01"},
        [
            {"id": 10, "code": 1000, "first_name": "Alex", "second_name": "Smith", "team": 1},
            {"id": 11, "code": 1001, "first_name": "Alex", "second_name": "Smith", "team": 2},
        ],
        [
            {"id": 10, "first_name": "Alex", "second_name": "Smith"},
            {"id": 11, "first_name": "Alex", "second_name": "Smith"},
        ],
        [],
        _teams(),
    )

    assert candidates[0]["candidate_status"] == "AMBIGUOUS"
    assert candidates[0]["candidate_fpl_element_id"] == ""
    assert candidates[0]["verification_status"] == "AMBIGUOUS"
    assert report["ambiguous_name_candidate_count"] == 1
    assert report["exact_name_unique_candidate_count"] == 0


def test_historical_identity_candidates_join_current_fpl_candidates_without_verifying():
    historical = [
        {
            "provider_player_id": 100,
            "candidate_fpl_element_id": 10,
            "verification_status": "PENDING",
            "review_priority": "P1_MULTI_MATCH_TEAM_SIGNATURE",
            "candidate_status": "PENDING",
        },
        {
            "provider_player_id": 200,
            "candidate_fpl_element_id": 20,
            "verification_status": "PENDING",
            "review_priority": "P2_TEAM_AND_FULL_SIGNATURE",
            "candidate_status": "PENDING",
        },
        {
            "provider_player_id": 300,
            "candidate_fpl_element_id": 30,
            "verification_status": "PENDING",
            "review_priority": "P1_MULTI_MATCH_TEAM_SIGNATURE",
            "candidate_status": "PENDING",
        },
    ]
    current = [
        {
            "provider_player_id": 100, "fpl_element_id": 1,
            "fpl_player_code": 1001, "fpl_player_name": "Player A",
            "fpl_team_id": 1, "fpl_team_name": "Arsenal",
            "fpl_birth_date": "1990-01-01", "confidence_level": "high",
            "verification_status": "pending",
        },
        {
            "provider_player_id": 200, "fpl_element_id": 2,
            "fpl_player_code": 2002, "fpl_player_name": "Player B",
            "fpl_team_id": 2, "fpl_team_name": "Bournemouth",
            "fpl_birth_date": "", "confidence_level": "review_required",
            "verification_status": "pending",
        },
    ]

    rows, report = attach_current_candidates(historical, current)

    assert rows[0]["current_fpl_element_id"] == 1
    assert rows[0]["cross_season_review_priority"] == "P1_HISTORICAL_AND_CURRENT_HIGH"
    assert rows[1]["current_fpl_element_id"] == 2
    assert rows[1]["cross_season_review_priority"] == "P3_HISTORICAL_P2_CURRENT_REVIEW"
    assert rows[2]["current_candidate_status"] == "NO_CURRENT_CANDIDATE"
    assert rows[2]["cross_season_review_priority"] == "P2_HISTORICAL_P1_CURRENT_NOT_HIGH"
    assert all(row["verification_status"] == "PENDING" for row in rows)
    assert report["historical_current_provider_id_overlap"] == 2
    assert report["historical_current_high_confidence_overlap"] == 1
