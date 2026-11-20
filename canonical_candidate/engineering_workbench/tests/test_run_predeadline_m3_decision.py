import base64
import hashlib
import json

import pytest

import run_predeadline_m3_decision as runner
import canonical_provider_forecast_contract
import canonical_forecast_recommendation_adapter


def _manifest():
    ids = list(range(1, 16))
    state = {
        "squad_15": ids,
        "bank": 0.9,
        "free_transfers": 1,
        "formation": "4-3-3",
        "starting_xi": list(range(1, 12)),
        "bench_order": [13, 14, 15],
        "reserve_goalkeeper_id": 12,
        "captain_id": 10,
        "vice_captain_id": 11,
        "chip_state": "NONE",
        "purchase_prices": {str(player_id): 5.0 for player_id in ids},
        "selling_prices": {str(player_id): 5.0 for player_id in ids},
    }
    metadata = [
        {"fpl_element_id": player_id, "price": 5.0, "position": (
            "GKP" if player_id in {1, 12} else
            "DEF" if player_id in {2, 3, 4, 5, 13} else
            "MID" if player_id in {6, 7, 8, 14} else "FWD"
        ), "team_id": player_id}
        for player_id in ids
    ]
    metadata.append({
        "fpl_element_id": 20, "price": 5.0, "position": "MID", "team_id": 20
    })
    def archive(source_type):
        raw = json.dumps({"source": source_type}).encode()
        return {
            "source_type": source_type,
            "source_url": f"https://example.test/{source_type}",
            "raw_snapshot_id": f"snapshot-{source_type}",
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "captured_at_utc": "2026-11-20T10:00:00Z",
            "raw_payload_base64": base64.b64encode(raw).decode(),
            **({"generated_at_utc": "2026-11-20T09:00:00Z"} if source_type == "provider_forecast" else {}),
        }
    return {
        "12": {
            "target_gameweek": 12,
            "manager_team_id": 421025,
            "season": "2026-27",
            "provider_snapshot": {
                "snapshot_id": "fplcat-gw12-test",
                "provider": {"name": "FPL Cat", "product": "published xP", "variant": "public-xp"},
            },
            "player_metadata": metadata,
            "player_metadata_provenance": {
                "source_url": "https://fantasy.premierleague.com/api/bootstrap-static/",
                "raw_snapshot_id": "metadata-snapshot",
                "raw_sha256": "a" * 64,
                "captured_at_utc": "2026-11-20T09:35:00Z",
                "row_count": len(metadata),
            },
            "manager_state": state,
            "decision_as_of_utc": "2026-11-20T10:00:00Z",
            "deadline_utc": "2026-11-21T11:00:00Z",
            "sources": [
                archive("provider_forecast"),
                archive("player_metadata"),
                archive("manager_deadline_state"),
            ],
        }
    }


def _engine_result():
    recommendation = {
        "recommendation_status": "EXPLORATORY_ONLY",
        "transfer_recommendation": {
            "action": "TRANSFER",
            "best_candidate": {
                "transfer_out_id": 15,
                "transfer_in_id": 20,
                "hit_cost_points": 0.0,
            },
            "alternatives": [{"transfer_out_id": 14, "transfer_in_id": 20}],
        },
        "squad_plan": {
            "formation": "4-3-3",
            "starting_xi": [1, 2, 3, 4, 5, 6, 7, 20, 9, 10, 11],
            "bench_order": [13, 14, 8],
            "reserve_goalkeeper": 12,
            "captain": 10,
            "vice_captain": 11,
        },
    }
    return {"recommendation": recommendation, "recommendation_status": "EXPLORATORY_ONLY"}


def test_freezes_one_conventional_recommendation_and_suppresses_alternatives(monkeypatch):
    monkeypatch.setattr(runner, "run_external_benchmark_personal_squad",
                        lambda payload: _engine_result())
    monkeypatch.setattr(
        canonical_provider_forecast_contract, "normalize_provider_snapshot",
        lambda snapshot: snapshot,
    )
    monkeypatch.setattr(
        canonical_forecast_recommendation_adapter, "build_recommendation_forecast_payload",
        lambda *args, **kwargs: {
            "player_forecasts": [
                {"fpl_element_id": row["fpl_element_id"], "position": row["position"],
                 "team_id": row["team_id"], "price": row["price"], "expected_points": 5,
                 "expected_minutes": 80}
                for row in _manifest()["12"]["player_metadata"]
            ]
        },
    )
    result = runner.run_predeadline_m3_decision(_manifest(), software_commit="b" * 40)
    assert result["run_type"] == "M3_CONVENTIONAL_PERSONAL_SQUAD_RECOMMENDATION"
    assert result["release_eligible"] is False
    assert result["frozen_decision"]["action"] == "TRANSFER"
    assert result["frozen_decision"]["transfer_out_id"] == 15
    assert result["frozen_decision"]["transfer_in_id"] == 20
    assert result["frozen_decision"]["squad_plan"]["squad_ids"] == list(range(1, 15)) + [20]
    assert result["recommendation"]["transfer_recommendation"]["alternatives_suppressed"] is True
    assert "alternatives" not in result["recommendation"]["transfer_recommendation"]
    candidate = result["evaluation_candidate"]
    assert candidate["evidence_class"] == "REAL_CANDIDATE"
    assert len(candidate["source_archives"]) == 3
    assert candidate["manager_state"]["hold_plan"]["captain_id"] == 10
    assert len(candidate["manager_state"]["squad_snapshot"]) == 15
    body = {key: value for key, value in result["frozen_decision"].items()
            if key != "decision_sha256"}
    digest = hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()
    assert result["frozen_decision"]["decision_sha256"] == digest


def test_rejects_bundle_with_multiple_gameweeks():
    bundle = _manifest()
    bundle["13"] = bundle["12"]
    with pytest.raises(runner.PredeadlineDecisionError, match="exactly one"):
        runner.run_predeadline_m3_decision(bundle, software_commit="b" * 40)


def test_runs_real_external_benchmark_engine_from_frozen_evidence_bundle():
    from test_run_external_benchmark_personal_squad import run_input

    engine_input = run_input()
    manager = engine_input["manager_context"]
    squad_ids = [row["fpl_element_id"] for row in manager["squad_snapshot"]]
    state = {
        "squad_15": squad_ids,
        "bank": manager["bank"],
        "free_transfers": manager["free_transfers"],
        "formation": "4-3-3",
        "starting_xi": [1, 3, 4, 5, 6, 8, 9, 10, 13, 14, 15],
        "bench_order": [7, 11, 12],
        "reserve_goalkeeper_id": 2,
        "captain_id": 13,
        "vice_captain_id": 14,
        "chip_state": "NONE",
        "purchase_prices": {
            str(row["fpl_element_id"]): row["purchase_price"]
            for row in manager["squad_snapshot"]
        },
        "selling_prices": {
            str(row["fpl_element_id"]): row["price"]
            for row in engine_input["player_metadata"]
            if row["fpl_element_id"] in squad_ids
        },
    }
    raw_provider = b"frozen-provider-source"
    raw_metadata = b"frozen-metadata-source"
    raw_manager = b"frozen-manager-source"
    engine_input["provider_snapshot"]["source"]["raw_sha256"] = hashlib.sha256(raw_provider).hexdigest()
    engine_input["provider_snapshot"]["source"]["raw_snapshot_id"] = "sha256:" + hashlib.sha256(raw_provider).hexdigest()
    engine_input["player_metadata_provenance"]["raw_sha256"] = hashlib.sha256(raw_metadata).hexdigest()
    engine_input["player_metadata_provenance"]["raw_snapshot_id"] = "sha256:" + hashlib.sha256(raw_metadata).hexdigest()
    sources = []
    for source_type, raw, url, captured in (
        ("provider_forecast", raw_provider, "https://provider.example/forecast.json", "2026-11-20T09:00:00Z"),
        ("player_metadata", raw_metadata, "https://fantasy.premierleague.com/api/bootstrap-static/", "2026-11-20T09:05:00Z"),
        ("manager_deadline_state", raw_manager, "https://fantasy.premierleague.com/entry/421025", "2026-11-20T09:10:00Z"),
    ):
        source = {
            "source_type": source_type,
            "source_url": url,
            "raw_snapshot_id": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "captured_at_utc": captured,
            "raw_payload_base64": base64.b64encode(raw).decode(),
        }
        if source_type == "provider_forecast":
            source["generated_at_utc"] = "2026-11-20T08:30:00Z"
        sources.append(source)
    bundle = {
        "11": {
            "target_gameweek": 11,
            "manager_team_id": 421025,
            "season": "2026-27",
            "provider_snapshot": engine_input["provider_snapshot"],
            "player_metadata": engine_input["player_metadata"],
            "player_metadata_provenance": engine_input["player_metadata_provenance"],
            "manager_state": state,
            "decision_as_of_utc": engine_input["as_of_utc"],
            "deadline_utc": engine_input["provider_snapshot"]["timing"]["deadline_utc"],
            "sources": sources,
        }
    }
    result = runner.run_predeadline_m3_decision(bundle, software_commit="c" * 40)
    assert result["recommendation_status"] == "EXPLORATORY_ONLY"
    assert result["release_eligible"] is False
    assert result["frozen_decision"]["action"] in {"HOLD", "TRANSFER"}
    assert len(result["evaluation_candidate"]["manager_state"]["squad_snapshot"]) == 15
    assert len(result["evaluation_candidate"]["source_archives"]) == 3
