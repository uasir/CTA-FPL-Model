"""Deterministic, regime-preserving Stage B historical replay sampling."""
from __future__ import annotations

from collections import Counter
from typing import Any, Sequence
import math

import numpy as np


REPLAY_PLAN_VERSION = "1.0.0"
LEGACY_REGIME_CODE = 0
DEFENSIVE_REGIME_CODE = 1


def build_stage_b_replay_plan(
    *,
    legacy_indices: Sequence[int],
    legacy_seasons: Sequence[str],
    legacy_regime_codes: Sequence[int],
    adaptation_indices: Sequence[int],
    adaptation_seasons: Sequence[str],
    adaptation_regime_codes: Sequence[int],
    replay_ratio: float,
    seed: int,
    replace: bool = False,
) -> dict[str, Any]:
    """Sample legacy rows for Stage B without relabelling their scoring regime.

    Inputs must already be restricted to the Stage B training partition. The
    function never accepts or discovers validation/OOT rows; callers own split
    isolation and pass only eligible training indices.
    """
    if not math.isfinite(float(replay_ratio)) or replay_ratio < 0:
        raise ValueError("replay_ratio must be finite and non-negative")
    if int(seed) != seed or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if not isinstance(replace, bool):
        raise ValueError("replace must be boolean")

    legacy = np.asarray(legacy_indices)
    adaptation = np.asarray(adaptation_indices)
    legacy_season = np.asarray(legacy_seasons, dtype=str)
    adaptation_season = np.asarray(adaptation_seasons, dtype=str)
    legacy_regime = np.asarray(legacy_regime_codes)
    adaptation_regime = np.asarray(adaptation_regime_codes)

    if legacy.ndim != 1 or adaptation.ndim != 1:
        raise ValueError("sample indices must be one-dimensional")
    if legacy.size == 0 or adaptation.size == 0:
        raise ValueError("legacy replay and 2025/26 adaptation pools must both be non-empty")
    if any(array.shape != legacy.shape for array in (legacy_season, legacy_regime)):
        raise ValueError("legacy season/regime metadata must align with legacy indices")
    if any(array.shape != adaptation.shape for array in (adaptation_season, adaptation_regime)):
        raise ValueError("adaptation season/regime metadata must align with adaptation indices")
    if not np.issubdtype(legacy.dtype, np.integer) or not np.issubdtype(adaptation.dtype, np.integer):
        raise ValueError("sample indices must be integers")
    if (legacy < 0).any() or (adaptation < 0).any():
        raise ValueError("sample indices must be non-negative")
    if len(set(legacy.tolist())) != legacy.size or len(set(adaptation.tolist())) != adaptation.size:
        raise ValueError("sample indices must be unique within each pool")
    if set(legacy.tolist()).intersection(adaptation.tolist()):
        raise ValueError("legacy replay and adaptation sample pools must be disjoint")
    if not np.isin(legacy_regime, [LEGACY_REGIME_CODE]).all():
        raise ValueError("legacy replay rows must retain scoring-regime code 0")
    if not np.isin(adaptation_regime, [DEFENSIVE_REGIME_CODE]).all():
        raise ValueError("2025/26 adaptation rows must use scoring-regime code 1")
    if not np.isin(legacy_season, ["2020-21", "2021-22", "2022-23", "2023-24", "2024-25"]).all():
        raise ValueError("legacy replay pool may contain only 2020/21–2024/25")
    if not np.all(adaptation_season == "2025-26"):
        raise ValueError("Stage B adaptation pool must contain only 2025/26 rows")

    replay_count = int(math.ceil(adaptation.size * float(replay_ratio)))
    if replay_count and not replace and replay_count > legacy.size:
        raise ValueError("requested replay count exceeds legacy pool without replacement")

    rng = np.random.default_rng(int(seed))
    selected_legacy = (
        rng.choice(legacy, size=replay_count, replace=replace).astype(np.int64)
        if replay_count else np.empty(0, dtype=np.int64)
    )
    selected_adaptation = adaptation.astype(np.int64, copy=True)
    combined_indices = np.concatenate([selected_adaptation, selected_legacy])
    combined_regimes = np.concatenate([
        np.full(selected_adaptation.size, DEFENSIVE_REGIME_CODE, dtype=np.uint8),
        np.full(selected_legacy.size, LEGACY_REGIME_CODE, dtype=np.uint8),
    ])
    legacy_season_by_index = {
        int(index): str(season) for index, season in zip(legacy, legacy_season)
    }
    selected_legacy_seasons = np.asarray(
        [legacy_season_by_index[int(index)] for index in selected_legacy],
        dtype=str,
    )
    combined_seasons = np.concatenate([adaptation_season, selected_legacy_seasons])
    source = np.concatenate([
        np.full(selected_adaptation.size, "new_regime_adaptation", dtype="U24"),
        np.full(selected_legacy.size, "legacy_replay", dtype="U24"),
    ])
    order = rng.permutation(combined_indices.size)
    combined_indices = combined_indices[order]
    combined_regimes = combined_regimes[order]
    combined_seasons = combined_seasons[order]
    source = source[order]

    return {
        "plan_version": REPLAY_PLAN_VERSION,
        "seed": int(seed),
        "bit_generator": "PCG64",
        "replay_ratio_legacy_per_adaptation_sample": float(replay_ratio),
        "replace_legacy_samples": replace,
        "adaptation_sample_count": int(selected_adaptation.size),
        "replay_sample_count": int(selected_legacy.size),
        "combined_sample_count": int(combined_indices.size),
        "indices": combined_indices.tolist(),
        "season_by_sample": combined_seasons.tolist(),
        "scoring_regime_code_by_sample": combined_regimes.tolist(),
        "source_by_sample": source.tolist(),
        "counts_by_season_and_regime": {
            f"{season}|{regime}": count
            for (season, regime), count in sorted(
                Counter(zip(combined_seasons.tolist(), combined_regimes.tolist())).items()
            )
        },
        "validation_or_oot_indices_accepted": False,
    }
