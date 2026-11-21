from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from m4_covar_matched_outcome_panel import (
    MatchedPanelError,
    build_matched_panel_archive,
)


def make_archive(root: Path, gw: int, pid: int = 10) -> Path:
    directory = root / f"gw{gw}"
    directory.mkdir()
    panel = {
        "dataset_type": "PROSPECTIVE_CONVENTIONAL_FORECAST_TO_FINAL_OUTCOME_MATCH",
        "season": "2026-27",
        "gameweek": gw,
        "forecast_snapshot_id": f"snapshot-{gw}",
        "forecast_as_of_utc": f"2026-11-{gw:02d}T08:00:00Z",
        "finality_status": "PASS_EXACT_MATCH",
        "missing_observations_zero_filled": 0,
        "decision_weight": 0.0,
        "production_eligible": False,
        "matched_rows": [{
            "season": "2026-27", "gameweek": gw, "fpl_element_id": pid,
            "expected_points": 4.0, "actual_points": 5.0,
            "finality_status": "PASS_EXACT_MATCH",
        }],
    }
    raw = (json.dumps(panel, indent=2, sort_keys=True) + "\n").encode()
    (directory / "matched_forecast_outcomes.json").write_bytes(raw)
    manifest = {
        "status": "MATCHED_RESEARCH_PANEL_CREATED",
        "season": "2026-27", "gameweek": gw, "matched_player_count": 1,
        "matched_output_sha256": hashlib.sha256(raw).hexdigest(),
    }
    (directory / "match_manifest.json").write_text(json.dumps(manifest))
    return directory


def test_accumulates_distinct_gameweek_clusters_and_preserves_rows(tmp_path):
    a = make_archive(tmp_path, 11, 10)
    b = make_archive(tmp_path, 12, 10)
    result = build_matched_panel_archive([b, a], tmp_path / "out", repository_root=tmp_path / "repo")
    panel = json.loads((tmp_path / "out" / "multi_gameweek_matched_panel.json").read_text())
    assert result["gameweeks"] == [11, 12]
    assert result["matched_player_gameweek_rows"] == 2
    assert [row["gameweek"] for row in panel["matched_rows"]] == [11, 12]
    assert panel["cluster_unit"] == "GAMEWEEK"
    assert panel["player_rows_within_gameweek_are_not_independent_gameweek_samples"] is True
    assert panel["joint_dependence_inferred_from_marginal_player_rows"] is False


def test_rejects_duplicate_gameweek_archive(tmp_path):
    a = make_archive(tmp_path, 11)
    with pytest.raises(MatchedPanelError, match="unique positive"):
        build_matched_panel_archive([a, a], tmp_path / "out", repository_root=tmp_path / "repo")


def test_rejects_cross_season_archives(tmp_path):
    a = make_archive(tmp_path, 11)
    b = make_archive(tmp_path, 12)
    panel_path = b / "matched_forecast_outcomes.json"
    panel = json.loads(panel_path.read_text())
    panel["season"] = "2025-26"
    raw = (json.dumps(panel, indent=2, sort_keys=True) + "\n").encode()
    panel_path.write_bytes(raw)
    manifest_path = b / "match_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["season"] = "2025-26"
    manifest["matched_output_sha256"] = hashlib.sha256(raw).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(MatchedPanelError, match="different seasons"):
        build_matched_panel_archive([a, b], tmp_path / "out", repository_root=tmp_path / "repo")


def test_rejects_tampered_matched_output(tmp_path):
    a = make_archive(tmp_path, 11)
    (a / "matched_forecast_outcomes.json").write_text("{}")
    with pytest.raises(MatchedPanelError, match="hash mismatch"):
        build_matched_panel_archive([a], tmp_path / "out", repository_root=tmp_path / "repo")


def test_rejects_production_eligible_input(tmp_path):
    a = make_archive(tmp_path, 11)
    path = a / "matched_forecast_outcomes.json"
    panel = json.loads(path.read_text())
    panel["production_eligible"] = True
    raw = (json.dumps(panel, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    manifest_path = a / "match_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["matched_output_sha256"] = hashlib.sha256(raw).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(MatchedPanelError, match="research-only"):
        build_matched_panel_archive([a], tmp_path / "out", repository_root=tmp_path / "repo")
