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
from collections import Counter, defaultdict
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


def _progress_x(point, attacks_right):
    return point[0] if attacks_right else PITCH_LENGTH - point[0]


def _finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return number if math.isfinite(number) else ""


def read_direction_map(path):
    """Read only explicit match-period-team attack directions; never infer a default."""
    if path is None or not path.exists():
        return {}
    result = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for line, row in enumerate(csv.DictReader(handle), start=2):
            match_id = str(row.get("match_id") or "").strip()
            period = str(row.get("period") or "").strip()
            team = str(row.get("team") or "").strip()
            raw = str(row.get("attacks_right") or "").strip().lower()
            if not (match_id and period and team):
                raise ValueError(f"Direction-map row {line} is missing match_id, period or team")
            if raw not in {"true", "false", "1", "0", "yes", "no"}:
                raise ValueError(f"Direction-map row {line} has invalid attacks_right value: {raw}")
            value = raw in {"true", "1", "yes"}
            key = (match_id, period, team)
            if key in result and result[key] != value:
                raise ValueError(f"Conflicting attack directions for {key}")
            result[key] = value
    return result


def _event_direction(event, match_id, direction_map, coordinate_orientation="action_executing_team"):
    team = event.get("team") or {}
    period = str(event.get("period") or "")
    for team_key in (str(team.get("id") or ""), str(team.get("name") or "")):
        if team_key:
            value = direction_map.get((str(match_id), period, team_key))
            if value is not None:
                return {
                    "attacks_right": bool(value),
                    "direction_source": "explicit_direction_map_override",
                    "confidence_level": "manual_map",
                    "evidence_count": "",
                }
    if coordinate_orientation == "action_executing_team" and team.get("id") is not None:
        return {
            "attacks_right": True,
            "direction_source": "statsbomb_action_executing_team_orientation",
            "confidence_level": "source_specification",
            "evidence_count": "",
        }
    return None


def contextual_event_features(event, frame, attacks_right=None):
    """Return auditable context; directional metrics are withheld without a verified direction."""
    event_type = _event_type(event)
    if event_type not in SUPPORTED_TYPES or not frame:
        return None

    visible = frame.get("freeze_frame")
    if not isinstance(visible, list):
        return None

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
    defenders = [p for p in opponents if not p["keeper"]]
    teammates = [p for p in valid_players if p["teammate"] is True and not p["actor"]]
    opponent_distances = [_distance(actor_position, p["location"]) for p in opponents]
    goalkeeper_distances = [
        _distance(actor_position, p["location"]) for p in opponents if p["keeper"]
    ]

    direction_known = isinstance(attacks_right, bool)
    directional = {
        "goal_corridor_opponents_5m": "",
        "goal_side_opponents_12m": "",
        "teammates_ahead_within_20": "",
        "nearest_opponent_ahead_lane_distance": "",
        "receiving_options_observed_ahead": "",
        "receiving_options_assessed_ahead": "",
        "open_receiving_options_ahead": "",
        "dangerous_receiving_options_open": "",
        "blocked_receiving_options_ahead": "",
        "nearest_open_receiver_distance": "",
        "threat_involvement_dangerous_receipt": "",
        "threat_creation_pass_attempt": "",
        "threat_creation_pass_completed": "",
        "progressive_pass_attempt": "",
        "progressive_pass_completed": "",
        "progressive_carry": "",
    }

    goal = None
    actor_progress = None
    if direction_known:
        goal = (PITCH_LENGTH if attacks_right else 0.0, PITCH_WIDTH / 2.0)
        actor_progress = _progress_x(actor_position, attacks_right)
        corridor_opponents = [
            p for p in defenders
            if _distance_to_segment(p["location"], actor_position, goal) <= 5.0
        ]
        goal_side_opponents = [
            p for p in defenders
            if _progress_x(p["location"], attacks_right) > actor_progress
            and abs(p["location"][1] - actor_position[1]) <= 12.0
        ]
        teammates_ahead = [
            p for p in teammates
            if _progress_x(p["location"], attacks_right) > actor_progress + 5.0
            and _distance(actor_position, p["location"]) <= 20.0
        ]
        opponents_ahead_lane = [
            _distance(actor_position, p["location"])
            for p in defenders
            if _progress_x(p["location"], attacks_right) > actor_progress
            and abs(p["location"][1] - actor_position[1]) <= 8.0
        ]

        observed_receivers = [
            p for p in teammates
            if _progress_x(p["location"], attacks_right) > actor_progress + 5.0
            and _distance(actor_position, p["location"]) <= 35.0
        ]
        assessed = 0
        open_receivers = []
        blocked_receivers = 0
        for receiver in observed_receivers:
            # A receiver is assessed only when at least one opponent is visible.
            # These are visible-frame options, not proof that the full pitch is open.
            if not defenders:
                continue
            assessed += 1
            lane_blocked = any(
                _distance_to_segment(opponent["location"], actor_position, receiver["location"]) <= 2.5
                and _distance(actor_position, opponent["location"]) > 2.0
                and _distance(receiver["location"], opponent["location"]) > 2.0
                for opponent in defenders
            )
            receiver_pressure = min(
                _distance(receiver["location"], opponent["location"])
                for opponent in opponents
            )
            if lane_blocked or receiver_pressure < 3.0:
                blocked_receivers += 1
            else:
                open_receivers.append(receiver)

        directional.update({
            "threat_creation_pass_attempt": 0 if event_type != "Pass" else "",
            "threat_creation_pass_completed": 0 if event_type != "Pass" else "",
            "progressive_pass_attempt": 0 if event_type != "Pass" else "",
            "progressive_pass_completed": 0 if event_type != "Pass" else "",
            "progressive_carry": 0 if event_type not in {"Carry", "Dribble"} else "",
            "goal_corridor_opponents_5m": len(corridor_opponents),
            "goal_side_opponents_12m": len(goal_side_opponents),
            "teammates_ahead_within_20": len(teammates_ahead),
            "nearest_opponent_ahead_lane_distance": (
                round(min(opponents_ahead_lane), 4) if opponents_ahead_lane else ""
            ),
            "receiving_options_observed_ahead": len(observed_receivers),
            "receiving_options_assessed_ahead": assessed,
            "open_receiving_options_ahead": len(open_receivers),
            "dangerous_receiving_options_open": sum(
                _distance(receiver["location"], goal) <= 40.0
                for receiver in open_receivers
            ),
            "blocked_receiving_options_ahead": blocked_receivers,
            "nearest_open_receiver_distance": (
                round(min(_distance(actor_position, p["location"]) for p in open_receivers), 4)
                if open_receivers else ""
            ),
            "threat_involvement_dangerous_receipt": (
                int(_distance(actor_position, goal) <= 40.0)
                if event_type in {"Ball Receipt*", "Ball Receipt"} else 0
            ),
        })

    pass_data = event.get("pass") or {}
    pass_end = _point(pass_data.get("end_location"))
    pass_outcome = (pass_data.get("outcome") or {}).get("name")
    pass_completed = event_type == "Pass" and bool(pass_data) and pass_outcome is None
    if direction_known and event_type == "Pass" and pass_end and _inside_pitch(pass_end):
        end_progress = _progress_x(pass_end, attacks_right)
        progressive = end_progress - actor_progress >= 10.0
        into_danger = _distance(pass_end, goal) <= 40.0
        creation_attempt = progressive or into_danger
        directional["threat_creation_pass_attempt"] = int(creation_attempt)
        directional["threat_creation_pass_completed"] = int(creation_attempt and pass_completed)
        directional["progressive_pass_attempt"] = int(progressive)
        directional["progressive_pass_completed"] = int(progressive and pass_completed)

    carry_data = event.get("carry") or {}
    carry_end = _point(carry_data.get("end_location"))
    if direction_known and event_type in {"Carry", "Dribble"} and carry_end and _inside_pitch(carry_end):
        directional["progressive_carry"] = int(
            _progress_x(carry_end, attacks_right) - actor_progress >= 10.0
        )

    shot_data = event.get("shot") or {}
    shot_outcome = (shot_data.get("outcome") or {}).get("name")
    shot_xg = _finite_number(shot_data.get("statsbomb_xg", shot_data.get("xg")))
    recipient = pass_data.get("recipient") or {}
    identity = _identity(event)
    return {
        "event_id": str(event.get("id") or ""),
        "event_type": event_type,
        "player_id": identity[0] if identity else "",
        "player_name": identity[1] if identity else "",
        "team_id": str((event.get("team") or {}).get("id") or ""),
        "team_name": str((event.get("team") or {}).get("name") or ""),
        "period": event.get("period"),
        "minute": event.get("minute"),
        "second": event.get("second"),
        "x": round(actor_position[0], 4),
        "y": round(actor_position[1], 4),
        "attacks_right": attacks_right if direction_known else "",
        "direction_known": direction_known,
        "attack_direction_source": "",
        "attack_direction_confidence": "",
        "attack_direction_evidence_count": "",
        "distance_to_attacking_goal": round(_distance(actor_position, goal), 4) if goal else "",
        "under_pressure": bool(event.get("under_pressure")),
        "visible_opponents": len(opponents),
        "visible_teammates": len(teammates),
        "opponents_within_5": sum(d <= 5.0 for d in opponent_distances),
        "opponents_within_10": sum(d <= 10.0 for d in opponent_distances),
        "nearest_opponent_distance": round(min(opponent_distances), 4) if opponent_distances else "",
        "goalkeeper_distance": round(min(goalkeeper_distances), 4) if goalkeeper_distances else "",
        "pass_recipient_id": str(recipient.get("id") or ""),
        "pass_recipient_name": str(recipient.get("name") or ""),
        "pass_completed": pass_completed if event_type == "Pass" else "",
        "pass_shot_assist": bool(pass_data.get("shot_assist")) if event_type == "Pass" else "",
        "pass_goal_assist": bool(pass_data.get("goal_assist")) if event_type == "Pass" else "",
        "shot_xg": shot_xg if event_type == "Shot" else "",
        "shot_goal": int(shot_outcome == "Goal") if event_type == "Shot" else "",
        "threat_realisation_shot": int(event_type == "Shot"),
        "threat_realisation_xg": shot_xg if event_type == "Shot" else "",
        "threat_realisation_goal": int(shot_outcome == "Goal") if event_type == "Shot" else "",
        "excluded_out_of_bounds_frame_players": excluded_out_of_bounds,
        **directional,
    }


def extract_contextual_threat(
    events, frames, match_id="", direction_map=None,
    coordinate_orientation="action_executing_team",
):
    direction_map = direction_map or {}
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
        resolved_match_id = str(match_id or event.get("_match_id") or "")
        direction_record = _event_direction(
            event, resolved_match_id, direction_map, coordinate_orientation
        )
        attacks_right = direction_record.get("attacks_right") if direction_record else None
        row = contextual_event_features(event, frame, attacks_right=attacks_right)
        if row is None:
            continue
        if direction_record:
            row["attack_direction_source"] = direction_record["direction_source"]
            row["attack_direction_confidence"] = direction_record["confidence_level"]
            row["attack_direction_evidence_count"] = direction_record["evidence_count"]
        row["match_id"] = resolved_match_id
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
            values = [float(r[field]) for r in rows if r[field] not in ("", None)]
            return round(sum(values) / len(values), 6) if values else ""
        def sum_numeric(field):
            values = [float(r[field]) for r in rows if r[field] not in ("", None)]
            return round(sum(values), 6) if values else ""
        directional_rows = [r for r in rows if r["direction_known"]]
        player_rows.append({
            "match_id": mid,
            "player_id": player_id,
            "player_name": rows[0]["player_name"],
            "team_id": team_id,
            "team_name": rows[0]["team_name"],
            "contextual_events": len(rows),
            "direction_known_events": len(directional_rows),
            "pressured_contextual_events": sum(r["under_pressure"] for r in rows),
            "mean_visible_opponents": mean_numeric("visible_opponents"),
            "mean_opponents_within_5": mean_numeric("opponents_within_5"),
            "mean_opponents_within_10": mean_numeric("opponents_within_10"),
            "mean_nearest_opponent_distance": mean_numeric("nearest_opponent_distance"),
            "mean_goal_corridor_opponents_5m": mean_numeric("goal_corridor_opponents_5m"),
            "mean_goal_side_opponents_12m": mean_numeric("goal_side_opponents_12m"),
            "mean_teammates_ahead_within_20": mean_numeric("teammates_ahead_within_20"),
            "mean_nearest_opponent_ahead_lane_distance": mean_numeric("nearest_opponent_ahead_lane_distance"),
            "mean_dangerous_receiving_options_open": mean_numeric("dangerous_receiving_options_open"),
            "mean_open_receiving_options_ahead": mean_numeric("open_receiving_options_ahead"),
            "mean_receiving_options_assessed_ahead": mean_numeric("receiving_options_assessed_ahead"),
            "threat_creation_pass_attempts": sum_numeric("threat_creation_pass_attempt"),
            "threat_creation_passes_completed": sum_numeric("threat_creation_pass_completed"),
            "progressive_pass_attempts": sum_numeric("progressive_pass_attempt"),
            "progressive_passes_completed": sum_numeric("progressive_pass_completed"),
            "progressive_carries": sum_numeric("progressive_carry"),
            "threat_involvement_dangerous_receipts": sum_numeric("threat_involvement_dangerous_receipt"),
            "threat_realisation_shots": sum_numeric("threat_realisation_shot"),
            "threat_realisation_xg": sum_numeric("threat_realisation_xg"),
            "threat_realisation_goals": sum_numeric("threat_realisation_goal"),
            "shot_assist_passes": sum(r["pass_shot_assist"] is True for r in rows),
            "goal_assist_passes": sum(r["pass_goal_assist"] is True for r in rows),
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
    direction_known_count = sum(1 for row in event_rows if row["direction_known"])
    report = {
        "provider": "StatsBomb Open Data",
        "match_id": str(match_id),
        "supported_event_types": sorted(SUPPORTED_TYPES),
        "supported_events": supported_count,
        "events_with_usable_360_context": len(event_rows),
        "event_context_coverage": round(len(event_rows) / supported_count, 6) if supported_count else None,
        "events_with_known_attack_direction": direction_known_count,
        "events_missing_attack_direction": len(event_rows) - direction_known_count,
        "direction_coverage": round(direction_known_count / len(event_rows), 6) if event_rows else None,
        "direction_sources": sorted({
            str(row.get("attack_direction_source") or "")
            for row in event_rows if row.get("attack_direction_source")
        }),
        "direction_confidence_counts": dict(Counter(
            str(row.get("attack_direction_confidence") or "unspecified")
            for row in event_rows if row.get("direction_known")
        )),
        "direction_map_rows": len(direction_map),
        "coordinate_orientation": coordinate_orientation,
        "unmatched_supported_events_without_frame": unmatched_supported_events,
        "duplicate_360_event_uuids": len(duplicate_frames),
        "context_rows_without_player_id": missing_player_events,
        "player_match_rows": len(player_rows),
        "threat_creation_pass_attempts": sum(float(r["threat_creation_pass_attempt"] or 0) for r in event_rows),
        "threat_involvement_dangerous_receipts": sum(float(r["threat_involvement_dangerous_receipt"] or 0) for r in event_rows),
        "threat_realisation_shots": sum(float(r["threat_realisation_shot"] or 0) for r in event_rows),
        "missing_context_policy": "Missing 360 frames are not imputed as zero; aggregates cover sampled 360-linked events only.",
        "direction_policy": (
            "StatsBomb event coordinates use ACTION_EXECUTING_TEAM orientation: +x points toward the opponent goal of the team executing the event. "
            "The 360 freeze-frame teammate/opponent flags and coordinates are interpreted relative to that event team. "
            "No global home/away direction map is required; an explicit map may override only when a different coordinate frame is independently established."
        ),
        "threat_dimensions": {
            "creation": "Passes progressing at least 10 pitch units or ending within 40 units of the attacking goal; attempts and completions reported separately.",
            "involvement_reception": "Ball receipts within 40 pitch units of the attacking goal.",
            "receiving_opportunity": "Visible forward teammates within 35 units, with a visible-defender lane and receiver-pressure assessment; not a full-pitch guarantee.",
            "realisation": "Shots, StatsBomb xG and goals kept as separate outcomes.",
        },
        "aggregation_policy": "Creation, involvement, receiving opportunity and realisation remain separate; no composite score or sequence double-counting is introduced.",
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
    parser.add_argument(
        "--direction-map", type=Path,
        help="Optional explicit override map for a separately verified non-StatsBomb coordinate frame",
    )
    parser.add_argument(
        "--coordinate-orientation",
        choices=["action_executing_team", "requires_direction_map"],
        default="action_executing_team",
        help="StatsBomb defaults to action-executing-team coordinates; use requires_direction_map only for a different verified frame",
    )
    parser.add_argument("--match-id", action="append", dest="match_ids", help="Optional match ID filter; repeat to select multiple matches")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    direction_map = read_direction_map(args.direction_map)
    summaries = []
    all_events, all_players = [], []
    event_paths = sorted(args.events_dir.glob("*.json"))
    if args.match_ids:
        wanted = set(str(value) for value in args.match_ids)
        event_paths = [path for path in event_paths if path.stem in wanted]
        found = {path.stem for path in event_paths}
        missing = sorted(wanted - found)
        if missing:
            raise SystemExit("Requested match IDs not found: " + ", ".join(missing))
    for event_path in event_paths:
        frame_path = args.three_sixty_dir / event_path.name
        if not frame_path.exists():
            continue
        events = json.loads(event_path.read_text(encoding="utf-8"))
        frames = json.loads(frame_path.read_text(encoding="utf-8"))
        event_rows, player_rows, report = extract_contextual_threat(
            events, frames, event_path.stem, direction_map=direction_map,
            coordinate_orientation=args.coordinate_orientation,
        )
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
        "direction_map_rows": len(direction_map),
        "direction_sources": sorted({
            source for summary in summaries for source in summary.get("direction_sources", [])
        }),
        "direction_confidence_counts": dict(Counter(
            confidence
            for summary in summaries
            for confidence, count in summary.get("direction_confidence_counts", {}).items()
            for _ in range(count)
        )),
        "coordinate_orientation": args.coordinate_orientation,
        "events_with_known_attack_direction": sum(r["events_with_known_attack_direction"] for r in summaries),
        "events_missing_attack_direction": sum(r["events_missing_attack_direction"] for r in summaries),
        "matches": summaries,
        "overall_status": "PASS_STRUCTURAL_ONLY",
        "prediction_validation": "NOT_EVALUATED",
        "warning": "360 is sampled context, not continuous tracking; directional features use StatsBomb action-executing-team coordinates and are withheld only when the event team or usable frame is missing.",
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
