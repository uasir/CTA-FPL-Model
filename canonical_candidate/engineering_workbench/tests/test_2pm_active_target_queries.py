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
