from types import SimpleNamespace

import pandas as pd

from rebuild_2pm_fixture_context import rebuild_deadline_team_context


WINDOWS = [1, 3, 5, 10, 38]
TEAM_FEATURES = {
    "scored": "goals_scored",
    "missed": "goals_conceded",
    "league_rank": "league_rank",
    "opp_league_rank": "opponent_league_rank",
    "xG": "xg",
    "deep_allowed": "deep_allowed",
    "ppda_allowed_att": "ppda_allowed_att",
    "ppda_allowed_def": "ppda_allowed_def",
    "xGA": "xga",
    "deep": "deep",
    "ppda_att": "ppda_att",
    "ppda_def": "ppda_def",
}


def match(season, date, team, opponent, scored, missed, xg=1.0):
    return {
        "season": season,
        "date": pd.Timestamp(date, tz="UTC"),
        "understat_team": team,
        "opponent": opponent,
        "is_home": 1.0,
        "scored": scored,
        "missed": missed,
        "pts": 3 if scored > missed else 1 if scored == missed else 0,
        "xG": xg,
        "xGA": 1.0,
        "deep": 5.0,
        "deep_allowed": 4.0,
        "ppda_att": 8.0,
        "ppda_def": 9.0,
        "ppda_allowed_att": 10.0,
        "ppda_allowed_def": 11.0,
    }


def fake_features():
    def prepare_team_matches(frame):
        out = frame.copy()
        for column in (
            "scored", "missed", "xG", "xGA", "deep", "deep_allowed",
            "ppda_att", "ppda_def", "ppda_allowed_att", "ppda_allowed_def",
        ):
            if column in out:
                out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0)
        return out

    return SimpleNamespace(
        _prepare_team_matches=prepare_team_matches,
        build_opponent_lookup=lambda frame: frame.copy(),
        compute_league_ranks=lambda frame: {
            (str(row.understat_team), str(row.season), row.date.strftime("%Y-%m-%d %H:%M")): 5
            for row in frame.itertuples()
        },
        fpl_to_understat=lambda value: value,
        TEAM_FEATURES=TEAM_FEATURES,
        WINDOWS=WINDOWS,
    )


def test_deadline_team_context_uses_only_completed_matches_and_target_opponent():
    team_matches = pd.DataFrame(
        [
            # Prior completed matches.
            match("2025-26", "2026-01-01", "T", "Q", 2, 0, 2.0),
            match("2025-26", "2026-01-02", "O", "A", 1, 1, 1.2),
            match("2025-26", "2026-01-03", "P", "C", 0, 2, 0.5),
            # Future same-Gameweek target results must not enter deadline features.
            match("2025-26", "2026-01-10", "T", "O", 9, 0, 5.0),
            match("2025-26", "2026-01-10", "O", "T", 0, 9, 0.1),
            match("2025-26", "2026-01-14", "T", "P", 8, 0, 4.0),
            match("2025-26", "2026-01-14", "P", "T", 0, 8, 0.1),
        ]
    )
    target = pd.DataFrame(
        [
            {
                "season": "2025-26", "deadline_time": pd.Timestamp("2026-01-09", tz="UTC"),
                "team_name": "T", "opponent_team_name": "O",
            },
            {
                "season": "2025-26", "deadline_time": pd.Timestamp("2026-01-09", tz="UTC"),
                "team_name": "T", "opponent_team_name": "P",
            },
        ]
    )
    result, report = rebuild_deadline_team_context(
        target, team_matches, fake_features()
    )
    first, second = result.iloc[0], result.iloc[1]
    assert first["team_goals_scored_1"] == 2.0
    assert second["team_goals_scored_1"] == 2.0
    assert first["opp_goals_scored_1"] == 1.0
    assert second["opp_goals_scored_1"] == 0.0
    assert first["team_xg_1"] == 2.0
    assert second["opp_xg_1"] == 0.5
    assert first["status_league_rank"] == second["status_league_rank"]
    assert first["opp_status_league_rank"] != second["opp_status_league_rank"]
    assert report["team_feature_count"] == 60
    assert report["opponent_feature_count"] == 60


def test_team_context_sidecar_detects_missing_source_before_upstream_zero_fill():
    team_matches = pd.DataFrame([
        match("2025-26", "2026-01-01", "T", "O", 2, 0, 2.0),
        match("2025-26", "2026-01-05", "T", "O", 0, 0, float("nan")),
        match("2025-26", "2026-01-01", "O", "T", 1, 1, 1.0),
    ])
    target = pd.DataFrame([{
        "season": "2025-26",
        "deadline_time": pd.Timestamp("2026-01-09", tz="UTC"),
        "team_name": "T",
        "opponent_team_name": "O",
    }])

    result, _ = rebuild_deadline_team_context(target, team_matches, fake_features())

    # The upstream preparation step turns missing xG into a finite zero.
    assert result.loc[0, "team_xg_3"] == 1.0
    # The sidecar still records that the rolling window was not fully observed.
    assert result.loc[0, "__observed__team_xg_3"] == 0
    assert result.loc[0, "__observed__opp_xg_1"] == 1
    assert result.loc[0, "__observed__status_league_rank"] == 1



def test_historical_rank_does_not_use_previous_match_inside_24_hour_availability_bound():
    team_matches = pd.DataFrame([
        match("2025-26", "2026-01-01 20:00", "T", "O", 2, 0),
        match("2025-26", "2026-01-01 20:00", "O", "T", 0, 2),
        # This kickoff is before the previous match's conservative +24h availability.
        match("2025-26", "2026-01-02 15:00", "T", "Q", 1, 0),
        match("2025-26", "2026-01-02 15:00", "Q", "T", 0, 1),
    ])
    target = pd.DataFrame([{
        "season": "2025-26",
        "deadline_time": pd.Timestamp("2026-01-04", tz="UTC"),
        "team_name": "T",
        "opponent_team_name": "O",
    }])

    result, _ = rebuild_deadline_team_context(target, team_matches, fake_features())

    # The target deadline has completed-match evidence, but the historical rank
    # attached to the Jan 2 match cannot use the Jan 1 result (available Jan 2 20:00).
    assert result.loc[0, "__observed__status_league_rank"] == 1
    assert pd.notna(result.loc[0, "team_league_rank_3"])
    assert result.loc[0, "__observed__team_league_rank_3"] == 0
