import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from rebuild_2pm_dastan_286_candidate import (
    expected_reconstruction_feature_map,
    expected_reconstruction_source_map,
    validate_reconstruction_coverage,
)


def pinned_feature_definitions():
    player_features = {
        "total_points": "fpl_points",
        "minutes": "minutes_played",
        "influence": "influence",
        "creativity": "creativity",
        "threat": "threat",
        "goals_scored": "goals_scored",
        "penalties_missed": "penalties_missed",
        "assists": "assists",
        "goals_conceded": "goals_conceded",
        "own_goals": "own_goals",
        "saves": "saves",
        "penalties_saved": "penalties_saved",
        "yellow_cards": "yellow_cards",
        "red_cards": "red_cards",
        "bps": "bps",
        "bonus": "fpl_bonus_points",
        "us_shots": "shots",
        "us_xG": "xg",
        "us_xGChain": "xgchain",
        "us_xGBuildup": "xgbuildup",
        "us_key_passes": "key_passes",
        "us_xA": "xa",
    }
    team_features = {
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
    return SimpleNamespace(
        WINDOWS=[1, 3, 5, 10, 38],
        PLAYER_FEATURES=player_features,
        TEAM_FEATURES=team_features,
    )


def test_exact_reconstruction_names_partition_the_pinned_286_schema():
    import json

    schema = json.loads(
        (ROOT / "config" / "2pm_dastan_286_schema.json").read_text()
    )
    feature_map = expected_reconstruction_feature_map(pinned_feature_definitions())
    flattened = [name for names in feature_map.values() for name in names]

    assert len(schema["feature_order"]) == 286
    assert len(flattened) == 286
    assert len(set(flattened)) == 286
    assert set(flattened) == set(schema["feature_order"])

    source_map = expected_reconstruction_source_map(pinned_feature_definitions())
    assert len(source_map) == 286
    assert set(source_map) == set(schema["feature_order"])
    assert "player_matches.us_xG" in source_map["player_xg_1"]
    assert "team_matches.scored" in source_map["team_goals_scored_1"]
    assert "opponent team_matches.scored" in source_map["opp_goals_scored_1"]
    assert "compute_league_ranks" in source_map["team_league_rank_1"]
    assert "team_matches.league_rank" not in source_map["team_league_rank_1"]
    assert "compute_league_ranks" in source_map["team_opponent_league_rank_1"]
    assert "historical opponent standings rank" in source_map["team_opponent_league_rank_1"]
    assert "historical opponent-of-opponent" in source_map["opp_opponent_league_rank_1"]
    assert "selected_by_percent" in source_map["selected"]
    assert "transfers_in_event - transfers_out_event" in source_map["transfers_balance"]
    assert "elements[].status" in source_map["sig_status_risk"]
    assert "chance_of_playing_next_round" in source_map["sig_chance_playing"]
    assert "elements[].news" in source_map["sig_has_news"]
    assert "pre_deadline_signals.status" not in source_map["sig_status_risk"]


def test_exact_name_validator_rejects_a_builder_schema_name_mismatch():
    definitions = pinned_feature_definitions()
    definitions.TEAM_FEATURES["scored"] = "goals_for"
    feature_map = expected_reconstruction_feature_map(definitions)
    schema = [
        name
        for names in expected_reconstruction_feature_map(pinned_feature_definitions()).values()
        for name in names
    ]
    frame = pd.DataFrame({
        **{name: [0.0] for name in schema},
        **{f"__observed__{name}": [1] for name in schema},
    })
    player_report = {
        "player_rolling_feature_count": 115,
        "availability_feature_count": 9,
        "defensive_player_history_feature_count": 26,
    }
    team_report = {
        "team_feature_count": 60,
        "opponent_feature_count": 60,
        "direct_rank_columns": ["status_league_rank", "opp_status_league_rank"],
    }
    fixture_report = {
        "fixture_context_columns": [
            "ar_rest_days", "ar_team_matches_14d",
            "ar_opp_dc_allowed_3", "ar_opp_dc_allowed_5",
            "ar_opp_dc_allowed_10", "ar_opp_tackles_allowed_5",
        ]
    }

    with pytest.raises(RuntimeError, match="Exact reconstruction/schema feature-name mismatch"):
        validate_reconstruction_coverage(
            schema, player_report, team_report, fixture_report, frame,
            definitions,
        )


def test_exact_name_validator_rejects_missing_observation_mask_column():
    definitions = pinned_feature_definitions()
    feature_map = expected_reconstruction_feature_map(definitions)
    schema = [name for names in feature_map.values() for name in names]
    frame = pd.DataFrame({
        **{name: [0.0] for name in schema},
        **{f"__observed__{name}": [1] for name in schema if name != "team_xg_1"},
    })
    player_report = {
        "player_rolling_feature_count": 115,
        "availability_feature_count": 9,
        "defensive_player_history_feature_count": 26,
    }
    team_report = {
        "team_feature_count": 60,
        "opponent_feature_count": 60,
        "direct_rank_columns": ["status_league_rank", "opp_status_league_rank"],
    }
    fixture_report = {
        "fixture_context_columns": [
            "ar_rest_days", "ar_team_matches_14d",
            "ar_opp_dc_allowed_3", "ar_opp_dc_allowed_5",
            "ar_opp_dc_allowed_10", "ar_opp_tackles_allowed_5",
        ]
    }

    with pytest.raises(RuntimeError, match="missing exact observation-mask columns"):
        validate_reconstruction_coverage(
            schema, player_report, team_report, fixture_report, frame,
            definitions,
        )
