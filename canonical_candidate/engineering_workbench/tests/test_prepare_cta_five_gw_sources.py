from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_cta_five_gw_sources import (
    understat_players_needing_refresh,
    historical_source_seasons,
    apply_historical_snapshot_safety_buffer,
    copy_verified_dastan_release,
    copy_verified_dastan_model_contract,
    copy_dastan_operational_mappings,
    historical_source_seasons,
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



def test_copy_verified_dastan_release_imports_only_verified_published_artifacts(tmp_path: Path):
    import hashlib
    import json
    import pytest

    release = tmp_path / "dastan" / "data"
    training = tmp_path / "training"
    release.mkdir(parents=True)
    files = {
        "features.parquet": b"published-feature-frame",
        "pre_deadline_ep_next.parquet": b"published-ep-next",
        "pre_deadline_signals.parquet": b"published-signals",
    }
    manifest_files = {}
    for name, payload in files.items():
        (release / name).write_bytes(payload)
        manifest_files[name] = {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
            "rows": 3,
            "columns": 5,
        }
    (release / "release_manifest.json").write_text(
        json.dumps({"files": manifest_files}), encoding="utf-8"
    )

    report = copy_verified_dastan_release(tmp_path / "dastan", training)
    assert set(report["artifacts"]) == set(files)
    for name, payload in files.items():
        assert (training / name).read_bytes() == payload
        assert report["artifacts"][name]["sha256"] == hashlib.sha256(payload).hexdigest()

    (release / "features.parquet").write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="hash mismatch"):
        copy_verified_dastan_release(tmp_path / "dastan", training)


def test_snapshot_safety_buffer_creates_provenance_for_imported_artifacts(tmp_path: Path):
    import json
    import pandas as pd

    for stem in ("pre_deadline_ep_next", "pre_deadline_signals"):
        pd.DataFrame({
            "season": ["2026-27", "2026-27"],
            "gameweek": [12, 12],
            "fpl_code": [101, 202],
            "snapshot_at": ["2026-11-01T09:54:00Z", "2026-11-01T09:57:00Z"],
            "deadline_time": ["2026-11-01T10:00:00Z", "2026-11-01T10:00:00Z"],
        }).to_parquet(tmp_path / f"{stem}.parquet", index=False)

    report = apply_historical_snapshot_safety_buffer(tmp_path, minutes=5)
    assert report["pre_deadline_ep_next"]["rows_retained"] == 1
    sidecar = json.loads((tmp_path / "pre_deadline_ep_next.json").read_text())
    assert sidecar["source"] == "imported Dastan release artifact"


def test_copy_verified_dastan_model_contract_imports_all_40_files(tmp_path: Path):
    import hashlib
    import json

    model_source = tmp_path / "dastan" / "models"
    model_source.mkdir(parents=True)
    files = {}
    for index in range(40):
        name = f"contract_{index:02d}.json"
        payload = f"artifact-{index}".encode()
        (model_source / name).write_bytes(payload)
        files[name] = {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
        }
    (model_source / "artifact_manifest.json").write_text(
        json.dumps({"public_version": "1.1.0", "files": files}),
        encoding="utf-8",
    )

    report = copy_verified_dastan_model_contract(tmp_path / "dastan", tmp_path / "outputs")
    assert report["artifact_count"] == 40
    assert report["model_version"] == "1.1.0"
    for name in files:
        assert (tmp_path / "outputs" / "dastan_model" / name).is_file()


def test_copy_dastan_operational_mappings_preserves_current_mapping_files(tmp_path: Path):
    source = tmp_path / "dastan" / "data" / "mappings"
    source.mkdir(parents=True)
    (source / "current_fpl_understat_players.csv").write_text("fpl_code,understat_player_id\n1,11\n")
    (source / "current_fpl_understat_clubs.csv").write_text("club_name,understat_name\nArsenal,Arsenal\n")
    report = copy_dastan_operational_mappings(tmp_path / "dastan", tmp_path / "outputs")
    assert report["artifact_count"] == 2
    assert (tmp_path / "outputs" / "dastan_mappings" / "current_fpl_understat_players.csv").is_file()


def test_understat_refresh_only_selects_current_roster_appearances_missing_from_both_caches(tmp_path: Path):
    import pandas as pd

    class FakeSources:
        @staticmethod
        def _expected_understat_player_dates(raw_dir, seasons):
            assert seasons == ["2026-27"]
            from datetime import date
            return {
                101: {date(2026, 8, 15)},
                202: set(),
                303: {date(2026, 9, 1)},
                404: {date(2026, 9, 15)},
                505: {date(2026, 10, 1)},
            }

    csv_root = tmp_path / "vaastav" / "understat" / "players"
    json_root = tmp_path / "understat" / "players"
    csv_root.mkdir(parents=True)
    json_root.mkdir(parents=True)
    pd.DataFrame({"date": ["2026-09-01"]}).to_csv(csv_root / "303.csv", index=False)
    (json_root / "404.json").write_text('[{"date":"2026-09-15"}]')
    (json_root / "505.json").write_text('[{"date":"2026-09-20"}]')

    selected = understat_players_needing_refresh(
        tmp_path, ["2026-27"], {101, 202, 303, 404, 505}, FakeSources,
    )
    assert selected == {101, 505}
