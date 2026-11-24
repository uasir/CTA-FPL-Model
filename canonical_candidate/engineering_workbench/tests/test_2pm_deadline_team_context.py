import pandas as pd

from rebuild_2pm_fixture_context import rebuild_deadline_team_context


class FakeFeatures:
    WINDOWS = [1, 3, 5, 10, 38]
    TEAM_FEATURES = {"xg": "xg"}

    @staticmethod
    def _prepare_team_matches(frame):
        return frame.copy()

    @staticmethod
    def build_opponent_lookup(frame):
        return frame.copy()

    @staticmethod
    def compute_league_ranks(frame):
        return {}


def test_opponent_rolling_and_direct_ranks_exclude_post_deadline_same_gameweek_result():
    # The second match is scheduled after the deadline and its result would
    # reverse the table. Its conservative availability is kickoff + 24h,
    # which is also after the target deadline.
    team_matches = pd.DataFrame([
        {
            "season": "2025-26", "understat_team": "T", "opponent": "O",
            "date": "2026-01-01 12:00", "scored": 0, "missed": 2,
            "pts": 0, "xg": 0.4,
        },
        {
            "season": "2025-26", "understat_team": "O", "opponent": "T",
            "date": "2026-01-01 12:00", "scored": 2, "missed": 0,
            "pts": 3, "xg": 1.2,
        },
        {
            "season": "2025-26", "understat_team": "T", "opponent": "O",
            "date": "2026-01-08 18:00", "scored": 4, "missed": 0,
            "pts": 3, "xg": 3.8,
        },
        {
            "season": "2025-26", "understat_team": "O", "opponent": "T",
            "date": "2026-01-08 18:00", "scored": 0, "missed": 4,
            "pts": 0, "xg": 0.2,
        },
    ])
    target = pd.DataFrame([{
        "season": "2025-26",
        "deadline_time": pd.Timestamp("2026-01-08 12:00", tz="UTC"),
        "team_name": "Team",
        "opponent_team_name": "Opponent",
    }])
    features = FakeFeatures()
    features.fpl_to_understat = {"Team": "T", "Opponent": "O"}

    result, report = rebuild_deadline_team_context(target, team_matches, features)

    assert result.loc[0, "opp_xg_1"] == 1.2
    assert result.loc[0, "team_xg_1"] == 0.4
    assert result.loc[0, "status_league_rank"] == 2
    assert result.loc[0, "opp_status_league_rank"] == 1
    assert report["availability_rule"].endswith(
        "strictly before official FPL deadline"
    )
