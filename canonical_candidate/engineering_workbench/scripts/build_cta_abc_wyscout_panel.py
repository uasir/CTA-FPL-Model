#!/usr/bin/env python3
"""Map verified historical Wyscout/FPL lagged evidence into CTA layers A/B/C.

This is an exploratory 2017/18 historical panel. It keeps Wyscout's missing
receiver identity and xG explicit, uses conservative gameweek cutoffs, and
does not claim archived point-in-time provider vintages or predictive validity.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from cta_four_layer_pipeline import LayerResult, LAYER_FEATURES, integrate_player_sequence


def number(value):
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def parse_time(value, field):
    if not value:
        raise ValueError(f"Missing {field}")
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def per90(row, feature, window=3):
    return number(row.get(f"{feature}_per90_prior_{window}_avg"))


def average(row, feature, window=3):
    return number(row.get(f"{feature}_prior_{window}_avg"))


def difference(left, right):
    return left - right if left is not None and right is not None else None


def coverage(features):
    return {name: "OBSERVED" if value is not None else "MISSING"
            for name, value in features.items()}


def build_panel(rows, source_report):
    output = []
    counts = Counter()
    observed = {layer: Counter() for layer in LAYER_FEATURES}
    for row in rows:
        kickoff = parse_time(row.get("kickoff_time_utc"), "kickoff_time_utc")
        cutoff = parse_time(row.get("feature_cutoff_time_utc"), "feature_cutoff_time_utc")
        if cutoff >= kickoff:
            raise ValueError("Historical feature cutoff must precede target kickoff")
        cutoff_policy = str(row.get("feature_cutoff_policy") or "")
        conservative_cutoff = cutoff_policy == "CONSERVATIVE_EARLIEST_GAMEWEEK_KICKOFF"
        prior_matches = int(number(row.get("prior_matches_count")) or 0)
        team_prior = int(number(row.get("team_prior_matches_count")) or 0)

        key3, key5 = per90(row, "key_pass_attempts", 3), per90(row, "key_pass_attempts", 5)
        threat3, threat5 = (
            per90(row, "threat_creation_pass_attempts", 3),
            per90(row, "threat_creation_pass_attempts", 5),
        )
        xg3, xg5 = None, None  # Wyscout public event data has no xG.
        progressive_passes = per90(row, "progressive_pass_completions", 3)
        progressive_carries = per90(row, "progressive_carry_attempts", 3)
        final_third_entries = per90(row, "final_third_entry_pass_attempts", 3)
        minutes3 = number(row.get("fpl_minutes_prior_3_avg"))
        minutes5 = number(row.get("fpl_minutes_prior_5_avg"))
        goals3 = average(row, "goals", 3)
        shots3 = average(row, "shot_attempts", 3)
        key_avg3 = average(row, "key_pass_attempts", 3)
        ground_won = average(row, "ground_defensive_duels_won", 3)
        ground_lost = average(row, "ground_defensive_duels_lost", 3)
        defensive_duel_total = (
            ground_won + ground_lost
            if ground_won is not None and ground_lost is not None else None
        )
        duel_success = (
            ground_won / defensive_duel_total
            if ground_won is not None and defensive_duel_total is not None
            and defensive_duel_total > 0 else None
        )
        defensive_action_rates = [
            per90(row, feature, 3)
            for feature in ("ground_defensive_duel_events", "aerial_duel_events",
                            "clearance_events", "interception_events")
        ]
        defensive_actions_per90 = (
            sum(value for value in defensive_action_rates if value is not None)
            if any(value is not None for value in defensive_action_rates) else None
        )
        team_ground_won = number(row.get("team_ground_defensive_duels_won_prior_3_avg"))
        team_aerial_won = number(row.get("team_aerial_duels_won_prior_3_avg"))
        team_duels_won = (
            team_ground_won + team_aerial_won
            if team_ground_won is not None and team_aerial_won is not None
            else None
        )
        opponent_shots_allowed = number(row.get("opponent_shot_attempts_allowed_prior_3_avg"))
        opponent_creation_allowed = number(row.get("opponent_threat_creation_pass_attempts_allowed_prior_3_avg"))

        # A — temporal football value: progression, penetration and threat creation.
        a = {
            "progressive_passes": progressive_passes,
            "progressive_carries": progressive_carries,
            "final_third_entries": final_third_entries,
            "dangerous_receipts": None,  # Public Wyscout schema has no pass recipient ID.
            "sequence_value": None,      # No calibrated sequence value is fitted in this panel.
            "recent_action_trend": difference(threat3, threat5),
            "team_final_third_entries": number(row.get("team_final_third_entry_pass_attempts_prior_3_avg")),
            "team_successful_dribbles": None,  # No successful-dribble event label in this adapter.
            "player_key_pass_rate": key3,
            "player_tracked_xg_rate": None,    # xG is absent from this source.
            "recent_key_pass_trend": difference(key3, key5),
            "recent_xg_trend": xg3 - xg5 if xg3 is not None and xg5 is not None else None,
        }

        # B — defensive intelligence: defensive duels, clearances and opponent
        # attack allowed. Pressure and pressure-induced turnovers remain absent.
        b = {
            "pressure_events": None,
            "pressure_success_rate": None,
            "duel_success_rate": duel_success,
            "defensive_actions": defensive_actions_per90,
            "turnovers_under_pressure": None,
            "opponent_threat_allowed": opponent_shots_allowed,
            "defensive_exposure": opponent_creation_allowed,
            "team_interceptions": number(row.get("team_interception_events_prior_3_avg")),
            "team_tackles_won": None,
            "team_ball_recoveries": None,
            "team_recoveries": None,
            "team_duels_won": team_duels_won,
            "opponent_box_attempts_allowed": None,
            "player_fouls_committed_rate": per90(row, "foul_events", 3),
        }

        # C — player intelligence: availability trend and threat creation/
        # realisation. Reception is withheld because receiver identity is absent.
        attacking_involvement = (
            key_avg3 + shots3 if key_avg3 is not None and shots3 is not None else None
        )
        key_per90, shot_per90 = key3, per90(row, "shot_attempts", 3)
        attacking_rate = (
            key_per90 + shot_per90
            if key_per90 is not None and shot_per90 is not None else None
        )
        c = {
            "role_stability": None,
            "minutes_trend": difference(minutes3, minutes5),
            "attacking_involvement": attacking_involvement,
            "threat_creation_rate": threat3,
            "threat_reception_rate": None,
            "threat_realisation_rate": (
                goals3 / shots3 if goals3 is not None and shots3 is not None and shots3 > 0 else None
            ),
            "contextual_threat_score": None,
            "attacking_involvement_rate": attacking_rate,
        }

        layers = [
            LayerResult("A_temporal_football_value", "RESEARCH_ONLY", a, coverage(a),
                        cutoff.isoformat(), "Wyscout player-match event counts and lagged team progression"),
            LayerResult("B_risk_defensive_intelligence", "RESEARCH_ONLY", b, coverage(b),
                        cutoff.isoformat(), "Wyscout defensive duels/clearances and opponent event aggregates"),
            LayerResult("C_player_intelligence", "RESEARCH_ONLY", c, coverage(c),
                        cutoff.isoformat(), "Historical FPL minutes plus Wyscout threat creation/realisation"),
        ]
        integrated = integrate_player_sequence(layers, cutoff.isoformat())
        identity_verified = bool(row.get("fpl_element_id") not in (None, ""))
        research_eligible = bool(identity_verified and conservative_cutoff and prior_matches > 0 and team_prior > 0)
        counts["rows"] += 1
        counts["verified_identity_rows"] += int(identity_verified)
        counts["conservative_gameweek_cutoff_rows"] += int(conservative_cutoff)
        counts["prior_player_history_rows"] += int(prior_matches > 0)
        counts["prior_team_context_rows"] += int(team_prior > 0)
        counts["research_eligible_rows"] += int(research_eligible)
        for layer_name, features in (
            ("A_temporal_football_value", a),
            ("B_risk_defensive_intelligence", b),
            ("C_player_intelligence", c),
        ):
            for name, value in features.items():
                observed[layer_name][name] += int(value is not None)

        record = {
            "season": "2017/18",
            "fpl_element_id": row.get("fpl_element_id", ""),
            "fixture_id": row.get("fixture_id", ""),
            "kickoff_time_utc": kickoff.isoformat(),
            "feature_cutoff_time_utc": cutoff.isoformat(),
            "feature_cutoff_policy": cutoff_policy,
            "target_fpl_total_points": number(row.get("target_fpl_total_points")),
            "target_fpl_minutes": number(row.get("target_fpl_minutes")),
            "identity_verified": identity_verified,
            "research_eligible_for_analysis": research_eligible,
            "abc_status": integrated["status"],
            "abc_missing_layers": json.dumps(integrated["missing_layers"]),
            "abc_layer_status": json.dumps(integrated["layer_status"], sort_keys=True),
            "abc_source_coverage": json.dumps(integrated["source_coverage"], sort_keys=True),
            "abc_provenance": json.dumps(integrated["provenance"], sort_keys=True),
        }
        for name, value in integrated["features"].items():
            record[f"abc_{name}"] = "" if value is None else value
        output.append(record)

    report = {
        "status": "PASS_STRUCTURAL_ONLY" if output else "NO_ROWS",
        **dict(counts),
        "layer_feature_observed_row_counts": {
            layer: dict(values) for layer, values in observed.items()
        },
        "model_training_eligible": False,
        "prediction_validation": "NOT_EVALUATED",
        "point_in_time_status": "NOT_VERIFIED",
        "point_in_time_limitation": (
            "The historical provider release and FPL archive are retrospective; exact archived provider snapshots "
            "at every FPL deadline are unavailable. Same-gameweek leakage is conservatively blocked using the "
            "earliest kickoff in each FPL round, but this does not prove source-vintage availability."
        ),
        "missingness_policy": "Unsupported receiver identity, xG, pressure and role features remain null, never zero-filled.",
        "source_hashes": source_report.get("source_hashes", {}),
        "attribution": source_report.get("attribution", ""),
    }
    return output, report


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lagged-features", type=Path, required=True)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    source_report = json.loads(args.source_report.read_text(encoding="utf-8"))
    rows, report = build_panel(read_csv(args.lagged_features), source_report)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["season", "fpl_element_id", "fixture_id", "abc_status"]
    with (args.out_dir / "cta_abc_wyscout_player_fixture_panel.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (args.out_dir / "cta_abc_wyscout_integration_report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS_STRUCTURAL_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
