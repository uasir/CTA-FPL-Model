from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_cta_five_gw_feature_matrix import (
    add_live_snapshot_features,
    anchor_team_features_to_deadline,
    anchor_player_features_to_deadline,
    anchor_opponent_features_to_deadline,
    build_future_rows,
    validate_bootstrap_snapshot,
)


BOOTSTRAP = {
    "teams": [{"id": 1, "name": "Arsenal"}, {"id": 2, "name": "Aston Villa"}],
    "elements": [
        {"id": 11, "code": 101, "element_type": 2, "team": 1, "web_name": "Def A",
         "now_cost": 55, "selected_by_percent": "10.0", "transfers_balance": 12,
         "ep_next": "5.2", "status": "a", "chance_of_playing_next_round": 100, "news": ""},
        {"id": 22, "code": 202, "element_type": 3, "team": 2, "web_name": "Mid B",
         "now_cost": 65, "selected_by_percent": "20.0", "transfers_balance": -3,
         "ep_next": None, "status": "d", "chance_of_playing_next_round": 75, "news": "Knock"},
    ],
}
FIXTURES = [{
    "id": 900, "event": 12, "team_h": 1, "team_a": 2,
    "kickoff_time": "2026-11-28T15:00:00Z",
}]
PLAYER_MAP = {
    101: {"understat_id": 9001, "mapping_status": "mapped"},
    202: {"understat_id": 9002, "mapping_status": "mapped"},
}
CLUB_MAP = {
    "Arsenal": {"understat_name": "Arsenal"},
    "Aston Villa": {"understat_name": "Aston Villa"},
}


class FiveGWFeatureMatrixTests(unittest.TestCase):
    def test_future_rows_are_fixture_grain_and_both_sides(self):
        players, teams, report = build_future_rows(
            BOOTSTRAP, FIXTURES, PLAYER_MAP, CLUB_MAP, "2026-27", [12]
        )
        self.assertEqual(len(players), 2)
        self.assertEqual(len(teams), 2)
        self.assertEqual(set(players["fixture"]), {900})
        self.assertEqual(report["understat_mapped_target_players"], 2)

    def test_shared_understat_id_is_not_used(self):
        mapping = dict(PLAYER_MAP)
        mapping[202] = {"understat_id": 9001, "mapping_status": "shared_understat_id"}
        players, _, report = build_future_rows(
            BOOTSTRAP, FIXTURES, mapping, CLUB_MAP, "2026-27", [12]
        )
        second = players[players["fpl_code"].eq(202)].iloc[0]
        self.assertTrue(pd.isna(second["understat_id"]))
        self.assertEqual(report["understat_unmapped_target_players"], 1)

    def test_missing_team_mapping_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Understat club mapping incomplete"):
            build_future_rows(
                BOOTSTRAP, FIXTURES, PLAYER_MAP, {"Arsenal": CLUB_MAP["Arsenal"]},
                "2026-27", [12]
            )

    def test_live_snapshot_values_only_apply_to_next_gameweek(self):
        frame = pd.DataFrame([
            {"gameweek": 12, "fpl_code": 101},
            {"gameweek": 13, "fpl_code": 101},
        ])
        result = add_live_snapshot_features(frame, BOOTSTRAP, 12)
        self.assertAlmostEqual(result.iloc[0]["ar_ep_next"], 5.2)
        self.assertEqual(result.iloc[0]["sig_status_risk"], 0)
        self.assertEqual(result.iloc[1]["ar_ep_next"], -1.0)
        self.assertEqual(result.iloc[1]["sig_status_risk"], -1.0)

    def test_team_and_opponent_history_are_reanchored(self):
        frame = pd.DataFrame([
            {"team_name": "Arsenal", "opponent_team_name": "Aston Villa",
             "kickoff_time": "2026-11-28T15:00:00Z", "fixture": 900,
             "team_xg_1": 2.0, "opp_xg_1": 3.0, "status_league_rank": 1,
             "opp_status_league_rank": 2},
            {"team_name": "Aston Villa", "opponent_team_name": "Arsenal",
             "kickoff_time": "2026-11-28T15:00:00Z", "fixture": 900,
             "team_xg_1": 3.0, "opp_xg_1": 2.0, "status_league_rank": 2,
             "opp_status_league_rank": 1},
            {"team_name": "Arsenal", "opponent_team_name": "Aston Villa",
             "kickoff_time": "2026-12-01T15:00:00Z", "fixture": 901,
             "team_xg_1": 99.0, "opp_xg_1": 88.0, "status_league_rank": 9,
             "opp_status_league_rank": 8},
        ])
        result = anchor_team_features_to_deadline(frame)
        last = result.iloc[2]
        self.assertEqual(last["team_xg_1"], 2.0)
        self.assertEqual(last["opp_xg_1"], 3.0)
        self.assertEqual(last["status_league_rank"], 1)
        self.assertEqual(last["opp_status_league_rank"], 2)


if __name__ == "__main__":
    unittest.main()

def test_bootstrap_snapshot_requires_five_minute_predeadline_margin():
    deadline = pd.Timestamp("2026-11-28T11:00:00Z")
    accepted = {
        "_cta_snapshot": {
            "gameweek": 13,
            "captured_at_utc": "2026-11-28T10:54:00Z",
            "deadline_time": "2026-11-28T11:00:00Z",
            "safety_buffer_minutes": 5,
        }
    }
    assert validate_bootstrap_snapshot(accepted, 13, deadline)["safety_buffer_minutes"] == 5

    too_late = {
        "_cta_snapshot": {
            **accepted["_cta_snapshot"],
            "captured_at_utc": "2026-11-28T10:56:00Z",
        }
    }
    try:
        validate_bootstrap_snapshot(too_late, 13, deadline)
    except ValueError as exc:
        assert "inside the deadline safety buffer" in str(exc)
    else:
        raise AssertionError("snapshot captured inside five-minute buffer was accepted")


def test_same_gameweek_player_history_is_anchored_across_dgw_fixtures():
    frame = pd.DataFrame([
        {"fpl_code": 101, "fixture": 900, "kickoff_time": "2026-11-28T15:00:00Z",
         "player_minutes_3": 180.0, "p60_3": 0.8, "ar_dc_hit_rate_3": 0.6,
         "ar_rest_days": 5.0, "ar_opp_dc_allowed_3": 2.0},
        {"fpl_code": 101, "fixture": 901, "kickoff_time": "2026-12-01T15:00:00Z",
         "player_minutes_3": 0.0, "p60_3": 0.0, "ar_dc_hit_rate_3": 0.0,
         "ar_rest_days": 2.0, "ar_opp_dc_allowed_3": 7.0},
    ])
    features = [
        "player_minutes_3", "p60_3", "ar_dc_hit_rate_3",
        "ar_rest_days", "ar_opp_dc_allowed_3",
    ]
    result = anchor_player_features_to_deadline(frame, features)
    assert result["player_minutes_3"].tolist() == [180.0, 180.0]
    assert result["p60_3"].tolist() == [0.8, 0.8]
    assert result["ar_dc_hit_rate_3"].tolist() == [0.6, 0.6]
    assert result["ar_rest_days"].tolist() == [5.0, 2.0]
    assert result["ar_opp_dc_allowed_3"].tolist() == [2.0, 7.0]


def test_opponent_history_is_anchored_to_predeadline_state_across_dgw_fixtures():
    frame = pd.DataFrame([
        {"opponent_team_name": "Arsenal", "fixture": 900,
         "kickoff_time": "2026-11-28T15:00:00Z", "ar_opp_dc_allowed_3": 4.0},
        {"opponent_team_name": "Arsenal", "fixture": 901,
         "kickoff_time": "2026-12-01T15:00:00Z", "ar_opp_dc_allowed_3": 0.0},
        {"opponent_team_name": "Chelsea", "fixture": 902,
         "kickoff_time": "2026-12-01T15:00:00Z", "ar_opp_dc_allowed_3": 7.0},
    ])
    result = anchor_opponent_features_to_deadline(
        frame, ["ar_opp_dc_allowed_3"]
    )
    assert result["ar_opp_dc_allowed_3"].tolist() == [4.0, 4.0, 7.0]
