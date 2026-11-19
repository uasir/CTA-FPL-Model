#!/usr/bin/env python3
"""Normalize Wyscout EPL events into CTA's provider-neutral event schema.

Possession IDs are inferred from event state and Wyscout duel outcome tags
(lost/neutral/won), never presented as provider supplied. These segments remain
provisional pending manual review. Wyscout player IDs remain namespaced; coordinates are converted from
attacking-team-relative percentages to the CTA 120x80 pitch. Missing recipient,
pressure, xG and other unsupported fields remain absent.
"""
from __future__ import annotations

import argparse
import json
import zipfile
from collections import Counter
from pathlib import Path

PERIODS = {"1H": 1, "2H": 2, "E1": 3, "E2": 4, "P": 5}
ACCURATE_TAG = 1801
INACCURATE_TAG = 1802
DUEL_LOST_TAG = 701
DUEL_NEUTRAL_TAG = 702
DUEL_WON_TAG = 703
RESTART_EVENTS = {"Free Kick", "Corner", "Throw in", "Goal kick", "Penalty"}


def _tags(event):
    return {int(t["id"]) for t in event.get("tags", [])
            if isinstance(t, dict) and t.get("id") is not None}


def _coord(position):
    if not isinstance(position, dict):
        return None
    try:
        x, y = float(position["x"]), float(position["y"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (0 <= x <= 100 and 0 <= y <= 100):
        return None
    return [round(x * 1.2, 6), round(y * 0.8, 6)]


def _period(event):
    raw = str(event.get("matchPeriod") or "").upper()
    if raw not in PERIODS:
        raise ValueError(f"Unsupported or missing Wyscout matchPeriod: {raw!r}")
    return PERIODS[raw]


def normalize_wyscout_events(events, players, teams, match_id):
    player_names = {
        str(p["wyId"]): str(p.get("shortName") or " ".join(
            x for x in (p.get("firstName"), p.get("lastName")) if x))
        for p in players if p.get("wyId") is not None
    }
    team_names = {
        str(t["wyId"]): str(t.get("name") or t.get("officialName") or "")
        for t in teams if t.get("wyId") is not None
    }
    ordered = sorted(enumerate(events), key=lambda pair: (
        _period(pair[1]), float(pair[1].get("eventSec") or 0),
        int(pair[1].get("id") or pair[0]), pair[0]))
    normalized = []
    skipped = {"missing_team": 0, "unmapped_event_type": 0}
    actor_quality = {"missing_player_id": 0, "unresolved_player_metadata": 0}
    boundary_counts = Counter()
    duel_outcome_counts = Counter()
    match_team_ids = sorted({
        str(event.get("teamId")) for event in events if event.get("teamId") is not None
    })
    opponent_by_team = (
        {match_team_ids[0]: match_team_ids[1], match_team_ids[1]: match_team_ids[0]}
        if len(match_team_ids) == 2 else {}
    )
    current_possession_team = None
    current_period = None
    possession = 0
    pending_dead_ball = False
    pending_after_shot = False

    for source_index, event in ordered:
        period = _period(event)
        team_id = event.get("teamId")
        player_id = event.get("playerId")
        if team_id is None:
            skipped["missing_team"] += 1
            continue
        team_key = str(team_id)
        if team_key not in team_names:
            skipped["missing_team"] += 1
            continue
        actor = None
        if player_id is None or str(player_id).strip() in {"", "0"}:
            actor_quality["missing_player_id"] += 1
        else:
            provider_player_id = str(player_id)
            actor_name = player_names.get(provider_player_id, "")
            if not actor_name:
                actor_quality["unresolved_player_metadata"] += 1
            actor = {"id": f"wyscout:{provider_player_id}", "name": actor_name}

        event_name = str(event.get("eventName") or "")
        sub_event_name = str(event.get("subEventName") or "")
        tags = _tags(event)
        if event_name == "Duel":
            if DUEL_LOST_TAG in tags:
                duel_outcome_counts["lost"] += 1
            if DUEL_NEUTRAL_TAG in tags:
                duel_outcome_counts["neutral"] += 1
            if DUEL_WON_TAG in tags:
                duel_outcome_counts["won"] += 1
        if event_name not in {"Pass", "Shot", "Others on the ball", "Duel",
                              "Foul", "Offside", "Free Kick", "Corner", "Throw in",
                              "Goal kick", "Penalty", "Save attempt",
                              "Interruption", "Goalkeeper leaving line"}:
            skipped["unmapped_event_type"] += 1
            continue

        is_free_kick_shot = event_name == "Free Kick" and sub_event_name.casefold() == "free kick shot"
        is_restart = event_name in RESTART_EVENTS
        switch_after_event_to = None
        boundary_reason = None

        if current_possession_team is None:
            initial_team = (
                opponent_by_team.get(team_key, team_key)
                if event_name == "Duel" and DUEL_LOST_TAG in tags else team_key
            )
            current_possession_team = initial_team
            possession += 1
            boundary_reason = "match_start"
        elif period != current_period:
            possession += 1
            current_possession_team = team_key
            pending_dead_ball = False
            pending_after_shot = False
            boundary_reason = "period_change"
        elif is_restart:
            possession += 1
            current_possession_team = team_key
            pending_dead_ball = False
            pending_after_shot = False
            boundary_reason = "restart_event"
        elif not pending_dead_ball and event_name == "Duel":
            if DUEL_WON_TAG in tags and team_key != current_possession_team:
                possession += 1
                current_possession_team = team_key
                boundary_reason = "duel_won"
            elif DUEL_LOST_TAG in tags and team_key == current_possession_team:
                switch_after_event_to = opponent_by_team.get(team_key)
        elif not pending_dead_ball and event_name not in {"Foul", "Offside", "Interruption", "Duel"}:
            if pending_after_shot and event_name in {"Save attempt", "Goalkeeper leaving line"}:
                if team_key != current_possession_team:
                    possession += 1
                    current_possession_team = team_key
                    boundary_reason = "after_shot_control"
                pending_after_shot = False
            elif team_key != current_possession_team:
                possession += 1
                current_possession_team = team_key
                boundary_reason = "controlled_team_change"
            elif pending_after_shot:
                pending_after_shot = False

        if boundary_reason:
            boundary_counts[boundary_reason] += 1
        current_period = period

        positions = event.get("positions") or []
        start = _coord(positions[0]) if positions else None
        end = _coord(positions[1]) if len(positions) > 1 else None
        if event_name == "Pass":
            kind = "Pass"
        elif event_name == "Shot" or is_free_kick_shot:
            kind = "Shot"
        elif event_name == "Others on the ball" and "acceleration" in str(event.get("subEventName") or "").casefold() and end is not None:
            kind = "Carry"
        else:
            kind = event_name

        row = {
            "id": str(event.get("id", source_index)),
            "_match_id": str(match_id),
            "_event_index": len(normalized),
            "type": {"name": kind},
            "team": {"name": team_names[team_key]},
            "possession_team": {"name": team_names[current_possession_team]},
            "possession": possession,
            "period": period,
            "minute": int(float(event.get("eventSec") or 0) // 60),
            "second": round(float(event.get("eventSec") or 0) % 60, 3),
            "location": start,
            "_provider": "Wyscout",
            "_provider_player_id": str(player_id),
            "_provider_match_id": str(match_id),
            "_provider_subevent_name": sub_event_name,
            "_possession_id_status": "INFERRED_EVENT_STATE_WITH_DUEL_OUTCOME_TAGS",
        }
        if actor is not None:
            row["player"] = actor
        if kind == "Pass":
            pass_data = {}
            if end is not None:
                pass_data["end_location"] = end
            if ACCURATE_TAG not in tags:
                # CTA's StatsBomb adapter treats absent outcome as completed.
                # Unknown and inaccurate passes must therefore be non-completed.
                pass_data["outcome"] = {"name": "Inaccurate" if INACCURATE_TAG in tags else "Unknown"}
            row["pass"] = pass_data
        elif kind == "Carry" and end is not None:
            row["carry"] = {"end_location": end}
        elif kind == "Shot":
            row["shot"] = {"outcome": {"name": "Goal" if 101 in tags else "Unknown"}}
        normalized.append(row)

        if switch_after_event_to is not None:
            possession += 1
            current_possession_team = switch_after_event_to
            boundary_counts["duel_lost"] += 1
        if event_name in {"Foul", "Offside", "Interruption"}:
            pending_dead_ball = True
            pending_after_shot = False
        elif kind == "Shot":
            pending_after_shot = True
        else:
            pending_after_shot = False

    report = {
        "status": "PASS_WYSCOUT_EVENTS_NORMALIZED" if normalized else "NO_NORMALIZED_EVENTS",
        "provider": "Wyscout",
        "provider_match_id": str(match_id),
        "normalized_event_count": len(normalized),
        "skipped_event_counts": skipped,
        "actor_quality_counts": actor_quality,
        "possession_boundary_reason_counts": dict(boundary_counts),
        "duel_outcome_tag_counts": dict(duel_outcome_counts),
        "free_kick_shots_mapped_to_shot": sum(
            row.get("_provider_subevent_name", "").casefold() == "free kick shot"
            and row["type"]["name"] == "Shot" for row in normalized
        ),
        "player_id_namespace": "wyscout: prefix retained; never interpreted as StatsBomb or FPL ID",
        "coordinate_conversion": "attacking-relative percentage x,y -> CTA pitch x*1.2,y*0.8; no direction flip",
        "possession_method": "INFERRED_EVENT_STATE_WITH_DUEL_OUTCOME_TAGS",
        "possession_boundary_policy": "period changes, restarts, controlled-action team changes, duel won/lost tags; fouls/offsides/interruptions pause possession changes",
        "limitations": [
            "Wyscout does not supply possession IDs in this public event schema; segments are inferred from event state and duel outcome tags and remain provisional.",
            "No pass recipient, pressure flag, StatsBomb xG or 360 context is synthesized.",
            "Unknown pass accuracy is marked non-completed rather than assumed completed.",
            "Provider player IDs remain Wyscout-namespaced and require a verified season-specific FPL crosswalk before FPL joins."
        ]
    }
    return normalized, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path)
    parser.add_argument("--events-zip", type=Path)
    parser.add_argument("--players", type=Path, required=True)
    parser.add_argument("--teams", type=Path, required=True)
    parser.add_argument("--match-id")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if bool(args.events) == bool(args.events_zip):
        parser.error("provide exactly one of --events or --events-zip")
    if args.events:
        events = json.loads(args.events.read_text())
    else:
        with zipfile.ZipFile(args.events_zip) as archive:
            members = [name for name in archive.namelist()
                       if Path(name).name.lower().startswith("events_england")]
            if len(members) != 1:
                raise ValueError(f"Expected one events_England JSON in archive; found {members[:5]}")
            with archive.open(members[0]) as handle:
                events = json.load(handle)
    players = json.loads(args.players.read_text())
    teams = json.loads(args.teams.read_text())
    if args.match_id:
        normalized, report = normalize_wyscout_events(events, players, teams, args.match_id)
        report["match_count"] = 1
    else:
        grouped = {}
        for event in events:
            if event.get("matchId") is not None:
                grouped.setdefault(str(event["matchId"]), []).append(event)
        normalized = []
        skipped = Counter()
        actor_quality = Counter()
        boundary_counts = Counter()
        duel_outcome_counts = Counter()
        match_reports = []
        for match_id, match_events in sorted(grouped.items()):
            rows, match_report = normalize_wyscout_events(match_events, players, teams, match_id)
            normalized.extend(rows)
            skipped.update(match_report["skipped_event_counts"])
            actor_quality.update(match_report["actor_quality_counts"])
            boundary_counts.update(match_report["possession_boundary_reason_counts"])
            duel_outcome_counts.update(match_report["duel_outcome_tag_counts"])
            match_reports.append(match_report)
        report = {
            "status": "PASS_WYSCOUT_EVENTS_NORMALIZED" if normalized else "NO_NORMALIZED_EVENTS",
            "provider": "Wyscout",
            "match_count": len(grouped),
            "normalized_event_count": len(normalized),
            "skipped_event_counts": dict(skipped),
            "actor_quality_counts": dict(actor_quality),
            "possession_boundary_reason_counts": dict(boundary_counts),
            "duel_outcome_tag_counts": dict(duel_outcome_counts),
            "player_id_namespace": "wyscout: prefix retained; never interpreted as StatsBomb or FPL ID",
            "coordinate_conversion": "attacking-relative percentage x,y -> CTA pitch x*1.2,y*0.8; no direction flip",
            "possession_method": "INFERRED_EVENT_STATE_WITH_DUEL_OUTCOME_TAGS",
            "possession_boundary_policy": "period changes, restarts, controlled-action team changes, duel won/lost tags; fouls/offsides/interruptions pause possession changes",
            "limitations": match_reports[0]["limitations"] if match_reports else [],
        }
    type_counts = Counter(row["type"]["name"] for row in normalized)
    possession_keys = {(row["_match_id"], row["period"], row["possession"]) for row in normalized}
    report.update({
        "source_event_count": len(events),
        "event_coverage_pct": round(100 * len(normalized) / len(events), 4) if events else None,
        "unique_inferred_possessions": len(possession_keys),
        "normalized_event_type_counts": dict(sorted(type_counts.items())),
        "events_missing_start_location": sum(row.get("location") is None for row in normalized),
        "pass_or_carry_events_missing_end_location": sum(
            row["type"]["name"] in {"Pass", "Carry"}
            and not (row.get("pass") or row.get("carry") or {}).get("end_location")
            for row in normalized
        ),
        "free_kick_shots_mapped_to_shot": sum(
            row.get("_provider_subevent_name", "").casefold() == "free kick shot"
            and row["type"]["name"] == "Shot" for row in normalized
        ),
    })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(normalized, separators=(",", ":")))
    args.report.write_text(json.dumps(report, indent=2))
    print(json.dumps({key: value for key, value in report.items()
                      if key != "per_match_reports"}, indent=2))


if __name__ == "__main__":
    main()
