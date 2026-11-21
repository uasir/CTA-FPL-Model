import base64
import copy
import hashlib
import json

import pytest

# This PR is intentionally stacked on the unmerged M3 provider-adapter PR.
# Skip this cross-milestone integration test on the standalone M4 branch until
# the M3 base branch is included in the checkout.
pytest.importorskip(
    "build_sideline_quant_provider_capture",
    reason="requires the Sideline Quant adapter from stacked M3 PR #58",
)
from build_sideline_quant_provider_capture import build_sideline_quant_provider_capture
from replay_frozen_m3_decision import (
    DecisionReplayError,
    _reconstruct_provider_and_metadata,
)


def _encoded(raw):
    return base64.b64encode(raw).decode("ascii")


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _manifest():
    player_ids = list(range(1, 16)) + [20]
    element_types = [
        {"id": 1, "singular_name_short": "GKP"},
        {"id": 2, "singular_name_short": "DEF"},
        {"id": 3, "singular_name_short": "MID"},
        {"id": 4, "singular_name_short": "FWD"},
    ]
    positions = {
        **{pid: 1 for pid in (1, 12)},
        **{pid: 2 for pid in (2, 3, 4, 5, 13)},
        **{pid: 3 for pid in (6, 7, 8, 14, 20)},
        **{pid: 4 for pid in (9, 10, 11, 15)},
    }
    elements = [
        {"id": pid, "element_type": positions[pid], "team": (pid % 20) + 1,
         "now_cost": 50}
        for pid in player_ids
    ]
    bootstrap = {
        "elements": elements,
        "element_types": element_types,
        "events": [{"id": 12, "deadline_time": "2026-11-21T11:00:00Z"}],
    }
    rows = [
        {"player_id": pid, "fixture_id": 1200 + pid, "gameweek": 12,
         "xP": 5.0 + pid / 100, "e_mins": 80.0, "p_start": 0.8,
         "gw_sigma": 2.0, "gw_p10": 1.0, "gw_p90": 8.0}
        for pid in player_ids
    ]
    provider_raw = _raw({
        "gameweek": 12,
        "generated_at": "2026-11-20T09:00:00Z",
        "deadline": "2026-11-21T11:00:00Z",
        "schema_version": "test-v1",
        "n_players": len(player_ids),
        "n_rows": len(rows),
        "rows": rows,
    })
    metadata_raw = _raw(bootstrap)
    provider_hash = hashlib.sha256(provider_raw).hexdigest()
    metadata_hash = hashlib.sha256(metadata_raw).hexdigest()
    provider_url = "https://sidelinequant.com/data/gw/12/projections.json"
    metadata_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    raw_capture = {
        "capture_id": "sidelinequant-gw12-20261120T100000000000Z",
        "provider": {"name": "Sideline Quant"},
        "season": "2026-27",
        "target_gameweek": 12,
        "timing": {
            "generated_at_utc": "2026-11-20T09:00:00Z",
            "captured_at_utc": "2026-11-20T10:00:00Z",
            "deadline_utc": "2026-11-21T11:00:00Z",
            "official_metadata_captured_at_utc": "2026-11-20T10:00:01Z",
        },
        "source": {
            "url": provider_url,
            "raw_snapshot_id": "sha256:" + provider_hash,
            "raw_sha256": provider_hash,
        },
        "coverage": {
            "declared_row_count": len(rows),
            "declared_player_count": len(player_ids),
        },
        "raw_archives": {
            "provider_response_base64": _encoded(provider_raw),
            "official_fpl_bootstrap_base64": _encoded(metadata_raw),
        },
        "official_metadata_provenance": {
            "source_url": metadata_url,
            "raw_snapshot_id": "sha256:" + metadata_hash,
            "raw_sha256": metadata_hash,
            "captured_at_utc": "2026-11-20T10:00:01Z",
        },
    }
    from parse_sideline_quant_snapshot import parse_sideline_quant_capture
    parsed = parse_sideline_quant_capture(raw_capture)
    envelope = build_sideline_quant_provider_capture(raw_capture, parsed)
    sources = [
        {
            "source_type": "provider_forecast",
            "source_url": provider_url,
            "raw_snapshot_id": "sha256:" + provider_hash,
            "raw_sha256": provider_hash,
            "captured_at_utc": "2026-11-20T10:00:00Z",
            "generated_at_utc": "2026-11-20T09:00:00Z",
            "raw_payload_base64": _encoded(provider_raw),
        },
        {
            "source_type": "player_metadata",
            "source_url": metadata_url,
            "raw_snapshot_id": "sha256:" + metadata_hash,
            "raw_sha256": metadata_hash,
            "captured_at_utc": "2026-11-20T10:00:01Z",
            "raw_payload_base64": _encoded(metadata_raw),
        },
    ]
    return {
        "season": "2026-27",
        "target_gameweek": 12,
        "provider_snapshot": envelope["provider_snapshot"],
        "player_metadata": envelope["player_metadata"],
        "player_metadata_provenance": envelope["player_metadata_provenance"],
    }, {row["source_type"]: row for row in sources}


def test_reconstructs_sideline_quant_raw_feed_into_exact_canonical_gameweek_snapshot():
    manifest, sources = _manifest()
    _reconstruct_provider_and_metadata(manifest, sources)


def test_rejects_sideline_quant_raw_change_even_when_archive_hash_is_rebased():
    manifest, sources = _manifest()
    provider_source = sources["provider_forecast"]
    raw = json.loads(base64.b64decode(provider_source["raw_payload_base64"]))
    raw["rows"][0]["xP"] = 99.0
    changed = _raw(raw)
    digest = hashlib.sha256(changed).hexdigest()
    provider_source["raw_payload_base64"] = _encoded(changed)
    provider_source["raw_sha256"] = digest
    provider_source["raw_snapshot_id"] = "sha256:" + digest
    manifest["provider_snapshot"]["source"]["raw_sha256"] = digest
    manifest["provider_snapshot"]["source"]["raw_snapshot_id"] = "sha256:" + digest
    with pytest.raises(DecisionReplayError, match="cannot be reconstructed"):
        _reconstruct_provider_and_metadata(manifest, sources)
