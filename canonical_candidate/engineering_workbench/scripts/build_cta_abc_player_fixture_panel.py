#!/usr/bin/env python3
"""Integrate deadline-safe 11footy player evidence and Opta team context into A/B/C.

This produces a research-only, prospective player-fixture feature panel. It
never adds target-fixture outcomes, never fills missing features with zero,
and never treats an identity candidate as verified. The current sources cover
one season and are not a multi-season point-in-time training archive.
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


def opta_value(team_row, feature):
    if team_row is None:
        return None
    return number(team_row.get(f"opta_prior3_{feature}_avg"))


def per90(value, minutes):
    if value is None or minutes is None or minutes <= 0:
        return None
    return value * 90.0 / minutes


def coverage(features):
    return {
        name: "OBSERVED" if value is not None else "MISSING"
        for name, value in features.items()
    }


def build_panel(cta_rows, opta_team_rows, cta_source_report, opta_source_report):
    source_as_of = parse_time(
        cta_source_report.get("source_built_at") or cta_source_report.get("source_built_at_utc"),
        "11footy source_built_at",
    )
    opta_report = opta_source_report.get("team_features", opta_source_report)
    opta_as_of_value = opta_report.get("source_snapshot_as_of")
    opta_as_of = parse_time(opta_as_of_value, "Opta source_snapshot_as_of") if opta_as_of_value else None
    cta_source_hashes = cta_source_report.get("source_hashes", {})
    opta_commit = (opta_source_report.get("identity") or {}).get("source_commit", "")
    if not opta_as_of:
        raise ValueError("Opta source report must contain its pinned source snapshot timestamp")

    opta_by_fixture_team = {}
    for row in opta_team_rows:
        key = (str(row.get("fixture_id") or ""), str(row.get("team_id") or ""))
        if not all(key):
            continue
        if key in opta_by_fixture_team:
            raise ValueError(f"Duplicate Opta fixture-team key: {key}")
        opta_by_fixture_team[key] = row

    output = []
    counts = Counter()
    feature_coverage = {
        layer: Counter() for layer in LAYER_FEATURES
    }
    for row in cta_rows:
        deadline = parse_time(row.get("features_as_of_deadline"), "features_as_of_deadline")
        kickoff = parse_time(row.get("kickoff_time"), "target kickoff_time")
        if kickoff <= deadline:
            raise ValueError("Target fixture must kick off after the FPL deadline")
        cta_available = truth(row.get("cta_snapshot_available_as_of_deadline"))
        cta_snapshot = parse_time(row.get("cta_source_snapshot_as_of"), "11footy snapshot timestamp") if row.get("cta_source_snapshot_as_of") else None
        if cta_snapshot and cta_snapshot != source_as_of:
            raise ValueError("11footy row snapshot timestamp disagrees with its source report")
        cta_temporal_ok = bool(cta_available and cta_snapshot and cta_snapshot <= deadline)
        opta_temporal_ok = bool(opta_as_of and opta_as_of <= deadline)

        fixture_id = str(row.get("fixture_id") or "")
        own_team_id = str(row.get("team_id") or "")
        opponent_team_id = str(row.get("opponent_team_id") or "")
        own_team = opta_by_fixture_team.get((fixture_id, own_team_id))
        opponent_team = opta_by_fixture_team.get((fixture_id, opponent_team_id))
        own_cutoff = parse_time(own_team.get("features_as_of"), "Opta own-team feature cutoff") if own_team and own_team.get("features_as_of") else None
        opponent_cutoff = parse_time(opponent_team.get("features_as_of"), "Opta opponent feature cutoff") if opponent_team and opponent_team.get("features_as_of") else None
        opta_cutoff_ok = bool(
            opta_temporal_ok and own_team and opponent_team and own_cutoff and opponent_cutoff
            and own_cutoff <= deadline and opponent_cutoff <= deadline
            and own_team.get("feature_cutoff_policy") == "OFFICIAL_FPL_DEADLINE"
            and opponent_team.get("feature_cutoff_policy") == "OFFICIAL_FPL_DEADLINE"
        )

        # A — player threat/action evidence plus team progression context.
        a = {
            "progressive_passes": None,
            "progressive_carries": None,
            "final_third_entries": None,
            "dangerous_receipts": None,
            "sequence_value": None,
            "recent_action_trend": None,
            "team_final_third_entries": opta_value(own_team, "finalThirdEntries") if opta_cutoff_ok else None,
            "team_successful_dribbles": opta_value(own_team, "successfulDribbles") if opta_cutoff_ok else None,
            "player_key_pass_rate": per90(prior(row, "key_passes"), prior(row, "minutes_played")),
            "player_tracked_xg_rate": per90(prior(row, "tracked_xg_sum"), prior(row, "minutes_played")),
            "recent_key_pass_trend": (
                prior(row, "key_passes", 3) - prior(row, "key_passes", 5)
                if prior(row, "key_passes", 3) is not None and prior(row, "key_passes", 5) is not None
                else None
            ),
            "recent_xg_trend": (
                prior(row, "tracked_xg_sum", 3) - prior(row, "tracked_xg_sum", 5)
                if prior(row, "tracked_xg_sum", 3) is not None and prior(row, "tracked_xg_sum", 5) is not None
                else None
            ),
        }

        # B — team defensive actions and opponent threat conceded in prior matches.
        # Event-level pressure/turnover/duel-success fields are unavailable in this source.
        b = {
            "pressure_events": None,
            "pressure_success_rate": None,
            "duel_success_rate": None,
            "defensive_actions": None,
            "turnovers_under_pressure": None,
            "opponent_threat_allowed": opta_value(own_team, "opponentExpectedGoals") if opta_cutoff_ok else None,
            "defensive_exposure": opta_value(own_team, "opponentAttemptsIbox") if opta_cutoff_ok else None,
            "team_interceptions": opta_value(own_team, "interception") if opta_cutoff_ok else None,
            "team_tackles_won": opta_value(own_team, "tacklesWon") if opta_cutoff_ok else None,
            "team_ball_recoveries": opta_value(own_team, "ballRecovery") if opta_cutoff_ok else None,
            "team_recoveries": opta_value(own_team, "recoveries") if opta_cutoff_ok else None,
            "team_duels_won": opta_value(own_team, "duelWon") if opta_cutoff_ok else None,
            "opponent_box_attempts_allowed": opta_value(own_team, "opponentAttemptsIbox") if opta_cutoff_ok else None,
            "player_fouls_committed_rate": per90(prior(row, "fouls_committed"), prior(row, "minutes_played")),
        }

        # C — player role/minutes and attacking threat. A calibrated contextual
        # score is intentionally withheld until a model is trained out of sample.
        minutes3 = prior(row, "minutes_played", 3)
        minutes5 = prior(row, "minutes_played", 5)
        key_passes3 = prior(row, "key_passes", 3)
        shots3 = prior(row, "shots", 3)
        attempts_box3 = prior(row, "attempts_inside_box", 3)
        goals3 = prior(row, "goals", 3)
        xg3 = prior(row, "tracked_xg_sum", 3)
        attacking_involvement = (
            key_passes3 + shots3
            if key_passes3 is not None and shots3 is not None else None
        )
        c = {
            "role_stability": None,
            "minutes_trend": minutes3 - minutes5 if minutes3 is not None and minutes5 is not None else None,
            "attacking_involvement": attacking_involvement,
            "threat_creation_rate": per90(key_passes3, minutes3),
            "threat_reception_rate": per90(attempts_box3, minutes3),
            "threat_realisation_rate": goals3 / xg3 if goals3 is not None and xg3 is not None and xg3 > 0 else None,
            "contextual_threat_score": None,
            "attacking_involvement_rate": per90(attacking_involvement, minutes3),
        }

        if not cta_temporal_ok:
            # Preserve observed values in the raw sidecar for diagnosis, but do
            # not let unavailable-after-deadline snapshots enter any layer.
            a["player_key_pass_rate"] = None
            a["player_tracked_xg_rate"] = None
            a["recent_key_pass_trend"] = None
            a["recent_xg_trend"] = None
            b["player_fouls_committed_rate"] = None
            for key in ("minutes_trend", "attacking_involvement", "threat_creation_rate",
                        "threat_reception_rate", "threat_realisation_rate", "attacking_involvement_rate"):
                c[key] = None

        layers = [
            LayerResult("A_temporal_football_value", "RESEARCH_ONLY", a, coverage(a),
                        deadline.isoformat(), f"11footy source hashes={json.dumps(cta_source_hashes, sort_keys=True)}; Opta commit={opta_commit}"),
            LayerResult("B_risk_defensive_intelligence", "RESEARCH_ONLY", b, coverage(b),
                        deadline.isoformat(), f"Opta commit={opta_commit}; 11footy source hashes={json.dumps(cta_source_hashes, sort_keys=True)}"),
            LayerResult("C_player_intelligence", "RESEARCH_ONLY", c, coverage(c),
                        deadline.isoformat(), f"11footy source hashes={json.dumps(cta_source_hashes, sort_keys=True)}; calibrated score withheld"),
        ]
        integrated = integrate_player_sequence(layers, deadline.isoformat())
        verified = truth(row.get("identity_verified"))
        research_eligible = bool(verified and cta_temporal_ok and opta_cutoff_ok)
        counts["rows"] += 1
        counts["verified_identity_rows"] += int(verified)
        counts["cta_snapshot_available_rows"] += int(cta_temporal_ok)
        counts["opta_snapshot_available_rows"] += int(opta_temporal_ok)
        counts["opta_deadline_cutoff_rows"] += int(opta_cutoff_ok)
        counts["research_eligible_rows"] += int(research_eligible)
        for layer_name, features in (
            ("A_temporal_football_value", a),
            ("B_risk_defensive_intelligence", b),
            ("C_player_intelligence", c),
        ):
            for name, value in features.items():
                feature_coverage[layer_name][name] += int(value is not None)

        record = {
            "season": row.get("season", ""),
            "fpl_element_id": row.get("fpl_element_id", ""),
            "fixture_id": fixture_id,
            "gameweek": row.get("gameweek", ""),
            "kickoff_time": kickoff.isoformat(),
            "features_as_of_deadline": deadline.isoformat(),
            "identity_verified": verified,
            "cta_snapshot_available_as_of_deadline": cta_temporal_ok,
            "opta_snapshot_available_as_of_deadline": opta_temporal_ok,
            "opta_deadline_cutoff_verified": opta_cutoff_ok,
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
        "rows": counts["rows"],
        "verified_identity_rows": counts["verified_identity_rows"],
        "cta_snapshot_available_rows": counts["cta_snapshot_available_rows"],
        "opta_snapshot_available_rows": counts["opta_snapshot_available_rows"],
        "opta_deadline_cutoff_rows": counts["opta_deadline_cutoff_rows"],
        "research_eligible_rows": counts["research_eligible_rows"],
        "layer_feature_observed_row_counts": {
            layer: dict(values) for layer, values in feature_coverage.items()
        },
        "model_training_eligible": False,
        "prediction_validation": "NOT_EVALUATED",
        "status_limitation": (
            "One 2026/27 source snapshot is a prospective integration pilot, not a multi-season "
            "point-in-time archive. A/B/C features are research-only and must not be promoted."
        ),
        "missingness_policy": "Missing provider evidence remains null; zero is retained only when explicitly observed as numeric zero.",
        "deadline_policy": "Both provider source vintages and all feature cutoffs must be no later than the official FPL deadline.",
        "identity_policy": "Only exact season-scoped verified 11footy/FPL identities are marked eligible.",
        "target_policy": "No target-fixture outcome fields are copied into the integrated A/B/C feature panel.",
        "provider_attribution": "11footy source release 2026-11-10; Opta/PulseLive pinned commit f0f3d40f803c69bc7fac48d0748b49175e2d08ce.",
    }
    return output, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--11footy-lagged", type=Path, required=True)
    parser.add_argument("--opta-team-features", type=Path, required=True)
    parser.add_argument("--11footy-source-report", type=Path, required=True)
    parser.add_argument("--opta-source-report", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    opta_report = json.loads(args.opta_source_report.read_text(encoding="utf-8"))
    cta_report = json.loads(args.11footy_source_report.read_text(encoding="utf-8"))
    rows, report = build_panel(
        read_csv(args.11footy_lagged), read_csv(args.opta_team_features),
        cta_report, opta_report,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with (args.out_dir / "cta_abc_player_fixture_panel.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = list(rows[0]) if rows else ["season", "fpl_element_id", "fixture_id", "abc_status"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    (args.out_dir / "cta_abc_integration_report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS_STRUCTURAL_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
