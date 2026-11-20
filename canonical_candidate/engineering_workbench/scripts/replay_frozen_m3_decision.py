#!/usr/bin/env python3
"""Deterministically replay a frozen M3 recommendation from its captured bundle.

This replay verifies the canonical captured inputs and the exact checked-out
M3 commit. Raw-source-to-normalized-input reconstruction remains a separate
provenance check performed by the capture/audit pipeline.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from run_predeadline_m3_decision import run_predeadline_m3_decision


class DecisionReplayError(ValueError):
    """Raised when a frozen M3 decision cannot be reproduced exactly."""


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise DecisionReplayError("decision payload is not canonical JSON") from exc


def _verify_archives(manifest: Mapping[str, Any]) -> None:
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise DecisionReplayError("capture manifest sources must be a list")
    required = {"provider_forecast", "player_metadata", "manager_deadline_state"}
    seen = set()
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping):
            raise DecisionReplayError(f"sources[{index}] must be an object")
        kind = source.get("source_type")
        if kind not in required or kind in seen:
            raise DecisionReplayError(f"unsupported or duplicate source type: {kind}")
        seen.add(kind)
        try:
            raw = base64.b64decode(source["raw_payload_base64"], validate=True)
        except (KeyError, ValueError, TypeError) as exc:
            raise DecisionReplayError(f"{kind} raw archive is invalid base64") from exc
        digest = hashlib.sha256(raw).hexdigest()
        if digest != source.get("raw_sha256"):
            raise DecisionReplayError(f"{kind} raw archive SHA-256 mismatch")
        if source.get("raw_snapshot_id") != f"sha256:{digest}" or not source.get("source_url"):
            raise DecisionReplayError(f"{kind} archive provenance is incomplete or detached from its hash")
    if seen != required:
        raise DecisionReplayError("provider, player metadata and manager-state archives are all required")

    provider = manifest.get("provider_snapshot")
    metadata_provenance = manifest.get("player_metadata_provenance")
    if not isinstance(provider, Mapping) or not isinstance(metadata_provenance, Mapping):
        raise DecisionReplayError("canonical provider or metadata provenance is missing")
    by_type = {row["source_type"]: row for row in sources}
    if provider.get("source", {}).get("raw_sha256") != by_type["provider_forecast"]["raw_sha256"]:
        raise DecisionReplayError("canonical provider snapshot is detached from its raw archive")
    if metadata_provenance.get("raw_sha256") != by_type["player_metadata"]["raw_sha256"]:
        raise DecisionReplayError("canonical metadata is detached from its raw archive")


def _decode_json_archive(source: Mapping[str, Any], label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = base64.b64decode(source["raw_payload_base64"], validate=True)
        payload = json.loads(raw)
    except Exception as exc:
        raise DecisionReplayError(f"{label} raw archive is not valid base64 JSON") from exc
    if not isinstance(payload, dict):
        raise DecisionReplayError(f"{label} raw archive must contain a JSON object")
    return raw, payload


def _utc_text(value: Any, label: str) -> str:
    from datetime import datetime, timezone
    if not isinstance(value, str) or not value:
        raise DecisionReplayError(f"{label} timestamp is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DecisionReplayError(f"{label} timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DecisionReplayError(f"{label} timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _reconstruct_provider_and_metadata(manifest: Mapping[str, Any],
                                       by_type: Mapping[str, Mapping[str, Any]]) -> None:
    provider_source = by_type["provider_forecast"]
    metadata_source = by_type["player_metadata"]
    provider_raw, raw_provider = _decode_json_archive(provider_source, "provider forecast")
    metadata_raw, bootstrap = _decode_json_archive(metadata_source, "official player metadata")
    provider = manifest.get("provider_snapshot")
    provenance = manifest.get("player_metadata_provenance")
    if not isinstance(provider, Mapping) or not isinstance(provenance, Mapping):
        raise DecisionReplayError("canonical provider or player metadata is missing")
    if provider_source.get("source_url") != "https://fplcat.com/api/v1/projections":
        raise DecisionReplayError("provider source URL is not the registered FPL Cat endpoint")
    if metadata_source.get("source_url") != "https://fantasy.premierleague.com/api/bootstrap-static/":
        raise DecisionReplayError("player metadata source URL is not the official FPL bootstrap endpoint")
    if provenance.get("source_url") != metadata_source.get("source_url"):
        raise DecisionReplayError("metadata provenance URL differs from the raw archive")
    if not isinstance(raw_provider.get("players"), list) or not isinstance(bootstrap.get("elements"), list):
        raise DecisionReplayError("raw provider or bootstrap payload has an invalid schema")
    gw = raw_provider.get("gameweek")
    if isinstance(gw, bool) or not isinstance(gw, int) or gw != manifest.get("target_gameweek"):
        raise DecisionReplayError("raw provider Gameweek differs from the capture manifest")
    elements = bootstrap["elements"]
    element_types = {
        row.get("id"): row.get("singular_name_short")
        for row in bootstrap.get("element_types", []) if isinstance(row, dict)
    }
    bootstrap_by_id = {
        row.get("id"): row for row in elements
        if isinstance(row, dict) and isinstance(row.get("id"), int)
    }
    records = []
    metadata = []
    seen = set()
    for index, player in enumerate(raw_provider["players"]):
        if not isinstance(player, dict):
            raise DecisionReplayError(f"raw provider players[{index}] is malformed")
        player_id = player.get("id")
        xp = player.get("xp")
        minutes = player.get("expected_minutes")
        if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id < 1 or player_id in seen:
            raise DecisionReplayError("raw provider contains an invalid or duplicate FPL player ID")
        if isinstance(xp, bool) or not isinstance(xp, (int, float)) or isinstance(minutes, bool) or not isinstance(minutes, (int, float)):
            raise DecisionReplayError(f"raw provider forecast is invalid for player {player_id}")
        official = bootstrap_by_id.get(player_id)
        if official is None:
            raise DecisionReplayError(f"official bootstrap is missing provider player {player_id}")
        position = element_types.get(official.get("element_type"))
        price = official.get("now_cost")
        team_id = official.get("team")
        if not isinstance(position, str) or isinstance(price, bool) or not isinstance(price, int) or isinstance(team_id, bool) or not isinstance(team_id, int):
            raise DecisionReplayError(f"official bootstrap metadata is incomplete for player {player_id}")
        seen.add(player_id)
        records.append({
            "fpl_element_id": player_id,
            "expected_points": xp,
            "expected_minutes": minutes,
        })
        metadata.append({
            "fpl_element_id": player_id,
            "price": price / 10,
            "position": position,
            "team_id": team_id,
        })
    from datetime import datetime, timezone
    def parse_time(value: Any, label: str) -> datetime:
        if not isinstance(value, str):
            raise DecisionReplayError(f"{label} is missing")
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DecisionReplayError(f"{label} is invalid") from exc
        if result.tzinfo is None or result.utcoffset() is None:
            raise DecisionReplayError(f"{label} must be timezone-aware")
        return result.astimezone(timezone.utc)
    deadline = parse_time(raw_provider.get("deadline"), "raw provider deadline")
    generated_raw = raw_provider.get("computed_at")
    generated = parse_time(generated_raw, "raw provider computed_at")
    captured = parse_time(provider_source.get("captured_at_utc"), "provider capture")
    bootstrap_captured = parse_time(metadata_source.get("captured_at_utc"), "metadata capture")
    if not generated < captured < deadline or not bootstrap_captured < deadline:
        raise DecisionReplayError("raw provider/metadata timing is not strictly pre-deadline")
    token = captured.strftime("%Y%m%dT%H%M%S%fZ")
    expected_snapshot = {
        "snapshot_id": f"fplcat-gw{gw}-{token}",
        "season": manifest.get("season"),
        "target_gameweek": gw,
        "provider": {
            "name": "FPL Cat",
            "product": "published xP",
            "variant": "public next-gameweek JSON API",
            "version": "api/v1",
        },
        "timing": {
            "generated_at_utc": generated.isoformat().replace("+00:00", "Z"),
            "captured_at_utc": captured.isoformat().replace("+00:00", "Z"),
            "deadline_utc": deadline.isoformat().replace("+00:00", "Z"),
        },
        "source": {
            "url": provider_source["source_url"],
            "raw_snapshot_id": provider_source["raw_snapshot_id"],
            "raw_sha256": hashlib.sha256(provider_raw).hexdigest(),
        },
        "grain": "player_gameweek",
        "records": records,
        "coverage": {
            "row_count": len(records),
            "expected_player_universe": len(elements),
            "identity_mapped_count": len(records),
        },
    }
    if _canonical(dict(provider)) != _canonical(expected_snapshot):
        raise DecisionReplayError("canonical provider snapshot cannot be reconstructed from its raw archive")
    expected_metadata_provenance = {
        "source_url": metadata_source["source_url"],
        "raw_snapshot_id": metadata_source["raw_snapshot_id"],
        "raw_sha256": hashlib.sha256(metadata_raw).hexdigest(),
        "captured_at_utc": _utc_text(metadata_source.get("captured_at_utc"), "metadata capture"),
        "row_count": len(metadata),
    }
    if _canonical(dict(provenance)) != _canonical(expected_metadata_provenance):
        raise DecisionReplayError("canonical player metadata provenance differs from its raw archive")
    if _canonical(manifest.get("player_metadata")) != _canonical(metadata):
        raise DecisionReplayError("canonical player metadata cannot be reconstructed from the official bootstrap")


def _reconstruct_manager_state(manifest: Mapping[str, Any],
                               source: Mapping[str, Any]) -> None:
    raw, envelope = _decode_json_archive(source, "manager deadline state")
    if envelope.get("capture_kind") != "USER_ATTESTED_PREDEADLINE_MANAGER_STATE":
        raise DecisionReplayError("manager source archive has an unsupported capture kind")
    manager_id = manifest.get("manager_team_id")
    gameweek = manifest.get("target_gameweek")
    if envelope.get("manager_team_id") != manager_id or envelope.get("target_gameweek") != gameweek:
        raise DecisionReplayError("raw manager archive identity differs from the capture manifest")
    if envelope.get("captured_at_utc") != source.get("captured_at_utc"):
        raise DecisionReplayError("raw manager archive capture time differs from source provenance")
    state = envelope.get("manager_state")
    canonical_state = manifest.get("manager_state")
    if not isinstance(state, Mapping) or not isinstance(canonical_state, Mapping):
        raise DecisionReplayError("attested or canonical manager state is missing")
    if _canonical(dict(state)) != _canonical(dict(canonical_state)):
        raise DecisionReplayError("canonical manager state differs from its archived attestation")
    squad = state.get("squad_15")
    if not isinstance(squad, list) or len(squad) != 15 or len(set(squad)) != 15:
        raise DecisionReplayError("archived manager attestation does not contain 15 unique players")
    purchase = state.get("purchase_prices")
    selling = state.get("selling_prices")
    expected_keys = {str(player_id) for player_id in squad}
    if not isinstance(purchase, Mapping) or set(purchase) != expected_keys:
        raise DecisionReplayError("manager purchase prices do not cover the attested squad")
    if not isinstance(selling, Mapping) or set(selling) != expected_keys:
        raise DecisionReplayError("manager selling prices do not cover the attested squad")

    method = envelope.get("capture_method")
    manager_urls = envelope.get("source_urls")
    if not isinstance(manager_urls, list) or not manager_urls:
        raise DecisionReplayError("manager attestation source URLs are missing")
    if method == "OFFICIAL_TARGET_GAMEWEEK_PICKS":
        expected_url = f"https://fantasy.premierleague.com/api/entry/{manager_id}/event/{gameweek}/picks/"
        if expected_url not in manager_urls:
            raise DecisionReplayError("official manager picks URL does not match manager/Gameweek")
        try:
            picks_raw = base64.b64decode(envelope["raw_manager_picks_base64"], validate=True)
            picks_payload = json.loads(picks_raw)
        except Exception as exc:
            raise DecisionReplayError("official manager picks archive is invalid") from exc
        if not isinstance(picks_payload, dict) or picks_payload.get("entry_history", {}).get("event") != gameweek:
            raise DecisionReplayError("official manager picks payload has the wrong Gameweek")
        picks = picks_payload.get("picks")
        if not isinstance(picks, list) or len(picks) != 15:
            raise DecisionReplayError("official manager picks must contain exactly 15 players")
        by_position = {row.get("position"): row for row in picks if isinstance(row, dict)}
        if set(by_position) != set(range(1, 16)) or {row.get("element") for row in picks} != set(squad):
            raise DecisionReplayError("official manager picks do not reproduce the attested squad")
        xi = [by_position[pos]["element"] for pos in range(1, 12)]
        if set(xi) != set(state.get("starting_xi", [])):
            raise DecisionReplayError("official manager picks do not reproduce the attested starting XI")
        # FPL bench order places the reserve goalkeeper among positions 12–15;
        # the three outfield substitutes retain their relative order.
        bench_ids = [by_position[pos]["element"] for pos in range(12, 16)]
        reserve = state.get("reserve_goalkeeper_id")
        outfield_bench = [player_id for player_id in bench_ids if player_id != reserve]
        if outfield_bench != state.get("bench_order") or bench_ids[-1] != reserve:
            raise DecisionReplayError("official manager picks do not reproduce the attested bench order/reserve goalkeeper")
        if [row["element"] for row in picks if row.get("is_captain") is True] != [state.get("captain_id")]:
            raise DecisionReplayError("official manager picks do not reproduce the attested captain")
        if [row["element"] for row in picks if row.get("is_vice_captain") is True] != [state.get("vice_captain_id")]:
            raise DecisionReplayError("official manager picks do not reproduce the attested vice-captain")
        history = picks_payload.get("entry_history", {})
        bank = history.get("bank")
        if isinstance(bank, bool) or not isinstance(bank, int) or abs(bank / 10 - state.get("bank", -100)) > 0.0001:
            raise DecisionReplayError("official manager picks do not reproduce the attested bank")
        official_purchase = {
            str(row["element"]): row["purchase_price"] / 10
            for row in picks if isinstance(row.get("purchase_price"), int) and not isinstance(row.get("purchase_price"), bool)
        }
        if official_purchase != dict(purchase):
            raise DecisionReplayError("official manager picks do not reproduce purchase prices")
        official_selling = {
            str(row["element"]): row["selling_price"] / 10
            for row in picks if isinstance(row.get("selling_price"), int) and not isinstance(row.get("selling_price"), bool)
        }
        if official_selling and official_selling != dict(selling):
            raise DecisionReplayError("official manager picks do not reproduce selling prices")
    elif method in {"USER_CONFIRMED_WITH_PREVIOUS_GW_PICKS", "USER_CONFIRMED_WITH_OFFICIAL_HISTORY"}:
        try:
            wrapper_raw = base64.b64decode(envelope["history_archive_base64"], validate=True)
            wrapper = json.loads(wrapper_raw)
        except Exception as exc:
            raise DecisionReplayError("official manager history wrapper is invalid") from exc
        if not isinstance(wrapper, dict):
            raise DecisionReplayError("official manager history wrapper must be an object")
        if wrapper.get("source_type") != ("PREVIOUS_GAMEWEEK_PICKS" if method == "USER_CONFIRMED_WITH_PREVIOUS_GW_PICKS" else "FPL_SEASON_HISTORY_RECONSTRUCTION"):
            raise DecisionReplayError("manager history source type differs from capture method")
        from capture_fpl_manager_context import reconstruct_purchase_prices
        def nested(name: str) -> dict[str, Any]:
            try:
                value = json.loads(base64.b64decode(wrapper[name], validate=True))
            except Exception as exc:
                raise DecisionReplayError(f"manager history archive {name} is invalid") from exc
            if not isinstance(value, (dict, list)):
                raise DecisionReplayError(f"manager history archive {name} has an invalid schema")
            return value
        previous = nested("previous_gameweek_picks")
        history = nested("history")
        if previous.get("entry_history", {}).get("event") != gameweek - 1:
            raise DecisionReplayError("previous manager picks archive has the wrong Gameweek")
        if method == "USER_CONFIRMED_WITH_PREVIOUS_GW_PICKS":
            if {row.get("element") for row in previous.get("picks", [])} != set(squad):
                raise DecisionReplayError("previous manager picks do not reproduce the attested squad")
            reconstructed = {
                str(row["element"]): row["purchase_price"] / 10
                for row in previous["picks"]
                if isinstance(row.get("purchase_price"), int) and not isinstance(row.get("purchase_price"), bool)
            }
        else:
            gw1 = nested("gw1_picks")
            transfers = nested("transfers")
            bootstrap = nested("bootstrap")
            reconstructed_rows = reconstruct_purchase_prices(gw1, transfers, history, gameweek, set(squad), bootstrap)
            reconstructed = {str(row["fpl_element_id"]): row["purchase_price"] for row in reconstructed_rows}
        if reconstructed != dict(purchase):
            raise DecisionReplayError("official manager history cannot reproduce attested purchase prices")
        chips = history.get("chips")
        if not isinstance(chips, list) or any(
            isinstance(chip, dict) and chip.get("event") == gameweek for chip in chips
        ):
            raise DecisionReplayError("official manager history does not prove a no-chip target Gameweek")
    else:
        raise DecisionReplayError(f"unsupported manager capture method: {method}")
    if hashlib.sha256(raw).hexdigest() != source.get("raw_sha256"):
        raise DecisionReplayError("manager attestation raw archive hash mismatch")


def replay_frozen_decision(
    evidence_bundle: Mapping[str, Any],
    frozen_output: Mapping[str, Any],
    *,
    software_commit: str,
) -> dict[str, Any]:
    if not isinstance(frozen_output, Mapping):
        raise DecisionReplayError("frozen recommendation must be an object")
    candidate = frozen_output.get("evaluation_candidate")
    if not isinstance(candidate, Mapping) or candidate.get("software_commit") != software_commit:
        raise DecisionReplayError("replay software commit does not match the frozen decision commit")
    if frozen_output.get("manager_team_id") != candidate.get("manager_team_id"):
        raise DecisionReplayError("frozen manager identity mismatch")
    if frozen_output.get("target_gameweek") != candidate.get("target_gameweek"):
        raise DecisionReplayError("frozen Gameweek mismatch")
    if not isinstance(evidence_bundle, Mapping) or len(evidence_bundle) != 1:
        raise DecisionReplayError("evidence bundle must contain exactly one Gameweek manifest")
    key, manifest = next(iter(evidence_bundle.items()))
    if not isinstance(manifest, Mapping):
        raise DecisionReplayError("Gameweek manifest must be an object")
    if str(candidate.get("target_gameweek")) != str(key):
        raise DecisionReplayError("capture manifest and frozen decision Gameweek differ")
    if manifest.get("manager_team_id") != candidate.get("manager_team_id"):
        raise DecisionReplayError("capture manifest and frozen decision manager differ")
    _verify_archives(manifest)
    by_type = {row["source_type"]: row for row in manifest["sources"]}
    _reconstruct_provider_and_metadata(manifest, by_type)
    _reconstruct_manager_state(manifest, by_type["manager_deadline_state"])

    replayed = run_predeadline_m3_decision(
        evidence_bundle, software_commit=software_commit
    )
    expected_decision = frozen_output.get("frozen_decision")
    actual_decision = replayed.get("frozen_decision")
    if _canonical(actual_decision) != _canonical(expected_decision):
        raise DecisionReplayError("replayed frozen decision differs from the archived decision")
    if _canonical(replayed.get("recommendation")) != _canonical(frozen_output.get("recommendation")):
        raise DecisionReplayError("replayed recommendation differs from the archived recommendation")

    decision_hash = hashlib.sha256(_canonical(actual_decision).encode("utf-8")).hexdigest()
    return {
        "status": "PASSED",
        "replay_type": "DETERMINISTIC_CANONICAL_INPUT_REEXECUTION",
        "manager_team_id": candidate["manager_team_id"],
        "target_gameweek": candidate["target_gameweek"],
        "software_commit": software_commit,
        "decision_sha256": actual_decision["decision_sha256"],
        "replayed_payload_sha256": decision_hash,
        "recommendation_match": True,
        "frozen_decision_match": True,
        "raw_archive_hashes_verified": True,
        "release_eligible": False,
        "limitations": [
            "Replay uses the canonical normalized inputs stored in the capture manifest.",
            "Raw-source-to-normalized-input reconstruction is not established by this replay alone.",
            "A successful replay proves deterministic reproduction, not forecast accuracy or decision value.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_bundle", type=Path)
    parser.add_argument("frozen_recommendation", type=Path)
    parser.add_argument("--software-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bundle = json.loads(args.evidence_bundle.read_text(encoding="utf-8"))
    frozen = json.loads(args.frozen_recommendation.read_text(encoding="utf-8"))
    result = replay_frozen_decision(bundle, frozen, software_commit=args.software_commit)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
