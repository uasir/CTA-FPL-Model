import pandas as pd
import pytest

import build_2pm_postmatch_state_vectors as builder


FEATURES = [f"feature_{index:03d}" for index in range(286)]
FEATURES[0] = "player_assists_1"
FEATURES[1] = "team_xg_1"
FEATURES[2] = "ar_rest_days"
FEATURES[3] = "ar_team_matches_14d"
FEATURES[4] = "ar_opp_dc_allowed_3"
FEATURES[5] = "ar_opp_dc_allowed_5"
FEATURES[6] = "ar_opp_dc_allowed_10"
FEATURES[7] = "ar_opp_tackles_allowed_5"
FEATURES[8] = "value"
FEATURES[9] = "selected"
FEATURES[10] = "transfers_balance"
FEATURES[11] = "ar_ep_next"
FEATURES[12] = "sig_status_risk"
FEATURES[13] = "sig_chance_playing"
FEATURES[14] = "sig_has_news"


def make_candidate():
    kickoff = pd.Timestamp("2026-08-01T12:00:00Z")
    row = {
        "season": "2026-27",
        "gameweek": 1,
        "fixture": "101",
        "fpl_code": 123,
        "kickoff_time": kickoff,
        "match_available_at": kickoff + pd.Timedelta(hours=24),
        "minutes": 90,
        "deadline_time": kickoff - pd.Timedelta(hours=3),
        "team_name": "Team A",
        "opponent_team_name": "Team B",
        "source_vintage_status": "RETROSPECTIVE_SOURCE_VINTAGE_NOT_VERIFIED",
        "ep_next_snapshot_at": kickoff - pd.Timedelta(hours=4),
        "signals_snapshot_at": kickoff - pd.Timedelta(hours=3, minutes=30),
        "market_snapshot_at": kickoff - pd.Timedelta(hours=3),
    }
    row.update({feature: 1.0 for feature in FEATURES})
    row.update({f"__observed__{feature}": 1 for feature in FEATURES})
    row.update({
        "ar_rest_days": 5.0,
        "ar_team_matches_14d": 2.0,
        "value": 55.0,
        "selected": 12.5,
        "transfers_balance": 100,
        "ar_ep_next": 4.2,
        "sig_status_risk": 0.1,
        "sig_chance_playing": 0.9,
        "sig_has_news": 0.0,
    })
    return pd.DataFrame([row])


def test_builds_postmatch_state_after_all_required_match_data_is_available(monkeypatch):
    observed = {"fixture_cutoffs": []}

    def player_rebuild(frame, history, features_module):
        observed["player_asof"] = frame["deadline_time"].iloc[0]
        out = frame.copy()
        out["player_assists_1"] = 11.0
        return out, {"status": "player_rebuilt"}

    def team_rebuild(frame, team_history, features_module):
        observed["team_asof"] = frame["deadline_time"].iloc[0]
        out = frame.copy()
        out["team_xg_1"] = 22.0
        return out, {"status": "team_rebuilt"}

    def fixture_rebuild(frame, history):
        observed["fixture_cutoffs"].append(frame["deadline_time"].iloc[0])
        out = frame.copy()
        out["ar_rest_days"] = 999.0
        out["ar_team_matches_14d"] = 999.0
        out["ar_opp_dc_allowed_3"] = 33.0
        out["ar_opp_dc_allowed_5"] = 35.0
        out["ar_opp_dc_allowed_10"] = 40.0
        out["ar_opp_tackles_allowed_5"] = 12.0
        return out, {"status": "fixture_rebuilt"}

    monkeypatch.setattr(builder, "rebuild_player_history_features", player_rebuild)
    monkeypatch.setattr(builder, "rebuild_deadline_team_context", team_rebuild)
    monkeypatch.setattr(builder, "rebuild_fixture_context", fixture_rebuild)

    result, report = builder.build_postmatch_state_vectors(
        make_candidate(),
        pd.DataFrame({"season": ["2026-27"]}),
        pd.DataFrame({"season": ["2026-27"]}),
        object(),
        FEATURES,
    )

    expected_asof = pd.Timestamp("2026-08-02T12:00:00.000000001Z")
    assert observed["player_asof"] == expected_asof
    assert observed["team_asof"] == expected_asof
    assert result.loc[0, "postmatch_state_as_of_time"] == expected_asof
    assert result.loc[0, "deadline_time"] == pd.Timestamp("2026-08-01T09:00:00Z")
    assert result.loc[0, "player_assists_1"] == 11.0
    assert result.loc[0, "team_xg_1"] == 22.0
    assert result.loc[0, "ar_opp_dc_allowed_3"] == 33.0
    # Rest/congestion are rebuilt immediately before kickoff, not copied from
    # a potentially later original Gameweek deadline.
    assert observed["fixture_cutoffs"][-1] == pd.Timestamp("2026-08-01T11:59:59.999999999Z")
    assert result.loc[0, "ar_rest_days"] == 999.0
    assert result.loc[0, "ar_team_matches_14d"] == 999.0
    # Snapshots captured safely before kickoff remain available to the token.
    assert result.loc[0, "value"] == 55.0
    assert result.loc[0, "ar_ep_next"] == 4.2
    assert report["admission_status"] == "NOT_ADMITTED"


def test_rejects_non_appearance_rows():
    frame = make_candidate()
    frame.loc[0, "minutes"] = 0
    with pytest.raises(ValueError, match="No played fixture rows"):
        builder.build_postmatch_state_vectors(
            frame, pd.DataFrame(), pd.DataFrame(), object(), FEATURES
        )


def test_rejects_missing_match_availability():
    frame = make_candidate()
    frame.loc[0, "match_available_at"] = pd.NaT
    with pytest.raises(ValueError, match="valid match data availability timestamp"):
        builder.build_postmatch_state_vectors(
            frame, pd.DataFrame(), pd.DataFrame(), object(), FEATURES
        )


def test_rejects_duplicate_player_fixture_keys():
    frame = pd.concat([make_candidate(), make_candidate()], ignore_index=True)
    with pytest.raises(ValueError, match="unique at season-fixture-player grain"):
        builder.build_postmatch_state_vectors(
            frame, pd.DataFrame(), pd.DataFrame(), object(), FEATURES
        )



def test_postmatch_player_history_receives_corrected_cross_season_identity_history(monkeypatch):
    frame = make_candidate()
    previous = make_candidate()
    previous.loc[0, "season"] = "2025-26"
    previous.loc[0, "fixture"] = "100"
    frame = pd.concat([previous, frame], ignore_index=True)
    seen_player_seasons = []
    seen_team_seasons = []

    def player_rebuild(targets, history, features_module):
        seen_player_seasons.append(tuple(history["season"].unique()))
        return targets.copy(), {"status": "player_rebuilt"}

    def team_rebuild(targets, history, features_module):
        seen_team_seasons.append(tuple(history["season"].unique()))
        return targets.copy(), {"status": "team_rebuilt"}

    def fixture_rebuild(targets, history):
        out = targets.copy()
        for column in builder.POSTMATCH_OPPONENT_CONTEXT:
            out[column] = 1.0
        return out, {"status": "fixture_rebuilt"}

    monkeypatch.setattr(builder, "rebuild_player_history_features", player_rebuild)
    monkeypatch.setattr(builder, "rebuild_deadline_team_context", team_rebuild)
    monkeypatch.setattr(builder, "rebuild_fixture_context", fixture_rebuild)

    player_history = pd.DataFrame({"season": ["2025-26", "2026-27"]})
    team_history = pd.DataFrame({"season": ["2025-26", "2026-27"]})
    result, report = builder.build_postmatch_state_vectors(
        frame, player_history, team_history, object(), FEATURES
    )
    assert seen_player_seasons == [("2025-26", "2026-27")]
    assert seen_team_seasons == [("2025-26", "2026-27")]
    assert result["season"].tolist() == ["2025-26", "2026-27"]
    assert report["cross_season_history"].startswith("corrected stable player_uid")



def test_mixed_frame_excludes_nonappearances_from_historical_state_tokens(monkeypatch):
    frame = make_candidate()
    dnp = make_candidate()
    dnp.loc[0, "fixture"] = "102"
    dnp.loc[0, "minutes"] = 0
    dnp.loc[0, "match_available_at"] = pd.NaT
    frame = pd.concat([frame, dnp], ignore_index=True)

    def player_rebuild(targets, history, features_module):
        return targets.copy(), {"status": "player_rebuilt"}

    def team_rebuild(targets, history, features_module):
        return targets.copy(), {"status": "team_rebuilt"}

    def fixture_rebuild(targets, history):
        out = targets.copy()
        for column in builder.POSTMATCH_OPPONENT_CONTEXT:
            out[column] = 1.0
        return out, {"status": "fixture_rebuilt"}

    monkeypatch.setattr(builder, "rebuild_player_history_features", player_rebuild)
    monkeypatch.setattr(builder, "rebuild_deadline_team_context", team_rebuild)
    monkeypatch.setattr(builder, "rebuild_fixture_context", fixture_rebuild)
    result, report = builder.build_postmatch_state_vectors(
        frame,
        pd.DataFrame({"season": ["2026-27"]}),
        pd.DataFrame({"season": ["2026-27"]}),
        object(),
        FEATURES,
    )
    assert len(result) == 1
    assert result.loc[0, "fixture"] == "101"
    assert report["nonappearance_rows_excluded"] == 1



def test_rejects_match_availability_after_conservative_team_bound():
    frame = make_candidate()
    frame.loc[0, "match_available_at"] += pd.Timedelta(hours=1)
    with pytest.raises(
        ValueError,
        match="exceeds the conservative kickoff.*maximum overrun 1.000000 hours.*overrun_hours",
    ):
        builder.build_postmatch_state_vectors(
            frame,
            pd.DataFrame({"season": ["2026-27"]}),
            pd.DataFrame({"season": ["2026-27"]}),
            object(),
            FEATURES,
        )


def test_invalidates_snapshots_captured_after_rescheduled_fixture_kickoff(monkeypatch):
    frame = make_candidate()
    kickoff = frame.loc[0, "kickoff_time"]
    frame.loc[0, "deadline_time"] = kickoff + pd.Timedelta(hours=2)
    frame.loc[0, "ep_next_snapshot_at"] = kickoff + pd.Timedelta(minutes=30)
    frame.loc[0, "signals_snapshot_at"] = kickoff + pd.Timedelta(minutes=40)
    frame.loc[0, "market_snapshot_at"] = kickoff + pd.Timedelta(minutes=50)

    def player_rebuild(targets, history, features_module):
        return targets.copy(), {"status": "player_rebuilt"}

    def team_rebuild(targets, team_history, features_module):
        return targets.copy(), {"status": "team_rebuilt"}

    def fixture_rebuild(targets, history):
        out = targets.copy()
        for column in builder.PREMATCH_FIXTURE_CONTEXT:
            out[column] = 7.0
        for column in builder.POSTMATCH_OPPONENT_CONTEXT:
            out[column] = 8.0
        return out, {"status": "fixture_rebuilt"}

    monkeypatch.setattr(builder, "rebuild_player_history_features", player_rebuild)
    monkeypatch.setattr(builder, "rebuild_deadline_team_context", team_rebuild)
    monkeypatch.setattr(builder, "rebuild_fixture_context", fixture_rebuild)

    result, report = builder.build_postmatch_state_vectors(
        frame,
        pd.DataFrame({"season": ["2026-27"]}),
        pd.DataFrame({"season": ["2026-27"]}),
        object(),
        FEATURES,
    )

    for column in (
        "value", "selected", "transfers_balance", "ar_ep_next",
        "sig_status_risk", "sig_chance_playing", "sig_has_news",
    ):
        assert result.loc[0, column] == -1.0
    assert report["snapshot_context_valid_rows_before_kickoff"] == {
        "ep_next_snapshot_at": 0,
        "signals_snapshot_at": 0,
        "market_snapshot_at": 0,
    }
