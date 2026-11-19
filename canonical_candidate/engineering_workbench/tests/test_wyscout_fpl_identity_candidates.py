from build_wyscout_fpl_identity_candidates import build_candidate_review_queue, read_csv


def _teams():
    names = [
        "Arsenal", "Bournemouth", "Brighton", "Burnley", "Chelsea",
        "Crystal Palace", "Everton", "Huddersfield", "Leicester", "Liverpool",
        "Man City", "Man Utd", "Newcastle", "Southampton", "Stoke",
        "Swansea", "Spurs", "Watford", "West Brom", "West Ham",
    ]
    return [{"season": "2017-18", "team": i + 1, "team_name": name} for i, name in enumerate(names)]


def test_wyscout_fpl_identity_candidates_use_exact_names_and_match_history_only():
    player_match_rows = [
        {
            "provider_match_id": 500, "match_date": "2018-04-01",
            "provider_player_id": 100, "provider_player_name": "Player A",
            "provider_team_name": "Arsenal", "opponent_team_name": "Bournemouth",
            "home_away": "home", "goals": 1, "own_goals": 0, "assists": 0,
        },
        {
            "provider_match_id": 500, "match_date": "2018-04-01",
            "provider_player_id": 200, "provider_player_name": "Player B",
            "provider_team_name": "Bournemouth", "opponent_team_name": "Arsenal",
            "home_away": "away", "goals": 0, "own_goals": 0, "assists": 1,
        },
    ]
    wyscout_players = [
        {"wyId": 100, "firstName": "Player", "lastName": "A", "birthDate": "1990-01-01"},
        {"wyId": 200, "firstName": "Player", "lastName": "B", "birthDate": "1991-01-01"},
    ]
    fpl_players = [
        {"id": 10, "code": 1000, "first_name": "Player", "second_name": "A", "team": 1,
         "goals_scored": 1, "assists": 0, "minutes": 90},
        {"id": 20, "code": 2000, "first_name": "Player", "second_name": "B", "team": 2,
         "goals_scored": 0, "assists": 1, "minutes": 90},
    ]
    fpl_idlist = [
        {"id": 10, "first_name": "Player", "second_name": "A"},
        {"id": 20, "first_name": "Player", "second_name": "B"},
    ]
    fpl_history = [
        {"element": 10, "fixture": 900, "kickoff_time": "2018-04-01T15:00:00Z",
         "opponent_team": 2, "was_home": "True", "minutes": 90,
         "goals_scored": 1, "own_goals": 0, "assists": 0},
        {"element": 20, "fixture": 900, "kickoff_time": "2018-04-01T15:00:00Z",
         "opponent_team": 1, "was_home": "False", "minutes": 90,
         "goals_scored": 0, "own_goals": 0, "assists": 1},
    ]

    candidates, report = build_candidate_review_queue(
        player_match_rows, wyscout_players, fpl_players, fpl_idlist,
        fpl_history, _teams(),
    )

    by_provider = {row["provider_player_id"]: row for row in candidates}
    assert by_provider[100]["candidate_fpl_element_id"] == 10
    assert by_provider[200]["candidate_fpl_element_id"] == 20
    assert by_provider[100]["review_priority"] == "P2_TEAM_AND_STAT_CROSSCHECK"
    assert by_provider[200]["review_priority"] == "P2_TEAM_AND_STAT_CROSSCHECK"
    assert by_provider[100]["goal_assist_signature_exact_rows"] == 1
    assert by_provider[200]["goal_assist_signature_exact_rows"] == 1
    assert all(row["verification_status"] == "PENDING" for row in candidates)
    assert report["wyscout_matches_with_fixture_status"] == {"matched": 1}
    assert report["verification_status"] == "NO_CANDIDATE_AUTO_VERIFIED"


def test_wyscout_fpl_identity_candidates_keep_ambiguous_names_unresolved():
    player_match_rows = [{
        "provider_match_id": 500, "match_date": "2018-04-01",
        "provider_player_id": 100, "provider_player_name": "Alex Smith",
        "provider_team_name": "Arsenal", "opponent_team_name": "Bournemouth",
        "home_away": "home", "goals": 0, "own_goals": 0, "assists": 0,
    }]
    wyscout_players = [{"wyId": 100, "firstName": "Alex", "lastName": "Smith"}]
    fpl_players = [
        {"id": 10, "code": 1000, "first_name": "Alex", "second_name": "Smith", "team": 1},
        {"id": 11, "code": 1001, "first_name": "Alex", "second_name": "Smith", "team": 2},
    ]
    fpl_idlist = [
        {"id": 10, "first_name": "Alex", "second_name": "Smith"},
        {"id": 11, "first_name": "Alex", "second_name": "Smith"},
    ]

    candidates, report = build_candidate_review_queue(
        player_match_rows, wyscout_players, fpl_players, fpl_idlist,
        [], _teams(),
    )

    assert candidates[0]["candidate_status"] == "AMBIGUOUS"
    assert candidates[0]["candidate_fpl_element_id"] == ""
    assert candidates[0]["verification_status"] == "AMBIGUOUS"
    assert report["ambiguous_name_candidate_count"] == 1
    assert report["exact_name_unique_candidate_count"] == 0


def test_zero_goal_assist_agreement_does_not_create_strong_identity_priority():
    dates = ["2018-04-01", "2018-04-08", "2018-04-15"]
    player_match_rows = []
    fpl_history = []
    for index, date in enumerate(dates):
        match_id = 500 + index
        fixture_id = 900 + index
        player_match_rows.append({
            "provider_match_id": match_id, "match_date": date,
            "provider_player_id": 100, "provider_player_name": "Player A",
            "provider_team_name": "Arsenal", "opponent_team_name": "Bournemouth",
            "home_away": "home", "goals": 0, "own_goals": 0, "assists": 0,
        })
        fpl_history.extend([
            {"element": 10, "fixture": fixture_id, "kickoff_time": date + "T15:00:00Z",
             "opponent_team": 2, "was_home": "True", "minutes": 90,
             "goals_scored": 0, "own_goals": 0, "assists": 0},
            {"element": 99, "fixture": fixture_id, "kickoff_time": date + "T15:00:00Z",
             "opponent_team": 1, "was_home": "False", "minutes": 90,
             "goals_scored": 0, "own_goals": 0, "assists": 0},
        ])
    candidates, report = build_candidate_review_queue(
        player_match_rows,
        [{"wyId": 100, "firstName": "Player", "lastName": "A"}],
        [{"id": 10, "code": 1000, "first_name": "Player", "second_name": "A", "team": 1}],
        [{"id": 10, "first_name": "Player", "second_name": "A"}],
        fpl_history,
        _teams(),
    )

    row = candidates[0]
    assert row["goal_assist_signature_exact_rows"] == 0
    assert row["goal_assist_signature_zero_only_rows"] == 3
    assert row["review_priority"] == "P3_HISTORY_REVIEW"
    assert row["verification_status"] == "PENDING"


def test_historical_fpl_csv_reader_falls_back_to_windows_1252(tmp_path):
    source = tmp_path / "players.csv"
    source.write_bytes(b"first_name,second_name\nSadio,Man\xe9\n")
    rows = read_csv(source)
    assert rows == [{"first_name": "Sadio", "second_name": "Mané"}]


def test_duplicate_fpl_player_fixture_history_is_isolated_from_corroboration():
    player_match_rows = [{
        "provider_match_id": 500, "match_date": "2018-04-01",
        "provider_player_id": 100, "provider_player_name": "Player A",
        "provider_team_name": "Arsenal", "opponent_team_name": "Bournemouth",
        "home_away": "home", "goals": 1, "own_goals": 0, "assists": 0,
    }]
    fpl_history = [
        {"element": 10, "fixture": 900, "kickoff_time": "2018-04-01T15:00:00Z",
         "opponent_team": 2, "was_home": "True", "minutes": 90,
         "goals_scored": 1, "own_goals": 0, "assists": 0},
        {"element": 10, "fixture": 900, "kickoff_time": "2018-04-01T15:00:00Z",
         "opponent_team": 2, "was_home": "True", "minutes": 90,
         "goals_scored": 0, "own_goals": 0, "assists": 0},
        {"element": 99, "fixture": 900, "kickoff_time": "2018-04-01T15:00:00Z",
         "opponent_team": 1, "was_home": "False", "minutes": 90,
         "goals_scored": 0, "own_goals": 0, "assists": 0},
    ]
    candidates, report = build_candidate_review_queue(
        player_match_rows,
        [{"wyId": 100, "firstName": "Player", "lastName": "A"}],
        [{"id": 10, "code": 1000, "first_name": "Player", "second_name": "A", "team": 1}],
        [{"id": 10, "first_name": "Player", "second_name": "A"}],
        fpl_history,
        _teams(),
    )
    row = candidates[0]
    assert row["fpl_history_ambiguous_rows"] == 1
    assert row["fpl_history_overlap_rows"] == 0
    assert row["goal_assist_signature_exact_rows"] == 0
    assert report["duplicate_fpl_player_fixture_keys"] == 1
