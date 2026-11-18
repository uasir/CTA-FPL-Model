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


def infer_directions(events, match_id, min_non_goal_evidence=2):
    teams_by_period = defaultdict(dict)
    evidence = defaultdict(lambda: defaultdict(list))
    ignored = Counter()

    for event in events:
        if not isinstance(event, dict):
            continue
        period = event.get("period")
        if period not in {1, 2, 3, 4}:
            continue
        team = event.get("team") or {}
        team_id = team.get("id")
        if team_id is not None:
            teams_by_period[str(period)][str(team_id)] = str(team.get("name") or "")
        if (event.get("type") or {}).get("name") != "Shot":
            continue
        shot = event.get("shot") or {}
        outcome = (shot.get("outcome") or {}).get("name")
        if outcome not in QUALIFYING_OUTCOMES:
            ignored["non_qualifying_outcome"] += 1
            continue
        team_id = team.get("id")
        if team_id is None:
            ignored["shot_missing_team_id"] += 1
            continue
        side = _goal_side(shot.get("end_location"))
        if side is None:
            ignored["endpoint_not_at_goal_line"] += 1
            continue
        evidence[(str(period), str(team_id))].append({
            "attacks_right": side,
            "outcome": outcome,
            "event_id": str(event.get("id") or ""),
            "team_name": str(team.get("name") or ""),
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
        team_evidence = {
            team_id: evidence.get((period, team_id), [])
            for team_id in team_ids
        }
        all_evidence = [item for values in team_evidence.values() for item in values]
        if not all_evidence:
            period_reports.append({
                "period": int(period),
                "status": "WITHHELD_NO_GOAL_LINE_SHOT_EVIDENCE",
                "team_count": 2,
                "evidence_count": 0,
            })
            continue

        team_directions = {}
        conflicts = []
        for team_id, rows in team_evidence.items():
            sides = {row["attacks_right"] for row in rows}
            if len(sides) > 1:
                conflicts.append(team_id)
            elif rows:
                team_directions[team_id] = next(iter(sides))

        if conflicts:
            period_reports.append({
                "period": int(period),
                "status": "WITHHELD_CONFLICTING_SHOT_ENDPOINTS",
                "conflicting_team_ids": conflicts,
                "evidence_count": len(all_evidence),
            })
            continue

        # The two teams must attack opposite goals in a period. If both have
        # direct evidence it must agree with that rule; if only one does, the
        # opponent direction is inferred from the two-team pitch geometry.
        if len(team_directions) == 2:
            values = list(team_directions.values())
            if values[0] == values[1]:
                period_reports.append({
                    "period": int(period),
                    "status": "WITHHELD_TEAMS_NOT_ATTACKING_OPPOSITE_GOALS",
                    "evidence_count": len(all_evidence),
                })
                continue
        elif len(team_directions) == 1:
            known_team = next(iter(team_directions))
            other_team = next(team_id for team_id in team_ids if team_id != known_team)
            team_directions[other_team] = not team_directions[known_team]
        else:
            continue

        goal_evidence_count = sum(row["outcome"] == "Goal" for row in all_evidence)
        non_goal_evidence_count = len(all_evidence) - goal_evidence_count
        if goal_evidence_count == 0 and len(all_evidence) < min_non_goal_evidence:
            period_reports.append({
                "period": int(period),
                "status": "WITHHELD_INSUFFICIENT_SHOT_ENDPOINT_EVIDENCE",
                "evidence_count": len(all_evidence),
                "goal_evidence_count": 0,
            })
            continue

        confidence = "high" if goal_evidence_count > 0 or len(all_evidence) >= min_non_goal_evidence else "medium"
        for team_id in team_ids:
            rows = team_evidence[team_id]
            direct = bool(rows)
            direction_rows.append({
                "match_id": str(match_id),
                "period": period,
                "team": team_id,
                "team_name": teams[team_id],
                "attacks_right": str(team_directions[team_id]).lower(),
                "direction_source": "shot_endpoint_outcomes" if direct else "opponent_opposite_goal_inference",
                "evidence_count": len(rows),
                "evidence_event_ids": ";".join(row["event_id"] for row in rows if row["event_id"]),
                "confidence_level": confidence,
                "goal_evidence_count_period": goal_evidence_count,
                "non_goal_evidence_count_period": non_goal_evidence_count,
            })
        period_reports.append({
            "period": int(period),
            "status": "INFERRED",
            "team_count": 2,
            "evidence_count": len(all_evidence),
            "goal_evidence_count": goal_evidence_count,
            "confidence_level": confidence,
            "mapped_team_count": 2,
        })

    report = {
        "provider": "StatsBomb Open Data",
        "match_id": str(match_id),
        "method": "Goal-line x-coordinate from Goal/Saved/Post shot outcomes; opponent direction inferred as opposite only when two-team period geometry and evidence agree.",
        "goal_line_tolerance_pitch_units": GOAL_LINE_TOLERANCE,
        "minimum_non_goal_evidence": min_non_goal_evidence,
        "direction_map_rows": len(direction_rows),
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
    parser.add_argument("--match-id", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--min-non-goal-evidence", type=int, default=2)
    args = parser.parse_args()

    events = json.loads(args.events.read_text(encoding="utf-8"))
    rows, report = infer_directions(events, args.match_id, args.min_non_goal_evidence)
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
