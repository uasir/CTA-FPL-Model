#!/usr/bin/env python3
"""Run the canonical CTA feature core over normalized Wyscout EPL events.

All player/sequence rows stay runner-local. Only the aggregate report is
intended for publication. Possessions are inferred and xT is retrospective.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "canonical_candidate" / "src"))

from cta_engine import build_features, event_type, fit_xt, possession_team_of  # noqa: E402


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        if fields:
            writer.writeheader()
            writer.writerows(rows)


def run(events_path: Path, out_dir: Path) -> dict:
    events = json.loads(events_path.read_text(encoding="utf-8"))
    if not isinstance(events, list) or not events:
        raise ValueError("Normalized CTA event input must be a non-empty JSON list")

    required = {"_match_id", "_event_index", "period", "possession", "team", "type"}
    missing = [index for index, event in enumerate(events)
               if not isinstance(event, dict) or not required.issubset(event)]
    if missing:
        raise ValueError(f"Canonical event rows missing required fields at indexes: {missing[:10]}")

    match_ids = {str(event["_match_id"]) for event in events}
    direction_keys = {
        (str(event["_match_id"]), int(event["period"]), possession_team_of(event))
        for event in events
    }
    # Wyscout coordinates are already attacking-team-relative. The adapter
    # converts percentages to 120x80 CTA units, so no second direction flip.
    directions = {key: True for key in direction_keys}

    xt_values, xt_report = fit_xt(events, directions)
    # 10 Wyscout percentage points equals 12 units on the 120-unit CTA x-axis.
    sequences, players = build_features(
        events, directions, xt_values, progressive_threshold=12.0
    )

    event_counts = Counter(event_type(event) for event in events)
    sequence_classes = Counter(row["sequence_class"] for row in sequences)
    possession_keys = {
        (str(event["_match_id"]), int(event["period"]),
         int(event["possession"]), possession_team_of(event))
        for event in events
    }
    actor_ids = {
        str((event.get("player") or {}).get("id"))
        for event in events if (event.get("player") or {}).get("id") is not None
    }
    known_actor_names = sum(
        bool((event.get("player") or {}).get("name")) for event in events
    )
    actorless_events = sum(not isinstance(event.get("player"), dict) for event in events)

    player_rows = []
    for provider_player_id, raw_counts in sorted(players.items()):
        counts = dict(raw_counts)
        player_name = counts.pop("statsbomb_player_name", "")
        player_rows.append({
            "provider": "Wyscout",
            "provider_player_id": provider_player_id,
            "provider_player_name": player_name,
            **counts,
        })

    out_dir.mkdir(parents=True, exist_ok=True)
    # These detailed files are deliberately not uploaded by the workflow.
    write_rows(out_dir / "cta_wyscout_player_features_runner_local.csv", player_rows)
    write_rows(out_dir / "cta_wyscout_sequence_features_runner_local.csv", sequences)

    durations = sorted(float(row["duration_seconds"]) for row in sequences)
    event_counts_per_sequence = sorted(int(row["event_count"]) for row in sequences)
    segments_per_match = sorted(Counter(row["match_id"] for row in sequences).values())
    def percentile(values, fraction):
        if not values:
            return None
        return round(values[min(len(values) - 1, int((len(values) - 1) * fraction))], 2)

    report = {
        "status": "PASS_CORE_ENGINE_EXECUTED_RESEARCH_ONLY",
        "provider": "Wyscout",
        "competition": "English Premier League",
        "season": "2017/18",
        "events_loaded": len(events),
        "unique_matches": len(match_ids),
        "inferred_possession_segments": len(possession_keys),
        "sequence_feature_rows": len(sequences),
        "provider_player_feature_rows": len(player_rows),
        "unique_provider_actor_ids": len(actor_ids),
        "events_with_actor_name_metadata": known_actor_names,
        "events_without_actor_object": actorless_events,
        "event_type_counts": dict(sorted(event_counts.items())),
        "sequence_class_counts": dict(sorted(sequence_classes.items())),
        "sequence_duration_seconds": {
            "p50": percentile(durations, 0.50),
            "p90": percentile(durations, 0.90),
            "mean": round(sum(durations) / len(durations), 2) if durations else None,
        },
        "events_per_sequence": {
            "p50": percentile(event_counts_per_sequence, 0.50),
            "p90": percentile(event_counts_per_sequence, 0.90),
            "mean": round(sum(event_counts_per_sequence) / len(event_counts_per_sequence), 2)
                    if event_counts_per_sequence else None,
            "single_event_sequences": sum(value == 1 for value in event_counts_per_sequence),
            "single_event_sequence_pct": round(
                100 * sum(value == 1 for value in event_counts_per_sequence)
                / len(event_counts_per_sequence), 2
            ) if event_counts_per_sequence else None,
        },
        "possession_segments_per_match": {
            "min": min(segments_per_match) if segments_per_match else None,
            "p50": percentile(segments_per_match, 0.50),
            "p90": percentile(segments_per_match, 0.90),
            "max": max(segments_per_match) if segments_per_match else None,
            "mean": round(sum(segments_per_match) / len(segments_per_match), 2)
                    if segments_per_match else None,
        },
        "cta_feature_coverage": {
            "progressive_action_threshold": "10 Wyscout percentage points (12 CTA pitch units)",
            "sequences_with_direction": sum(bool(row["direction_available"]) for row in sequences),
            "sequences_with_xt_gain": sum(row["mean_action_xt_gain"] != "" for row in sequences),
            "sequences_with_shots": sum(int(row["shot_count"]) > 0 for row in sequences),
            "sequences_with_box_entries": sum(
                row["box_entries"] != "" and int(row["box_entries"]) > 0 for row in sequences
            ),
            "sequences_with_final_third_entries": sum(
                row["final_third_entries"] != "" and int(row["final_third_entries"]) > 0
                for row in sequences
            ),
            "pressure_features_available": False,
            "receipt_features_available": False,
            "recipient_attribution_available": False,
            "xg_available": False,
        },
        "xt_fit": xt_report,
        "coordinate_policy": "Wyscout attacking-team-relative percentages scaled to CTA 120x80; no direction flip.",
        "possession_policy": "INFERRED_EVENT_STATE_WITH_DUEL_OUTCOME_TAGS; not yet manually validated against video.",
        "possession_quality_status": "INFERRED_NOT_MANUALLY_VALIDATED",
        "manual_review_required": True,
        "validation_status": "STRUCTURAL_EXECUTION_ONLY",
        "predictive_validation": "NOT_EVALUATED",
        "point_in_time_status": "RETROSPECTIVE_FULL_SEASON_XT_FIT_NOT_POINT_IN_TIME_SAFE",
        "decision_use_status": "RESEARCH_ONLY_NOT_IN_BASELINE",
        "cta_decision_weight_applied": False,
        "cta_ranking_effect": "NONE",
        "publication_policy": "Aggregate report only; player and sequence feature rows remain runner-local.",
        "limitations": [
            "Possession boundaries are inferred from controlled-team changes, duel outcome tags, restarts and dead-ball state transitions; no provider possession IDs are available.",
            "Coordinates and possession segments require independent sample review before football-validity claims.",
            "The full-season xT grid is retrospective and must be refit within each training fold for predictive validation.",
            "Wyscout has no pass-recipient IDs, pressure flags, tracking/360 or xG in this public schema.",
            "This historical single-season run is not evidence of current-season player performance or predictive uplift.",
        ],
    }
    (out_dir / "wyscout_cta_core_execution_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.events, args.out_dir), indent=2))


if __name__ == "__main__":
    main()
