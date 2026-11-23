#!/usr/bin/env python3
"""Build an Opta-independent ABC feature panel from verified 11footy evidence.

This is a research adapter, not a predictor. It preserves the existing A/B/C
feature contract while leaving unavailable provider features null. Only
season-scoped verified identities and deadline-available 11footy snapshots
can contribute to the analysis-eligible cohort. Historical source-vintage
availability is not established by this adapter.
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


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def number(value):
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def truth(value):
    return str(value).strip().lower() in {"true", "1", "yes"}


def parse_time(value, field):
    if not value:
        raise ValueError(f"Missing {field}")
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def prior(row, feature, window=3):
    return number(row.get(f"cta_prior{window}_matches_{feature}_avg"))


def per90(value, minutes):
    if value is None or minutes is None or minutes <= 0:
        return None
    return value * 90.0 / minutes


def coverage(features):
    return {name: "OBSERVED" if value is not None else "MISSING"
            for name, value in features.items()}


def build_panel(rows, source_report):
    source_as_of = parse_time(
        source_report.get("source_built_at") or source_report.get("source_built_at_utc"),
        "11footy source_built_at",
    )
    source_hashes = source_report.get("source_hashes", {})
    output = []
    counts = Counter()
    observed = {layer: Counter() for layer in LAYER_FEATURES}
    seen = set()

    for row in rows:
        player_id = str(row.get("fpl_element_id") or "").strip()
        fixture_id = str(row.get("fixture_id") or "").strip()
        if not player_id or not fixture_id:
            raise ValueError("11footy target row is missing player or fixture identity")
        key = (player_id, fixture_id)
        if key in seen:
            raise ValueError(f"Duplicate 11footy player-fixture target: {key}")
        seen.add(key)

        deadline = parse_time(row.get("features_as_of_deadline"), "features_as_of_deadline")
        kickoff = parse_time(row.get("kickoff_time"), "target kickoff_time")
        if kickoff <= deadline:
            raise ValueError(f"Target fixture {fixture_id} must kick off after its FPL deadline")

        row_snapshot = row.get("cta_source_snapshot_as_of")
        if row_snapshot:
            if parse_time(row_snapshot, "cta_source_snapshot_as_of") != source_as_of:
                raise ValueError("11footy row snapshot timestamp disagrees with its source report")
        snapshot_available = truth(row.get("cta_snapshot_available_as_of_deadline")) and source_as_of <= deadline
        identity_verified = truth(row.get("identity_verified"))
        prior_count = int(number(row.get("cta_prior_matches_count")) or 0)

        minutes3, minutes5 = prior(row, "minutes_played", 3), prior(row, "minutes_played", 5)
        key_passes3, key_passes5 = prior(row, "key_passes", 3), prior(row, "key_passes", 5)
        xg3, xg5 = prior(row, "tracked_xg_sum", 3), prior(row, "tracked_xg_sum", 5)
        shots3 = prior(row, "shots", 3)
        attempts_box3 = prior(row, "attempts_inside_box", 3)
        goals3 = prior(row, "goals", 3)
        fouls3 = prior(row, "fouls_committed", 3)
        involvement = key_passes3 + shots3 if key_passes3 is not None and shots3 is not None else None

        # A: only directly observed 11footy player actions; no Opta team proxies.
        a = {
            "progressive_passes": None,
            "progressive_carries": None,
            "final_third_entries": None,
            "dangerous_receipts": None,
            "sequence_value": None,
            "recent_action_trend": None,
            "team_final_third_entries": None,
            "team_successful_dribbles": None,
            "player_key_pass_rate": per90(key_passes3, minutes3),
            "player_tracked_xg_rate": per90(xg3, minutes3),
            "recent_key_pass_trend": key_passes3 - key_passes5 if key_passes3 is not None and key_passes5 is not None else None,
            "recent_xg_trend": xg3 - xg5 if xg3 is not None and xg5 is not None else None,
        }
        # B: the selected 11footy release does not expose the event-level
        # pressure/duel/recovery features in this contract. Do not substitute
        # team-level Opta values or infer defensive actions from unrelated stats.
        b = {
            "pressure_events": None,
            "pressure_success_rate": None,
            "duel_success_rate": None,
            "defensive_actions": None,
            "turnovers_under_pressure": None,
            "opponent_threat_allowed": None,
            "defensive_exposure": None,
            "team_interceptions": None,
            "team_tackles_won": None,
            "team_ball_recoveries": None,
            "team_recoveries": None,
            "team_duels_won": None,
            "opponent_box_attempts_allowed": None,
            "player_fouls_committed_rate": per90(fouls3, minutes3),
        }
        # C: player involvement, threat and minutes stability from prior matches.
        c = {
            "role_stability": None,
            "minutes_trend": minutes3 - minutes5 if minutes3 is not None and minutes5 is not None else None,
            "attacking_involvement": involvement,
            "threat_creation_rate": per90(key_passes3, minutes3),
            "threat_reception_rate": per90(attempts_box3, minutes3),
            "threat_realisation_rate": goals3 / xg3 if goals3 is not None and xg3 is not None and xg3 > 0 else None,
            "contextual_threat_score": None,
            "attacking_involvement_rate": per90(involvement, minutes3),
        }

        if not snapshot_available:
            for features in (a, b, c):
                for name in features:
                    features[name] = None

        layers = [
            LayerResult("A_temporal_football_value", "RESEARCH_ONLY", a, coverage(a),
                        deadline.isoformat(), f"11footy source hashes={json.dumps(source_hashes, sort_keys=True)}"),
            LayerResult("B_risk_defensive_intelligence", "RESEARCH_ONLY", b, coverage(b),
                        deadline.isoformat(), "11footy only; unsupported defensive event features remain null"),
            LayerResult("C_player_intelligence", "RESEARCH_ONLY", c, coverage(c),
                        deadline.isoformat(), f"11footy source hashes={json.dumps(source_hashes, sort_keys=True)}"),
        ]
        integrated = integrate_player_sequence(layers, deadline.isoformat())
        eligible = bool(identity_verified and snapshot_available and prior_count > 0)
        counts["rows"] += 1
        counts["verified_identity_rows"] += int(identity_verified)
        counts["snapshot_available_rows"] += int(snapshot_available)
        counts["rows_with_prior_history"] += int(prior_count > 0)
        counts["analysis_eligible_rows"] += int(eligible)
        for layer, features in zip(LAYER_FEATURES, (a, b, c)):
            for name, value in features.items():
                observed[layer][name] += int(value is not None)

        record = {
            "season": row.get("season", ""),
            "fpl_element_id": player_id,
            "fixture_id": fixture_id,
            "gameweek": row.get("gameweek", ""),
            "kickoff_time": kickoff.isoformat(),
            "features_as_of_deadline": deadline.isoformat(),
            "identity_verified": identity_verified,
            "cta_snapshot_available_as_of_deadline": snapshot_available,
            "cta_prior_matches_count": prior_count,
            "research_eligible_for_analysis": eligible,
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
        "provider": "11footy_only",
        "rows": counts["rows"],
        "verified_identity_rows": counts["verified_identity_rows"],
        "snapshot_available_rows": counts["snapshot_available_rows"],
        "rows_with_prior_history": counts["rows_with_prior_history"],
        "analysis_eligible_rows": counts["analysis_eligible_rows"],
        "layer_feature_observed_row_counts": {layer: dict(values) for layer, values in observed.items()},
        "opta_dependency": False,
        "opta_features_used": False,
        "model_training_eligible": False,
        "prediction_validation": "NOT_EVALUATED",
        "point_in_time_status": "NOT_VERIFIED_FOR_RETROSPECTIVE_TRAINING",
        "identity_policy": "Only exact season-scoped verified 11footy/FPL identities can be analysis eligible.",
        "deadline_policy": "11footy snapshot and all contributing player matches must be available no later than the official FPL deadline; target fixture must kick off after deadline.",
        "missingness_policy": "Unsupported 11footy features remain null; no Opta substitution, zero filling, or inferred defensive events.",
        "scope_limitation": "The selected 11footy release does not provide the full event-level defensive and progression feature set. This adapter is an exploratory source-compatibility test, not a complete or validated ABC model.",
        "provider_attribution": source_report.get("attribution", "11footy; CC BY-NC 4.0; non-commercial use only."),
        "source_hashes": source_hashes,
    }
    return output, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--11footy-lagged", dest="footy_lagged", type=Path, required=True)
    parser.add_argument("--11footy-source-report", dest="footy_source_report", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    source_report = json.loads(args.footy_source_report.read_text(encoding="utf-8"))
    rows, report = build_panel(read_csv(args.footy_lagged), source_report)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["season", "fpl_element_id", "fixture_id", "abc_status"]
    with (args.out_dir / "cta_abc_11footy_only_panel.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    (args.out_dir / "cta_abc_11footy_only_report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS_STRUCTURAL_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
