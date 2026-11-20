#!/usr/bin/env python3
"""Run and freeze the single conventional M3 recommendation from a capture bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from run_external_benchmark_personal_squad import run_external_benchmark_personal_squad


class PredeadlineDecisionError(ValueError):
    pass


def _plan_for_evaluation(plan: Mapping[str, Any], squad_ids: list[int]) -> dict[str, Any]:
    return {
        "squad_ids": sorted(squad_ids),
        "starting_xi": list(plan["starting_xi"]),
        "bench_order": list(plan["bench_order"]),
        "reserve_goalkeeper_id": plan["reserve_goalkeeper"],
        "captain_id": plan["captain"],
        "vice_captain_id": plan["vice_captain"],
        "formation": plan["formation"],
    }


def run_predeadline_m3_decision(
    evidence_bundle: Mapping[str, Any],
    *,
    software_commit: str,
) -> dict[str, Any]:
    if not isinstance(evidence_bundle, Mapping) or len(evidence_bundle) != 1:
        raise PredeadlineDecisionError("evidence bundle must contain exactly one Gameweek manifest")
    if not isinstance(software_commit, str) or len(software_commit) not in (40, 64) or any(
        char not in "0123456789abcdef" for char in software_commit.lower()
    ):
        raise PredeadlineDecisionError("software_commit must be a full hexadecimal Git commit hash")

    gameweek_key, manifest = next(iter(evidence_bundle.items()))
    if not isinstance(manifest, Mapping):
        raise PredeadlineDecisionError("Gameweek manifest must be an object")
    try:
        gameweek = int(gameweek_key)
    except (TypeError, ValueError) as exc:
        raise PredeadlineDecisionError("evidence bundle key must be a Gameweek number") from exc
    if manifest.get("target_gameweek") != gameweek:
        raise PredeadlineDecisionError("manifest key and target_gameweek do not match")

    required = (
        "manager_team_id", "season", "provider_snapshot", "player_metadata",
        "player_metadata_provenance", "manager_state", "decision_as_of_utc",
        "deadline_utc", "sources",
    )
    missing = [field for field in required if field not in manifest]
    if missing:
        raise PredeadlineDecisionError("manifest missing fields: " + ", ".join(missing))

    state = manifest["manager_state"]
    provider = manifest["provider_snapshot"]
    metadata = manifest["player_metadata"]
    metadata_provenance = manifest["player_metadata_provenance"]
    if not isinstance(state, Mapping) or not isinstance(provider, Mapping):
        raise PredeadlineDecisionError("manager_state and provider_snapshot must be objects")
    if not isinstance(metadata, list) or not isinstance(metadata_provenance, Mapping):
        raise PredeadlineDecisionError("player_metadata and provenance are invalid")

    metadata_by_id = {row["fpl_element_id"]: row for row in metadata}
    squad_ids = list(state["squad_15"])
    purchase_prices = state["purchase_prices"]
    squad_snapshot = []
    for player_id in squad_ids:
        meta = metadata_by_id.get(player_id)
        if meta is None:
            raise PredeadlineDecisionError(f"metadata missing for owned player {player_id}")
        squad_snapshot.append({
            "fpl_element_id": player_id,
            "purchase_price": purchase_prices[str(player_id)],
        })

    manager_context = {
        "squad_snapshot": squad_snapshot,
        "bank": state["bank"],
        "free_transfers": state["free_transfers"],
        "personal_risk_profile": "aggressive",
        "formation": state["formation"],
        "starting_xi": list(state["starting_xi"]),
        "bench_order": list(state["bench_order"]),
        "personal_preferences": {},
    }
    engine_payload = {
        "provider_snapshot": provider,
        "player_metadata": metadata,
        "player_metadata_provenance": metadata_provenance,
        "manager_context": manager_context,
        "as_of_utc": manifest["decision_as_of_utc"],
    }
    engine_run = run_external_benchmark_personal_squad(engine_payload)
    engine_recommendation = engine_run["recommendation"]
    transfer = engine_recommendation["transfer_recommendation"]
    action = transfer["action"]
    if action not in {"HOLD", "TRANSFER"}:
        raise PredeadlineDecisionError("engine returned an unsupported action")

    # The recommendation adapter's joined forecasts are authoritative for transfer metadata.
    from canonical_provider_forecast_contract import normalize_provider_snapshot
    from canonical_forecast_recommendation_adapter import build_recommendation_forecast_payload
    normalized = normalize_provider_snapshot(provider)
    joined = build_recommendation_forecast_payload(
        normalized, metadata, as_of_utc=manifest["decision_as_of_utc"], forecast_horizon_gameweeks=1
    )["player_forecasts"]
    forecast_by_id = {row["fpl_element_id"]: row for row in joined}

    candidate = transfer.get("best_candidate") if action == "TRANSFER" else None
    transfer_out_id = candidate["transfer_out_id"] if candidate else None
    transfer_in_id = candidate["transfer_in_id"] if candidate else None
    incoming_player = None
    transfer_hit = 0.0
    if candidate:
        incoming = forecast_by_id.get(transfer_in_id)
        if incoming is None:
            raise PredeadlineDecisionError("recommended incoming player is missing from joined forecasts")
        incoming_player = {
            "fpl_element_id": transfer_in_id,
            "position": incoming["position"],
            "team_id": incoming["team_id"],
            "purchase_price": incoming["price"],
            "current_price": incoming["price"],
        }
        transfer_hit = candidate["hit_cost_points"]

    recommended_plan = engine_recommendation["squad_plan"]
    post_squad_ids = (
        sorted((set(squad_ids) - {transfer_out_id}) | {transfer_in_id})
        if candidate else sorted(squad_ids)
    )
    frozen_decision_body = {
        "action": action,
        "transfer_out_id": transfer_out_id,
        "transfer_in_id": transfer_in_id,
        "incoming_player": incoming_player,
        "transfer_hit_points": transfer_hit,
        "squad_plan": _plan_for_evaluation(recommended_plan, post_squad_ids),
    }
    frozen_decision = {
        **frozen_decision_body,
        "decision_sha256": hashlib.sha256(
            json.dumps(frozen_decision_body, sort_keys=True, separators=(",", ":"),
                       allow_nan=False).encode("utf-8")
        ).hexdigest(),
    }

    manager_roster = []
    for player_id in squad_ids:
        meta = forecast_by_id.get(player_id)
        if meta is None:
            raise PredeadlineDecisionError(f"forecast missing for owned player {player_id}")
        manager_roster.append({
            "fpl_element_id": player_id,
            "position": meta["position"],
            "team_id": meta["team_id"],
            "purchase_price": purchase_prices[str(player_id)],
            "current_price": meta["price"],
        })
    hold_plan = {
        "squad_ids": sorted(squad_ids),
        "starting_xi": list(state["starting_xi"]),
        "bench_order": list(state["bench_order"]),
        "reserve_goalkeeper_id": state["reserve_goalkeeper_id"],
        "captain_id": state["captain_id"],
        "vice_captain_id": state["vice_captain_id"],
        "formation": state["formation"],
    }

    archive_by_type = {row["source_type"]: row for row in manifest["sources"]}
    source_map = (
        ("provider_forecast", "provider"),
        ("player_metadata", "player_metadata"),
        ("manager_deadline_state", "manager_state"),
    )
    evaluation_archives = []
    for manifest_type, evaluation_type in source_map:
        source = archive_by_type.get(manifest_type)
        if not isinstance(source, Mapping):
            raise PredeadlineDecisionError(f"manifest source missing: {manifest_type}")
        archive = {
            "source_type": evaluation_type,
            "source_url": source["source_url"],
            "raw_snapshot_id": source["raw_snapshot_id"],
            "raw_sha256": source["raw_sha256"],
            "captured_at_utc": source["captured_at_utc"],
            "raw_payload_base64": source["raw_payload_base64"],
        }
        if evaluation_type == "provider":
            archive["generated_at_utc"] = source["generated_at_utc"]
        evaluation_archives.append(archive)

    evaluation_candidate = {
        "evidence_class": "REAL_CANDIDATE",
        "manager_team_id": manifest["manager_team_id"],
        "target_gameweek": gameweek,
        "deadline_utc": manifest["deadline_utc"],
        "as_of_utc": manifest["decision_as_of_utc"],
        "season": manifest["season"],
        "provider_snapshot_id": provider["snapshot_id"],
        "provider_identity": dict(provider["provider"]),
        "decision_contract_version": "1.0.0",
        "software_commit": software_commit,
        "source_archives": evaluation_archives,
        "manager_state": {
            "squad_snapshot": manager_roster,
            "bank": state["bank"],
            "free_transfers": state["free_transfers"],
            "personal_risk_profile": "aggressive",
            "formation": state["formation"],
            "chip": "NONE",
            "hold_plan": hold_plan,
        },
        "frozen_decision": frozen_decision,
        "evaluation_status": "AWAITING_FINALIZED_OFFICIAL_POINTS_AND_ADMISSION",
    }

    # Expose only the single best transfer candidate; alternatives remain internal to the engine.
    presentation_recommendation = dict(engine_recommendation)
    presentation_transfer = dict(transfer)
    presentation_transfer.pop("alternatives", None)
    presentation_transfer["alternatives_suppressed"] = True
    presentation_recommendation["transfer_recommendation"] = presentation_transfer

    return {
        "run_contract_version": "1.0.0",
        "run_type": "M3_CONVENTIONAL_PERSONAL_SQUAD_RECOMMENDATION",
        "manager_team_id": manifest["manager_team_id"],
        "target_gameweek": gameweek,
        "decision_as_of_utc": manifest["decision_as_of_utc"],
        "deadline_utc": manifest["deadline_utc"],
        "provider_identity": dict(provider["provider"]),
        "provider_snapshot_id": provider["snapshot_id"],
        "recommendation_status": engine_run["recommendation_status"],
        "recommendation": presentation_recommendation,
        "frozen_decision": frozen_decision,
        "evaluation_candidate": evaluation_candidate,
        "release_eligible": False,
        "release_blockers": [
            "M3 historical decision-evaluation gates have not been completed.",
            "The external provider forecast has not been promoted through independent validation.",
            "The manager free-transfer count is manager-confirmed rather than independently sourced.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_bundle", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--software-commit", default=os.environ.get("M3_CODE_SHA"))
    args = parser.parse_args()
    bundle = json.loads(args.evidence_bundle.read_text(encoding="utf-8"))
    result = run_predeadline_m3_decision(bundle, software_commit=args.software_commit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
                           encoding="utf-8")
    print(json.dumps({
        "manager_team_id": result["manager_team_id"],
        "target_gameweek": result["target_gameweek"],
        "action": result["frozen_decision"]["action"],
        "transfer_out_id": result["frozen_decision"]["transfer_out_id"],
        "transfer_in_id": result["frozen_decision"]["transfer_in_id"],
        "recommendation_status": result["recommendation_status"],
        "release_eligible": result["release_eligible"],
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
