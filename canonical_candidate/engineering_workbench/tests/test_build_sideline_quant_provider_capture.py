import base64
import hashlib
import json

import pytest

from build_sideline_quant_provider_capture import (
    ProviderCaptureBuildError,
    build_sideline_quant_provider_capture,
)
from capture_fpl_cat_snapshot import FPL_BOOTSTRAP_URL


def _fixtures():
    provider_raw = json.dumps({"gameweek": 12}).encode()
    bootstrap_raw = json.dumps({
        "elements": [{"id": 1, "element_type": 2, "team": 3, "now_cost": 45}],
        "element_types": [{"id": 2, "singular_name_short": "DEF"}],
    }).encode()
    provider_hash = hashlib.sha256(provider_raw).hexdigest()
    bootstrap_hash = hashlib.sha256(bootstrap_raw).hexdigest()
    timing = {
        "generated_at_utc": "2026-11-21T17:00:00Z",
        "captured_at_utc": "2026-11-21T17:10:00Z",
        "deadline_utc": "2026-11-27T18:30:00Z",
        "official_metadata_captured_at_utc": "2026-11-21T17:10:01Z",
        "point_in_time_status": "PROVIDER_GENERATED_AND_CAPTURED_BEFORE_DEADLINE",
    }
    raw = {
        "provider": {"name": "Sideline Quant"},
        "season": "2026-27",
        "target_gameweek": 12,
        "timing": timing,
        "source": {"raw_sha256": provider_hash, "url": "https://sidelinequant.com/data/gw/12/projections.json"},
        "raw_archives": {
            "provider_response_base64": base64.b64encode(provider_raw).decode(),
            "official_fpl_bootstrap_base64": base64.b64encode(bootstrap_raw).decode(),
        },
        "official_metadata_provenance": {
            "source_url": FPL_BOOTSTRAP_URL,
            "raw_sha256": bootstrap_hash,
            "raw_snapshot_id": f"sha256:{bootstrap_hash}",
            "captured_at_utc": timing["official_metadata_captured_at_utc"],
        },
    }
    aggregation = {
        "method": "SUM(xP) and SUM(e_mins) grouped by player_id within target Gameweek",
        "source_grain": "player_fixture",
        "target_grain": "player_gameweek",
        "publisher_documented": True,
        "native_fixture_rows_preserved": True,
    }
    parsed = {
        "player_gameweek_snapshot": {
            "snapshot_id": "sidelinequant-gw12-test:player_gameweek_sum_xp",
            "season": "2026-27",
            "target_gameweek": 12,
            "provider": {
                "name": "Sideline Quant",
                "product": "gameweek_projections",
                "variant": "provider_native_xp",
            },
            "grain": "player_gameweek",
            "decision_eligible": True,
            "timing": {
                key: timing[key]
                for key in ("generated_at_utc", "captured_at_utc", "deadline_utc")
            },
            "source": {"raw_sha256": provider_hash},
            "records": [{"fpl_element_id": 1, "expected_points": 4.2, "expected_minutes": 80}],
        },
        "aggregation_provenance": aggregation,
    }
    return raw, parsed, provider_hash, bootstrap_hash, aggregation


def test_builds_registered_sideline_quant_capture_envelope_with_aggregation_provenance():
    raw, parsed, provider_hash, bootstrap_hash, aggregation = _fixtures()
    result = build_sideline_quant_provider_capture(raw, parsed)
    assert result["provider_snapshot"]["provider"]["name"] == "Sideline Quant"
    assert result["provider_snapshot"]["grain"] == "player_gameweek"
    assert result["provider_snapshot"]["source"]["raw_sha256"] == provider_hash
    assert result["forecast_aggregation_provenance"] == aggregation
    assert result["player_metadata"] == [{
        "fpl_element_id": 1, "price": 4.5, "position": "DEF", "team_id": 3,
    }]
    assert result["player_metadata_provenance"]["raw_sha256"] == bootstrap_hash
    assert result["raw_archives"]["provider_response_base64"] == raw["raw_archives"]["provider_response_base64"]


def test_rejects_provider_hash_mismatch():
    raw, parsed, _, _, _ = _fixtures()
    raw["source"]["raw_sha256"] = "0" * 64
    with pytest.raises(ProviderCaptureBuildError, match="provider raw hash"):
        build_sideline_quant_provider_capture(raw, parsed)


def test_rejects_fixture_grain_snapshot_for_decision_handoff():
    raw, parsed, _, _, _ = _fixtures()
    parsed["player_gameweek_snapshot"]["grain"] = "player_fixture"
    with pytest.raises(ProviderCaptureBuildError, match="not decision eligible"):
        build_sideline_quant_provider_capture(raw, parsed)


def test_rejects_unmapped_player_metadata():
    raw, parsed, _, _, _ = _fixtures()
    parsed["player_gameweek_snapshot"]["records"][0]["fpl_element_id"] = 2
    with pytest.raises(ProviderCaptureBuildError, match="missing player IDs"):
        build_sideline_quant_provider_capture(raw, parsed)


def test_rejects_raw_and_normalized_generation_time_mismatch():
    raw, parsed, _, _, _ = _fixtures()
    parsed["player_gameweek_snapshot"]["timing"]["generated_at_utc"] = "2026-11-21T16:59:00Z"
    with pytest.raises(ProviderCaptureBuildError, match="generated_at_utc differ"):
        build_sideline_quant_provider_capture(raw, parsed)


def test_rejects_missing_or_unsupported_aggregation_provenance():
    raw, parsed, _, _, aggregation = _fixtures()
    del parsed["aggregation_provenance"]
    with pytest.raises(ProviderCaptureBuildError, match="lacks aggregation provenance"):
        build_sideline_quant_provider_capture(raw, parsed)
    raw, parsed, _, _, aggregation = _fixtures()
    parsed["aggregation_provenance"]["publisher_documented"] = False
    with pytest.raises(ProviderCaptureBuildError, match="incomplete or unsupported"):
        build_sideline_quant_provider_capture(raw, parsed)
