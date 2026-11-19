from evaluate_two_pm_transformer_walk_forward import (
    build_history_index, make_windows, points_representatives,
    within_band_eight_plus_share,
)


def _row(gw, points_feature, actual_points=2.0, appeared=1.0):
    return {
        "season": "2024-25",
        "fpl_element_id": "10",
        "gameweek": gw,
        "prior_gw_points": points_feature,
        "actual_points": actual_points,
        "appeared": appeared,
    }


def test_transformer_windows_are_player_season_scoped_and_never_include_future_gws():
    rows = [_row(1, 1.0), _row(2, 2.0), _row(3, 3.0)]
    index = build_history_index(rows)
    windows = make_windows([rows[1]], index, max_length=6)
    assert [r["gameweek"] for r in windows[0]] == [1, 2]
    assert windows[0][-1]["prior_gw_points"] == 2.0


def test_points_representatives_and_8plus_share_use_only_supplied_fit_rows():
    rows = [
        _row(1, 0, actual_points=0),
        _row(2, 0, actual_points=1),
        _row(3, 0, actual_points=7),
        _row(4, 0, actual_points=9),
        _row(5, 0, actual_points=12),
        _row(6, 0, actual_points=16, appeared=0),
    ]
    reps = points_representatives(rows)
    assert reps.shape == (6,)
    assert reps[1] == 0.0
    assert within_band_eight_plus_share(rows) == 0.5
