#!/usr/bin/env python3
"""Normalize official FPL API payloads into private M4 replay cases.

This module is pure: it performs no network requests and emits no manager
identity, entry ID, name, or rank. Keep generated real replay files local.
"""
from __future__ import annotations

from typing import Any, Mapping

from m4_covar_fpl_replay_validation import played_from_official_element_stats


class CovarFplApiReplayAdapterError(ValueError):
    """Raised when official FPL API payloads are incomplete or inconsistent."""


_ELEMENT_TYPE_TO_POSITION = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def _required_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CovarFplApiReplayAdapterError(f"{label} must be an object")
    return value


def _required_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise CovarFplApiReplayAdapterError(f"{label} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise CovarFplApiReplayAdapterError(f"{label} must be an integer") from exc
    if str(value).strip() not in (str(parsed), f"{parsed}.0"):
        raise CovarFplApiReplayAdapterError(f"{label} must be an integer")
    return parsed


def normalize_official_fpl_replay(
    picks_payload: Mapping[str, Any],
    live_payload: Mapping[str, Any],
    bootstrap_payload: Mapping[str, Any],
    *,
    event_id: int,
    mode: str | None = None,
) -> dict[str, Any]:
    """Build one anonymized replay case from the three official FPL API payloads.

    Expected payloads are the event picks response, event live response, and
    bootstrap-static response. The caller is responsible for obtaining and
    storing these privately; this function never accesses the network.
    """
    picks_payload = _required_mapping(picks_payload, "picks_payload")
    live_payload = _required_mapping(live_payload, "live_payload")
    bootstrap_payload = _required_mapping(bootstrap_payload, "bootstrap_payload")
    event = _required_int(event_id, "event_id")
    if event < 1:
        raise CovarFplApiReplayAdapterError("event_id must be positive")
    # The official picks response includes entry_history.event. Fail closed
    # if the endpoint payload does not identify the requested Gameweek.
    entry_history = _required_mapping(
        picks_payload.get("entry_history"), "picks_payload.entry_history"
    )
    payload_event = _required_int(
        entry_history.get("event"), "picks_payload.entry_history.event"
    )
    if payload_event != event:
        raise CovarFplApiReplayAdapterError(
            f"picks payload Gameweek {payload_event} does not match requested event {event}"
        )

    raw_picks = picks_payload.get("picks")
    raw_live = live_payload.get("elements")
    raw_bootstrap = bootstrap_payload.get("elements")
    if not isinstance(raw_picks, list) or len(raw_picks) != 15:
        raise CovarFplApiReplayAdapterError("official picks payload must contain exactly 15 picks")
    if not isinstance(raw_live, list) or not raw_live:
        raise CovarFplApiReplayAdapterError("event live payload must contain elements")
    if not isinstance(raw_bootstrap, list) or not raw_bootstrap:
        raise CovarFplApiReplayAdapterError("bootstrap payload must contain elements")

    bootstrap_positions: dict[str, str] = {}
    for row in raw_bootstrap:
        row = _required_mapping(row, "bootstrap element")
        pid = str(_required_int(row.get("id"), "bootstrap element id"))
        if pid in bootstrap_positions:
            raise CovarFplApiReplayAdapterError(f"duplicate bootstrap player id: {pid}")
        element_type = _required_int(row.get("element_type"), f"bootstrap element {pid}.element_type")
        if element_type not in _ELEMENT_TYPE_TO_POSITION:
            raise CovarFplApiReplayAdapterError(f"unsupported element_type for player {pid}")
        bootstrap_positions[pid] = _ELEMENT_TYPE_TO_POSITION[element_type]

    live_stats: dict[str, Mapping[str, Any]] = {}
    for row in raw_live:
        row = _required_mapping(row, "live element")
        pid = str(_required_int(row.get("id"), "live element id"))
        if pid in live_stats:
            raise CovarFplApiReplayAdapterError(f"duplicate live player id: {pid}")
        stats = _required_mapping(row.get("stats"), f"live element {pid}.stats")
        # Validate required stats now, rather than creating a partial replay.
        for key in ("minutes", "yellow_cards", "red_cards", "total_points"):
            if key not in stats or stats[key] is None:
                raise CovarFplApiReplayAdapterError(f"live element {pid}.stats.{key} is required")
        live_stats[pid] = stats

    ordered_picks: list[tuple[int, str, Mapping[str, Any]]] = []
    seen_ids: set[str] = set()
    seen_positions: set[int] = set()
    for raw in raw_picks:
        pick = _required_mapping(raw, "official pick")
        pid = str(_required_int(pick.get("element"), "pick.element"))
        position = _required_int(pick.get("position"), f"pick {pid}.position")
        if pid in seen_ids or position in seen_positions or not 1 <= position <= 15:
            raise CovarFplApiReplayAdapterError("picks must have unique player IDs and positions 1 through 15")
        if pid not in bootstrap_positions:
            raise CovarFplApiReplayAdapterError(f"player {pid} is missing from bootstrap metadata")
        if pid not in live_stats:
            raise CovarFplApiReplayAdapterError(f"player {pid} is missing from event live data")
        for flag in ("is_captain", "is_vice_captain"):
            if not isinstance(pick.get(flag), bool):
                raise CovarFplApiReplayAdapterError(f"pick {pid}.{flag} must be boolean")
        multiplier = pick.get("multiplier")
        if isinstance(multiplier, bool) or multiplier not in (0, 1, 2, 3):
            raise CovarFplApiReplayAdapterError(f"pick {pid}.multiplier must be 0, 1, 2 or 3")
        seen_ids.add(pid)
        seen_positions.add(position)
        ordered_picks.append((position, pid, pick))
    if seen_positions != set(range(1, 16)):
        raise CovarFplApiReplayAdapterError("official pick positions must cover exactly 1 through 15")
    ordered_picks.sort(key=lambda item: item[0])
    player_ids = [pid for _, pid, _ in ordered_picks]
    starting = player_ids[:11]
    reserve_gk = player_ids[11]
    bench = player_ids[12:]
    positions = {pid: bootstrap_positions[pid] for pid in player_ids}
    if positions[reserve_gk] != "GK":
        raise CovarFplApiReplayAdapterError("pick position 12 must be the reserve goalkeeper")
    if sum(positions[pid] == "GK" for pid in starting) != 1:
        raise CovarFplApiReplayAdapterError("starting XI must contain exactly one goalkeeper")
    if any(positions[pid] == "GK" for pid in bench):
        raise CovarFplApiReplayAdapterError("positions 13-15 must be outfield substitutes")
    formation = {role: sum(positions[pid] == role for pid in starting) for role in ("DEF", "MID", "FWD")}
    if sum(formation.values()) != 10 or formation["DEF"] < 3 or formation["MID"] < 2 or formation["FWD"] < 1:
        raise CovarFplApiReplayAdapterError("starting XI does not satisfy legal FPL formation minimums")

    captain_ids = [pid for _, pid, pick in ordered_picks if pick["is_captain"]]
    vice_ids = [pid for _, pid, pick in ordered_picks if pick["is_vice_captain"]]
    if len(captain_ids) != 1 or len(vice_ids) != 1 or captain_ids[0] == vice_ids[0]:
        raise CovarFplApiReplayAdapterError("official picks must identify one distinct captain and vice-captain")
    if captain_ids[0] not in starting or vice_ids[0] not in starting:
        raise CovarFplApiReplayAdapterError("captain and vice-captain must be in the starting XI")

    active_chip = picks_payload.get("active_chip")
    if active_chip is not None and not isinstance(active_chip, str):
        raise CovarFplApiReplayAdapterError("active_chip must be a string or null")
    inferred_mode = "FREE_HIT" if active_chip == "freehit" else "REGULAR_GW"
    selected_mode = mode or inferred_mode
    if selected_mode not in ("REGULAR_GW", "FREE_HIT"):
        raise CovarFplApiReplayAdapterError("mode must be REGULAR_GW or FREE_HIT")
    if active_chip == "freehit" and selected_mode != "FREE_HIT":
        raise CovarFplApiReplayAdapterError("a Free Hit chip cannot be normalized as REGULAR_GW")

    outcomes: dict[str, dict[str, Any]] = {}
    official_points: dict[str, float | int] = {}
    official_final_picks: list[dict[str, Any]] = []
    for position, pid, pick in ordered_picks:
        stats = live_stats[pid]
        played = played_from_official_element_stats(stats)
        outcomes[pid] = {
            "minutes": stats["minutes"],
            "played": played,
            "fpl_points": stats["total_points"],
        }
        official_points[pid] = stats["total_points"]
        official_final_picks.append({
            "element": pid,
            "position": position,
            "multiplier": int(pick["multiplier"]),
            "is_captain": pick["is_captain"],
            "is_vice_captain": pick["is_vice_captain"],
        })

    return {
        "replay_id": f"gw{event}-official-replay",
        "mode": selected_mode,
        "lineup": {
            "player_ids": player_ids,
            "starting_player_ids": starting,
            "starting_goalkeeper_id": next(pid for pid in starting if positions[pid] == "GK"),
            "reserve_goalkeeper_id": reserve_gk,
            "bench_order": bench,
            "player_positions": positions,
            "captain_id": captain_ids[0],
            "vice_captain_id": vice_ids[0],
            "active_chip": active_chip,
        },
        "player_outcomes": outcomes,
        "official_final": {
            "picks": official_final_picks,
            "player_total_points": official_points,
        },
    }
