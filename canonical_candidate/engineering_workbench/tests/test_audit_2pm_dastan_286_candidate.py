from pathlib import Path
import json

import pandas as pd
import pytest

from audit_2pm_dastan_286_candidate import audit_frame
from build_2pm_dastan_sequence_dataset import load_schema

ROOT = Path(__file__).resolve().parents[1]
FEATURES, _ = load_schema(ROOT / "config" / "2pm_dastan_286_schema.json")


def make_candidate_row(fixture, opp_value=0.0):
    row = {
        "season": "2025-26",
        "gameweek": 20,
        "fixture": fixture,
        "fpl_code": 1001,
        "deadline_time": "2026-01-01T10:00:00Z",
        "ep_next_snapshot_at": "2026-01-01T08:00:00Z",
        "signals_snapshot_at": "2026-01-01T08:30:00Z",
    }
    row.update({feature: 0.0 for feature in FEATURES})
    row["opp_xg_1"] = opp_value
    row["ar_defensive_contribution_3"] = -1.0
    return row


def test_candidate_audit_checks_schema_snapshots_and_only_claims_selected_anchor_scope():
    frame = pd.DataFrame(
        [
            make_candidate_row(5001, 1.0),
            make_candidate_row(5002, 2.0),
        ]
    )
    report = audit_frame(frame, FEATURES)
    assert report["feature_count"] == 286
    assert sum(report["feature_family_counts"].values()) == 286
    assert report["duplicate_player_fixture_keys"] == 0
    assert report["nonfinite_feature_values"] == 0
    assert report["same_player_gameweek_upstream_anchor_check"]["groups_with_differences"] == 0
    assert report["snapshot_timestamps"]["ep_next_snapshot_at"]["post_deadline_rows"] == 0
    assert report["defensive_feature_coverage"]["2025-26"]["columns"] > 0
    assert report["admission_status"] == "NOT_ADMITTED"


def test_candidate_audit_rejects_duplicate_player_fixture_keys():
    row = make_candidate_row(5001)
    with pytest.raises(ValueError, match="duplicate"):
        audit_frame(pd.DataFrame([row, row]), FEATURES)
