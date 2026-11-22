"""Feature-availability policy shared by CTA points training and inference."""
from __future__ import annotations

import re
import pandas as pd

WINDOW_SUFFIX = re.compile(r"_(1|3|5|10|38)$")

# Understat-derived features are unavailable in the FPL-native pipeline mode.
# Keep the 286-column interface stable, but mask these columns to zero in both
# CTA points training and scoring so the model sees the same feature contract.
UNAVAILABLE_BASES = {
    "player_shots",
    "player_xg",
    "player_xa",
    "player_xgchain",
    "player_xgbuildup",
    "player_key_passes",
    "team_xg",
    "team_xga",
    "team_deep",
    "team_deep_allowed",
    "team_ppda_att",
    "team_ppda_def",
    "team_ppda_allowed_att",
    "team_ppda_allowed_def",
    "opp_xg",
    "opp_xga",
    "opp_deep",
    "opp_deep_allowed",
    "opp_ppda_att",
    "opp_ppda_def",
    "opp_ppda_allowed_att",
    "opp_ppda_allowed_def",
}


def unavailable_feature_names(feature_order: list[str]) -> list[str]:
    """Return unavailable feature columns in their original schema order."""
    return [
        name for name in feature_order
        if WINDOW_SUFFIX.sub("", name) in UNAVAILABLE_BASES
    ]


def mask_unavailable_features(
    frame: pd.DataFrame, feature_order: list[str],
) -> tuple[pd.DataFrame, list[str]]:
    """Zero-fill unavailable Understat features consistently at train and score."""
    missing = sorted(set(feature_order) - set(frame.columns))
    if missing:
        raise ValueError(f"Feature frame is missing schema columns: {missing[:20]}")
    masked = unavailable_feature_names(feature_order)
    out = frame.copy()
    if masked:
        out.loc[:, masked] = 0.0
    return out, masked
