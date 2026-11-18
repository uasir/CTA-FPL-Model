import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_opta_team_context import evaluate, OPTA_FEATURES


def test_paired_temporal_holdout_compares_player_form_with_team_context():
    fpl_rows, opta_rows = [], []
    for gw in range(1, 11):
        for player_id in range(1, 13):
            fixture_id = (gw - 1) * 12 + player_id
            prior = float((gw + player_id) % 8)
            team_xg = float((gw * 2 + player_id) % 6) / 2
            fpl_rows.append({
                "season": "2026-27", "fpl_element_id": str(player_id),
                "fixture_id": str(fixture_id), "gameweek": str(gw),
                "prior_gameweeks_count": str(max(1, gw - 1)),
                "prior_gw_points": str(prior), "prior3_gw_points_avg": str(prior + 0.2),
                "prior5_gw_points_avg": str(prior + 0.1), "prior3_gw_minutes_avg": "70",
                "prior5_gw_minutes_avg": "65", "prior3_gw_xg_avg": "0.2",
                "prior3_gw_xa_avg": "0.1", "season_to_date_points_per90": "0.5",
                "was_home": "True", "team_difficulty_snapshot": "3",
                "opponent_difficulty_snapshot": "3", "target_total_points": str(2 + prior + team_xg),
            })
            opta_rows.append({
                "fpl_element_id": str(player_id), "fixture_id": str(fixture_id),
                **{feature: "0" for feature in OPTA_FEATURES},
                "opta_prior_matches_count": "3",
                "opta_prior3_expectedGoals_avg": str(team_xg),
            })
    report = evaluate(fpl_rows, opta_rows)
    assert report["status"] == "EXPLORATORY_ONLY"
    assert report["decision"] == "DO_NOT_PROMOTE"
    assert report["training_gameweeks"] == [1, 2, 3, 4, 5, 6]
    assert report["validation_gameweeks"] == [7, 8, 9, 10]
    assert report["join"]["joined_rows"] == 120
    assert report["join"]["missing_rows"] == 0
    assert "opta_prior3_expectedGoals_avg" in report["features"]["added_opta"]


def test_evaluation_rejects_missing_opta_context_rows():
    fpl_rows = [{"fpl_element_id": "1", "fixture_id": "1", "gameweek": "1"}]
    opta_rows = []
    try:
        evaluate(fpl_rows * 10, opta_rows)
    except ValueError as exc:
        assert "Missing Opta context" in str(exc)
    else:
        raise AssertionError("Expected missing Opta context to be rejected")
