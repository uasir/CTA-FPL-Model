import pytest

from evaluate_two_pm_transformer_walk_forward import (
    TRANSFORMER_FEATURES, available_features, build_history_index, make_windows,
    points_representatives, within_band_eight_plus_share,
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


def test_encoded_windows_are_left_aligned_for_last_valid_step_pooling():
    from evaluate_two_pm_transformer_walk_forward import (
        TRANSFORMER_FEATURES, encode_windows, fit_preprocessor,
    )
    rows = [
        {name: float(i + 1) for i, name in enumerate(TRANSFORMER_FEATURES)},
        {name: float(i + 2) for i, name in enumerate(TRANSFORMER_FEATURES)},
    ]
    preprocessor = fit_preprocessor(rows)
    encoded, padding = encode_windows([rows], preprocessor, max_length=4)
    assert padding[0].tolist() == [False, False, True, True]
    assert encoded.shape == (1, 4, len(TRANSFORMER_FEATURES) * 2)


def test_fold_feature_selection_excludes_only_features_unobserved_in_training():
    rows = [{name: None for name in TRANSFORMER_FEATURES}]
    rows[0]["prior_gw_points"] = 0.0
    rows[0]["prior3_gw_xg_avg"] = None
    assert available_features(rows) == ("prior_gw_points",)


def test_affine_expected_points_calibrator_uses_calibration_pairs_and_clips_negative_outputs():
    from evaluate_two_pm_transformer_walk_forward import (
        apply_affine_expected_points_calibrator,
        fit_affine_expected_points_calibrator,
    )
    slope, intercept = fit_affine_expected_points_calibrator(
        [1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0]
    )
    assert slope == pytest.approx(2.0)
    assert intercept == pytest.approx(0.0)
    calibrated = apply_affine_expected_points_calibrator([-1.0, 1.0, 2.0], slope, intercept)
    assert calibrated == pytest.approx([0.0, 2.0, 4.0])


def test_affine_expected_points_calibrator_falls_back_when_calibration_is_degenerate():
    from evaluate_two_pm_transformer_walk_forward import fit_affine_expected_points_calibrator
    assert fit_affine_expected_points_calibrator([2.0, 2.0, 2.0], [1.0, 2.0, 3.0]) == (1.0, 0.0)
