import copy
import hashlib

import pytest

import replay_frozen_m3_decision as replay
import run_predeadline_m3_decision as runner
import canonical_provider_forecast_contract
import canonical_forecast_recommendation_adapter
from test_run_predeadline_m3_decision import _engine_result, _manifest


def _prepare(monkeypatch):
    bundle = _manifest()
    manifest = bundle["12"]
    sources = {row["source_type"]: row for row in manifest["sources"]}
    manifest["provider_snapshot"]["source"] = {
        "raw_sha256": sources["provider_forecast"]["raw_sha256"]
    }
    manifest["player_metadata_provenance"]["raw_sha256"] = sources["player_metadata"]["raw_sha256"]
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
                for row in manifest["player_metadata"]
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
    with pytest.raises(replay.DecisionReplayError, match="replayed frozen decision differs"):
        replay.replay_frozen_decision(bundle, frozen, software_commit="b" * 40)
