"""Audit 2025/26 defensive rolling-feature warm-up without reading target labels."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

EXPECTED_SCHEMA_FEATURES = 286
EXPECTED_DEFENSIVE_FEATURES = 27
DEFENSIVE_PREFIXES = (
    "ar_defensive_contribution_", "ar_cbit_", "ar_recoveries_",
    "ar_tackles_", "ar_dc_hit_rate_", "ar_dc_near_rate_",
    "ar_dc_ppg_", "ar_opp_dc_allowed_", "ar_opp_tackles_allowed_",
)
IDENTITY_COLUMNS = ("season", "gameweek", "fpl_code")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def derive_defensive_features(schema: dict[str, Any]) -> list[str]:
    features = schema.get("feature_order")
    if not isinstance(features, list) or len(features) != EXPECTED_SCHEMA_FEATURES:
        raise ValueError("Pinned schema must contain exactly 286 ordered features")
    if len(features) != len(set(features)):
        raise ValueError("Pinned schema contains duplicate feature names")
    selected = [
        name for name in features
        if any(name.startswith(prefix) for prefix in DEFENSIVE_PREFIXES)
    ]
    if len(selected) != EXPECTED_DEFENSIVE_FEATURES:
        raise ValueError(
            f"Expected exactly 27 defensive features, found {len(selected)}"
        )
    return selected


def audit_frame(frame: pd.DataFrame, features: list[str]) -> dict[str, Any]:
    identity_columns = [*IDENTITY_COLUMNS]
    if "fixture" in frame.columns:
        identity_columns.append("fixture")
    required = set(identity_columns) | set(features)
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Candidate is missing required audit columns: {missing}")
    data = frame[[*identity_columns, *features]].copy()
    data["season"] = data["season"].astype(str)
    if data["season"].nunique() != 1 or data["season"].iloc[0] != "2025-26":
        raise ValueError("Warm-up audit accepts only 2025-26 candidate rows")
    data["gameweek"] = pd.to_numeric(data["gameweek"], errors="coerce")
    data["fpl_code"] = pd.to_numeric(data["fpl_code"], errors="coerce")
    if data[["gameweek", "fpl_code"]].isna().any().any():
        raise ValueError("Player/Gameweek identity contains null or non-numeric values")
    data["gameweek"] = data["gameweek"].astype(int)
    data["fpl_code"] = data["fpl_code"].astype(int)
    if data.duplicated(identity_columns).any():
        grain = "player-fixture" if "fixture" in identity_columns else "player-Gameweek"
        raise ValueError(f"Duplicate {grain} candidate rows")
    numeric = data[features].apply(pd.to_numeric, errors="coerce")
    values = numeric.to_numpy(dtype=np.float64)
    if np.isinf(values).any():
        raise ValueError("Defensive feature block contains infinite values")
    finite = numeric.notna()
    complete = finite.all(axis=1)
    by_feature: dict[str, Any] = {}
    for name in features:
        observed = numeric[name].dropna()
        by_feature[name] = {
            "finite": int(observed.size),
            "missing": int(numeric[name].isna().sum()),
            "zero": int(observed.eq(0).sum()),
            "nonzero": int(observed.ne(0).sum()),
            "first_gw_with_any_finite": (
                int(data.loc[numeric[name].notna(), "gameweek"].min())
                if numeric[name].notna().any() else None
            ),
            "first_gw_with_full_feature_coverage": next(
                (
                    int(gw) for gw, idx in data.groupby("gameweek").groups.items()
                    if bool(numeric.loc[idx, name].notna().all())
                ),
                None,
            ),
        }
    by_gw: dict[str, Any] = {}
    for gw, idx in data.groupby("gameweek", sort=True).groups.items():
        gw_finite = finite.loc[idx]
        row_key = "player_fixture_rows" if "fixture" in identity_columns else "player_gameweek_rows"
        by_gw[str(int(gw))] = {
            row_key: int(len(idx)),
            "candidate_rows": int(len(idx)),
            "distinct_players": int(data.loc[idx, "fpl_code"].nunique()),
            "finite_values": int(gw_finite.to_numpy().sum()),
            "possible_values": int(gw_finite.size),
            "missing_values": int((~gw_finite).to_numpy().sum()),
            "complete_27_feature_rows": int(complete.loc[idx].sum()),
            "rows_with_any_defensive_history": int(gw_finite.any(axis=1).sum()),
            "per_feature": {
                name: {
                    "finite": int(gw_finite[name].sum()),
                    "missing": int((~gw_finite[name]).sum()),
                }
                for name in features
            },
        }
    return {
        "season": "2025-26",
        "candidate_rows": int(len(data)),
        "identity_grain": "player_fixture" if "fixture" in identity_columns else "player_gameweek",
        "distinct_gameweeks": sorted(int(x) for x in data["gameweek"].unique()),
        "defensive_feature_count": len(features),
        "feature_order": features,
        "feature_level": by_feature,
        "gameweek_level": by_gw,
        "label_isolation": {
            "target_points_loaded": False,
            "total_points_loaded": False,
            "target_labels_used_for_cutoff": False,
        },
        "interpretation_guardrails": [
            "Missing values remain missing; they are not converted to zero.",
            "Complete-feature coverage is descriptive and does not authorize dropping rows.",
            "This audit does not choose a training/validation cutoff.",
            "This audit does not establish point-in-time publication availability.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    schema_bytes = args.schema.read_bytes()
    schema = json.loads(schema_bytes)
    features = derive_defensive_features(schema)
    frame = pd.read_parquet(
        args.candidate,
        columns=[*IDENTITY_COLUMNS, *features],
    )
    report = audit_frame(frame, features)
    report["candidate_file_sha256"] = sha256(args.candidate)
    report["schema_file_sha256"] = hashlib.sha256(schema_bytes).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
