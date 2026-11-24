import pandas as pd
import pytest

from build_2pm_active_target_queries import build_fixture_player_rows


class DummyFeatures:
    @staticmethod
    def fpl_to_understat(name):
        return {"Arsenal": "Arsenal", "Chelsea": "Chelsea"}.get(name)


def inputs():
    fixtures = pd.DataFrame(
        [
            {
                "id": 9001,
                "event": 12,
                "team_h": 1,
                "team_a": 2,
                "kickoff_time": "2026-11-28T15:00:00Z",
                "finished": False,
            },
            {
                "id": 9002,
                "event": 12,
                "team_h": 2,
                "team_a": 1,
                "kickoff_time": "2026-11-29T15:00:00Z",
                "finished": False,
            },
        ]
    )
    elements = [
        {"id": 101, "code": 1001, "team": 1, "element_type": 3},
        {"id": 102, "code": 1002, "team": 2, "element_type": 4},
        {"id": 103, "code": 1003, "team": 1, "element_type": 1},
    ]
    teams = pd.DataFrame([{"id": 1, "name": "Arsenal"}, {"id": 2, "name": "Chelsea"}])
    assignments = pd.DataFrame(
        [
            {"season": "2026-27", "fpl_code": 1001, "understat_id": 501},
            {"season": "2026-27", "fpl_code": 1002, "understat_id": 502},
            {"season": "2026-27", "fpl_code": 1003, "understat_id": None},
        ]
    )
    deadline = pd.Timestamp("2026-11-27T11:00:00Z")
    now = pd.Timestamp("2026-11-27T10:00:00Z")
    return fixtures, elements, teams, assignments, deadline, now


def test_builds_fixture_grain_rows_for_each_player_and_preserves_identity():
    fixtures, elements, teams, assignments, deadline, now = inputs()
    result = build_fixture_player_rows(
        fixtures.iloc[:1],
        elements,
        teams,
        assignments,
        season="2026-27",
        gameweek=12,
        deadline=deadline,
        now=now,
        features_module=DummyFeatures,
    )
    assert len(result) == 3
    assert set(result["fixture"]) == {9001}
    assert set(result["position"]) == {"GKP", "MID", "FWD"}
    assert result.loc[result["fpl_code"].eq(1001), "understat_id"].iat[0] == 501
    assert pd.isna(result.loc[result["fpl_code"].eq(1003), "understat_id"].iat[0])
    assert result["minutes"].eq(0).all()
    assert result["total_points"].eq(0).all()
    assert result["us_opponent"].notna().all()


def test_double_gameweek_keeps_two_distinct_fixture_contexts():
    fixtures, elements, teams, assignments, deadline, now = inputs()
    result = build_fixture_player_rows(
        fixtures,
        elements,
        teams,
        assignments,
        season="2026-27",
        gameweek=12,
        deadline=deadline,
        now=now,
        features_module=DummyFeatures,
    )
    player = result[result["fpl_code"].eq(1001)].sort_values("fixture")
    assert player["fixture"].tolist() == [9001, 9002]
    assert player["opponent_team_name"].tolist() == ["Chelsea", "Chelsea"]
    assert player["is_home"].tolist() == [True, False]


def test_refuses_target_gameweek_after_first_fixture_has_started():
    fixtures, elements, teams, assignments, deadline, now = inputs()
    fixtures.loc[0, "kickoff_time"] = "2026-11-27T09:00:00Z"
    with pytest.raises(ValueError, match="already started"):
        build_fixture_player_rows(
            fixtures,
            elements,
            teams,
            assignments,
            season="2026-27",
            gameweek=12,
            deadline=deadline,
            now=now,
            features_module=DummyFeatures,
        )


def test_refuses_fixture_before_official_deadline():
    fixtures, elements, teams, assignments, deadline, now = inputs()
    fixtures.loc[0, "kickoff_time"] = "2026-11-27T10:30:00Z"
    with pytest.raises(ValueError, match="not after its official deadline"):
        build_fixture_player_rows(
            fixtures.iloc[:1],
            elements,
            teams,
            assignments,
            season="2026-27",
            gameweek=12,
            deadline=deadline,
            now=now,
            features_module=DummyFeatures,
        )



def snapshot_artifacts(tmp_path, market_capture):
    key = {"season": "2026-27", "gameweek": 12, "fpl_code": 1001}
    pd.DataFrame(
        [{**key, "ep_next": 4.2, "snapshot_at": "2026-11-27T10:00:00Z"}]
    ).to_parquet(tmp_path / "pre_deadline_ep_next.parquet", index=False)
    pd.DataFrame(
        [{
            **key,
            "sig_status_risk": 0.0,
            "sig_chance_playing": 100.0,
            "sig_has_news": 0.0,
            "snapshot_at": "2026-11-27T10:00:00Z",
        }]
    ).to_parquet(tmp_path / "pre_deadline_signals.parquet", index=False)
    pd.DataFrame(
        [{
            **key,
            "value": 55.0,
            "selected": 7.3,
            "transfers_balance": 60.0,
            "snapshot_at": market_capture,
        }]
    ).to_parquet(tmp_path / "pre_deadline_market.parquet", index=False)


def test_snapshot_join_preserves_values_and_accepts_safe_capture_times(tmp_path):
    from build_2pm_active_target_queries import attach_snapshot_features

    snapshot_artifacts(tmp_path, "2026-11-27T10:00:00Z")
    frame = pd.DataFrame([{
        "season": "2026-27",
        "gameweek": 12,
        "fpl_code": 1001,
        "deadline_time": pd.Timestamp("2026-11-27T11:00:00Z"),
        "value": 4.0,
        "selected": 1.0,
        "transfers_balance": 0.0,
        "ar_ep_next": 0.0,
        "sig_status_risk": 0.0,
        "sig_chance_playing": 0.0,
        "sig_has_news": 0.0,
    }])
    result, report = attach_snapshot_features(frame, tmp_path)
    assert result.loc[0, "value"] == 55.0
    assert result.loc[0, "selected"] == 7.3
    assert result.loc[0, "transfers_balance"] == 60.0
    assert result.loc[0, "ar_ep_next"] == 4.2
    assert report["snapshot_coverage"]["market_snapshot_at"] == 1


def test_snapshot_join_rejects_market_capture_inside_safety_buffer(tmp_path):
    from build_2pm_active_target_queries import attach_snapshot_features

    snapshot_artifacts(tmp_path, "2026-11-27T10:58:00Z")
    frame = pd.DataFrame([{
        "season": "2026-27",
        "gameweek": 12,
        "fpl_code": 1001,
        "deadline_time": pd.Timestamp("2026-11-27T11:00:00Z"),
    }])
    with pytest.raises(RuntimeError, match="five-minute safety buffer"):
        attach_snapshot_features(frame, tmp_path)
