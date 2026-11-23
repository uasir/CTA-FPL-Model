"""Player-level forecast record adapter for the paper-governed 2PM model.

This adapter exposes only the predictive distribution and provenance. It contains no
ownership, EO, CoVar, transfer, squad, XI, bench, captaincy or recommendation logic.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

import torch

from two_component_poisson_transformer import (
    MODEL_NAME,
    MODEL_ARCHITECTURE_VERSION,
    poisson_mixture_tail_probability,
)


def _iso_timestamp(value: str | datetime, field: str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError(f"{field} must be timezone-aware")
        return value.isoformat()
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty ISO timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.isoformat()


def build_forecast_records(
    output: dict[str, Any],
    *,
    player_ids: Sequence[int | str],
    target_gameweeks: Sequence[int],
    target_fixture_ids: Sequence[int | str],
    forecast_as_of: str | datetime,
    training_cutoff: str | datetime,
    feature_schema_version: str,
    data_snapshot_hashes: dict[str, str],
    model_version: str = MODEL_ARCHITECTURE_VERSION,
    quality_metadata: dict[str, Any] | Sequence[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Serialize analytic forecasts and full mixture parameters into player rows."""
    if torch is None:
        raise ImportError("PyTorch is required to serialize 2PM model outputs")
    count = len(player_ids)
    if (
        count == 0
        or len(target_gameweeks) != count
        or len(target_fixture_ids) != count
    ):
        raise ValueError(
            "player_ids, target_gameweeks and target_fixture_ids must be non-empty and equal length"
        )
    if any(not str(fixture_id).strip() for fixture_id in target_fixture_ids):
        raise ValueError("target_fixture_ids must be non-empty")
    if any(int(gameweek) < 1 for gameweek in target_gameweeks):
        raise ValueError("target_gameweeks must be positive integers")
    identity_keys = [
        (str(player), int(gameweek), str(fixture))
        for player, gameweek, fixture in zip(
            player_ids, target_gameweeks, target_fixture_ids
        )
    ]
    if len(identity_keys) != len(set(identity_keys)):
        raise ValueError("duplicate player/Gameweek/fixture forecast identities")
    if not feature_schema_version.strip() or not model_version.strip():
        raise ValueError("feature schema and model versions are required")
    if not isinstance(data_snapshot_hashes, dict) or not data_snapshot_hashes:
        raise ValueError("data_snapshot_hashes must be a non-empty mapping")
    if any(not key or not value for key, value in data_snapshot_hashes.items()):
        raise ValueError("snapshot hash keys and values must be non-empty")

    as_of = _iso_timestamp(forecast_as_of, "forecast_as_of")
    cutoff = _iso_timestamp(training_cutoff, "training_cutoff")
    if datetime.fromisoformat(cutoff) > datetime.fromisoformat(as_of):
        raise ValueError("training_cutoff cannot be later than forecast_as_of")

    required = {
        "p", "lambda_1", "lambda_2", "expected_points", "variance",
        "standard_deviation",
    }
    missing = sorted(required - set(output))
    if missing:
        raise ValueError(f"model output is missing fields: {missing}")
    vectors = {}
    for field in required:
        tensor = torch.as_tensor(output[field]).detach().cpu().reshape(-1)
        if tensor.numel() != count or not torch.isfinite(tensor).all():
            raise ValueError(f"model output field {field} has invalid shape or values")
        vectors[field] = tensor

    if (vectors["p"] <= 0).any() or (vectors["p"] >= 1).any():
        raise ValueError("mixture probabilities must be strictly between zero and one")
    if (vectors["lambda_1"] <= 0).any() or (vectors["lambda_2"] <= 0).any():
        raise ValueError("Poisson rates must be strictly positive")
    if (vectors["variance"] < 0).any() or (vectors["standard_deviation"] < 0).any():
        raise ValueError("predictive variance and standard deviation must be non-negative")
    expected = (
        vectors["p"] * vectors["lambda_1"]
        + (1.0 - vectors["p"]) * vectors["lambda_2"]
    )
    second_moment = (
        vectors["p"] * (vectors["lambda_1"] + vectors["lambda_1"].square())
        + (1.0 - vectors["p"]) * (
            vectors["lambda_2"] + vectors["lambda_2"].square()
        )
    )
    variance = (second_moment - expected.square()).clamp_min(0.0)
    if not torch.allclose(vectors["expected_points"], expected, rtol=1e-5, atol=1e-6):
        raise ValueError("expected_points disagrees with mixture parameters")
    if not torch.allclose(vectors["variance"], variance, rtol=1e-5, atol=1e-6):
        raise ValueError("variance disagrees with mixture parameters")
    if not torch.allclose(
        vectors["standard_deviation"], torch.sqrt(variance), rtol=1e-5, atol=1e-6
    ):
        raise ValueError("standard_deviation disagrees with mixture variance")

    tails = {
        threshold: poisson_mixture_tail_probability(output, threshold)
        .detach().cpu().reshape(-1)
        for threshold in (6, 8, 10)
    }
    if any(not torch.isfinite(values).all() for values in tails.values()):
        raise ValueError("mixture threshold probabilities must be finite")

    if quality_metadata is None:
        qualities = [{} for _ in range(count)]
    elif isinstance(quality_metadata, dict):
        qualities = [quality_metadata.copy() for _ in range(count)]
    else:
        qualities = list(quality_metadata)
        if len(qualities) != count:
            raise ValueError("quality_metadata sequence must match forecast batch size")

    records = []
    for index, (player_id, gameweek, fixture_id) in enumerate(
        zip(player_ids, target_gameweeks, target_fixture_ids)
    ):
        records.append(
            {
                "player_id": player_id,
                "target_gameweek": int(gameweek),
                "target_fixture_id": fixture_id,
                "forecast_grain": "player_fixture",
                "forecast_type": "fixture_level_analytic_two_component_poisson_mixture",
                "model_name": MODEL_NAME,
                "model_version": model_version,
                "feature_schema_version": feature_schema_version,
                "forecast_as_of": as_of,
                "training_cutoff": cutoff,
                "data_snapshot_hashes": data_snapshot_hashes.copy(),
                "p": float(vectors["p"][index]),
                "lambda_1": float(vectors["lambda_1"][index]),
                "lambda_2": float(vectors["lambda_2"][index]),
                "expected_points": float(vectors["expected_points"][index]),
                "variance": float(vectors["variance"][index]),
                "standard_deviation": float(vectors["standard_deviation"][index]),
                "probability_6_plus": float(tails[6][index]),
                "probability_8_plus": float(tails[8][index]),
                "probability_10_plus": float(tails[10][index]),
                "quality_metadata": qualities[index],
                "production_eligible": False,
            }
        )
    return records
