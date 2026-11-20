import base64
import copy
import hashlib
import json

import pytest

import replay_frozen_m3_decision as replay
import run_predeadline_m3_decision as runner
import canonical_provider_forecast_contract
import canonical_forecast_recommendation_adapter
from test_run_predeadline_m3_decision import _engine_result, _manifest


def _bind_raw_sources(manifest):
    metadata_rows = manifest["player_metadata"]
    type_ids = {"GKP": 1, "DEF": 2, "MID": 3, "FWD": 4}
    bootstrap = {
        "elements": [
            {"id": row["fpl_element_id"], "element_type": type_ids[row["position"]],
             "team": row["team_id"], "now_cost": int(row["price"] * 10),
             "cost_change_start": 0}
            for row in metadata_rows
        ],
        "element_types": [
            {"id": type_id, "singular_name_short": position}
            for position, type_id in type_ids.items()
        ],
        "events": [{"id": 12, "deadline_time": "2026-11-21T11:00:00Z"}],
    }
    provider_raw_object = {
        "gameweek": 12,
        "deadline": "2026-11-21T11:00:00Z",
        "computed_at": "2026-11-20T09:00:00Z",
        "players": [
            {"id": row["fpl_element_id"], "xp": 5, "expected_minutes": 80}
            for row in metadata_rows
        ],
    }
    def raw_bytes(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    provider_raw = raw_bytes(provider_raw_object)
    metadata_raw = raw_bytes(bootstrap)
    state = manifest["manager_state"]
    picks = []
    lineup = state["starting_xi"]
    bench = state["bench_order"] + [state["reserve_goalkeeper_id"]]
    for position, player_id in enumerate(lineup + bench, 1):
        picks.append({
            "element": player_id,
            "position": position,
            "purchase_price": 50,
            "selling_price": 50,
            "is_captain": player_id == state["captain_id"],
            "is_vice_captain": player_id == state["vice_captain_id"],
        })
    manager_picks = {"entry_history": {"event": 12, "bank": 9}, "picks": picks, "active_chip": None}
    picks_raw = raw_bytes(manager_picks)
    manager_envelope = {
        "capture_kind": "USER_ATTESTED_PREDEADLINE_MANAGER_STATE",
        "capture_method": "OFFICIAL_TARGET_GAMEWEEK_PICKS",
        "manager_team_id": 421025,
        "target_gameweek": 12,
        "captured_at_utc": "2026-11-20T10:00:00Z",
        "source_urls": ["https://fantasy.premierleague.com/api/entry/421025/event/12/picks/"],
        "raw_manager_picks_base64": base64.b64encode(picks_raw).decode(),
        "history_archive_base64": None,
        "manager_state": state,
    }
    manager_raw = raw_bytes(manager_envelope)
    def source(kind, raw, url, captured, generated=None):
        digest = hashlib.sha256(raw).hexdigest()
        item = {
            "source_type": kind,
            "source_url": url,
            "raw_snapshot_id": "sha256:" + digest,
            "raw_sha256": digest,
            "captured_at_utc": captured,
            "raw_payload_base64": base64.b64encode(raw).decode(),
        }
        if generated:
            item["generated_at_utc"] = generated
        return item
    manifest["sources"] = [
        source("provider_forecast", provider_raw, "https://fplcat.com/api/v1/projections",
               "2026-11-20T10:00:00Z", "2026-11-20T09:00:00Z"),
        source("player_metadata", metadata_raw,
               "https://fantasy.premierleague.com/api/bootstrap-static/",
               "2026-11-20T09:35:00Z"),
        source("manager_deadline_state", manager_raw,
               "https://fantasy.premierleague.com/entry/421025",
               "2026-11-20T10:00:00Z"),
    ]
    provider_digest = hashlib.sha256(provider_raw).hexdigest()
    manifest["provider_snapshot"] = {
        "snapshot_id": "fplcat-gw12-20261120T100000000000Z",
        "season": "2026-27",
        "target_gameweek": 12,
        "provider": {
            "name": "FPL Cat", "product": "published xP",
            "variant": "public next-gameweek JSON API", "version": "api/v1",
        },
        "timing": {
            "generated_at_utc": "2026-11-20T09:00:00Z",
            "captured_at_utc": "2026-11-20T10:00:00Z",
            "deadline_utc": "2026-11-21T11:00:00Z",
        },
        "source": {
            "url": "https://fplcat.com/api/v1/projections",
            "raw_snapshot_id": "sha256:" + provider_digest,
            "raw_sha256": provider_digest,
        },
        "grain": "player_gameweek",
        "records": provider_raw_object["players"] and [
            {"fpl_element_id": row["id"], "expected_points": row["xp"],
             "expected_minutes": row["expected_minutes"]}
            for row in provider_raw_object["players"]
        ],
        "coverage": {
            "row_count": len(metadata_rows), "expected_player_universe": len(bootstrap["elements"]),
            "identity_mapped_count": len(metadata_rows),
        },
    }
    metadata_digest = hashlib.sha256(metadata_raw).hexdigest()
    manifest["player_metadata_provenance"] = {
        "source_url": "https://fantasy.premierleague.com/api/bootstrap-static/",
        "raw_snapshot_id": "sha256:" + metadata_digest,
        "raw_sha256": metadata_digest,
        "captured_at_utc": "2026-11-20T09:35:00Z",
        "row_count": len(metadata_rows),
    }


def _replace_raw_source(manifest, source_type, payload):
    source = next(row for row in manifest["sources"] if row["source_type"] == source_type)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(raw).hexdigest()
    source["raw_payload_base64"] = base64.b64encode(raw).decode()
    source["raw_sha256"] = digest
    source["raw_snapshot_id"] = "sha256:" + digest
    if source_type == "provider_forecast":
        manifest["provider_snapshot"]["source"]["raw_sha256"] = digest
        manifest["provider_snapshot"]["source"]["raw_snapshot_id"] = "sha256:" + digest
    elif source_type == "player_metadata":
        manifest["player_metadata_provenance"]["raw_sha256"] = digest
        manifest["player_metadata_provenance"]["raw_snapshot_id"] = "sha256:" + digest


def _prepare(monkeypatch):
    bundle = _manifest()
    manifest = bundle["12"]
    _bind_raw_sources(manifest)
    monkeypatch.setattr(runner, "run_external_benchmark_personal_squad",
                        lambda payload: _engine_result())
    monkeypatch.setattr(canonical_provider_forecast_contract, "normalize_provider_snapshot",
                        lambda snapshot: snapshot)
    monkeypatch.setattr(
        canonical_forecast_recommendation_adapter, "build_recommendation_forecast_payload",
        lambda *args, **kwargs: {
            "player_forecasts": [
                {"fpl_element_id": row["fpl_element_id"], "position": row["position"],
                 "team_id": row["team_id"], "price": row["price"], "expected_points": 5,
                 "expected_minutes": 80}
                for row in args[1]
            ]
        },
    )
    frozen = runner.run_predeadline_m3_decision(bundle, software_commit="b" * 40)
    return bundle, frozen


def test_replays_frozen_recommendation_from_exact_canonical_bundle(monkeypatch):
    bundle, frozen = _prepare(monkeypatch)
    result = replay.replay_frozen_decision(bundle, frozen, software_commit="b" * 40)
    assert result["status"] == "PASSED"
    assert result["recommendation_match"] is True
    assert result["frozen_decision_match"] is True
    assert result["raw_archive_hashes_verified"] is True
    assert result["release_eligible"] is False


def test_replay_rejects_changed_provider_archive(monkeypatch):
    bundle, frozen = _prepare(monkeypatch)
    bundle = copy.deepcopy(bundle)
    bundle["12"]["sources"][0]["raw_payload_base64"] += " "
    with pytest.raises(replay.DecisionReplayError, match="raw archive is invalid base64"):
        replay.replay_frozen_decision(bundle, frozen, software_commit="b" * 40)


def test_replay_rejects_different_software_commit(monkeypatch):
    bundle, frozen = _prepare(monkeypatch)
    with pytest.raises(replay.DecisionReplayError, match="software commit"):
        replay.replay_frozen_decision(bundle, frozen, software_commit="c" * 40)


def test_replay_rejects_modified_frozen_recommendation(monkeypatch):
    bundle, frozen = _prepare(monkeypatch)
    frozen = copy.deepcopy(frozen)
    frozen["frozen_decision"]["transfer_in_id"] = 999
    with pytest.raises(replay.DecisionReplayError, match="replayed frozen decision differs"):
        replay.replay_frozen_decision(bundle, frozen, software_commit="b" * 40)


def test_replay_rejects_changed_player_metadata(monkeypatch):
    bundle, frozen = _prepare(monkeypatch)
    bundle = copy.deepcopy(bundle)
    next(row for row in bundle["12"]["player_metadata"] if row["fpl_element_id"] == 20)["price"] = 6.0
    with pytest.raises(replay.DecisionReplayError, match="canonical player metadata cannot be reconstructed"):
        replay.replay_frozen_decision(bundle, frozen, software_commit="b" * 40)

def test_replay_rejects_provider_raw_change_even_when_archive_hash_is_rebased(monkeypatch):
    bundle, frozen = _prepare(monkeypatch)
    bundle = copy.deepcopy(bundle)
    manifest = bundle["12"]
    source = next(row for row in manifest["sources"] if row["source_type"] == "provider_forecast")
    payload = json.loads(base64.b64decode(source["raw_payload_base64"]))
    payload["players"][0]["xp"] = 99
    _replace_raw_source(manifest, "provider_forecast", payload)
    with pytest.raises(replay.DecisionReplayError, match="canonical provider snapshot cannot be reconstructed"):
        replay.replay_frozen_decision(bundle, frozen, software_commit="b" * 40)


def test_replay_rejects_bootstrap_change_even_when_archive_hash_is_rebased(monkeypatch):
    bundle, frozen = _prepare(monkeypatch)
    bundle = copy.deepcopy(bundle)
    manifest = bundle["12"]
    source = next(row for row in manifest["sources"] if row["source_type"] == "player_metadata")
    payload = json.loads(base64.b64decode(source["raw_payload_base64"]))
    next(row for row in payload["elements"] if row["id"] == 20)["team"] = 19
    _replace_raw_source(manifest, "player_metadata", payload)
    with pytest.raises(replay.DecisionReplayError, match="canonical player metadata cannot be reconstructed"):
        replay.replay_frozen_decision(bundle, frozen, software_commit="b" * 40)


def test_replay_rejects_manager_attestation_change_even_when_archive_hash_is_rebased(monkeypatch):
    bundle, frozen = _prepare(monkeypatch)
    bundle = copy.deepcopy(bundle)
    manifest = bundle["12"]
    source = next(row for row in manifest["sources"] if row["source_type"] == "manager_deadline_state")
    envelope = json.loads(base64.b64decode(source["raw_payload_base64"]))
    envelope["manager_state"]["bank"] = 1.0
    raw = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(raw).hexdigest()
    source["raw_payload_base64"] = base64.b64encode(raw).decode()
    source["raw_sha256"] = digest
    source["raw_snapshot_id"] = "sha256:" + digest
    with pytest.raises(replay.DecisionReplayError, match="canonical manager state differs"):
        replay.replay_frozen_decision(bundle, frozen, software_commit="b" * 40)

def test_replay_reconstructs_manager_purchase_prices_from_previous_gameweek_picks(monkeypatch):
    bundle, frozen = _prepare(monkeypatch)
    manifest = bundle["12"]
    source = next(row for row in manifest["sources"] if row["source_type"] == "manager_deadline_state")
    envelope = json.loads(base64.b64decode(source["raw_payload_base64"]))
    previous = json.loads(base64.b64decode(envelope["raw_manager_picks_base64"]))
    previous["entry_history"]["event"] = 11
    history = {"chips": []}
    def encoded(value):
        return base64.b64encode(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).decode()
    wrapper = {
        "source_type": "PREVIOUS_GAMEWEEK_PICKS",
        "previous_gameweek_picks": encoded(previous),
        "history": encoded(history),
    }
    envelope["capture_method"] = "USER_CONFIRMED_WITH_PREVIOUS_GW_PICKS"
    envelope["source_urls"] = [
        "https://fantasy.premierleague.com/api/entry/421025/event/11/picks/",
        "https://fantasy.premierleague.com/api/entry/421025/history/",
    ]
    envelope["history_archive_base64"] = encoded(wrapper)
    envelope["raw_manager_picks_base64"] = None
    raw = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(raw).hexdigest()
    source["raw_payload_base64"] = base64.b64encode(raw).decode()
    source["raw_sha256"] = digest
    source["raw_snapshot_id"] = "sha256:" + digest
    result = replay.replay_frozen_decision(bundle, frozen, software_commit="b" * 40)
    assert result["status"] == "PASSED"
    assert result["replay_type"] == "DETERMINISTIC_RAW_AND_CANONICAL_INPUT_REEXECUTION"

