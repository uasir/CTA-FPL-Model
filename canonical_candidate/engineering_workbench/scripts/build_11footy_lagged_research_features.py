#!/usr/bin/env python3
"""Build strictly prior-match CTA features for an isolated provisional research panel.

This is not a production training dataset: candidate identities remain pending,
and the official FPL history snapshot may contain retrospective revisions.
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


def build_lagged_research_features(cta_rows, fpl_training_rows, fpl_report):
    if not fpl_training_rows:
        raise ValueError("FPL lagged training input is empty")

    history_by_player = defaultdict(list)
    seen_cta_keys = set()
    skipped_cta = Counter()
    for row in cta_rows:
        player_id = str(row.get("fpl_element_id", "")).strip()
        fixture_id = str(row.get("fpl_fixture_id", "")).strip()
        if not player_id or not fixture_id:
            skipped_cta["missing_player_or_fixture_id"] += 1
            continue
        key = (player_id, fixture_id)
        if key in seen_cta_keys:
            raise ValueError(f"Duplicate provisional CTA player-fixture key: {key}")
        seen_cta_keys.add(key)
        if str(row.get("identity_status", "")) != "PENDING_RESEARCH_ONLY":
            skipped_cta["not_pending_research_identity"] += 1
            continue
        if str(row.get("research_only", "")).strip().lower() not in {"true", "1", "yes"}:
            skipped_cta["not_marked_research_only"] += 1
            continue
        try:
            kickoff = parse_time(row.get("match_kickoff_utc"), "CTA match_kickoff_utc")
        except ValueError:
            skipped_cta["missing_or_invalid_match_kickoff"] += 1
            continue
        history_by_player[player_id].append({
            **row,
            "_kickoff": kickoff,
            "_kickoff_ts": kickoff.timestamp(),
        })

    for player_id in history_by_player:
        history_by_player[player_id].sort(
            key=lambda row: (row["_kickoff_ts"], str(row.get("fpl_fixture_id", "")))
        )
        times = [row["_kickoff_ts"] for row in history_by_player[player_id]]
        if len(times) != len(set(times)):
            # Multiple fixtures at the same kickoff are possible only in rare
            # data anomalies for a single player; preserve stable fixture order.
            pass

    seen_targets = set()
    output = []
    rows_with_prior = 0
    players_with_prior = set()
    coverage_by_gw = Counter()
    feature_nonempty = Counter()

    for target in fpl_training_rows:
        player_id = str(target.get("fpl_element_id", "")).strip()
        fixture_id = str(target.get("fixture_id", "")).strip()
        if not player_id or not fixture_id:
            raise ValueError("FPL target row is missing fpl_element_id or fixture_id")
        target_key = (player_id, fixture_id)
        if target_key in seen_targets:
            raise ValueError(f"Duplicate FPL target player-fixture key: {target_key}")
        seen_targets.add(target_key)

        deadline = parse_time(target.get("features_as_of_deadline"), "features_as_of_deadline")
        target_kickoff = parse_time(target.get("kickoff_time"), "target kickoff_time")
        if target_kickoff <= deadline:
            raise ValueError(
                f"Target fixture {fixture_id} does not kick off after its feature deadline"
            )

        history = history_by_player.get(player_id, [])
        timestamps = [row["_kickoff_ts"] for row in history]
        cutoff_index = bisect.bisect_left(timestamps, deadline.timestamp())
        prior = [
            row for row in history[:cutoff_index]
            if str(row.get("fpl_fixture_id", "")) != fixture_id
        ]
        prior3 = prior[-3:]
        prior5 = prior[-5:]
        has_prior = bool(prior)
        if has_prior:
            rows_with_prior += 1
            players_with_prior.add(player_id)
            coverage_by_gw[str(target.get("gameweek", ""))] += 1

        row_out = {
            "season": target.get("season", ""),
            "fpl_element_id": player_id,
            "fixture_id": fixture_id,
            "gameweek": target.get("gameweek", ""),
            "kickoff_time": target.get("kickoff_time", ""),
            "features_as_of_deadline": deadline.isoformat(),
            "cta_prior_matches_count": len(prior),
            "cta_prior3_matches_count": len(prior3),
            "cta_prior5_matches_count": len(prior5),
            "identity_status": "PENDING_RESEARCH_ONLY" if has_prior else "NO_PROVISIONAL_CTA_HISTORY",
            "research_only": True,
            "target_minutes": target.get("target_minutes", ""),
            "target_total_points": target.get("target_total_points", ""),
            "target_goals": target.get("target_goals", ""),
            "target_assists": target.get("target_assists", ""),
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

    report = {
        "status": "PASS_LAGGED_RESEARCH_FEATURES_BUILT",
        "rows": len(output),
        "unique_players": len({row["fpl_element_id"] for row in output}),
        "unique_fixtures": len({row["fixture_id"] for row in output}),
        "gameweeks": sorted({int(row["gameweek"]) for row in output if str(row["gameweek"]).isdigit()}),
        "rows_with_prior_cta_history": rows_with_prior,
        "rows_without_prior_cta_history": len(output) - rows_with_prior,
        "players_with_prior_cta_history": len(players_with_prior),
        "coverage_by_gameweek": dict(sorted(coverage_by_gw.items(), key=lambda item: int(item[0]) if item[0].isdigit() else 0)),
        "prior_feature_coverage_rows": dict(feature_nonempty),
        "source_cta_research_rows": len(cta_rows),
        "source_cta_rows_skipped": dict(skipped_cta),
        "temporal_policy": (
            "For every target player-fixture, CTA features use only provisional player-match rows "
            "whose exact match_kickoff_utc is strictly earlier than features_as_of_deadline. "
            "Same-fixture and same-deadline/future matches are excluded."
        ),
        "rolling_window_unit": "previous 3 and 5 player matches, not gameweeks",
        "target_policy": "FPL target columns are carried for research only and are never included in CTA feature calculations.",
        "identity_status": "PENDING_RESEARCH_ONLY; no identity is promoted or production joined.",
        "fpl_point_in_time_status": fpl_report.get("point_in_time_status", "UNKNOWN"),
        "fpl_point_in_time_caveat": fpl_report.get("point_in_time_caveat", "No FPL point-in-time report supplied."),
        "prediction_training_eligible": False,
        "production_eligible": False,
        "eligibility_reason": (
            "The provisional provider identities remain pending and the current official FPL history "
            "snapshot is not verified as point-in-time data. This dataset is a leakage-guarded research "
            "feature build only, not an approved backtest or production training source."
        ),
        "publication_policy": "Player-level lagged research rows remain inside the Actions runner; aggregate metrics only.",
    }
    return output, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cta-panel", type=Path, required=True)
    parser.add_argument("--fpl-training", type=Path, required=True)
    parser.add_argument("--fpl-report", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    fpl_report = json.loads(args.fpl_report.read_text(encoding="utf-8"))
    rows, report = build_lagged_research_features(
        read_csv(args.cta_panel), read_csv(args.fpl_training), fpl_report
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "11footy_lagged_research_features.csv", rows)
    (args.out_dir / "11footy_lagged_research_report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
