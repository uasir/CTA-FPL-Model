from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_cta_five_gw_sources import (
    apply_historical_snapshot_safety_buffer,
    player_elements,
    season_from_bootstrap,
)


def test_player_elements_excludes_manager_entities():
    bootstrap = {
        "elements": [
            {"id": 1, "element_type": 1},
            {"id": 2, "element_type": 2},
            {"id": 3, "element_type": 3},
            {"id": 4, "element_type": 4},
            {"id": 5, "element_type": 5},
            {"id": 6, "element_type": 6},
        ]
    }
    assert [row["id"] for row in player_elements(bootstrap)] == [1, 2, 3, 4]


def test_season_from_bootstrap_handles_january_deadlines():
    bootstrap = {
        "events": [
            {"deadline_time": "2027-01-01T12:00:00Z"},
            {"deadline_time": "2027-01-08T12:00:00Z"},
        ]
    }
    assert season_from_bootstrap(bootstrap) == "2026-27"

def test_historical_snapshot_safety_buffer_rejects_captures_within_five_minutes(tmp_path: Path):
    import json
    import pandas as pd

    for stem in ("pre_deadline_ep_next", "pre_deadline_signals"):
        frame = pd.DataFrame({
            "season": ["2026-27", "2026-27"],
            "gameweek": [12, 12],
            "fpl_code": [101, 202],
            "snapshot_at": ["2026-11-01T09:54:00Z", "2026-11-01T09:57:00Z"],
            "deadline_time": ["2026-11-01T10:00:00Z", "2026-11-01T10:00:00Z"],
        })
        frame.to_parquet(tmp_path / f"{stem}.parquet", index=False)
        (tmp_path / f"{stem}.json").write_text(json.dumps({"rows": 2}))
    report = apply_historical_snapshot_safety_buffer(tmp_path, minutes=5)
    assert report["pre_deadline_ep_next"]["rows_retained"] == 1
    assert report["pre_deadline_ep_next"]["rows_rejected"] == 1
    filtered = pd.read_parquet(tmp_path / "pre_deadline_ep_next.parquet")
    assert filtered["fpl_code"].tolist() == [101]
