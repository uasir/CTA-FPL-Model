#!/usr/bin/env python3
"""Normalize Wyscout EPL events into CTA's provider-neutral event schema.

Possession IDs are inferred, never presented as provider supplied. Wyscout
player IDs remain namespaced as Wyscout IDs; coordinates are converted from
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
    skipped = {"missing_team": 0, "missing_player": 0, "unmapped_event_type": 0}
    current_team = None
    current_period = None
    possession = 0
    previous_event_name = None

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
        if player_id is None or str(player_id) not in player_names:
            skipped["missing_player"] += 1
            continue

        event_name = str(event.get("eventName") or "")
        if event_name not in {"Pass", "Shot", "Others on the ball", "Duel",
                              "Foul", "Offside", "Free Kick", "Corner", "Throw in",
                              "Goal kick", "Penalty", "Save attempt",
                              "Interruption", "Goalkeeper leaving line"}:
            skipped["unmapped_event_type"] += 1
            continue

        boundary = (
            current_team is None or period != current_period
            or team_key != current_team or event_name in RESTART_EVENTS
            or previous_event_name in {"Shot", "Offside", "Foul", "Interruption"}
        )
        if boundary:
            possession += 1
        current_team, current_period = team_key, period
        previous_event_name = event_name

        positions = event.get("positions") or []
        start = _coord(positions[0]) if positions else None
        end = _coord(positions[1]) if len(positions) > 1 else None
        tags = _tags(event)
        if event_name == "Pass":
            kind = "Pass"
        elif event_name == "Shot":
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
            "player": {"id": f"wyscout:{player_id}", "name": player_names[str(player_id)]},
            "team": {"name": team_names[team_key]},
            "possession_team": {"name": team_names[team_key]},
            "possession": possession,
            "period": period,
            "minute": int(float(event.get("eventSec") or 0) // 60),
            "second": round(float(event.get("eventSec") or 0) % 60, 3),
            "location": start,
            "_provider": "Wyscout",
            "_provider_player_id": str(player_id),
            "_provider_match_id": str(match_id),
            "_possession_id_status": "INFERRED_CONTIGUOUS_TEAM_BLOCK",
        }
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

    report = {
        "status": "PASS_WYSCOUT_EVENTS_NORMALIZED" if normalized else "NO_NORMALIZED_EVENTS",
        "provider": "Wyscout",
        "provider_match_id": str(match_id),
        "normalized_event_count": len(normalized),
        "skipped_event_counts": skipped,
        "player_id_namespace": "wyscout: prefix retained; never interpreted as StatsBomb or FPL ID",
        "coordinate_conversion": "attacking-relative percentage x,y -> CTA pitch x*1.2,y*0.8; no direction flip",
        "possession_method": "INFERRED_CONTIGUOUS_TEAM_BLOCK",
        "possession_boundary_policy": "period/team changes, restarts, and after shot/offside/foul/interruption",
        "limitations": [
            "Wyscout does not supply possession IDs in this public event schema; inferred segments are provisional.",
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
        match_reports = []
        for match_id, match_events in sorted(grouped.items()):
            rows, match_report = normalize_wyscout_events(match_events, players, teams, match_id)
            normalized.extend(rows)
            skipped.update(match_report["skipped_event_counts"])
            match_reports.append(match_report)
        report = {
            "status": "PASS_WYSCOUT_EVENTS_NORMALIZED" if normalized else "NO_NORMALIZED_EVENTS",
            "provider": "Wyscout",
            "match_count": len(grouped),
            "normalized_event_count": len(normalized),
            "skipped_event_counts": dict(skipped),
            "player_id_namespace": "wyscout: prefix retained; never interpreted as StatsBomb or FPL ID",
            "coordinate_conversion": "attacking-relative percentage x,y -> CTA pitch x*1.2,y*0.8; no direction flip",
            "possession_method": "INFERRED_CONTIGUOUS_TEAM_BLOCK",
            "possession_boundary_policy": "period/team changes, restarts, and after shot/offside/foul/interruption",
            "limitations": match_reports[0]["limitations"] if match_reports else [],
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(normalized, separators=(",", ":")))
    args.report.write_text(json.dumps(report, indent=2))
    print(json.dumps({key: value for key, value in report.items()
                      if key != "per_match_reports"}, indent=2))


if __name__ == "__main__":
    main()
