import json

import pandas as pd

import audit_2pm_understat_player_fixture_membership as audit


def _calendars():
    return {"2022-23": pd.DataFrame([
        {"season":"2022-23", "fixture_id":61, "event":25,
         "kickoff_time":pd.Timestamp("2023-03-01T19:45:00Z"),
         "home_team":"Arsenal", "away_team":"Everton"},
    ])}


def _history(date="2023-03-01", season="2022", player_id=1250):
    row = {"season":season, "date":date, "h_team":"Arsenal", "a_team":"Everton"}
    return {"pinned_commit":"vaastav-pin", "results":[{
        "source_kind":"pinned_player_csv",
        "source_path":f"data/2024-25/understat/Player_{player_id}.csv",
        "row_history":{f"{player_id}|{date}":{
            "first_value_signature":json.dumps(row),
            "latest_value_signature":json.dumps(row),
            "present_in_latest_revision":True,
            "first_seen_at":"2023-03-02T12:00:00Z",
            "latest_at":"2023-03-02T12:00:00Z",
            "value_revision_count":0,
            "missing_revision_count":0,
            "reappearance_count":0,
        }},
    }]}


def _membership():
    return pd.DataFrame([{
        "season":"2022-23", "fixture_id":61, "gameweek":25,
        "fpl_code":100, "element_id":10, "understat_id":1250,
    }])


def test_exact_player_row_requires_assignment_and_fixture_membership():
    report = audit.reconcile_player_rows(_history(), _calendars(), _membership())
    row = report["rows"][0]
    assert row["reconciliation_status"] == "MATCHED_PLAYER_FIXTURE"
    assert row["fixture_id"] == 61
    assert row["fpl_code"] == 100
    assert row["element_id"] == 10
    assert report["training_authorized"] is False


def test_one_day_player_date_shift_is_candidate_not_admitted():
    report = audit.reconcile_player_rows(_history(date="2023-03-02"), _calendars(), _membership())
    row = report["rows"][0]
    assert row["reconciliation_status"] == "PLAYER_DATE_TOLERANCE_CANDIDATE"
    assert row["fixture_id"] is None


def test_missing_fpl_player_fixture_row_is_explicit():
    empty = pd.DataFrame(columns=["season", "fixture_id", "gameweek", "fpl_code", "element_id", "understat_id"])
    report = audit.reconcile_player_rows(_history(), _calendars(), empty)
    assert report["rows"][0]["reconciliation_status"] == "PLAYER_NOT_IN_FPL_FIXTURE_ROWS"


def test_shared_understat_id_with_multiple_fpl_codes_is_ambiguous():
    links = pd.concat([_membership(), pd.DataFrame([{
        "season":"2022-23", "fixture_id":61, "gameweek":25,
        "fpl_code":101, "element_id":11, "understat_id":1250,
    }])], ignore_index=True)
    report = audit.reconcile_player_rows(_history(), _calendars(), links)
    assert report["rows"][0]["reconciliation_status"] == "AMBIGUOUS_PLAYER_ASSIGNMENT"
    assert report["rows"][0]["fixture_id"] is None


def test_player_rows_outside_selected_seasons_are_not_counted_as_unmatched():
    report = audit.reconcile_player_rows(_history(date="2020-09-01", season="2020"), _calendars(), _membership())
    assert report["rows"][0]["reconciliation_status"] == "OUTSIDE_AUDITED_SEASONS"


def test_loader_applies_dastan_gameweek_assignment_interval(tmp_path, monkeypatch):
    season_root = tmp_path / "source" / "2022-23"
    (season_root / "gws").mkdir(parents=True)
    pd.DataFrame([
        {"fixture":61,"element":10,"position":"MID","GW":25},
        {"fixture":62,"element":10,"position":"MID","GW":26},
        {"fixture":63,"element":10,"position":"AM","GW":27},
    ]).to_csv(season_root / "gws" / "merged_gw.csv", index=False)
    pd.DataFrame([{"id":10,"code":100}]).to_csv(season_root / "players_raw.csv", index=False)
    assignment = tmp_path / "assignments.csv"
    pd.DataFrame([{
        "season":"2022-23", "fpl_code":100, "understat_id":1250,
        "first_gameweek":26, "last_gameweek":38, "mapped_rows":13,
    }]).to_csv(assignment, index=False)

    def fake_fetch(session, repository, commit, source_path, cache_root):
        if source_path == "data/mappings/fpl_understat_training_assignments.csv":
            return assignment
        return tmp_path / "source" / source_path.removeprefix("data/")

    monkeypatch.setattr(audit, "fetch_pinned_file", fake_fetch)
    result = audit.load_player_fixture_membership(
        ["2022-23"], "vaastav-pin", audit.DASTAN_COMMIT, tmp_path / "cache"
    )
    assert set(result.fixture_id.astype(int)) == {62}
    assert set(result.understat_id.astype(int)) == {1250}


def test_double_gameweek_player_rows_resolve_to_their_own_fixture():
    fixtures = pd.DataFrame([
        {"season":"2022-23", "fixture_id":71, "event":30,
         "kickoff_time":pd.Timestamp("2023-04-01T14:00:00Z"),
         "home_team":"Arsenal", "away_team":"Leeds"},
        {"season":"2022-23", "fixture_id":72, "event":30,
         "kickoff_time":pd.Timestamp("2023-04-05T19:00:00Z"),
         "home_team":"Arsenal", "away_team":"Chelsea"},
    ])
    links = pd.DataFrame([
        {"season":"2022-23", "fixture_id":71, "gameweek":30, "fpl_code":100, "element_id":10, "understat_id":1250},
        {"season":"2022-23", "fixture_id":72, "gameweek":30, "fpl_code":100, "element_id":10, "understat_id":1250},
    ])
    row = {"season":"2022", "date":"2023-04-05", "h_team":"Arsenal", "a_team":"Chelsea"}
    history = {"results":[{"source_kind":"pinned_player_csv",
        "source_path":"data/2024-25/understat/Player_1250.csv",
        "row_history":{"1250|2023-04-05":{"first_value_signature":json.dumps(row)}}}]}
    result = audit.reconcile_player_rows(history, {"2022-23":fixtures}, links)
    assert result["rows"][0]["reconciliation_status"] == "MATCHED_PLAYER_FIXTURE"
    assert result["rows"][0]["fixture_id"] == 72


def test_duplicate_exact_fixture_identity_is_ambiguous():
    fixture = {"season":"2022-23", "event":30,
               "kickoff_time":pd.Timestamp("2023-04-01T14:00:00Z"),
               "home_team":"Arsenal", "away_team":"Leeds"}
    fixtures = pd.DataFrame([{**fixture, "fixture_id":71}, {**fixture, "fixture_id":73}])
    links = pd.DataFrame(columns=["season", "fixture_id", "gameweek", "fpl_code", "element_id", "understat_id"])
    row = {"season":"2022", "date":"2023-04-01", "h_team":"Arsenal", "a_team":"Leeds"}
    history = {"results":[{"source_kind":"pinned_player_csv",
        "source_path":"data/2024-25/understat/Player_1250.csv",
        "row_history":{"1250|2023-04-01":{"first_value_signature":json.dumps(row)}}}]}
    result = audit.reconcile_player_rows(history, {"2022-23":fixtures}, links)
    assert result["rows"][0]["reconciliation_status"] == "AMBIGUOUS_FIXTURE"
    assert result["rows"][0]["fixture_id"] is None
