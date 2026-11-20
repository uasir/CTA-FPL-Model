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


def test_affine_expected_points_calibrator_never_reverses_prediction_order():
    from evaluate_two_pm_transformer_walk_forward import fit_affine_expected_points_calibrator
    slope, intercept = fit_affine_expected_points_calibrator(
        [1.0, 2.0, 3.0, 4.0], [8.0, 6.0, 4.0, 2.0]
    )
    assert slope == 0.0
    assert intercept == pytest.approx(5.0)


def test_deadline_local_ranking_summary_averages_deadlines_not_pooled_player_rows():
    from evaluate_two_pm_transformer_walk_forward import summarize_deadline_ranking_rows

    rows = {
        ("2017-18", 1): {
            "n": 100, "spearman": 0.5, "selected_mean_points": 4.0,
            "oracle_top_k_mean_points": 10.0, "top_k_lift_over_universe": 1.0,
            "top_k_regret_vs_oracle": 6.0,
        },
        ("2017-18", 2): {
            "n": 1000, "spearman": 0.7, "selected_mean_points": 6.0,
            "oracle_top_k_mean_points": 12.0, "top_k_lift_over_universe": 2.0,
            "top_k_regret_vs_oracle": 6.0,
        },
        ("2018-19", 1): {
            "n": 200, "spearman": 0.9, "selected_mean_points": 8.0,
            "oracle_top_k_mean_points": 14.0, "top_k_lift_over_universe": 3.0,
            "top_k_regret_vs_oracle": 6.0,
        },
    }
    summary = summarize_deadline_ranking_rows(rows, top_k=100)
    assert summary["n_deadlines"] == 3
    assert summary["n_seasons"] == 2
    assert summary["macro_spearman"] == pytest.approx(0.7)
    assert summary["macro_selected_mean_points"] == pytest.approx(6.0)
    assert summary["by_season"]["2017-18"]["selected_mean_points"] == pytest.approx(5.0)


def test_paired_deadline_ranking_bootstrap_is_paired_and_candidate_minus_reference():
    from evaluate_two_pm_transformer_walk_forward import paired_deadline_ranking_bootstrap

    reference = {
        ("2017-18", 1): {"selected_mean_points": 4.0, "spearman": 0.5},
        ("2017-18", 2): {"selected_mean_points": 5.0, "spearman": 0.6},
        ("2018-19", 1): {"selected_mean_points": 6.0, "spearman": 0.7},
    }
    candidate = {
        key: {"selected_mean_points": row["selected_mean_points"] + 1.0,
              "spearman": row["spearman"] + 0.1}
        for key, row in reference.items()
    }
    report = paired_deadline_ranking_bootstrap(candidate, reference, n_boot=100)
    assert report["season_clusters"] == 2
    assert report["deadline_clusters"] == 3
    assert report["candidate_minus_reference_macro_selected_mean_points"] == pytest.approx(1.0)
    assert report["candidate_minus_reference_macro_spearman"] == pytest.approx(0.1)
    assert report["selected_mean_points_delta_ci95"] == pytest.approx([1.0, 1.0])


def test_paired_deadline_ranking_bootstrap_rejects_nonidentical_deadlines():
    from evaluate_two_pm_transformer_walk_forward import paired_deadline_ranking_bootstrap

    with pytest.raises(ValueError, match="identical deadlines"):
        paired_deadline_ranking_bootstrap(
            {("2017-18", 1): {"selected_mean_points": 4.0, "spearman": 0.5}},
            {("2017-18", 2): {"selected_mean_points": 4.0, "spearman": 0.5}},
            n_boot=10,
        )
