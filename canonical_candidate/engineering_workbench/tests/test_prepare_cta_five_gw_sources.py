from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_cta_five_gw_sources import player_elements, season_from_bootstrap


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
