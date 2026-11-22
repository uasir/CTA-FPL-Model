"""Feature-availability policy shared by CTA points training and inference."""
from __future__ import annotations

import re
import pandas as pd

WINDOW_SUFFIX = re.compile(r"_(1|3|5|10|38)$")
FPL_NATIVE_MODE = "FPL_NATIVE_NO_UNDERSTAT"
PLAYER_UNDERSTAT_MODE = "FPL_PLAYER_UNDERSTAT"
UNDERSTAT_MODE = "FPL_UNDERSTAT"

PLAYER_UNDERSTAT_BASES = {
    "player_shots",
    "player_xg",
    "player_xa",
    "player_xgchain",
    "player_xgbuildup",
    "player_key_passes",
}
TEAM_UNDERSTAT_BASES = {
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
ALL_UNDERSTAT_BASES = PLAYER_UNDERSTAT_BASES | TEAM_UNDERSTAT_BASES


def unavailable_feature_names(
    feature_order: list[str],
    feature_source_mode: str = FPL_NATIVE_MODE,
) -> list[str]:
    """Return unavailable columns in schema order for the selected source mode."""
    if feature_source_mode == UNDERSTAT_MODE:
        unavailable = set()
    elif feature_source_mode == PLAYER_UNDERSTAT_MODE:
        unavailable = TEAM_UNDERSTAT_BASES
    elif feature_source_mode == FPL_NATIVE_MODE:
        unavailable = ALL_UNDERSTAT_BASES
    else:
        raise ValueError(f"unsupported feature source mode: {feature_source_mode}")
    return [
        name for name in feature_order
        if WINDOW_SUFFIX.sub("", name) in unavailable
    ]


def mask_unavailable_features(
    frame: pd.DataFrame,
    feature_order: list[str],
    feature_source_mode: str = FPL_NATIVE_MODE,
) -> tuple[pd.DataFrame, list[str]]:
    """Zero-fill unavailable Understat features consistently at train and score."""
    missing = sorted(set(feature_order) - set(frame.columns))
    if missing:
        raise ValueError(f"Feature frame is missing schema columns: {missing[:20]}")
    masked = unavailable_feature_names(feature_order, feature_source_mode)
    out = frame.copy()
    if masked:
        out.loc[:, masked] = 0.0
    return out, masked
