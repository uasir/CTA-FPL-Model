#!/usr/bin/env python3
"""Stress-test CoVar's lineup resolver on public Overall-league manager replays.

Manager IDs, names and ranks are used only in memory to sample public Overall
league pages. The report contains aggregate counts only; no manager picks,
entry IDs, names, exact ranks or individual lineups are retained.
This is a resolver stress-test, not a representative field estimate.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import stat
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from m4_covar_fpl_api_replay_adapter import (
    CovarFplApiReplayAdapterError,
    normalize_official_fpl_replay,
)
from m4_covar_fpl_api_replay_fetch import (
    BASE_URL,
    OfficialFplFetchError,
    fetch_official_json,
)
from m4_covar_fpl_replay_validation import (
    CovarFplReplayError,
    validate_official_replay_case,
)


# Keep the cohort and event window bounded to avoid excessive public API requests.
OVERALL_LEAGUE_ID = 314


class PublicFieldReplayAuditError(ValueError):
    """Raised when the public cohort replay sample cannot be safely audited."""


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise PublicFieldReplayAuditError(f"{label} must be a positive integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise PublicFieldReplayAuditError(f"{label} must be a positive integer") from exc
    if number < 1 or str(value).strip() not in (str(number), f"{number}.0"):
        raise PublicFieldReplayAuditError(f"{label} must be a positive integer")
    return number


def sample_public_entries(
    page_payloads: Mapping[int, Mapping[str, Any]],
    *,
    rank_pages: Sequence[int],
    sample_positions: Sequence[int] = (0, 10, 20, 30, 40),
) -> list[dict[str, int]]:
    """Select deterministic public entries from separated Overall-league pages."""
    if not rank_pages or len(set(rank_pages)) != len(rank_pages):
        raise PublicFieldReplayAuditError("rank_pages must be non-empty and unique")
    if not sample_positions or len(set(sample_positions)) != len(sample_positions):
        raise PublicFieldReplayAuditError("sample_positions must be non-empty and unique")
    if any(isinstance(pos, bool) or not isinstance(pos, int) or pos < 0 for pos in sample_positions):
        raise PublicFieldReplayAuditError("sample_positions must be zero-based non-negative integers")

    selected: list[dict[str, int]] = []
    seen_entries: set[int] = set()
    for page in rank_pages:
        page_id = _positive_int(page, "rank page")
        payload = page_payloads.get(page_id)
        if not isinstance(payload, Mapping):
            raise PublicFieldReplayAuditError(f"Overall league page {page_id} is missing")
        standings = payload.get("standings")
        rows = standings.get("results") if isinstance(standings, Mapping) else None
        if not isinstance(rows, list) or not rows:
            raise PublicFieldReplayAuditError(f"Overall league page {page_id} has no standings")
        for position in sample_positions:
            if position >= len(rows):
                continue
            row = rows[position]
            if not isinstance(row, Mapping):
                raise PublicFieldReplayAuditError("Overall league standings row must be an object")
            entry_id = _positive_int(row.get("entry"), "standings entry")
            _positive_int(row.get("rank"), "standings rank")
            if entry_id in seen_entries:
                continue
            seen_entries.add(entry_id)
            selected.append({"entry_id": entry_id, "rank_page": page_id})
    if not selected:
        raise PublicFieldReplayAuditError("no public Overall-league managers were selected")
    return selected


def _capture_failure_code(exc: Exception) -> str:
    """Classify capture failures without retaining player or manager identifiers."""
    message = str(exc).lower()
    patterns = (
        ("captain and vice-captain must be in the reconstructed deadline starting xi", "CAPTAIN_OR_VICE_NOT_STARTING"),
        ("starting xi does not satisfy legal fpl formation", "ILLEGAL_STARTING_FORMATION"),
        ("position 12 must be the reserve goalkeeper", "RESERVE_GOALKEEPER_POSITION_INVALID"),
        ("starting xi must contain exactly one goalkeeper", "STARTING_GOALKEEPER_COUNT_INVALID"),
        ("captain and vice-captain must be distinct starting xi players", "CAPTAINCY_SELECTION_INVALID"),
        ("official picks must identify one distinct captain and vice-captain", "OFFICIAL_CAPTAINCY_FLAGS_INVALID"),
        ("official captain does not match submitted lineup captain", "CAPTAIN_ID_MISMATCH"),
        ("official vice-captain does not match submitted lineup vice-captain", "VICE_CAPTAIN_ID_MISMATCH"),
        ("picks must have unique player ids and positions", "PICK_ORDER_OR_ID_INVALID"),
        ("missing from bootstrap metadata", "PLAYER_BOOTSTRAP_METADATA_MISSING"),
        ("missing from event live data", "PLAYER_EVENT_LIVE_DATA_MISSING"),
    )
    for phrase, code in patterns:
        if phrase in message:
            return code
    if isinstance(exc, OfficialFplFetchError):
        return "OFFICIAL_API_FETCH_FAILURE"
    if isinstance(exc, CovarFplApiReplayAdapterError):
        return "ADAPTER_VALIDATION_OTHER"
    if isinstance(exc, CovarFplReplayError):
        return "REPLAY_VALIDATION_OTHER"
    return "UNCLASSIFIED_CAPTURE_FAILURE"


def _autosub_pair_diagnostic(
    case: Mapping[str, Any], result: Mapping[str, Any], *, event_id: int, rank_page: int
) -> dict[str, Any] | None:
    """Summarize pair mismatches by lineup position/role without exposing a roster."""
    mismatches = result.get("mismatched_automatic_substitutions") or []
    if not mismatches:
        return None
    lineup = case["lineup"]
    positions = {str(pid): index + 1 for index, pid in enumerate(lineup["player_ids"])}
    roles = {str(pid): str(role) for pid, role in lineup["player_positions"].items()}

    def describe(pairs: Sequence[Sequence[str]]) -> list[dict[str, Any]]:
        rows = []
        for incoming, outgoing in pairs:
            incoming, outgoing = str(incoming), str(outgoing)
            rows.append({
                "incoming_original_position": positions.get(incoming),
                "incoming_role": roles.get(incoming),
                "outgoing_original_position": positions.get(outgoing),
                "outgoing_role": roles.get(outgoing),
            })
        return sorted(rows, key=lambda row: (
            row["incoming_original_position"] or 0,
            row["outgoing_original_position"] or 0,
        ))

    first = mismatches[0]
    resolver_pairs = first.get("resolver_pairs", [])
    api_pairs = first.get("api_metadata_pairs", [])
    resolver_in = {str(pair[0]) for pair in resolver_pairs}
    resolver_out = {str(pair[1]) for pair in resolver_pairs}
    api_in = {str(pair[0]) for pair in api_pairs}
    api_out = {str(pair[1]) for pair in api_pairs}
    return {
        "event_id": event_id,
        "rank_page": rank_page,
        "resolver_pairs_by_position": describe(resolver_pairs),
        "api_pairs_by_position": describe(api_pairs),
        "same_incoming_player_set": resolver_in == api_in,
        "same_outgoing_player_set": resolver_out == api_out,
        "same_pair_count": len(resolver_pairs) == len(api_pairs),
        "final_multiplier_match": result.get("official_multiplier_match"),
        "team_points_reconcile": result.get("official_team_points_reconcile"),
        "non_scoring_target_ambiguity": result.get("non_scoring_substitution_target_ambiguity", False),
    }


def audit_public_field_replays(
    event_ids: Sequence[int],
    *,
    rank_pages: Sequence[int] = (1, 200, 2000, 20000, 100000),
    sample_positions: Sequence[int] = (4, 24, 44),
    fetch: Callable[[str], dict[str, Any]] = fetch_official_json,
    sleep: Callable[[float], None] = time.sleep,
    min_replays: int = 25,
) -> dict[str, Any]:
    if not event_ids or any(isinstance(event, bool) or not isinstance(event, int) or event < 1 for event in event_ids):
        raise ValueError("event_ids must be a non-empty list of positive integers")
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("event_ids must be unique")
    if isinstance(min_replays, bool) or min_replays < 1:
        raise ValueError("min_replays must be a positive integer")

    bootstrap = fetch(f"{BASE_URL}/bootstrap-static/")
    official_events = bootstrap.get("events")
    if not isinstance(official_events, list):
        raise OfficialFplFetchError("bootstrap event status is missing")
    event_status: dict[int, list[Mapping[str, Any]]] = {}
    for row in official_events:
        if isinstance(row, Mapping) and isinstance(row.get("id"), int) and not isinstance(row.get("id"), bool):
            event_status.setdefault(row["id"], []).append(row)

    page_payloads: dict[int, Mapping[str, Any]] = {}
    for page in rank_pages:
        page_id = _positive_int(page, "rank page")
        page_payloads[page_id] = fetch(
            f"{BASE_URL}/leagues-classic/{OVERALL_LEAGUE_ID}/standings/?page_standings={page_id}"
        )
        sleep(0.25)
    managers = sample_public_entries(
        page_payloads, rank_pages=rank_pages, sample_positions=sample_positions
    )

    replay_count = 0
    passed_count = 0
    mismatch_count = 0
    capture_failures: list[dict[str, Any]] = []
    skipped_events: list[int] = []
    by_event: dict[str, dict[str, int]] = {}
    by_rank_page: dict[str, int] = {}
    by_chip: dict[str, int] = {}
    autosub_replays = 0
    autosub_players = 0
    goalkeeper_autosubs = 0
    outfield_autosubs = 0
    captain_fallbacks = 0
    team_points_cases = 0
    team_points_failures = 0
    validation_failure_types: dict[str, int] = {}
    capture_failure_types: dict[str, int] = {}
    autosub_metadata_mismatch_replays = 0
    autosub_player_set_mismatch_replays = 0
    autosub_target_ambiguity_replays = 0
    autosub_pair_mismatch_diagnostics: list[dict[str, Any]] = []

    for event in event_ids:
        matching = event_status.get(event, [])
        if len(matching) != 1:
            capture_failures.append({"event_id": event, "failure_type": "BOOTSTRAP_EVENT_MISSING_OR_DUPLICATED"})
            continue
        if matching[0].get("finished") is not True or matching[0].get("data_checked") is not True:
            skipped_events.append(event)
            continue
        try:
            live = fetch(f"{BASE_URL}/event/{event}/live/")
        except OfficialFplFetchError:
            capture_failures.append({"event_id": event, "failure_type": "EVENT_LIVE_FETCH_FAILED"})
            continue
        sleep(0.25)
        event_summary = by_event.setdefault(
            str(event),
            {"replay_count": 0, "passed_count": 0, "failed_count": 0, "autosub_replays": 0},
        )

        for manager in managers:
            entry_id = manager["entry_id"]
            rank_page = manager["rank_page"]
            try:
                picks = fetch(f"{BASE_URL}/entry/{entry_id}/event/{event}/picks/")
                sleep(0.25)
                case = normalize_official_fpl_replay(
                    picks, live, bootstrap, event_id=event, expected_entry_id=entry_id
                )
                result = validate_official_replay_case(case)
            except (OfficialFplFetchError, CovarFplApiReplayAdapterError, CovarFplReplayError, ValueError) as exc:
                capture_failures.append({
                    "event_id": event,
                    "rank_page": rank_page,
                    "failure_type": type(exc).__name__,
                    "failure_code": _capture_failure_code(exc),
                })
                code = _capture_failure_code(exc)
                capture_failure_types[code] = capture_failure_types.get(code, 0) + 1
                continue

            replay_count += 1
            event_summary["replay_count"] += 1
            by_rank_page[str(rank_page)] = by_rank_page.get(str(rank_page), 0) + 1
            chip = str(case["lineup"].get("active_chip") or "NONE")
            by_chip[chip] = by_chip.get(chip, 0) + 1
            if result["status"] == "PASS":
                passed_count += 1
                event_summary["passed_count"] += 1
            else:
                mismatch_count += 1
                event_summary["failed_count"] += 1
                if not result["official_scoring_equivalence_match"]:
                    validation_failure_types["PICK_MULTIPLIER_MISMATCH"] = validation_failure_types.get("PICK_MULTIPLIER_MISMATCH", 0) + 1
                if not result["player_points_match"]:
                    validation_failure_types["PLAYER_POINTS_MISMATCH"] = validation_failure_types.get("PLAYER_POINTS_MISMATCH", 0) + 1
                if not result["active_captain_match"]:
                    validation_failure_types["CAPTAIN_MISMATCH"] = validation_failure_types.get("CAPTAIN_MISMATCH", 0) + 1
                if (
                    result.get("automatic_substitution_player_sets_match") is False
                    and not result.get("non_scoring_substitution_target_ambiguity")
                ):
                    validation_failure_types["AUTOSUB_PLAYER_SET_MISMATCH"] = validation_failure_types.get("AUTOSUB_PLAYER_SET_MISMATCH", 0) + 1
                if result["official_team_points_reconcile"] is False:
                    validation_failure_types["TEAM_POINTS_MISMATCH"] = validation_failure_types.get("TEAM_POINTS_MISMATCH", 0) + 1

            if result.get("automatic_substitution_metadata_match") is False:
                autosub_metadata_mismatch_replays += 1
                diagnostic = _autosub_pair_diagnostic(
                    case, result, event_id=event, rank_page=rank_page
                )
                if diagnostic is not None:
                    autosub_pair_mismatch_diagnostics.append(diagnostic)
            if result["official_team_points_reconcile"] is not None:
                team_points_cases += 1
                team_points_failures += int(result["official_team_points_reconcile"] is False)
            if result["resolver_active_captain_id"] == case["lineup"]["vice_captain_id"]:
                captain_fallbacks += 1

            # After reversing official automatic_subs, original bench positions
            # are restored while final scoring multipliers remain attached.
            bench_picks = [row for row in case["official_final"]["picks"] if int(row["position"]) > 11]
            actual_autosubs = (
                [row for row in bench_picks if int(row["multiplier"]) > 0]
                if chip != "bboost" else []
            )
            if actual_autosubs:
                autosub_replays += 1
                event_summary["autosub_replays"] += 1
                autosub_players += len(actual_autosubs)
                goalkeeper_autosubs += sum(int(row["position"]) == 12 for row in actual_autosubs)
                outfield_autosubs += sum(int(row["position"]) > 12 for row in actual_autosubs)

    if replay_count < min_replays:
        raise OfficialFplFetchError(
            f"only {replay_count} public manager-Gameweek replays captured; minimum required is {min_replays}"
        )

    return {
        "schema_version": "1.0.0",
        "status": "PASS" if mismatch_count == 0 and not capture_failures else ("PARTIAL" if mismatch_count == 0 else "FAIL"),
        "validation_status": "PASS" if mismatch_count == 0 else "FAIL",
        "capture_status": "PASS" if not capture_failures else "PARTIAL",
        "league_source": "OFFICIAL_FPL_OVERALL_CLASSIC_LEAGUE",
        "rank_pages_sampled": list(rank_pages),
        "sample_positions_per_page": list(sample_positions),
        "sampled_manager_count": len(managers),
        "gameweek_count": len([key for key in by_event if key not in {str(x) for x in skipped_events}]),
        "requested_event_ids": list(event_ids),
        "audited_event_ids": sorted(int(key) for key in by_event),
        "skipped_unfinalized_event_ids": skipped_events,
        "replay_count": replay_count,
        "passed_count": passed_count,
        "failed_count": mismatch_count,
        "capture_failure_count": len(capture_failures),
        "capture_failure_types": capture_failure_types,
        "by_gameweek": by_event,
        "by_rank_page_replay_count": by_rank_page,
        "by_chip": by_chip,
        "autosub_replay_count": autosub_replays,
        "autosub_player_count": autosub_players,
        "automatic_substitution_metadata_mismatch_replays": autosub_metadata_mismatch_replays,
        "automatic_substitution_player_set_mismatch_replays": autosub_player_set_mismatch_replays,
        "non_scoring_substitution_target_ambiguity_replays": autosub_target_ambiguity_replays,
        "autosub_pair_mismatch_diagnostics": autosub_pair_mismatch_diagnostics,
        "goalkeeper_autosub_count": goalkeeper_autosubs,
        "outfield_autosub_count": outfield_autosubs,
        "captain_fallback_count": captain_fallbacks,
        "team_points_reconciliation_cases": team_points_cases,
        "team_points_reconciliation_failures": team_points_failures,
        "validation_failure_types": validation_failure_types,
        "capture_failures": capture_failures,
        "manager_entry_ids_retained": False,
        "manager_names_retained": False,
        "exact_ranks_retained": False,
        "raw_manager_picks_retained": False,
        "privacy_note": "Public manager IDs, names, ranks and picks were used only in memory; only aggregate validation counts are emitted. This is not a representative field estimate.",
        "decision_weight": 0.0,
        "production_eligible": False,
    }


def write_report(report: Mapping[str, Any], output: Path) -> Path:
    if not output.is_absolute():
        raise ValueError("output must be absolute")
    target = output.resolve()
    repository_root = Path(__file__).resolve().parents[3]
    if target.is_relative_to(repository_root):
        raise ValueError("output must be outside the repository")
    if target.exists():
        raise FileExistsError("refusing to overwrite existing report")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", required=True)
    parser.add_argument("--rank-pages", default="1,200,2000,20000,100000")
    parser.add_argument("--sample-positions", default="0,10,20,30,40")
    parser.add_argument("--min-replays", type=int, default=25)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    events = [int(value) for value in args.events.split(",")]
    pages = [int(value) for value in args.rank_pages.split(",")]
    positions = [int(value) for value in args.sample_positions.split(",")]
    report = audit_public_field_replays(
        events, rank_pages=pages, sample_positions=positions,
        min_replays=args.min_replays,
    )
    target = write_report(report, args.output)
    print(json.dumps({
        "status": report["status"],
        "validation_status": report["validation_status"],
        "capture_status": report["capture_status"],
        "sampled_manager_count": report["sampled_manager_count"],
        "replay_count": report["replay_count"],
        "passed_count": report["passed_count"],
        "failed_count": report["failed_count"],
        "capture_failure_count": report["capture_failure_count"],
        "autosub_replay_count": report["autosub_replay_count"],
        "autosub_player_count": report["autosub_player_count"],
        "automatic_substitution_metadata_mismatch_replays": report["automatic_substitution_metadata_mismatch_replays"],
        "automatic_substitution_player_set_mismatch_replays": report["automatic_substitution_player_set_mismatch_replays"],
        "non_scoring_substitution_target_ambiguity_replays": report["non_scoring_substitution_target_ambiguity_replays"],
        "goalkeeper_autosub_count": report["goalkeeper_autosub_count"],
        "outfield_autosub_count": report["outfield_autosub_count"],
        "captain_fallback_count": report["captain_fallback_count"],
        "team_points_reconciliation_cases": report["team_points_reconciliation_cases"],
        "team_points_reconciliation_failures": report["team_points_reconciliation_failures"],
        "output": str(target),
        "manager_entry_ids_retained": False,
        "manager_names_retained": False,
        "exact_ranks_retained": False,
        "raw_manager_picks_retained": False,
        "decision_weight": 0.0,
        "production_eligible": False,
    }, indent=2))
    return 0 if report["validation_status"] == "PASS" and report["replay_count"] >= args.min_replays else 1


if __name__ == "__main__":
    raise SystemExit(main())
