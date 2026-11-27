import numpy as np
import pytest

from two_pm_staged_replay import build_stage_b_replay_plan


def pools():
    legacy = np.arange(10, dtype=np.int64)
    legacy_seasons = np.array(
        ["2020-21"] * 2 + ["2021-22"] * 2 + ["2022-23"] * 2
        + ["2023-24"] * 2 + ["2024-25"] * 2
    )
    legacy_regimes = np.zeros(10, dtype=np.uint8)
    adaptation = np.array([20, 21, 22, 23], dtype=np.int64)
    adaptation_seasons = np.array(["2025-26"] * 4)
    adaptation_regimes = np.ones(4, dtype=np.uint8)
    return legacy, legacy_seasons, legacy_regimes, adaptation, adaptation_seasons, adaptation_regimes


def build(seed=17, ratio=1.0, replace=False):
    legacy, legacy_seasons, legacy_regimes, adaptation, adaptation_seasons, adaptation_regimes = pools()
    return build_stage_b_replay_plan(
        legacy_indices=legacy,
        legacy_seasons=legacy_seasons,
        legacy_regime_codes=legacy_regimes,
        adaptation_indices=adaptation,
        adaptation_seasons=adaptation_seasons,
        adaptation_regime_codes=adaptation_regimes,
        replay_ratio=ratio,
        seed=seed,
        replace=replace,
    )


def test_stage_b_replay_plan_is_deterministic_and_preserves_regimes():
    first = build(seed=17, ratio=1.0)
    second = build(seed=17, ratio=1.0)
    assert first == second
    assert first["adaptation_sample_count"] == 4
    assert first["replay_sample_count"] == 4
    assert first["combined_sample_count"] == 8
    assert set(first["scoring_regime_code_by_sample"]) == {0, 1}
    for source, regime, season in zip(
        first["source_by_sample"],
        first["scoring_regime_code_by_sample"],
        first["season_by_sample"],
    ):
        if source == "legacy_replay":
            assert regime == 0
            assert season in {"2020-21", "2021-22", "2022-23", "2023-24", "2024-25"}
        else:
            assert source == "new_regime_adaptation"
            assert regime == 1
            assert season == "2025-26"


def test_stage_b_replay_plan_reports_per_season_regime_counts():
    plan = build(seed=9, ratio=1.5)
    assert plan["replay_sample_count"] == 6
    assert plan["combined_sample_count"] == 10
    assert sum(plan["counts_by_season_and_regime"].values()) == 10
    assert plan["counts_by_season_and_regime"]["2025-26|1"] == 4


def test_stage_b_replay_plan_fails_closed_on_wrong_regime_or_season():
    legacy, legacy_seasons, legacy_regimes, adaptation, adaptation_seasons, adaptation_regimes = pools()
    bad_regimes = adaptation_regimes.copy()
    bad_regimes[0] = 0
    with pytest.raises(ValueError, match="2025/26 adaptation rows"):
        build_stage_b_replay_plan(
            legacy_indices=legacy,
            legacy_seasons=legacy_seasons,
            legacy_regime_codes=legacy_regimes,
            adaptation_indices=adaptation,
            adaptation_seasons=adaptation_seasons,
            adaptation_regime_codes=bad_regimes,
            replay_ratio=1.0,
            seed=1,
        )
    bad_seasons = legacy_seasons.copy()
    bad_seasons[0] = "2025-26"
    with pytest.raises(ValueError, match="legacy replay pool"):
        build_stage_b_replay_plan(
            legacy_indices=legacy,
            legacy_seasons=bad_seasons,
            legacy_regime_codes=legacy_regimes,
            adaptation_indices=adaptation,
            adaptation_seasons=adaptation_seasons,
            adaptation_regime_codes=adaptation_regimes,
            replay_ratio=1.0,
            seed=1,
        )


def test_stage_b_replay_plan_requires_explicit_replacement_when_pool_is_too_small():
    legacy, legacy_seasons, legacy_regimes, adaptation, adaptation_seasons, adaptation_regimes = pools()
    with pytest.raises(ValueError, match="exceeds legacy pool"):
        build_stage_b_replay_plan(
            legacy_indices=legacy[:2],
            legacy_seasons=legacy_seasons[:2],
            legacy_regime_codes=legacy_regimes[:2],
            adaptation_indices=adaptation,
            adaptation_seasons=adaptation_seasons,
            adaptation_regime_codes=adaptation_regimes,
            replay_ratio=1.0,
            seed=1,
        )
    plan = build_stage_b_replay_plan(
        legacy_indices=legacy[:2],
        legacy_seasons=legacy_seasons[:2],
        legacy_regime_codes=legacy_regimes[:2],
        adaptation_indices=adaptation,
        adaptation_seasons=adaptation_seasons,
        adaptation_regime_codes=adaptation_regimes,
        replay_ratio=1.0,
        seed=1,
        replace=True,
    )
    assert plan["replay_sample_count"] == 4
