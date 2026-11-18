#!/usr/bin/env python3
"""Infer StatsBomb match-period attacking directions from shot endpoint evidence.

The inference is conservative: only goal-line endpoints from goals, saved shots
or posts are used. A period is mapped only when evidence is internally
consistent and reaches the configured confidence threshold. No default direction
is assigned when evidence is insufficient.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

PITCH_LENGTH = 120.0
GOAL_LINE_TOLERANCE = 5.0
QUALIFYING_OUTCOMES = {"Goal", "Saved", "Post", "Saved to Post"}


def _goal_side(end_location):
    if not isinstance(end_location, (list, tuple)) or len(end_location) < 2:
        return None
    try:
        x = float(end_location[0])
    except (TypeError, ValueError):
        return None
    if x <= GOAL_LINE_TOLERANCE:
        return False
    if x >= PITCH_LENGTH - GOAL_LINE_TOLERANCE:
        return True
    return None


def _keeper_goal_side(location):
    if not isinstance(location, (list, tuple)) or len(location) < 2:
        return None
    try:
        x = float(location[0])
    except (TypeError, ValueError):
        return None
    if x <= 30.0:
        return False
    if x >= 90.0:
        return True
    return None


def infer_directions(
    events,
    match_id,
    frames=None,
    min_non_goal_evidence=2,
    min_keeper_evidence=5,
    keeper_consistency=0.8,
):
    teams_by_period = defaultdict(dict)
    shot_evidence = defaultdict(list)
    keeper_evidence = defaultdict(list)
    ignored = Counter()
    frame_by_uuid = {
        str(frame.get("event_uuid")): frame
        for frame in (frames or [])
        if isinstance(frame, dict) and frame.get("event_uuid")
    }

    for event in events:
        if not isinstance(event, dict):
            continue
        period = event.get("period")
        if period not in {1, 2, 3, 4}:
            continue
        team = event.get("team") or {}
        team_id = team.get("id")
        if team_id is None:
            continue
        period_key = str(period)
        team_key = str(team_id)
        teams_by_period[period_key][team_key] = str(team.get("name") or "")
        event_id = str(event.get("id") or "")

        frame = frame_by_uuid.get(event_id)
        if frame:
            freeze_frame = frame.get("freeze_frame")
            if isinstance(freeze_frame, list):
                opponent_keepers = [
                    item for item in freeze_frame
                    if isinstance(item, dict)
                    and item.get("keeper") is True
                    and item.get("teammate") is False
                ]
                if len(opponent_keepers) == 1:
                    keeper = opponent_keepers[0]
                    side = _keeper_goal_side(keeper.get("location"))
                    if side is not None:
                        keeper_evidence[(period_key, team_key)].append({
                            "attacks_right": side,
                            "event_id": event_id,
                            "keeper_x": float(keeper["location"][0]),
                        })
                elif len(opponent_keepers) > 1:
                    ignored["multiple_opponent_keepers_in_frame"] += 1

        if (event.get("type") or {}).get("name") != "Shot":
            continue
        shot = event.get("shot") or {}
        outcome = (shot.get("outcome") or {}).get("name")
        if outcome not in QUALIFYING_OUTCOMES:
            ignored["non_qualifying_outcome"] += 1
            continue
        side = _goal_side(shot.get("end_location"))
        if side is None:
            ignored["endpoint_not_at_goal_line"] += 1
            continue
        shot_evidence[(period_key, team_key)].append({
            "attacks_right": side,
            "outcome": outcome,
            "event_id": event_id,
        })

    direction_rows = []
    period_reports = []
    for period, teams in sorted(teams_by_period.items(), key=lambda item: int(item[0])):
        if len(teams) != 2:
            period_reports.append({
                "period": int(period),
                "status": "WITHHELD_TEAM_COUNT_NOT_TWO",
                "team_count": len(teams),
            })
            continue

        team_ids = sorted(
            teams,
            key=lambda value: (0, int(value)) if value.isdigit() else (1, value),
        )
        direct_directions = {}
        direct_sources = {}
        direct_confidence = {}
        direct_evidence = {}
        conflicts = []

        for team_id in team_ids:
            shots = shot_evidence.get((period, team_id), [])
            keepers = keeper_evidence.get((period, team_id), [])
            shot_sides = {row["attacks_right"] for row in shots}
            keeper_counts = Counter(row["attacks_right"] for row in keepers)
            shot_direction = None
            keeper_direction = None
            goal_count = sum(row["outcome"] == "Goal" for row in shots)

            if len(shot_sides) > 1:
                conflicts.append({"team_id": team_id, "source": "shot_endpoint_outcomes"})
                continue
            if shots and (goal_count > 0 or len(shots) >= min_non_goal_evidence):
                shot_direction = next(iter(shot_sides))

            if len(keepers) >= min_keeper_evidence:
                side, count = keeper_counts.most_common(1)[0]
                if count / len(keepers) >= keeper_consistency:
                    keeper_direction = side
                else:
                    conflicts.append({"team_id": team_id, "source": "keeper_position"})
                    continue

            if (
                shot_direction is not None
                and keeper_direction is not None
                and shot_direction != keeper_direction
            ):
                conflicts.append({"team_id": team_id, "source": "shot_keeper_disagreement"})
                continue

            chosen = keeper_direction if keeper_direction is not None else shot_direction
            if chosen is None:
                continue
            direct_directions[team_id] = chosen
            if keeper_direction is not None and shot_direction is not None:
                direct_sources[team_id] = "combined_keeper_and_shot_evidence"
            elif keeper_direction is not None:
                direct_sources[team_id] = "opponent_goalkeeper_position"
            else:
                direct_sources[team_id] = "shot_endpoint_outcomes"
            direct_confidence[team_id] = "high"
            direct_evidence[team_id] = shots + keepers

        if conflicts:
            period_reports.append({
                "period": int(period),
                "status": "WITHHELD_CONFLICTING_DIRECTION_EVIDENCE",
                "conflicts": conflicts,
                "shot_endpoint_evidence_count": sum(len(shot_evidence.get((period, t), [])) for t in team_ids),
                "keeper_position_evidence_count": sum(len(keeper_evidence.get((period, t), [])) for t in team_ids),
            })
            continue
        if not direct_directions:
            period_reports.append({
                "period": int(period),
                "status": "WITHHELD_INSUFFICIENT_DIRECTION_EVIDENCE",
                "shot_endpoint_evidence_count": sum(len(shot_evidence.get((period, t), [])) for t in team_ids),
                "keeper_position_evidence_count": sum(len(keeper_evidence.get((period, t), [])) for t in team_ids),
            })
            continue

        if len(direct_directions) == 2:
            values = list(direct_directions.values())
            if values[0] == values[1]:
                period_reports.append({
                    "period": int(period),
                    "status": "WITHHELD_TEAMS_NOT_ATTACKING_OPPOSITE_GOALS",
                    "evidence_count": sum(len(direct_evidence.get(t, [])) for t in team_ids),
                })
                continue
        elif len(direct_directions) == 1:
            known_team = next(iter(direct_directions))
            other_team = next(team_id for team_id in team_ids if team_id != known_team)
            direct_directions[other_team] = not direct_directions[known_team]
            direct_sources[other_team] = "opponent_opposite_goal_inference"
            direct_confidence[other_team] = direct_confidence[known_team]
            direct_evidence[other_team] = []

        for team_id in team_ids:
            rows = direct_evidence.get(team_id, [])
            shots = shot_evidence.get((period, team_id), [])
            keepers = keeper_evidence.get((period, team_id), [])
            direction_rows.append({
                "match_id": str(match_id),
                "period": period,
                "team": team_id,
                "team_name": teams[team_id],
                "attacks_right": str(direct_directions[team_id]).lower(),
                "direction_source": direct_sources[team_id],
                "evidence_count": len(rows),
                "evidence_event_ids": ";".join(sorted({row["event_id"] for row in rows if row.get("event_id")})),
                "confidence_level": direct_confidence[team_id],
                "goal_evidence_count_period": sum(
                    row["outcome"] == "Goal"
                    for t in team_ids for row in shot_evidence.get((period, t), [])
                ),
                "shot_endpoint_evidence_count_team": len(shots),
                "keeper_position_evidence_count_team": len(keepers),
                "keeper_position_consistency_team": (
                    round(max(Counter(row["attacks_right"] for row in keepers).values()) / len(keepers), 4)
                    if keepers else ""
                ),
            })

        period_reports.append({
            "period": int(period),
            "status": "INFERRED",
            "team_count": 2,
            "shot_endpoint_evidence_count": sum(len(shot_evidence.get((period, t), [])) for t in team_ids),
            "keeper_position_evidence_count": sum(len(keeper_evidence.get((period, t), [])) for t in team_ids),
            "mapped_team_count": 2,
            "confidence_level": "high",
        })

    report = {
        "provider": "StatsBomb Open Data",
        "match_id": str(match_id),
        "method": "Cross-check opponent goalkeeper position in 360 freeze frames against Goal/Saved/Post shot goal-line endpoints; infer the opponent's opposite direction only in a two-team period when direct evidence is consistent.",
        "goal_line_tolerance_pitch_units": GOAL_LINE_TOLERANCE,
        "keeper_goal_side_thresholds": {"left_x_max": 30.0, "right_x_min": 90.0},
        "minimum_non_goal_shot_evidence": min_non_goal_evidence,
        "minimum_keeper_position_evidence": min_keeper_evidence,
        "keeper_consistency_threshold": keeper_consistency,
        "direction_map_rows": len(direction_rows),
        "keeper_position_evidence_events": sum(len(rows) for rows in keeper_evidence.values()),
        "shot_endpoint_evidence_events": sum(len(rows) for rows in shot_evidence.values()),
        "periods_inferred": sum(row["status"] == "INFERRED" for row in period_reports),
        "periods_withheld": sum(row["status"] != "INFERRED" for row in period_reports),
        "period_reports": period_reports,
        "ignored_event_counts": dict(ignored),
        "status": "PASS_EVIDENCE_BACKED_DIRECTION_MAP" if direction_rows else "DIRECTION_NOT_INFERRED",
        "prediction_validation": "NOT_EVALUATED",
    }
    return direction_rows, report


def main():
    parser = argparse.ArgumentParser(description="Infer StatsBomb attack directions from shot endpoint evidence")
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--three-sixty", type=Path, help="Optional StatsBomb 360 freeze-frame file for goalkeeper-position evidence")
    parser.add_argument("--match-id", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--min-non-goal-evidence", type=int, default=2)
    args = parser.parse_args()

    events = json.loads(args.events.read_text(encoding="utf-8"))
    frames = (
        json.loads(args.three_sixty.read_text(encoding="utf-8"))
        if args.three_sixty and args.three_sixty.exists() else None
    )
    rows, report = infer_directions(
        events, args.match_id, frames=frames,
        min_non_goal_evidence=args.min_non_goal_evidence,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    fields = [
        "match_id", "period", "team", "team_name", "attacks_right",
        "direction_source", "evidence_count", "evidence_event_ids",
        "confidence_level", "goal_evidence_count_period",
        "non_goal_evidence_count_period",
    ]
    with (args.out_dir / "direction_map.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (args.out_dir / "direction_inference_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
