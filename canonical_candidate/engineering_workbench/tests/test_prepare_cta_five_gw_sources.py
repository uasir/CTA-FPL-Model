from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_cta_five_gw_sources import (
    apply_historical_snapshot_safety_buffer,
    download_and_merge_pinned_understat_player_histories,
    player_elements,
    season_from_bootstrap,
    write_csv_frame,
    write_live_fixture_schedule,
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


def test_historical_source_seasons_excludes_live_season_and_preserves_order():
    assert historical_source_seasons(
        ["2022-23", "2023-24", "2024-25", "2025-26"], "2026-27"
    ) == ["2022-23", "2023-24", "2024-25", "2025-26"]


def test_historical_source_seasons_rejects_training_overlap():
    import pytest

    with pytest.raises(ValueError, match="overlaps"):
        historical_source_seasons(["2025-26", "2026-27"], "2026-27")


def test_historical_source_seasons_rejects_empty_training_history():
    import pytest

    with pytest.raises(ValueError, match="empty"):
        historical_source_seasons([], "2026-27")

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


def test_csv_writer_uses_real_newlines_and_round_trips(tmp_path: Path):
    import pandas as pd

    path = tmp_path / "nested" / "sample.csv"
    write_csv_frame(pd.DataFrame([{"id": 1, "name": "Arsenal"}]), path)
    raw = path.read_bytes()
    assert bytes([92, 110]) not in raw
    assert raw.count(bytes([10])) >= 2
    assert pd.read_csv(path).to_dict("records") == [{"id": 1, "name": "Arsenal"}]

def test_live_fixture_schedule_writer_round_trips(tmp_path: Path):
    import pandas as pd

    path = write_live_fixture_schedule(tmp_path, "2026-27", [{
        "id": 99, "event": 12, "finished": False,
        "team_h": 1, "team_a": 2, "kickoff_time": "2026-11-28T15:00:00Z",
    }])
    frame = pd.read_csv(path)
    assert frame.loc[0, "id"] == 99
    assert frame.loc[0, "event"] == 12


def test_parallel_understat_fallbacks_fetch_concurrently_and_write_json(tmp_path, monkeypatch):
    import json
    import sys
    import threading
    import time
    import types
    from prepare_cta_five_gw_sources import parallel_understat_fallbacks

    lock = threading.Lock()
    active = 0
    peak = 0

    class FakeSession:
        def request(self, method, url, **kwargs):
            assert kwargs.get("timeout") == (10, 45)
            return None

    class FakeClient:
        def __init__(self):
            self.session = FakeSession()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def player(self, player):
            self.player_id = int(player)
            return self

        def get_match_data(self):
            nonlocal active, peak
            self.session.request("GET", "https://understat.example/player")
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.03)
            with lock:
                active -= 1
            return [{"id": self.player_id}]

    fake_module = types.ModuleType("understatapi")
    fake_module.UnderstatClient = FakeClient
    monkeypatch.setitem(sys.modules, "understatapi", fake_module)

    parallel_understat_fallbacks(
        tmp_path, [11, 12, 13, 14, 15, 16], [],
        force=False, allow_missing=False, workers=3,
    )

    assert 1 < peak <= 3
    for player_id in [11, 12, 13, 14, 15, 16]:
        path = tmp_path / "understat" / "players" / f"{player_id}.json"
        assert json.loads(path.read_text()) == [{"id": player_id}]


def test_pinned_understat_histories_merge_all_seasons_before_fallback(tmp_path: Path):
    import pandas as pd

    season_rows = {
        "https://raw.example/data/2023-24/understat/Mohamed_Salah_1250.csv":
            """id,date,season,goals
1,2023-09-01,2023,1
""",
        "https://raw.example/data/2024-25/understat/Mohamed_Salah_1250.csv":
            """id,date,season,goals
2,2024-09-01,2024,0
""",
    }

    class FakeSources:
        VAASTAV_RAW = "https://raw.example/"

        @staticmethod
        def _needed_understat_ids(raw_dir, seasons):
            return {1250}

        @staticmethod
        def _tree(raw_dir, force=False):
            return [
                "data/2023-24/understat/Mohamed_Salah_1250.csv",
                "data/2024-25/understat/Mohamed_Salah_1250.csv",
                "data/2024-25/understat/Other_Player_9999.csv",
                "data/2022-23/understat/Mohamed_Salah_1250.csv",
            ]

        @staticmethod
        def _download_many(jobs, workers, force):
            for url, destination in jobs:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(season_rows[url])

    report = download_and_merge_pinned_understat_player_histories(
        tmp_path, ["2023-24", "2024-25"], FakeSources, workers=2,
    )
    merged = pd.read_csv(
        tmp_path / "vaastav" / "understat" / "players" / "1250.csv"
    )
    assert merged["id"].tolist() == [1, 2]
    assert merged["season"].tolist() == [2023, 2024]
    assert report["pinned_season_files_downloaded"] == 2
    assert report["pinned_player_ids_merged"] == 1

def test_parallel_understat_fallback_stops_on_provider_wide_preflight_failure(tmp_path, monkeypatch):
    import sys
    import types
    import pytest
    from prepare_cta_five_gw_sources import parallel_understat_fallbacks

    class FakeSession:
        def request(self, method, url, **kwargs):
            raise RuntimeError("HTTP 403 from Understat")

    class FakeClient:
        def __init__(self):
            self.session = FakeSession()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def player(self, player):
            return self

        def get_match_data(self):
            self.session.request("GET", "https://understat.example/player")
            return []

    fake_module = types.ModuleType("understatapi")
    fake_module.UnderstatClient = FakeClient
    monkeypatch.setitem(sys.modules, "understatapi", fake_module)

    with pytest.raises(RuntimeError, match="preflight failed.*HTTP 403"):
        parallel_understat_fallbacks(
            tmp_path, [101, 202, 303, 404, 505], [],
            force=False, allow_missing=False, workers=4,
        )

