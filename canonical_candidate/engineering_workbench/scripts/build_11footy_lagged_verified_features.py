#!/usr/bin/env python3
"""Build deadline-safe upcoming FPL CTA features from verified 11footy player matches.

This is a research sidecar, not a production forecast input. It requires a
verified provider-to-FPL identity join and also checks that the pinned
provider snapshot itself existed before each target deadline.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

CTA_FEATURES = (
    "minutes_played", "goals", "assists", "own_goals", "shots",
    "shots_on_target", "key_passes", "attempts", "attempts_inside_box",
    "attempts_outside_box", "big_chances", "offsides", "fouls_suffered",
    "fouls_committed", "tracked_shots", "tracked_shots_with_xg", "tracked_xg_sum",
)


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else (
        ["season", "fpl_element_id", "fixture_id", "gameweek",
         "features_as_of_deadline", "cta_prior_matches_count",
         "identity_status", "research_only"]
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_time(value, field_name):
    if value in (None, ""):
        raise ValueError(f"Missing {field_name}")
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def number(value):
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def mean_known(rows, feature):
    values = [number(row.get(feature)) for row in rows]
    values = [value for value in values if value is not None]
    return round(sum(values) / len(values), 8) if values else ""


def sum_known(rows, feature):
    values = [number(row.get(feature)) for row in rows]
    values = [value for value in values if value is not None]
    return round(sum(values), 8) if values else ""


def build_upcoming_targets(players, fixtures, bootstrap, source_metadata, target_gameweek=None):
    events = {
        int(row["id"]): row
        for row in bootstrap.get("events", [])
        if row.get("id") is not None and row.get("deadline_time")
    }
    fetched_at = parse_time(
        source_metadata.get("fetched_at_utc"), "FPL source fetched_at_utc"
    )
    if target_gameweek in (None, ""):
        target_gameweek = source_metadata.get("next_deadline_event_id")
    if target_gameweek in (None, ""):
        future = []
        for event_id, event in events.items():
            deadline = parse_time(event.get("deadline_time"), "FPL event deadline_time")
            if deadline > fetched_at:
                future.append((deadline, event_id))
        if not future:
            raise ValueError("No upcoming FPL gameweek deadline is available")
        target_gameweek = min(future)[1]
    target_gameweek = int(target_gameweek)
    event = events.get(target_gameweek)
    if event is None:
        raise ValueError(f"Target gameweek {target_gameweek} has no official deadline")
    deadline = parse_time(event["deadline_time"], "target gameweek deadline_time")

    players_by_team = defaultdict(list)
    for player in players:
        team_id = str(player.get("team_id") or "").strip()
        element_id = str(player.get("fpl_element_id") or "").strip()
        if team_id and element_id:
            players_by_team[team_id].append(player)

    targets = []
    fixture_ids = set()
    for fixture in fixtures:
        if str(fixture.get("gameweek") or "") != str(target_gameweek):
            continue
        fixture_id = str(fixture.get("fixture_id") or "").strip()
        kickoff_value = fixture.get("kickoff_time")
        if not fixture_id or not kickoff_value:
            continue
        kickoff = parse_time(kickoff_value, "FPL fixture kickoff_time")
        if kickoff <= deadline:
            continue
        home_id = str(fixture.get("team_h_id") or "").strip()
        away_id = str(fixture.get("team_a_id") or "").strip()
        if not home_id or not away_id:
            continue
        fixture_ids.add(fixture_id)
        for team_id, opponent_id, was_home in (
            (home_id, away_id, True),
            (away_id, home_id, False),
        ):
            for player in players_by_team.get(team_id, []):
                targets.append({
                    "season": player.get("season", ""),
                    "fpl_element_id": str(player["fpl_element_id"]),
                    "fpl_player_code": str(player.get("fpl_player_code") or ""),
                    "fpl_player_name": str(player.get("player_name") or ""),
                    "team_id": team_id,
                    "opponent_team_id": opponent_id,
                    "was_home": was_home,
                    "fixture_id": fixture_id,
                    "gameweek": str(target_gameweek),
                    "features_as_of_deadline": deadline.isoformat(),
                    "kickoff_time": kickoff.isoformat(),
                })
    report = {
        "target_gameweek": target_gameweek,
        "target_deadline": deadline.isoformat(),
        "target_fixture_count": len(fixture_ids),
        "target_player_fixture_rows": len(targets),
        "target_players": len({row["fpl_element_id"] for row in targets}),
        "target_fixture_ids": sorted(fixture_ids),
    }
    return targets, report


def build_lagged_verified_features(
    cta_rows, targets, source_report, fpl_source_metadata=None, verified_fpl_element_ids=None
):
    if not targets:
        raise ValueError("Upcoming FPL target fixture rows are empty")
    if not source_report.get("join_ready"):
        raise ValueError("11footy/FPL player-match source report is not join-ready")
    if int(source_report.get("verified_crosswalk_rows") or 0) < 1:
        raise ValueError("No verified 11footy-to-FPL player identities are available")

    source_built_at = None
    source_built_at_error = None
    try:
        source_built_at = parse_time(
            source_report.get("source_built_at"), "11footy source_built_at"
        )
    except (TypeError, ValueError) as exc:
        source_built_at_error = str(exc)

    history_by_player = defaultdict(list)
    seen_cta_keys = set()
    skipped = Counter()
    for row in cta_rows:
        if str(row.get("join_status") or "") != "VERIFIED_IDENTITY_AND_FIXTURE":
            skipped["not_verified_identity_and_fixture"] += 1
            continue
        player_id = str(row.get("fpl_element_id") or "").strip()
        fixture_id = str(row.get("fpl_fixture_id") or "").strip()
        if not player_id or not fixture_id:
            skipped["missing_player_or_fixture_id"] += 1
            continue
        key = (player_id, fixture_id)
        if key in seen_cta_keys:
            raise ValueError(f"Duplicate verified CTA player-fixture key: {key}")
        seen_cta_keys.add(key)
        try:
            kickoff = parse_time(row.get("match_kickoff_utc"), "CTA match_kickoff_utc")
        except ValueError:
            skipped["missing_or_invalid_match_kickoff"] += 1
            continue
        history_by_player[player_id].append({
            **row, "_kickoff": kickoff, "_kickoff_ts": kickoff.timestamp()
        })

    for player_id in history_by_player:
        history_by_player[player_id].sort(
            key=lambda row: (row["_kickoff_ts"], str(row.get("fpl_fixture_id", "")))
        )

    verified_ids = set(str(value) for value in (verified_fpl_element_ids or history_by_player.keys()))
    output = []
    rows_with_prior = 0
    target_rows_verified_identity = 0
    target_rows_unverified_identity = 0
    rows_snapshot_available = 0
    players_with_prior = set()
    coverage_by_gw = Counter()
    feature_nonempty = Counter()
    seen_targets = set()
    rows_snapshot_unavailable = 0

    for target in targets:
        player_id = str(target.get("fpl_element_id") or "").strip()
        fixture_id = str(target.get("fixture_id") or "").strip()
        if not player_id or not fixture_id:
            raise ValueError("FPL target row is missing fpl_element_id or fixture_id")
        target_key = (player_id, fixture_id)
        if target_key in seen_targets:
            raise ValueError(f"Duplicate FPL target player-fixture key: {target_key}")
        seen_targets.add(target_key)

        deadline = parse_time(
            target.get("features_as_of_deadline"), "features_as_of_deadline"
        )
        target_kickoff = parse_time(target.get("kickoff_time"), "target kickoff_time")
        if target_kickoff <= deadline:
            raise ValueError(
                f"Target fixture {fixture_id} does not kick off after its feature deadline"
            )

        snapshot_available = source_built_at is not None and source_built_at <= deadline
        if snapshot_available:
            rows_snapshot_available += 1
        else:
            rows_snapshot_unavailable += 1

        identity_verified = player_id in verified_ids
        if identity_verified:
            target_rows_verified_identity += 1
        else:
            target_rows_unverified_identity += 1
        history = history_by_player.get(player_id, [])
        timestamps = [row["_kickoff_ts"] for row in history]
        cutoff_index = (
            bisect.bisect_left(timestamps, deadline.timestamp())
            if snapshot_available else 0
        )
        prior = [
            row for row in history[:cutoff_index]
            if str(row.get("fpl_fixture_id") or "") != fixture_id
        ]
        prior3 = prior[-3:]
        prior5 = prior[-5:]
        has_prior = bool(prior)
        if has_prior:
            rows_with_prior += 1
            players_with_prior.add(player_id)
            coverage_by_gw[str(target.get("gameweek") or "")] += 1

        if not snapshot_available:
            identity_status = "SOURCE_SNAPSHOT_AFTER_DEADLINE"
        elif not identity_verified:
            identity_status = "NO_VERIFIED_IDENTITY"
        elif has_prior:
            identity_status = "VERIFIED_IDENTITY_AND_PRIOR_CTA_HISTORY"
        else:
            identity_status = "VERIFIED_IDENTITY_NO_PRIOR_HISTORY"

        row_out = {
            "season": target.get("season", ""),
            "fpl_element_id": player_id,
            "fpl_player_code": target.get("fpl_player_code", ""),
            "fpl_player_name": target.get("fpl_player_name", ""),
            "fixture_id": fixture_id,
            "team_id": target.get("team_id", ""),
            "opponent_team_id": target.get("opponent_team_id", ""),
            "was_home": target.get("was_home", ""),
            "gameweek": target.get("gameweek", ""),
            "kickoff_time": target.get("kickoff_time", ""),
            "features_as_of_deadline": deadline.isoformat(),
            "cta_source_snapshot_as_of": source_built_at.isoformat() if source_built_at else "",
            "cta_snapshot_available_as_of_deadline": snapshot_available,
            "cta_prior_matches_count": len(prior),
            "cta_prior3_matches_count": len(prior3),
            "cta_prior5_matches_count": len(prior5),
            "identity_verified": identity_verified,
            "identity_status": identity_status,
            "research_only": True,
            "decision_use_status": "RESEARCH_ONLY_NOT_IN_BASELINE",
        }
        for feature in CTA_FEATURES:
            value3 = mean_known(prior3, feature)
            value5 = mean_known(prior5, feature)
            value_season = sum_known(prior, feature)
            row_out[f"cta_prior3_matches_{feature}_avg"] = value3
            row_out[f"cta_prior5_matches_{feature}_avg"] = value5
            row_out[f"cta_season_to_date_{feature}_sum"] = value_season
            feature_nonempty[feature] += int(value3 != "")
        output.append(row_out)

    status = (
        "BLOCKED_UNKNOWN_SOURCE_SNAPSHOT_TIME" if source_built_at is None
        else "PASS_LAGGED_VERIFIED_FEATURES_BUILT" if rows_with_prior
        else "NO_PRIOR_VERIFIED_CTA_COVERAGE"
    )
    report = {
        "status": status,
        "rows": len(output),
        "unique_players": len({row["fpl_element_id"] for row in output}),
        "unique_fixtures": len({row["fixture_id"] for row in output}),
        "gameweeks": sorted({int(row["gameweek"]) for row in output if str(row["gameweek"]).isdigit()}),
        "verified_crosswalk_rows": source_report.get("verified_crosswalk_rows", 0),
        "verified_player_match_panel_rows": source_report.get("verified_player_match_panel_rows", 0),
        "source_snapshot_as_of": source_built_at.isoformat() if source_built_at else "",
        "source_snapshot_time_error": source_built_at_error,
        "rows_with_source_snapshot_available_as_of_deadline": rows_snapshot_available,
        "rows_without_source_snapshot_available_as_of_deadline": rows_snapshot_unavailable,
        "rows_with_prior_cta_history": rows_with_prior,
        "rows_without_prior_cta_history": len(output) - rows_with_prior,
        "target_rows_with_verified_identity": target_rows_verified_identity,
        "target_rows_without_verified_identity": target_rows_unverified_identity,
        "verified_fpl_element_ids_available": len(verified_ids),
        "players_with_prior_cta_history": len(players_with_prior),
        "coverage_by_gameweek": dict(sorted(coverage_by_gw.items())),
        "prior_feature_coverage_rows": dict(feature_nonempty),
        "source_cta_rows": len(cta_rows),
        "source_cta_rows_skipped": dict(skipped),
        "target_gameweeks": sorted({int(row["gameweek"]) for row in output if str(row["gameweek"]).isdigit()}),
        "temporal_policy": (
            "The pinned 11footy source snapshot must have been built no later than the target "
            "FPL deadline, and each contributing player match must have kicked off strictly "
            "before that deadline. The target fixture is excluded."
        ),
        "rolling_window_unit": "previous 3 and 5 verified player matches, not gameweeks",
        "target_policy": "Only future FPL player-fixture targets are generated; no target outcome enters CTA features.",
        "identity_status": "VERIFIED_IDENTITY_AND_FIXTURE",
        "fpl_snapshot_fetched_at_utc": (fpl_source_metadata or {}).get("fetched_at_utc", ""),
        "fpl_point_in_time_status": "NOT_APPLICABLE_TO_FUTURE_TARGET_FEATURES",
        "prediction_training_eligible": False,
        "production_eligible": False,
        "decision_use_status": "RESEARCH_ONLY_NOT_IN_BASELINE",
        "eligibility_reason": (
            "The provider-to-FPL identities and fixture joins are verified, but the CTA feature "
            "signal has not yet passed multi-match calibration, independent review and out-of-sample "
            "FPL decision-value testing. Features remain a research sidecar."
        ),
        "source_hashes": source_report.get("source_hashes", {}),
        "attribution": source_report.get("attribution", "11footy; CC BY-NC 4.0; non-commercial use only."),
        "publication_policy": "Player-level lagged CTA features remain inside the workflow runner; aggregate metrics only.",
    }
    return output, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cta-panel", type=Path, required=True)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--fpl-players", type=Path, required=True)
    parser.add_argument("--fpl-fixtures", type=Path, required=True)
    parser.add_argument("--bootstrap", type=Path, required=True)
    parser.add_argument("--source-metadata", type=Path, required=True)
    parser.add_argument("--identity-crosswalk", type=Path)
    parser.add_argument("--target-gameweek", type=int)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    source_report = json.loads(args.source_report.read_text(encoding="utf-8"))
    bootstrap = json.loads(args.bootstrap.read_text(encoding="utf-8"))
    source_metadata = json.loads(args.source_metadata.read_text(encoding="utf-8"))
    targets, target_report = build_upcoming_targets(
        read_csv(args.fpl_players), read_csv(args.fpl_fixtures),
        bootstrap, source_metadata, args.target_gameweek,
    )
    verified_ids = None
    if args.identity_crosswalk:
        verified_ids = {
            str(row.get("fpl_element_id") or "").strip()
            for row in read_csv(args.identity_crosswalk)
            if str(row.get("fpl_element_id") or "").strip()
        }
    rows, report = build_lagged_verified_features(
        read_csv(args.cta_panel), targets, source_report, source_metadata, verified_ids
    )
    report["upcoming_target_summary"] = target_report
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "11footy_lagged_verified_upcoming_features.csv", rows)
    (args.out_dir / "11footy_lagged_verified_upcoming_report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
