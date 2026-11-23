from prepare_abc_11footy_verified_inputs import prepare


def test_cross_provider_bridge_is_converted_to_11footy_provider_contract():
    candidates = [{
        "season": "2017/18", "provider_player_id": "501",
        "candidate_fpl_element_id": "10",
    }]
    crosswalk = [{
        "season": "2017/18",
        "corroborating_provider_player_id": "501",
        "corroborating_provider_player_name": "Player One",
        "corroborating_provider_birth_date": "1990-01-01",
        "fpl_element_id": "10",
        "fpl_player_code": "123",
        "verification_status": "VERIFIED_CROSS_PROVIDER_IDENTITY_AND_FPL_HISTORY",
        "verification_method": "strict test",
    }]
    history = [
        {"element": "10", "fixture": "1", "kickoff_time": "2017-08-12T14:00:00Z",
         "round": "1", "minutes": "90", "total_points": "6", "goals_scored": "1",
         "assists": "0", "team": "1", "opponent_team": "2", "was_home": "True"},
        {"element": "11", "fixture": "1", "kickoff_time": "2017-08-12T14:00:00Z",
         "round": "1", "minutes": "90", "total_points": "2", "goals_scored": "0",
         "assists": "0", "team": "2", "opponent_team": "1", "was_home": "False"},
    ]
    players = [{"id": "10", "code": "123", "web_name": "Player One"}]
    teams = [{"id": "1", "name": "Home FC"}, {"id": "2", "name": "Away FC"}]

    candidate_rows, verified_rows, fixtures, player_rows, history_rows, validation = prepare(
        candidates, crosswalk, history, players, teams
    )

    assert candidate_rows[0]["fpl_element_id"] == "10"
    assert verified_rows[0]["provider"] == "11footy"
    assert verified_rows[0]["provider_player_id"] == "501"
    assert verified_rows[0]["verification_status"] == "verified"
    assert validation["status"] == "PASS"
    assert len(fixtures) == 1
    assert fixtures[0]["team_h_name"] == "Home FC"
    assert fixtures[0]["team_a_name"] == "Away FC"
    assert player_rows[0]["fpl_element_id"] == "10"
    assert history_rows[0]["fpl_element_id"] == "10"
    assert history_rows[0]["fixture_id"] == "1"


def test_unverified_cross_provider_rows_are_not_promoted():
    _, verified_rows, fixtures, player_rows, history_rows, validation = prepare(
        [],
        [{"verification_status": "NOT_VERIFIED"}],
        [{"element": "10", "fixture": "1", "kickoff_time": "2017-08-12T14:00:00Z",
          "round": "1", "team": "1", "was_home": "True"}],
        [{"id": "10", "code": "123", "web_name": "Player One"}],
        [{"id": "1", "name": "Home FC"}],
    )
    assert verified_rows == []
    assert validation["status"] == "NO_VERIFIED_MAPPINGS"
    assert fixtures == []


def test_read_csv_supports_legacy_cp1252_names(tmp_path):
    from prepare_abc_11footy_verified_inputs import read_csv

    source = tmp_path / "legacy.csv"
    source.write_bytes(bytes([110, 97, 109, 101, 44, 118, 97, 108, 117, 101, 10, 65, 110, 100, 114, 101, 233, 44, 49, 10]))
    rows = read_csv(source)
    assert rows == [{"name": "Andreé", "value": "1"}]
