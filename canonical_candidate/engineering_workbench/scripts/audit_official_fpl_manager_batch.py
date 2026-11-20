#!/usr/bin/env python3
"""Verify integrity and coverage of a multi-Gameweek official FPL reconciliation batch."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from capture_fpl_manager_context import reconstruct_purchase_prices


class BatchAuditError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BatchAuditError(message)




def _decode_archive(encoded: Any, label: str) -> tuple[bytes, Any]:
    _require(isinstance(encoded, str) and encoded, f"{label}: raw archive missing")
    try:
        raw = base64.b64decode(encoded, validate=True)
        payload = json.loads(raw)
    except Exception as exc:
        raise BatchAuditError(f"{label}: invalid base64/JSON archive") from exc
    return raw, payload


def _validate_attested_manager_state(envelope: dict[str, Any], archive: dict[str, Any],
                                     manager_team_id: int, gameweek: int) -> dict[str, Any]:
    _require(envelope.get("capture_kind") == "USER_ATTESTED_PREDEADLINE_MANAGER_STATE",
             f"GW{gameweek}: unsupported manager deadline-state envelope")
    _require(envelope.get("manager_team_id") == manager_team_id
             and envelope.get("target_gameweek") == gameweek,
             f"GW{gameweek}: manager attestation identity mismatch")
    _require(envelope.get("captured_at_utc") == archive.get("captured_at_utc"),
             f"GW{gameweek}: manager attestation capture timestamp mismatch")
    state = envelope.get("manager_state")
    _require(isinstance(state, dict), f"GW{gameweek}: manager attestation state missing")
    squad = state.get("squad_15")
    xi = state.get("starting_xi")
    bench = state.get("bench_order")
    reserve_gk = state.get("reserve_goalkeeper_id")
    _require(isinstance(squad, list) and len(squad) == 15 and len(set(squad)) == 15,
             f"GW{gameweek}: attested squad must contain 15 unique players")
    _require(isinstance(xi, list) and len(xi) == 11 and len(set(xi)) == 11
             and set(xi).issubset(set(squad)),
             f"GW{gameweek}: attested starting XI is invalid")
    _require(isinstance(bench, list) and len(bench) == 3 and len(set(bench)) == 3
             and set(bench).issubset(set(squad)),
             f"GW{gameweek}: attested outfield bench order is invalid")
    _require(reserve_gk in squad and reserve_gk not in set(xi) | set(bench),
             f"GW{gameweek}: attested reserve goalkeeper is invalid")
    _require(set(xi) | set(bench) | {reserve_gk} == set(squad),
             f"GW{gameweek}: attested XI and bench do not partition the squad")
    _require(state.get("chip_state") == "NONE",
             f"GW{gameweek}: attested chip state is not NONE")
    _require(state.get("captain_id") in squad and state.get("vice_captain_id") in squad
             and state.get("captain_id") != state.get("vice_captain_id"),
             f"GW{gameweek}: attested captain/vice-captain is invalid")
    _require(isinstance(state.get("bank"), (int, float)) and not isinstance(state.get("bank"), bool)
             and state["bank"] >= 0,
             f"GW{gameweek}: attested bank is invalid")
    ft = state.get("free_transfers")
    _require(isinstance(ft, int) and not isinstance(ft, bool) and 0 <= ft <= 5,
             f"GW{gameweek}: attested free-transfer count is invalid")
    _require(state.get("formation") in {"3-4-3", "3-5-2", "4-3-3", "4-4-2",
                                        "4-5-1", "5-2-3", "5-3-2", "5-4-1"},
             f"GW{gameweek}: attested formation is unsupported")
    for field in ("purchase_prices", "selling_prices"):
        prices = state.get(field)
        _require(isinstance(prices, dict)
                 and set(prices) == {str(player_id) for player_id in squad},
                 f"GW{gameweek}: attested {field} must cover the exact squad")
        _require(all(isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
                     for value in prices.values()),
                 f"GW{gameweek}: attested {field} contains invalid values")

    method = envelope.get("capture_method")
    source_urls = envelope.get("source_urls")
    _require(isinstance(source_urls, list) and source_urls,
             f"GW{gameweek}: manager attestation source URLs missing")
    history_archive_b64 = envelope.get("history_archive_base64")
    if method in {"USER_CONFIRMED_WITH_OFFICIAL_HISTORY",
                  "USER_CONFIRMED_WITH_PREVIOUS_GW_PICKS"}:
        _, wrapper = _decode_archive(history_archive_b64, f"GW{gameweek}/manager history wrapper")
        _require(isinstance(wrapper, dict), f"GW{gameweek}: manager history wrapper must be an object")
        previous_url = f"https://fantasy.premierleague.com/api/entry/{manager_team_id}/event/{gameweek - 1}/picks/"
        history_url = f"https://fantasy.premierleague.com/api/entry/{manager_team_id}/history/"
        if method == "USER_CONFIRMED_WITH_PREVIOUS_GW_PICKS":
            _require(wrapper.get("source_type") == "PREVIOUS_GAMEWEEK_PICKS",
                     f"GW{gameweek}: previous-Gameweek source type mismatch")
            _require(previous_url in source_urls and history_url in source_urls,
                     f"GW{gameweek}: previous-Gameweek source URLs mismatch")
            _, previous = _decode_archive(wrapper.get("previous_gameweek_picks"),
                                          f"GW{gameweek}/previous picks")
            _, history = _decode_archive(wrapper.get("history"), f"GW{gameweek}/history")
            _require(previous.get("entry_history", {}).get("event") == gameweek - 1,
                     f"GW{gameweek}: previous picks event mismatch")
            previous_picks = previous.get("picks")
            _require(isinstance(previous_picks, list) and len(previous_picks) == 15,
                     f"GW{gameweek}: previous picks must contain 15 players")
            previous_ids = {row.get("element") for row in previous_picks if isinstance(row, dict)}
            _require(previous_ids == set(squad),
                     f"GW{gameweek}: previous-Gameweek squad does not match attested squad")
            prior_prices = {}
            for row in previous_picks:
                _require(isinstance(row, dict)
                         and isinstance(row.get("purchase_price"), int)
                         and not isinstance(row.get("purchase_price"), bool),
                         f"GW{gameweek}: previous picks purchase_price missing")
                prior_prices[str(row["element"])] = row["purchase_price"] / 10
            _require(prior_prices == state["purchase_prices"],
                     f"GW{gameweek}: purchase prices do not match official previous-Gameweek picks")
        else:
            _require(wrapper.get("source_type") == "FPL_SEASON_HISTORY_RECONSTRUCTION",
                     f"GW{gameweek}: official-history source type mismatch")
            gw1_url = f"https://fantasy.premierleague.com/api/entry/{manager_team_id}/event/1/picks/"
            transfers_url = f"https://fantasy.premierleague.com/api/entry/{manager_team_id}/transfers/"
            bootstrap_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
            _require(all(url in source_urls for url in
                         (previous_url, gw1_url, transfers_url, history_url, bootstrap_url)),
                     f"GW{gameweek}: official-history source URLs incomplete")
            _, previous = _decode_archive(wrapper.get("previous_gameweek_picks"),
                                          f"GW{gameweek}/previous picks")
            _, gw1 = _decode_archive(wrapper.get("gw1_picks"), f"GW{gameweek}/GW1 picks")
            _, transfers = _decode_archive(wrapper.get("transfers"), f"GW{gameweek}/transfers")
            _, history = _decode_archive(wrapper.get("history"), f"GW{gameweek}/history")
            _, bootstrap = _decode_archive(wrapper.get("bootstrap"), f"GW{gameweek}/history bootstrap")
            _require(previous.get("entry_history", {}).get("event") == gameweek - 1,
                     f"GW{gameweek}: previous picks event mismatch")
            _require(gw1.get("entry_history", {}).get("event") == 1,
                     f"GW{gameweek}: GW1 picks event mismatch")
            _require(isinstance(transfers, list), f"GW{gameweek}: transfers archive must be a list")
            reconstructed = reconstruct_purchase_prices(
                gw1, transfers, history, gameweek, set(squad), bootstrap
            )
            reconstructed_prices = {
                str(row["fpl_element_id"]): row["purchase_price"]
                for row in reconstructed
            }
            _require(reconstructed_prices == state["purchase_prices"],
                     f"GW{gameweek}: purchase prices fail independent official-history reconstruction")
        chips = history.get("chips")
        _require(isinstance(chips, list) and not any(
            isinstance(chip, dict) and chip.get("event") == gameweek for chip in chips
        ), f"GW{gameweek}: official manager history shows a chip in the target Gameweek")
    elif method == "OFFICIAL_TARGET_GAMEWEEK_PICKS":
        picks_url = f"https://fantasy.premierleague.com/api/entry/{manager_team_id}/event/{gameweek}/picks/"
        _require(picks_url in source_urls,
                 f"GW{gameweek}: official target picks source URL mismatch")
        _, picks_payload = _decode_archive(envelope.get("raw_manager_picks_base64"),
                                           f"GW{gameweek}/official target picks")
        _require(picks_payload.get("entry_history", {}).get("event") == gameweek,
                 f"GW{gameweek}: official target picks event mismatch")
        _require(picks_payload.get("active_chip") is None,
                 f"GW{gameweek}: official target picks show an active chip")
        picks = picks_payload.get("picks")
        _require(isinstance(picks, list) and len(picks) == 15
                 and {row.get("element") for row in picks} == set(squad),
                 f"GW{gameweek}: official target picks do not match attested squad")
        official_purchase_prices = {
            str(row["element"]): row["purchase_price"] / 10
            for row in picks if isinstance(row, dict)
            and isinstance(row.get("purchase_price"), int)
            and not isinstance(row.get("purchase_price"), bool)
        }
        _require(official_purchase_prices == state["purchase_prices"],
                 f"GW{gameweek}: purchase prices differ from official target picks")
        official_selling_prices = {
            str(row["element"]): row["selling_price"] / 10
            for row in picks if isinstance(row, dict)
            and isinstance(row.get("selling_price"), int)
            and not isinstance(row.get("selling_price"), bool)
        }
        if official_selling_prices:
            _require(official_selling_prices == state["selling_prices"],
                     f"GW{gameweek}: selling prices differ from official target picks")
        bank_raw = picks_payload.get("entry_history", {}).get("bank")
        _require(isinstance(bank_raw, int) and not isinstance(bank_raw, bool)
                 and abs(bank_raw / 10 - state["bank"]) < 0.0001,
                 f"GW{gameweek}: official target picks bank differs from attested bank")
        official_purchase_prices = {
            str(row["element"]): row.get("purchase_price") / 10
            for row in picks if isinstance(row, dict)
            and isinstance(row.get("purchase_price"), int)
            and not isinstance(row.get("purchase_price"), bool)
        }
        if official_purchase_prices:
            _require(official_purchase_prices == state["purchase_prices"],
                     f"GW{gameweek}: purchase prices differ from official target picks")
    else:
        raise BatchAuditError(f"GW{gameweek}: unsupported manager attestation capture method")
    return state


def _verify_selling_prices(state: dict[str, Any], metadata: dict[str, Any],
                           gameweek: int) -> None:
    elements = metadata.get("elements")
    _require(isinstance(elements, list), f"GW{gameweek}: player metadata elements missing")
    by_id = {row.get("id"): row for row in elements if isinstance(row, dict)}
    for player_id in state["squad_15"]:
        row = by_id.get(player_id)
        _require(isinstance(row, dict), f"GW{gameweek}: metadata missing player {player_id}")
        now_cost = row.get("now_cost")
        purchase_tenths = round(float(state["purchase_prices"][str(player_id)]) * 10)
        _require(isinstance(now_cost, int) and not isinstance(now_cost, bool) and now_cost > 0,
                 f"GW{gameweek}: current price missing for player {player_id}")
        expected = (
            purchase_tenths + (now_cost - purchase_tenths) // 2
            if now_cost > purchase_tenths else now_cost
        )
        actual = round(float(state["selling_prices"][str(player_id)]) * 10)
        _require(actual == expected,
                 f"GW{gameweek}: selling price for player {player_id} fails official FPL price rule")


def _verify_finalized_manager_state(record: dict[str, Any], state: dict[str, Any],
                                    manager_team_id: int, gameweek: int) -> None:
    archives = record.get("source_archives", [])
    manager_archive = next((row for row in archives if row.get("source_type") == "manager_picks"), None)
    _require(isinstance(manager_archive, dict),
             f"GW{gameweek}: finalized official manager picks missing for state verification")
    _, payload = _decode_archive(manager_archive.get("raw_payload_base64"),
                                 f"GW{gameweek}/finalized manager picks")
    picks = payload.get("picks")
    _require(isinstance(picks, list) and len(picks) == 15,
             f"GW{gameweek}: finalized manager picks must contain 15 players")
    _require({row.get("element") for row in picks} == set(state["squad_15"]),
             f"GW{gameweek}: finalized official squad differs from predeadline attestation")
    _require(payload.get("active_chip") is None,
             f"GW{gameweek}: finalized official picks show an active chip")
    entry_history = payload.get("entry_history", {})
    bank_raw = entry_history.get("bank")
    _require(isinstance(bank_raw, int) and not isinstance(bank_raw, bool)
             and abs(bank_raw / 10 - state["bank"]) < 0.0001,
             f"GW{gameweek}: finalized official bank differs from predeadline attestation")

    positions = {row["element"]: row["position"] for row in picks}
    automatic_subs = payload.get("automatic_subs", [])
    _require(isinstance(automatic_subs, list),
             f"GW{gameweek}: official automatic_subs must be a list")
    for substitution in automatic_subs:
        incoming, outgoing = substitution.get("element_in"), substitution.get("element_out")
        _require(incoming in positions and outgoing in positions,
                 f"GW{gameweek}: malformed official autosub pair")
        positions[incoming], positions[outgoing] = positions[outgoing], positions[incoming]
    reconstructed_xi = {player_id for player_id, position in positions.items() if position <= 11}
    _require(reconstructed_xi == set(state["starting_xi"]),
             f"GW{gameweek}: predeadline starting XI differs from finalized official lineup")
    element_types = {row["element"]: row.get("element_type") for row in picks}
    bench = sorted(
        (player_id for player_id, position in positions.items()
         if position > 11 and element_types[player_id] != 1),
        key=lambda player_id: positions[player_id],
    )
    reserve_gks = [player_id for player_id, position in positions.items()
                   if position > 11 and element_types[player_id] == 1]
    _require(bench == state["bench_order"],
             f"GW{gameweek}: predeadline outfield bench order differs from finalized official lineup")
    _require(reserve_gks == [state["reserve_goalkeeper_id"]],
             f"GW{gameweek}: predeadline reserve goalkeeper differs from finalized official lineup")
    captains = [row["element"] for row in picks if row.get("is_captain") is True]
    vice_captains = [row["element"] for row in picks if row.get("is_vice_captain") is True]
    _require(captains == [state["captain_id"]] and vice_captains == [state["vice_captain_id"]],
             f"GW{gameweek}: captain/vice-captain differs from predeadline attestation")
    actual_counts = {
        position: sum(element_types.get(player_id) == element_type
                      for player_id in state["starting_xi"])
        for element_type, position in ((1, "GKP"), (2, "DEF"), (3, "MID"), (4, "FWD"))
    }
    expected_counts = dict(zip(("DEF", "MID", "FWD"),
                               (int(value) for value in state["formation"].split("-"))))
    _require(actual_counts["GKP"] == 1 and all(
        actual_counts[position] == expected_counts[position]
        for position in ("DEF", "MID", "FWD")
    ), f"GW{gameweek}: attested formation does not match finalized official lineup")


def _audit_archives(record: dict[str, Any], manager_team_id: int, gameweek: int,
                    decision_sources_out: list[dict[str, Any]]) -> list[dict[str, Any]]:
    archives = record.get("source_archives")
    _require(isinstance(archives, list), f"GW{gameweek}: source_archives must be a list")
    by_type = {row.get("source_type"): row for row in archives if isinstance(row, dict)}
    expected = {"bootstrap_static", "manager_picks", "event_live"}
    _require(set(by_type) == expected and len(archives) == 3,
             f"GW{gameweek}: expected exactly three unique official source archives")
    audited = []
    for source_type in sorted(expected):
        archive = by_type[source_type]
        raw_b64 = archive.get("raw_payload_base64")
        _require(isinstance(raw_b64, str) and raw_b64, f"GW{gameweek}/{source_type}: raw payload missing")
        try:
            raw = base64.b64decode(raw_b64, validate=True)
        except Exception as exc:
            raise BatchAuditError(f"GW{gameweek}/{source_type}: invalid base64 payload") from exc
        digest = hashlib.sha256(raw).hexdigest()
        _require(digest == archive.get("raw_sha256"),
                 f"GW{gameweek}/{source_type}: SHA-256 mismatch")
        try:
            payload = json.loads(raw)
        except Exception as exc:
            raise BatchAuditError(f"GW{gameweek}/{source_type}: archived payload is not valid JSON") from exc
        _require(isinstance(payload, dict), f"GW{gameweek}/{source_type}: archived payload must be an object")
        captured = archive.get("captured_at_utc")
        _require(isinstance(captured, str), f"GW{gameweek}/{source_type}: capture timestamp missing")
        try:
            parsed = datetime.fromisoformat(captured.replace("Z", "+00:00"))
        except ValueError as exc:
            raise BatchAuditError(f"GW{gameweek}/{source_type}: invalid capture timestamp") from exc
        _require(parsed.tzinfo is not None, f"GW{gameweek}/{source_type}: capture timestamp must be timezone-aware")
        url = archive.get("source_url", "")
        if source_type == "manager_picks":
            _require(url.endswith(f"/entry/{manager_team_id}/event/{gameweek}/picks/"),
                     f"GW{gameweek}: manager picks archive URL does not match manager/event")
            _require(payload.get("entry_history", {}).get("event") == gameweek,
                     f"GW{gameweek}: archived manager picks event mismatch")
        elif source_type == "event_live":
            _require(url.endswith(f"/event/{gameweek}/live/"),
                     f"GW{gameweek}: event-live archive URL mismatch")
            _require(isinstance(payload.get("elements"), list),
                     f"GW{gameweek}: event-live archive has no elements")
        else:
            _require(url.endswith("/bootstrap-static/"),
                     f"GW{gameweek}: bootstrap archive URL mismatch")
            events = payload.get("events")
            matches = [row for row in events or [] if isinstance(row, dict) and row.get("id") == gameweek]
            _require(len(matches) == 1 and matches[0].get("finished") is True
                     and matches[0].get("data_checked") is True,
                     f"GW{gameweek}: bootstrap does not confirm finalized event")
        _require(archive.get("raw_snapshot_id"), f"GW{gameweek}/{source_type}: snapshot ID missing")
        audited.append({
            "source_type": source_type,
            "raw_snapshot_id": archive["raw_snapshot_id"],
            "raw_sha256": digest,
            "captured_at_utc": captured,
            "source_url": url,
            "bytes": len(raw),
        })

    # Decision-input archives are distinct from post-deadline scoring archives.
    # Each must carry its own raw bytes and exact point-in-time provenance.
    decision_archives = record.get("decision_source_archives", [])
    _require(isinstance(decision_archives, list),
             f"GW{gameweek}: decision_source_archives must be a list")
    allowed_decision_types = {
        "provider_forecast", "player_metadata", "manager_deadline_state"
    }
    seen_decision_types = set()
    decision_payloads: dict[str, Any] = {}
    decision_archive_rows: dict[str, dict[str, Any]] = {}
    for archive in decision_archives:
        _require(isinstance(archive, dict),
                 f"GW{gameweek}: malformed decision evidence archive")
        source_type = archive.get("source_type")
        _require(source_type in allowed_decision_types and source_type not in seen_decision_types,
                 f"GW{gameweek}: unsupported or duplicate decision evidence archive type")
        seen_decision_types.add(source_type)
        raw_b64 = archive.get("raw_payload_base64")
        _require(isinstance(raw_b64, str) and raw_b64,
                 f"GW{gameweek}/{source_type}: raw payload missing")
        try:
            raw = base64.b64decode(raw_b64, validate=True)
            payload = json.loads(raw)
        except Exception as exc:
            raise BatchAuditError(
                f"GW{gameweek}/{source_type}: invalid base64 or JSON payload"
            ) from exc
        _require(isinstance(payload, (dict, list)),
                 f"GW{gameweek}/{source_type}: payload must be a JSON object or array")
        decision_payloads[source_type] = payload
        decision_archive_rows[source_type] = archive
        digest = hashlib.sha256(raw).hexdigest()
        _require(digest == archive.get("raw_sha256"),
                 f"GW{gameweek}/{source_type}: SHA-256 mismatch")
        captured = archive.get("captured_at_utc")
        try:
            parsed = datetime.fromisoformat(captured.replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise BatchAuditError(
                f"GW{gameweek}/{source_type}: invalid capture timestamp"
            ) from exc
        _require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
                 f"GW{gameweek}/{source_type}: capture timestamp must be timezone-aware")
        url = archive.get("source_url")
        _require(isinstance(url, str) and url.startswith("https://"),
                 f"GW{gameweek}/{source_type}: HTTPS source URL missing")
        snapshot_id = archive.get("raw_snapshot_id")
        _require(isinstance(snapshot_id, str) and snapshot_id,
                 f"GW{gameweek}/{source_type}: snapshot ID missing")
        if source_type == "player_metadata":
            _require(url.endswith("/bootstrap-static/"),
                     f"GW{gameweek}: player metadata source URL mismatch")
        elif source_type == "manager_deadline_state":
            if payload.get("capture_kind") == "USER_ATTESTED_PREDEADLINE_MANAGER_STATE":
                _require(url == f"https://fantasy.premierleague.com/entry/{manager_team_id}",
                         f"GW{gameweek}: manager attestation URL mismatch")
            else:
                _require(url.endswith(f"/entry/{manager_team_id}/event/{gameweek}/picks/"),
                         f"GW{gameweek}: manager deadline-state source URL mismatch")
                _require(payload.get("entry_history", {}).get("event") == gameweek,
                         f"GW{gameweek}: manager deadline-state payload Gameweek mismatch")
        generated = archive.get("generated_at_utc")
        provider_id = archive.get("provider_id")
        provider_variant = archive.get("provider_variant")
        if source_type == "provider_forecast":
            try:
                generated_time = datetime.fromisoformat(generated.replace("Z", "+00:00"))
            except (TypeError, ValueError) as exc:
                raise BatchAuditError(
                    f"GW{gameweek}: provider forecast generation timestamp missing or invalid"
                ) from exc
            _require(generated_time.tzinfo is not None and generated_time.utcoffset() is not None,
                     f"GW{gameweek}: provider generation timestamp must be timezone-aware")
            _require(isinstance(provider_id, str) and provider_id
                     and isinstance(provider_variant, str) and provider_variant,
                     f"GW{gameweek}: provider identity and variant are required")
        decision_sources_out.append({
            "source_type": source_type,
            "raw_snapshot_id": snapshot_id,
            "raw_sha256": digest,
            "captured_at_utc": captured,
            "source_url": url,
            "generated_at_utc": generated,
            "provider_id": provider_id,
            "provider_variant": provider_variant,
            "bytes": len(raw),
        })
    _require(not decision_archives or seen_decision_types == allowed_decision_types,
             f"GW{gameweek}: decision evidence archive set must contain all three required sources")
    if decision_archives:
        manager_envelope = decision_payloads.get("manager_deadline_state")
        if isinstance(manager_envelope, dict) and manager_envelope.get("capture_kind") == "USER_ATTESTED_PREDEADLINE_MANAGER_STATE":
            manager_state = _validate_attested_manager_state(
                manager_envelope, decision_archive_rows["manager_deadline_state"],
                manager_team_id, gameweek
            )
            if manager_envelope.get("capture_method") == "USER_CONFIRMED_WITH_OFFICIAL_HISTORY":
                _, wrapper = _decode_archive(
                    manager_envelope.get("history_archive_base64"),
                    f"GW{gameweek}/manager history wrapper"
                )
                nested_bootstrap_raw, _ = _decode_archive(
                    wrapper.get("bootstrap"), f"GW{gameweek}/manager history bootstrap"
                )
                metadata_raw, _ = _decode_archive(
                    decision_archive_rows["player_metadata"].get("raw_payload_base64"),
                    f"GW{gameweek}/player metadata"
                )
                _require(nested_bootstrap_raw == metadata_raw,
                         f"GW{gameweek}: manager price-history bootstrap differs from player metadata archive")
            _verify_selling_prices(
                manager_state, decision_payloads["player_metadata"], gameweek
            )
            _verify_finalized_manager_state(record, manager_state, manager_team_id, gameweek)
    return audited


def audit_batch(batch: dict[str, Any],
                decision_manifests: dict[str, Any] | None = None) -> dict[str, Any]:
    _require(batch.get("batch_contract_version") == "0.1.0", "unsupported batch contract version")
    manager_id = batch.get("manager_team_id")
    _require(isinstance(manager_id, int) and manager_id > 0, "invalid manager_team_id")
    requested = batch.get("requested_gameweeks")
    results = batch.get("results")
    _require(isinstance(requested, list) and requested and len(set(requested)) == len(requested),
             "requested_gameweeks must be unique and non-empty")
    _require(isinstance(results, list), "batch results must be a list")
    _require([row.get("gameweek") for row in results] == requested,
             "batch results must cover requested Gameweeks in order")

    manifests = decision_manifests or {}
    audited_events = []
    reconciled_gws, excluded_gws, autosub_gws, hit_gws = [], [], [], []
    for row in results:
        gw, status = row.get("gameweek"), row.get("status")
        _require(isinstance(gw, int) and gw > 0, "invalid result Gameweek")
        record = row.get("result") if status == "RECONCILED" else row.get("diagnostic_record")
        if status == "RECONCILED":
            _require(isinstance(record, dict), f"GW{gw}: reconciled result missing")
            _require(record.get("manager_team_id") == manager_id and record.get("target_gameweek") == gw,
                     f"GW{gw}: child record identity mismatch")
            _require(record.get("event_finalized") is True, f"GW{gw}: event not marked finalized")
            _require(record.get("historical_evidence_admitted") is False,
                     f"GW{gw}: historical evidence admission must remain false")
            reconciliation = record.get("reconciliation", {})
            _require(reconciliation.get("status") == "RECONCILED",
                     f"GW{gw}: child reconciliation status mismatch")
            _require(reconciliation.get("historical_evidence_admitted") is False,
                     f"GW{gw}: reconciliation evidence admission must remain false")
            reconciled_gws.append(gw)
            if reconciliation.get("automatic_substitutions"):
                autosub_gws.append(gw)
            if reconciliation.get("official_transfer_cost", 0) > 0:
                hit_gws.append(gw)
        else:
            _require(status == "EXCLUDED", f"GW{gw}: unknown batch status")
            excluded_gws.append(gw)
            if record is None:
                audited_events.append({"gameweek": gw, "status": "EXCLUDED", "archives": [], "decision_sources": []})
                continue
            _require(record.get("historical_evidence_admitted") is False,
                     f"GW{gw}: diagnostic evidence admission must remain false")
        decision_sources = []
        manifest = manifests.get(str(gw), manifests.get(gw))
        record_for_audit = record
        if manifest is not None:
            _require(isinstance(manifest, dict),
                     f"GW{gw}: decision evidence manifest must be an object")
            source_rows = manifest.get("sources")
            _require(isinstance(source_rows, list)
                     and len(source_rows) == 3
                     and {source.get("source_type") for source in source_rows
                          if isinstance(source, dict)} == {
                              "provider_forecast", "player_metadata", "manager_deadline_state"
                          },
                     f"GW{gw}: decision manifest must contain all three unique source archives")
            record_for_audit = dict(record)
            record_for_audit["decision_source_archives"] = source_rows
        archives = _audit_archives(record_for_audit, manager_id, gw, decision_sources)
        audited_events.append({
            "gameweek": gw, "status": status, "archives": archives,
            "decision_sources": decision_sources,
        })

    _require(batch.get("reconciled_count") == len(reconciled_gws), "reconciled Gameweek count mismatch")
    _require(batch.get("excluded_count") == len(excluded_gws), "excluded Gameweek count mismatch")
    _require(batch.get("reconciled_gameweeks") == reconciled_gws, "reconciled Gameweek summary mismatch")
    _require(batch.get("excluded_gameweeks") == excluded_gws, "excluded Gameweek summary mismatch")
    _require(batch.get("gameweeks_with_automatic_substitutions") == autosub_gws,
             "automatic-substitution Gameweek summary mismatch")
    _require(batch.get("gameweeks_with_transfer_hits") == hit_gws,
             "transfer-hit Gameweek summary mismatch")
    _require(batch.get("historical_evidence_admitted") is False,
             "batch historical evidence admission must remain false")
    return {
        "audit_contract_version": "0.1.0",
        "status": "PASSED",
        "manager_team_id": manager_id,
        "requested_gameweeks": requested,
        "reconciled_gameweeks": reconciled_gws,
        "excluded_gameweeks": excluded_gws,
        "gameweeks_with_automatic_substitutions": autosub_gws,
        "gameweeks_with_transfer_hits": hit_gws,
        "historical_evidence_admitted": False,
        "events": audited_events,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    parser.add_argument("--decision-manifests", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    batch = json.loads(args.batch.read_text(encoding="utf-8"))
    manifests = (json.loads(args.decision_manifests.read_text(encoding="utf-8"))
                 if args.decision_manifests else None)
    audit = audit_batch(batch, manifests)
    args.output.write_text(json.dumps(audit, indent=2, sort_keys=True) + chr(10), encoding="utf-8")
    print(json.dumps({key: value for key, value in audit.items() if key != "events"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
