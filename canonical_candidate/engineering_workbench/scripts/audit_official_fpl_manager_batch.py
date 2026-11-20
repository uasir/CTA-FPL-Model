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


def _validate_predeadline_recommendation(recommendation: dict[str, Any],
                                        manager_team_id: int, gameweek: int,
                                        manifest: dict[str, Any]) -> dict[str, Any]:
    _require(recommendation.get("manager_team_id") == manager_team_id
             and recommendation.get("target_gameweek") == gameweek,
             f"GW{gameweek}: predeadline recommendation identity mismatch")
    _require(recommendation.get("decision_as_of_utc") == manifest.get("decision_as_of_utc")
             and recommendation.get("deadline_utc") == manifest.get("deadline_utc"),
             f"GW{gameweek}: recommendation timing does not match decision manifest")
    _require(recommendation.get("release_eligible") is False
             and recommendation.get("recommendation_status") == "EXPLORATORY_ONLY",
             f"GW{gameweek}: recommendation release status is invalid")
    frozen = recommendation.get("frozen_decision")
    _require(isinstance(frozen, dict), f"GW{gameweek}: frozen decision missing")
    decision_body = {key: value for key, value in frozen.items() if key != "decision_sha256"}
    digest = hashlib.sha256(json.dumps(
        decision_body, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")).hexdigest()
    _require(digest == frozen.get("decision_sha256"),
             f"GW{gameweek}: frozen recommendation decision hash mismatch")

    candidate = recommendation.get("evaluation_candidate")
    _require(isinstance(candidate, dict)
             and candidate.get("evidence_class") == "REAL_CANDIDATE"
             and candidate.get("manager_team_id") == manager_team_id
             and candidate.get("target_gameweek") == gameweek
             and candidate.get("as_of_utc") == manifest.get("decision_as_of_utc")
             and candidate.get("deadline_utc") == manifest.get("deadline_utc")
             and candidate.get("frozen_decision") == frozen,
             f"GW{gameweek}: evaluation candidate does not bind the frozen decision")
    _require(isinstance(candidate.get("software_commit"), str)
             and len(candidate["software_commit"]) in (40, 64),
             f"GW{gameweek}: recommendation software commit missing")

    manifest_sources = {row["source_type"]: row for row in manifest.get("sources", [])}
    candidate_sources = candidate.get("source_archives")
    _require(isinstance(candidate_sources, list) and len(candidate_sources) == 3,
             f"GW{gameweek}: evaluation candidate must bind all three predeadline archives")
    expected_types = {
        "provider_forecast": "provider",
        "player_metadata": "player_metadata",
        "manager_deadline_state": "manager_state",
    }
    candidate_by_type = {row.get("source_type"): row for row in candidate_sources}
    _require(set(candidate_by_type) == set(expected_types.values()),
             f"GW{gameweek}: recommendation source archive set is invalid")
    for manifest_type, candidate_type in expected_types.items():
        source = manifest_sources.get(manifest_type)
        candidate_source = candidate_by_type.get(candidate_type)
        _require(isinstance(source, dict) and isinstance(candidate_source, dict),
                 f"GW{gameweek}: recommendation source binding missing for {manifest_type}")
        for field in ("source_url", "raw_snapshot_id", "raw_sha256", "captured_at_utc",
                      "raw_payload_base64"):
            _require(candidate_source.get(field) == source.get(field),
                     f"GW{gameweek}: recommendation {candidate_type} source binding mismatch")
        if manifest_type == "provider_forecast":
            _require(candidate_source.get("generated_at_utc") == source.get("generated_at_utc"),
                     f"GW{gameweek}: recommendation provider generation time mismatch")

    state = manifest.get("manager_state")
    candidate_state = candidate.get("manager_state")
    _require(isinstance(state, dict) and isinstance(candidate_state, dict),
             f"GW{gameweek}: manager state missing from recommendation candidate")
    _require(candidate_state.get("bank") == state.get("bank")
             and candidate_state.get("free_transfers") == state.get("free_transfers")
             and candidate_state.get("formation") == state.get("formation")
             and candidate_state.get("chip") == state.get("chip_state") == "NONE",
             f"GW{gameweek}: candidate manager constraints differ from decision manifest")
    hold = candidate_state.get("hold_plan")
    _require(isinstance(hold, dict), f"GW{gameweek}: candidate hold plan missing")
    expected_hold = {
        "squad_ids": sorted(state["squad_15"]),
        "starting_xi": list(state["starting_xi"]),
        "bench_order": list(state["bench_order"]),
        "reserve_goalkeeper_id": state["reserve_goalkeeper_id"],
        "captain_id": state["captain_id"],
        "vice_captain_id": state["vice_captain_id"],
        "formation": state["formation"],
    }
    _require(hold == expected_hold, f"GW{gameweek}: frozen hold plan differs from manager attestation")
    roster = candidate_state.get("squad_snapshot")
    _require(isinstance(roster, list) and len(roster) == 15,
             f"GW{gameweek}: candidate manager roster must contain 15 players")
    roster_by_id = {row.get("fpl_element_id"): row for row in roster if isinstance(row, dict)}
    _require(set(roster_by_id) == set(state["squad_15"]),
             f"GW{gameweek}: candidate manager roster identity mismatch")
    for player_id in state["squad_15"]:
        _require(roster_by_id[player_id].get("purchase_price") == state["purchase_prices"][str(player_id)],
                 f"GW{gameweek}: candidate purchase price mismatch for player {player_id}")

    action = frozen.get("action")
    plan = frozen.get("squad_plan")
    _require(action in {"HOLD", "TRANSFER"} and isinstance(plan, dict),
             f"GW{gameweek}: unsupported frozen recommendation action/plan")
    plan_squad = plan.get("squad_ids")
    plan_xi = plan.get("starting_xi")
    plan_bench = plan.get("bench_order")
    _require(isinstance(plan_squad, list) and len(plan_squad) == 15 and len(set(plan_squad)) == 15
             and isinstance(plan_xi, list) and len(plan_xi) == 11 and len(set(plan_xi)) == 11
             and isinstance(plan_bench, list) and len(plan_bench) == 3 and len(set(plan_bench)) == 3,
             f"GW{gameweek}: frozen recommendation squad plan is malformed")
    _require(plan.get("reserve_goalkeeper_id") == state["reserve_goalkeeper_id"]
             and plan.get("formation") == state["formation"],
             f"GW{gameweek}: recommendation changed the designated goalkeeper or formation")
    _require(plan.get("captain_id") in plan_squad and plan.get("vice_captain_id") in plan_squad
             and plan.get("captain_id") != plan.get("vice_captain_id"),
             f"GW{gameweek}: recommended captain/vice-captain is invalid")

    if action == "HOLD":
        _require(frozen.get("transfer_out_id") is None and frozen.get("transfer_in_id") is None
                 and frozen.get("incoming_player") is None
                 and frozen.get("transfer_hit_points") == 0,
                 f"GW{gameweek}: HOLD decision contains transfer details")
        _require(set(plan_squad) == set(state["squad_15"])
                 and set(plan_xi) == set(state["starting_xi"])
                 and plan_bench == state["bench_order"],
                 f"GW{gameweek}: HOLD decision changed squad, starting XI or emergency bench order")
    else:
        out_id, in_id = frozen.get("transfer_out_id"), frozen.get("transfer_in_id")
        incoming = frozen.get("incoming_player")
        _require(isinstance(out_id, int) and isinstance(in_id, int)
                 and out_id in state["squad_15"] and in_id not in state["squad_15"]
                 and isinstance(incoming, dict) and incoming.get("fpl_element_id") == in_id,
                 f"GW{gameweek}: recommended transfer identity is invalid")
        _require(frozen.get("transfer_hit_points") == (0 if state["free_transfers"] > 0 else 4),
                 f"GW{gameweek}: recommended transfer hit does not match free transfers")
        outgoing = roster_by_id[out_id]
        _require(outgoing.get("position") == incoming.get("position")
                 and outgoing.get("position") != "GKP"
                 and incoming.get("purchase_price") == incoming.get("current_price"),
                 f"GW{gameweek}: recommended transfer violates position/goalkeeper/price rules")
        expected_squad = (set(state["squad_15"]) - {out_id}) | {in_id}
        _require(set(plan_squad) == expected_squad,
                 f"GW{gameweek}: recommended post-transfer squad identity mismatch")
        counts: dict[int, int] = {}
        for player_id, row in roster_by_id.items():
            if player_id != out_id:
                counts[row["team_id"]] = counts.get(row["team_id"], 0) + 1
        counts[incoming["team_id"]] = counts.get(incoming["team_id"], 0) + 1
        _require(all(count <= 3 for count in counts.values()),
                 f"GW{gameweek}: recommended transfer violates the three-per-club limit")
        if out_id in state["starting_xi"]:
            expected_xi = (set(state["starting_xi"]) - {out_id}) | {in_id}
            expected_bench = list(state["bench_order"])
        else:
            removed = set(state["starting_xi"]) - (set(plan_xi) - {in_id})
            added = set(plan_xi) - set(state["starting_xi"])
            _require(added == {in_id} and len(removed) == 1,
                     f"GW{gameweek}: bench transfer must promote one incoming player and displace one starter")
            displaced_id = next(iter(removed))
            _require(roster_by_id[displaced_id].get("position") == incoming.get("position"),
                     f"GW{gameweek}: bench transfer displaced a player in the wrong position")
            expected_xi = (set(state["starting_xi"]) - {displaced_id}) | {in_id}
            expected_bench = [
                displaced_id if player_id == out_id else player_id
                for player_id in state["bench_order"]
            ]
        _require(set(plan_xi) == expected_xi and plan_bench == expected_bench,
                 f"GW{gameweek}: recommended XI/bench does not preserve the fixed-XI emergency-bench policy")
    return frozen


def _verify_finalized_manager_state(record: dict[str, Any], state: dict[str, Any],
                                    manager_team_id: int, gameweek: int,
                                    recommended_decision: dict[str, Any] | None = None) -> str:
    archives = record.get("source_archives", [])
    manager_archive = next((row for row in archives if row.get("source_type") == "manager_picks"), None)
    _require(isinstance(manager_archive, dict),
             f"GW{gameweek}: finalized official manager picks missing for state verification")
    _, payload = _decode_archive(manager_archive.get("raw_payload_base64"),
                                 f"GW{gameweek}/finalized manager picks")
    picks = payload.get("picks")
    _require(isinstance(picks, list) and len(picks) == 15,
             f"GW{gameweek}: finalized manager picks must contain 15 players")
    _require(payload.get("active_chip") is None,
             f"GW{gameweek}: finalized official picks show an active chip")
    entry_history = payload.get("entry_history", {})
    bank_raw = entry_history.get("bank")
    _require(isinstance(bank_raw, int) and not isinstance(bank_raw, bool),
             f"GW{gameweek}: finalized official bank is missing")
    positions = {row["element"]: row["position"] for row in picks}
    automatic_subs = payload.get("automatic_subs", [])
    _require(isinstance(automatic_subs, list),
             f"GW{gameweek}: official automatic_subs must be a list")
    for substitution in automatic_subs:
        incoming, outgoing = substitution.get("element_in"), substitution.get("element_out")
        _require(incoming in positions and outgoing in positions,
                 f"GW{gameweek}: malformed official autosub pair")
        positions[incoming], positions[outgoing] = positions[outgoing], positions[incoming]
    actual_xi = {player_id for player_id, position in positions.items() if position <= 11}
    element_types = {row["element"]: row.get("element_type") for row in picks}
    actual_bench = sorted(
        (player_id for player_id, position in positions.items()
         if position > 11 and element_types[player_id] != 1),
        key=lambda player_id: positions[player_id],
    )
    actual_reserve_gks = [player_id for player_id, position in positions.items()
                          if position > 11 and element_types[player_id] == 1]
    actual_captains = [row["element"] for row in picks if row.get("is_captain") is True]
    actual_vice = [row["element"] for row in picks if row.get("is_vice_captain") is True]
    actual_counts = {
        position: sum(element_types.get(player_id) == element_type for player_id in actual_xi)
        for element_type, position in ((1, "GKP"), (2, "DEF"), (3, "MID"), (4, "FWD"))
    }
    actual_formation = "-".join(str(actual_counts[position]) for position in ("DEF", "MID", "FWD"))
    actual = {
        "squad_ids": set(positions),
        "starting_xi": actual_xi,
        "bench_order": actual_bench,
        "reserve_goalkeeper_id": actual_reserve_gks[0] if len(actual_reserve_gks) == 1 else None,
        "captain_id": actual_captains[0] if len(actual_captains) == 1 else None,
        "vice_captain_id": actual_vice[0] if len(actual_vice) == 1 else None,
        "formation": actual_formation,
        "bank": bank_raw / 10,
    }
    official_transfer_cost = record.get("reconciliation", {}).get("official_transfer_cost", 0)

    def matches(plan: dict[str, Any], expected_bank: float, expected_transfer_cost: float) -> bool:
        return (
            actual["squad_ids"] == set(plan["squad_ids"])
            and actual["starting_xi"] == set(plan["starting_xi"])
            and actual["bench_order"] == plan["bench_order"]
            and actual["reserve_goalkeeper_id"] == plan["reserve_goalkeeper_id"]
            and actual["captain_id"] == plan["captain_id"]
            and actual["vice_captain_id"] == plan["vice_captain_id"]
            and actual["formation"] == plan["formation"]
            and abs(actual["bank"] - expected_bank) < 0.0001
            and official_transfer_cost == expected_transfer_cost
        )

    hold_plan = {
        "squad_ids": sorted(state["squad_15"]),
        "starting_xi": list(state["starting_xi"]),
        "bench_order": list(state["bench_order"]),
        "reserve_goalkeeper_id": state["reserve_goalkeeper_id"],
        "captain_id": state["captain_id"],
        "vice_captain_id": state["vice_captain_id"],
        "formation": state["formation"],
    }
    if matches(hold_plan, float(state["bank"]), 0):
        return "HOLD_BASELINE_MATCHED"

    if recommended_decision is not None:
        recommended_plan = recommended_decision["squad_plan"]
        expected_bank = float(state["bank"])
        expected_cost = recommended_decision["transfer_hit_points"]
        if recommended_decision["action"] == "TRANSFER":
            out_id = recommended_decision["transfer_out_id"]
            incoming = recommended_decision["incoming_player"]
            expected_bank += float(state["selling_prices"][str(out_id)]) - float(incoming["purchase_price"])
        if matches(recommended_plan, round(expected_bank, 1), expected_cost):
            return "RECOMMENDATION_MATCHED"
    raise BatchAuditError(
        f"GW{gameweek}: finalized manager state matches neither the frozen hold baseline "
        "nor the frozen recommendation"
    )


def _audit_archives(record: dict[str, Any], manager_team_id: int, gameweek: int,
                    decision_sources_out: list[dict[str, Any]],
                    recommended_decision: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], str | None]:
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
            execution_match = _verify_finalized_manager_state(
                record, manager_state, manager_team_id, gameweek, recommended_decision
            )
        else:
            execution_match = None
    else:
        execution_match = None
    return audited, execution_match


def audit_batch(batch: dict[str, Any],
                decision_manifests: dict[str, Any] | None = None,
                predeadline_recommendation: dict[str, Any] | None = None) -> dict[str, Any]:
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
    if predeadline_recommendation is not None:
        _require(bool(manifests),
                 "predeadline recommendation cannot be audited without its decision manifest")
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
        recommended_decision = None
        recommendation_verification = None
        if predeadline_recommendation is not None and manifest is not None:
            recommended_decision = _validate_predeadline_recommendation(
                predeadline_recommendation, manager_id, gw, manifest
            )
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
        archives, execution_match = _audit_archives(
            record_for_audit, manager_id, gw, decision_sources, recommended_decision
        )
        if recommended_decision is not None:
            _require(execution_match in {"HOLD_BASELINE_MATCHED", "RECOMMENDATION_MATCHED"},
                     f"GW{gw}: frozen recommendation execution state was not verified")
            recommendation_verification = {
                "status": "VERIFIED",
                "decision_sha256": recommended_decision["decision_sha256"],
                "action": recommended_decision["action"],
                "execution_match": execution_match,
            }
        audited_events.append({
            "gameweek": gw, "status": status, "archives": archives,
            "decision_sources": decision_sources,
            "predeadline_recommendation": recommendation_verification,
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
    parser.add_argument("--predeadline-recommendation", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    batch = json.loads(args.batch.read_text(encoding="utf-8"))
    manifests = (json.loads(args.decision_manifests.read_text(encoding="utf-8"))
                 if args.decision_manifests else None)
    recommendation = (json.loads(args.predeadline_recommendation.read_text(encoding="utf-8"))
                      if args.predeadline_recommendation else None)
    audit = audit_batch(batch, manifests, recommendation)
    args.output.write_text(json.dumps(audit, indent=2, sort_keys=True) + chr(10), encoding="utf-8")
    print(json.dumps({key: value for key, value in audit.items() if key != "events"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
