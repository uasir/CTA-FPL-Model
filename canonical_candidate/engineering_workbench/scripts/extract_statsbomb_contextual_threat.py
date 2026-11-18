#!/usr/bin/env python3
"""Extract auditable StatsBomb 360 contextual-threat features.

This is a research sidecar: it does not change the existing CTA core or claim
that any feature predicts FPL points. Missing 360 frames remain missing rather
than being interpreted as zero defensive pressure or zero surrounding players.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

PITCH_LENGTH = 120.0
PITCH_WIDTH = 80.0
GOAL = (120.0, 40.0)
SUPPORTED_TYPES = {"Pass", "Carry", "Shot", "Ball Receipt*", "Ball Receipt", "Dribble"}


def _point(value: Any):
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        x, y = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    return (x, y)


def _inside_pitch(point):
    return point is not None and 0 <= point[0] <= PITCH_LENGTH and 0 <= point[1] <= PITCH_WIDTH


def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _distance_to_segment(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    denom = dx * dx + dy * dy
    if denom == 0:
        return _distance(point, start)
    t = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / denom
    t = min(1.0, max(0.0, t))
    projection = (start[0] + t * dx, start[1] + t * dy)
    return _distance(point, projection)


def _event_type(event):
    return str((event.get("type") or {}).get("name") or "")


def _identity(event):
    player = event.get("player") or {}
    player_id = player.get("id")
    if player_id is None:
        return None
    return str(player_id), str(player.get("name") or "")


def _frame_map(frames):
    result = {}
    duplicates = []
    for frame in frames:
        event_uuid = str(frame.get("event_uuid") or "")
        if not event_uuid:
            continue
        if event_uuid in result:
            duplicates.append(event_uuid)
            continue
        result[event_uuid] = frame
    return result, duplicates


def contextual_event_features(event, frame):
    """Return one event's spatial context, or None when usable context is absent."""
    event_type = _event_type(event)
    if event_type not in SUPPORTED_TYPES or not frame:
        return None

    visible = frame.get("freeze_frame")
    if not isinstance(visible, list):
        return None

    # StatsBomb marks the acting player in 360. Prefer that observed position;
    # fall back to the event location only when the actor marker is absent.
    actor_position = None
    valid_players = []
    excluded_out_of_bounds = 0
    for item in visible:
        if not isinstance(item, dict):
            continue
        location = _point(item.get("location"))
        if location is None:
            continue
        if not _inside_pitch(location):
            excluded_out_of_bounds += 1
            continue
        player = {
            "location": location,
            "teammate": item.get("teammate"),
            "actor": bool(item.get("actor")),
            "keeper": bool(item.get("keeper")),
        }
        valid_players.append(player)
        if player["actor"]:
            actor_position = location

    if actor_position is None:
        actor_position = _point(event.get("location"))
    if not _inside_pitch(actor_position):
        return None

    opponents = [p for p in valid_players if p["teammate"] is False and not p["actor"]]
    teammates = [p for p in valid_players if p["teammate"] is True and not p["actor"]]
    opponent_distances = [_distance(actor_position, p["location"]) for p in opponents]
    goalkeeper_distances = [
        _distance(actor_position, p["location"]) for p in opponents if p["keeper"]
    ]

    # Count non-goalkeeper opponents occupying the direct ball-to-goal corridor.
    corridor_opponents = [
        p for p in opponents
        if not p["keeper"] and _distance_to_segment(p["location"], actor_position, GOAL) <= 5.0
    ]
    goal_side_opponents = [
        p for p in opponents
        if not p["keeper"]
        and p["location"][0] > actor_position[0]
        and abs(p["location"][1] - actor_position[1]) <= 12.0
    ]
    teammates_ahead = [
        p for p in teammates
        if p["location"][0] > actor_position[0] + 5.0
        and _distance(actor_position, p["location"]) <= 20.0
    ]
    opponents_ahead_lane = [
        _distance(actor_position, p["location"])
        for p in opponents
        if p["location"][0] > actor_position[0]
        and abs(p["location"][1] - actor_position[1]) <= 8.0
    ]

    return {
        "event_id": str(event.get("id") or ""),
        "event_type": event_type,
        "player_id": _identity(event)[0] if _identity(event) else "",
        "player_name": _identity(event)[1] if _identity(event) else "",
        "team_id": str((event.get("team") or {}).get("id") or ""),
        "team_name": str((event.get("team") or {}).get("name") or ""),
        "period": event.get("period"),
        "minute": event.get("minute"),
        "second": event.get("second"),
        "x": round(actor_position[0], 4),
        "y": round(actor_position[1], 4),
        "under_pressure": bool(event.get("under_pressure")),
        "visible_opponents": len(opponents),
        "visible_teammates": len(teammates),
        "opponents_within_5": sum(d <= 5.0 for d in opponent_distances),
        "opponents_within_10": sum(d <= 10.0 for d in opponent_distances),
        "nearest_opponent_distance": round(min(opponent_distances), 4) if opponent_distances else "",
        "goalkeeper_distance": round(min(goalkeeper_distances), 4) if goalkeeper_distances else "",
        "goal_corridor_opponents_5m": len(corridor_opponents),
        "goal_side_opponents_12m": len(goal_side_opponents),
        "teammates_ahead_within_20": len(teammates_ahead),
        "nearest_opponent_ahead_lane_distance": (
            round(min(opponents_ahead_lane), 4) if opponents_ahead_lane else ""
        ),
        "excluded_out_of_bounds_frame_players": excluded_out_of_bounds,
    }


def extract_contextual_threat(events, frames, match_id=""):
    frame_by_uuid, duplicate_frames = _frame_map(frames)
    event_rows = []
    unmatched_supported_events = 0
    missing_player_events = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        kind = _event_type(event)
        if kind not in SUPPORTED_TYPES:
            continue
        event_id = str(event.get("id") or "")
        frame = frame_by_uuid.get(event_id)
        if frame is None:
            unmatched_supported_events += 1
            continue
        row = contextual_event_features(event, frame)
        if row is None:
            continue
        row["match_id"] = str(match_id or event.get("_match_id") or "")
        event_rows.append(row)
        if not row["player_id"]:
            missing_player_events += 1

    grouped = defaultdict(list)
    for row in event_rows:
        if row["player_id"]:
            grouped[(row["match_id"], row["player_id"], row["team_id"])].append(row)

    player_rows = []
    for (mid, player_id, team_id), rows in sorted(grouped.items()):
        def mean_numeric(field):
            values = [float(r[field]) for r in rows if r[field] != ""]
            return round(sum(values) / len(values), 6) if values else ""
        player_rows.append({
            "match_id": mid,
            "player_id": player_id,
            "player_name": rows[0]["player_name"],
            "team_id": team_id,
            "team_name": rows[0]["team_name"],
            "contextual_events": len(rows),
            "pressured_contextual_events": sum(r["under_pressure"] for r in rows),
            "mean_visible_opponents": mean_numeric("visible_opponents"),
            "mean_opponents_within_5": mean_numeric("opponents_within_5"),
            "mean_opponents_within_10": mean_numeric("opponents_within_10"),
            "mean_nearest_opponent_distance": mean_numeric("nearest_opponent_distance"),
            "mean_goal_corridor_opponents_5m": mean_numeric("goal_corridor_opponents_5m"),
            "mean_goal_side_opponents_12m": mean_numeric("goal_side_opponents_12m"),
            "mean_teammates_ahead_within_20": mean_numeric("teammates_ahead_within_20"),
            "mean_nearest_opponent_ahead_lane_distance": mean_numeric("nearest_opponent_ahead_lane_distance"),
            "shot_context_events": sum(r["event_type"] == "Shot" for r in rows),
            "pass_context_events": sum(r["event_type"] == "Pass" for r in rows),
            "carry_context_events": sum(r["event_type"] in {"Carry", "Dribble"} for r in rows),
            "receipt_context_events": sum(r["event_type"] in {"Ball Receipt*", "Ball Receipt"} for r in rows),
            "under_pressure_rate": round(sum(r["under_pressure"] for r in rows) / len(rows), 6),
            "feature_scope": "360_sampled_events_only_not_full_match_totals",
        })

    supported_count = sum(
        1 for e in events if isinstance(e, dict) and _event_type(e) in SUPPORTED_TYPES
    )
    report = {
        "provider": "StatsBomb Open Data",
        "match_id": str(match_id),
        "supported_event_types": sorted(SUPPORTED_TYPES),
        "supported_events": supported_count,
        "events_with_usable_360_context": len(event_rows),
        "event_context_coverage": round(len(event_rows) / supported_count, 6) if supported_count else None,
        "unmatched_supported_events_without_frame": unmatched_supported_events,
        "duplicate_360_event_uuids": len(duplicate_frames),
        "context_rows_without_player_id": missing_player_events,
        "player_match_rows": len(player_rows),
        "missing_context_policy": "Missing 360 frames are not imputed as zero; aggregates cover sampled 360-linked events only.",
        "status": "PASS_STRUCTURAL_ONLY",
        "prediction_validation": "NOT_EVALUATED",
    }
    return event_rows, player_rows, report


def _write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for row in rows for k in row))
    if not fields:
        fields = ["match_id"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Extract StatsBomb 360 contextual-threat research features")
    parser.add_argument("--events-dir", type=Path, required=True)
    parser.add_argument("--three-sixty-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    all_events, all_players = [], []
    for event_path in sorted(args.events_dir.glob("*.json")):
        frame_path = args.three_sixty_dir / event_path.name
        if not frame_path.exists():
            continue
        events = json.loads(event_path.read_text(encoding="utf-8"))
        frames = json.loads(frame_path.read_text(encoding="utf-8"))
        event_rows, player_rows, report = extract_contextual_threat(events, frames, event_path.stem)
        all_events.extend(event_rows)
        all_players.extend(player_rows)
        summaries.append(report)
    _write_csv(args.out_dir / "contextual_threat_events.csv", all_events)
    _write_csv(args.out_dir / "contextual_threat_player_match.csv", all_players)
    result = {
        "provider": "StatsBomb Open Data",
        "matches_processed": len(summaries),
        "event_context_rows": len(all_events),
        "player_match_rows": len(all_players),
        "matches": summaries,
        "overall_status": "PASS_STRUCTURAL_ONLY",
        "prediction_validation": "NOT_EVALUATED",
        "warning": "360 is sampled context, not continuous tracking; player aggregates are not full-match totals.",
    }
    (args.out_dir / "contextual_threat_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({
        "matches_processed": len(summaries),
        "event_context_rows": len(all_events),
        "player_match_rows": len(all_players),
        "overall_status": result["overall_status"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
