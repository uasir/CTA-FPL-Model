#!/usr/bin/env python3
"""Aggregate-only CTA evidence coverage for a real FPL manager squad."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


FEATURE_KEYS = {
    "shots": "cta_prior3_matches_shots_avg",
    "shots_on_target": "cta_prior3_matches_shots_on_target_avg",
    "key_passes": "cta_prior3_matches_key_passes_avg",
    "box_attempts": "cta_prior3_matches_attempts_inside_box_avg",
    "tracked_xg": "cta_prior3_matches_tracked_xg_sum_avg",
    "big_chances": "cta_prior3_matches_big_chances_avg",
}


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def summarize_cta(cta):
    if not isinstance(cta, dict):
        cta = {}
    fixtures = cta.get("fixtures") if isinstance(cta.get("fixtures"), list) else []
    available = [
        row for row in fixtures
        if isinstance(row, dict) and row.get("snapshot_available_as_of_deadline") is True
    ]
    source = available[0] if available else next(
        (row for row in fixtures if isinstance(row, dict)), {}
    )
    identity_verified = cta.get("identity_verified") is True
    prior = int(_number(source.get("prior_matches_count")) or 0)
    features = source.get("features") if isinstance(source.get("features"), dict) else {}
    values = {
        label: value
        for label, key in FEATURE_KEYS.items()
        if (value := _number(features.get(key))) is not None
    }
    if not identity_verified:
        status = "UNVERIFIED_IDENTITY"
    elif prior <= 0:
        status = "VERIFIED_IDENTITY_NO_PRIOR_HISTORY"
    elif not values:
        status = "VERIFIED_IDENTITY_NO_FEATURE_VALUES"
    else:
        status = "RESEARCH_ONLY_EVIDENCE_AVAILABLE"
    return {
        "status": status,
        "identity_verified": identity_verified,
        "prior_matches_count": prior,
        "feature_values_present": sorted(values),
        "source_snapshot_as_of": cta.get("source_snapshot_as_of"),
        "decision_weight": 0.0,
        "ranking_effect": "NONE",
    }


def build_report(entry_id, picks_payload, snapshot):
    picks = picks_payload.get("picks")
    if not isinstance(picks, list):
        raise ValueError("Manager picks payload does not contain a picks list")
    ordered = sorted(picks, key=lambda row: int(row.get("position", 0)))
    elements = [int(row["element"]) for row in ordered]
    positions = [int(row["position"]) for row in ordered]
    if len(elements) != len(set(elements)):
        raise ValueError("Manager picks contain duplicate FPL element IDs")
    if len(positions) != len(set(positions)):
        raise ValueError("Manager picks contain duplicate squad positions")
    if any(position < 1 or position > 15 for position in positions):
        raise ValueError("Manager squad positions must be between 1 and 15")

    forecasts = snapshot.get("player_forecasts")
    if not isinstance(forecasts, list):
        raise ValueError("Forecast snapshot does not contain player_forecasts")
    by_id = {int(row["fpl_element_id"]): row for row in forecasts}
    target_gw = (
        snapshot.get("forecast_quality", {})
        .get("data_coverage", {})
        .get("target_gameweek")
    )
    if target_gw is None:
        raise ValueError("Forecast snapshot is missing target_gameweek")
    picks_event = (picks_payload.get("entry_history") or {}).get("event")
    if picks_event is not None and int(picks_event) != int(target_gw):
        raise ValueError("Manager picks event does not match the forecast target gameweek")

    summaries = []
    for pick in ordered:
        element = int(pick["element"])
        forecast = by_id.get(element)
        summaries.append({
            "position": int(pick["position"]),
            "is_starter": int(pick["position"]) <= 11,
            "is_captain": bool(pick.get("is_captain")),
            "is_vice_captain": bool(pick.get("is_vice_captain")),
            "forecast_available": forecast is not None,
            "cta": summarize_cta(forecast.get("cta") if forecast else None),
        })

    starters = [row for row in summaries if row["is_starter"]]
    bench = [row for row in summaries if not row["is_starter"]]
    status_counts = Counter(row["cta"]["status"] for row in summaries)
    feature_counts = Counter(
        feature
        for row in summaries
        for feature in row["cta"]["feature_values_present"]
    )
    history_count = sum(row["cta"]["prior_matches_count"] > 0 for row in summaries)
    evidence_count = status_counts["RESEARCH_ONLY_EVIDENCE_AVAILABLE"]
    captain = next((row for row in summaries if row["is_captain"]), None)
    vice = next((row for row in summaries if row["is_vice_captain"]), None)
    entry_history = picks_payload.get("entry_history") or {}
    report_status = (
        "PASS_MANAGER_CTA_COVERAGE"
        if len(ordered) == 15 and len(starters) == 11 and len(bench) == 4
        and all(row["forecast_available"] for row in summaries)
        else "PARTIAL_MANAGER_CTA_COVERAGE"
    )
    return {
        "status": report_status,
        "entry_id": int(entry_id),
        "target_gameweek": int(target_gw),
        "forecast_snapshot_id": snapshot.get("forecast_snapshot_id"),
        "squad_size": len(summaries),
        "starting_xi_count": len(starters),
        "bench_count": len(bench),
        "forecast_missing_squad_players": sum(not row["forecast_available"] for row in summaries),
        "squad_players_with_verified_identity": sum(row["cta"]["identity_verified"] for row in summaries),
        "squad_players_with_prior_history": history_count,
        "squad_players_with_cta_evidence": evidence_count,
        "starting_xi_with_prior_history": sum(row["cta"]["prior_matches_count"] > 0 for row in starters),
        "starting_xi_with_cta_evidence": sum(row["cta"]["status"] == "RESEARCH_ONLY_EVIDENCE_AVAILABLE" for row in starters),
        "bench_with_cta_evidence": sum(row["cta"]["status"] == "RESEARCH_ONLY_EVIDENCE_AVAILABLE" for row in bench),
        "captain_has_cta_evidence": bool(captain and captain["cta"]["status"] == "RESEARCH_ONLY_EVIDENCE_AVAILABLE"),
        "vice_captain_has_cta_evidence": bool(vice and vice["cta"]["status"] == "RESEARCH_ONLY_EVIDENCE_AVAILABLE"),
        "cta_identity_status_counts": dict(sorted(status_counts.items())),
        "cta_feature_coverage_counts": dict(sorted(feature_counts.items())),
        "source_snapshot_as_of": next(
            (row["cta"]["source_snapshot_as_of"] for row in summaries if row["cta"]["source_snapshot_as_of"]),
            None,
        ),
        "decision_use_status": "RESEARCH_ONLY_NOT_IN_BASELINE",
        "cta_features_used_in_expected_points": False,
        "cta_decision_weight_applied": False,
        "cta_ranking_effect": "NONE",
        "free_transfers_status": "NOT_READ_FROM_PUBLIC_PICKS_ENDPOINT",
        "publication_policy": "Aggregate squad coverage only; no player names, IDs or player-level CTA values are published.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--entry-id", type=int, required=True)
    parser.add_argument("--picks-json", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(
        args.entry_id,
        json.loads(args.picks_json.read_text(encoding="utf-8")),
        json.loads(args.snapshot.read_text(encoding="utf-8")),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS_MANAGER_CTA_COVERAGE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
