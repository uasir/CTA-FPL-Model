#!/usr/bin/env python3
"""Join verified Wyscout player-match threat features to historical FPL outcomes.

Only cross-provider verified identities are admitted. Match joins use the
existing exact-date/opponent/home-away fixture resolver. Lagged features use
strictly earlier FPL kickoff timestamps; same-match Wyscout features never
enter that match's predictor row.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from build_wyscout_fpl_identity_candidates import (
    as_int,
    as_number,
    build_fixture_index,
    build_fpl_team_names,
    build_wyscout_match_fixture_map,
    read_csv,
)

FEATURES = (
    "pass_attempts", "pass_completions", "key_pass_attempts",
    "smart_pass_attempts", "through_pass_attempts", "opportunity_pass_attempts",
    "progressive_pass_attempts", "progressive_pass_completions",
    "final_third_entry_pass_attempts", "danger_zone_entry_pass_attempts",
    "threat_creation_pass_attempts", "threat_creation_pass_completions",
    "progressive_carry_attempts", "shot_attempts", "accurate_shot_attempts",
    "shot_opportunity_attempts", "dangerous_ball_losses", "offside_events",
    "duel_events", "duels_won", "duels_lost",
    "ground_defensive_duel_events", "ground_defensive_duels_won",
    "ground_defensive_duels_lost", "aerial_duel_events",
    "aerial_duels_won", "aerial_duels_lost", "clearance_events",
    "foul_events", "interception_events",
)
TEAM_A_FEATURES = (
    "progressive_pass_completions", "final_third_entry_pass_attempts",
    "danger_zone_entry_pass_attempts", "threat_creation_pass_attempts",
    "progressive_carry_attempts",
)
TEAM_B_FEATURES = (
    "ground_defensive_duel_events", "ground_defensive_duels_won",
    "ground_defensive_duels_lost", "aerial_duel_events",
    "aerial_duels_won", "aerial_duels_lost", "clearance_events",
    "foul_events", "interception_events", "dangerous_ball_losses",
)
OPPONENT_ALLOWED_FEATURES = (
    "shot_attempts", "shot_opportunity_attempts",
    "threat_creation_pass_attempts", "danger_zone_entry_pass_attempts",
    "progressive_pass_completions",
)
TARGETS = ("total_points", "minutes", "goals_scored", "assists", "bonus", "bps")


def parse_kickoff(value):
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Historical FPL row is missing kickoff_time")
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"kickoff_time must be timezone-aware: {raw}")
    return parsed.astimezone(timezone.utc)


def verified_identity_map(crosswalk_rows):
    mapping = {}
    reverse = {}
    for row in crosswalk_rows:
        if row.get("verification_status") != "VERIFIED_CROSS_PROVIDER_IDENTITY_AND_FPL_HISTORY":
            continue
        provider_id = as_int(row.get("provider_player_id"))
        fpl_id = as_int(row.get("fpl_element_id"))
        if provider_id is None or fpl_id is None:
            raise ValueError("Verified crosswalk row has an invalid numeric identity")
        if provider_id in mapping or fpl_id in reverse:
            raise ValueError("Verified crosswalk must be one-to-one for Wyscout and FPL IDs")
        mapping[provider_id] = fpl_id
        reverse[fpl_id] = provider_id
    return mapping


def build_verified_panel(player_match_rows, crosswalk_rows, fpl_history, match_to_fixture):
    identity = verified_identity_map(crosswalk_rows)
    history_by_key = {}
    fixture_kickoff_by_id = {}
    for row in fpl_history:
        player_id = as_int(row.get("element"))
        fixture_id = as_int(row.get("fixture"))
        if player_id is None or fixture_id is None:
            continue
        key = (player_id, fixture_id)
        if key in history_by_key:
            raise ValueError(f"Duplicate historical FPL player-fixture row: {key}")
        history_by_key[key] = row
        kickoff = parse_kickoff(row.get("kickoff_time"))
        existing = fixture_kickoff_by_id.get(fixture_id)
        if existing is not None and existing != kickoff:
            raise ValueError(f"Conflicting kickoff timestamps for historical fixture {fixture_id}")
        fixture_kickoff_by_id[fixture_id] = kickoff

    # Team context is aggregated from the complete provider panel before player
    # identity filtering. Unverified players contribute only to team totals.
    team_match_stats = defaultdict(Counter)
    team_match_opponents = {}
    for source_row in player_match_rows:
        match_id = as_int(source_row.get("provider_match_id"))
        team_id = as_int(source_row.get("provider_team_id"))
        opponent_id = as_int(source_row.get("opponent_team_id"))
        if match_id is None or team_id is None or team_id <= 0:
            continue
        key = (match_id, team_id)
        if opponent_id is not None:
            prior_opponent = team_match_opponents.get(key)
            if prior_opponent is not None and prior_opponent != opponent_id:
                raise ValueError(f"Conflicting opponent IDs for Wyscout team-match {key}")
            team_match_opponents[key] = opponent_id
        for feature in FEATURES:
            value = as_number(source_row.get(feature))
            if value is not None:
                team_match_stats[key][feature] += value

    team_history_by_id = defaultdict(list)
    for (match_id, team_id), own_stats in team_match_stats.items():
        fixture_id = match_to_fixture.get(match_id)
        opponent_id = team_match_opponents.get((match_id, team_id))
        kickoff = fixture_kickoff_by_id.get(int(fixture_id)) if fixture_id is not None else None
        if fixture_id is None or kickoff is None or opponent_id is None:
            continue
        opponent_stats = team_match_stats.get((match_id, opponent_id), Counter())
        team_history_by_id[team_id].append({
            "provider_match_id": match_id,
            "fixture_id": int(fixture_id),
            "kickoff_time": kickoff,
            "own_stats": own_stats,
            "opponent_stats": opponent_stats,
        })
    for rows in team_history_by_id.values():
        rows.sort(key=lambda item: (item["kickoff_time"], item["fixture_id"]))

    seen_provider_keys = set()
    panel = []
    counts = Counter()
    for row in player_match_rows:
        provider_id = as_int(row.get("provider_player_id"))
        match_id = as_int(row.get("provider_match_id"))
        if provider_id is None or provider_id <= 0 or match_id is None or match_id <= 0:
            counts["invalid_provider_keys"] += 1
            continue
        if provider_id not in identity:
            counts["unverified_identity_rows_excluded"] += 1
            continue
        key = (provider_id, match_id)
        if key in seen_provider_keys:
            raise ValueError(f"Duplicate verified Wyscout player-match row: {key}")
        seen_provider_keys.add(key)
        fixture_id = match_to_fixture.get(match_id)
        if fixture_id is None:
            counts["unmapped_fixture_rows_excluded"] += 1
            continue
        fpl_id = identity[provider_id]
        outcome = history_by_key.get((fpl_id, int(fixture_id)))
        if outcome is None:
            counts["missing_fpl_outcome_rows_excluded"] += 1
            continue
        kickoff = parse_kickoff(outcome.get("kickoff_time"))
        record = {
            "season": "2017/18",
            "provider": "Wyscout",
            "provider_player_id": provider_id,
            "provider_match_id": match_id,
            "provider_team_id": as_int(row.get("provider_team_id")),
            "opponent_team_id": as_int(row.get("opponent_team_id")),
            "fpl_element_id": fpl_id,
            "fixture_id": int(fixture_id),
            "kickoff_time_utc": kickoff.isoformat(),
            "match_date": str(row.get("match_date") or "")[:10],
            "fpl_minutes": as_number(outcome.get("minutes")),
            "fpl_total_points": as_number(outcome.get("total_points")),
            "fpl_goals_scored": as_number(outcome.get("goals_scored")),
            "fpl_assists": as_number(outcome.get("assists")),
            "fpl_bonus": as_number(outcome.get("bonus")),
            "fpl_bps": as_number(outcome.get("bps")),
        }
        for feature in FEATURES:
            record[feature] = as_number(row.get(feature))
        panel.append(record)
        counts["verified_player_fixture_rows_joined"] += 1

    panel.sort(key=lambda row: (row["fpl_element_id"], row["kickoff_time_utc"], row["fixture_id"]))
    lagged = []
    by_player = defaultdict(list)
    for row in panel:
        by_player[row["fpl_element_id"]].append(row)
    for player_id, rows in by_player.items():
        for index, target in enumerate(rows):
            target_time = parse_kickoff(target["kickoff_time_utc"])
            prior = [candidate for candidate in rows[:index]
                     if parse_kickoff(candidate["kickoff_time_utc"]) < target_time]
            record = {
                "fpl_element_id": player_id,
                "fixture_id": target["fixture_id"],
                "provider_match_id": target["provider_match_id"],
                "provider_team_id": target["provider_team_id"],
                "opponent_team_id": target["opponent_team_id"],
                "kickoff_time_utc": target["kickoff_time_utc"],
                "target_fpl_total_points": target["fpl_total_points"],
                "target_fpl_minutes": target["fpl_minutes"],
                "prior_matches_count": len(prior),
                "prior_3_matches_count": min(3, len(prior)),
                "prior_5_matches_count": min(5, len(prior)),
            }
            for target_field in ("fpl_total_points", "fpl_minutes"):
                for window in (3, 5):
                    sample = prior[-window:]
                    values = [candidate[target_field] for candidate in sample if candidate[target_field] is not None]
                    record[f"{target_field}_prior_{window}_avg"] = (
                        sum(values) / len(values) if values else None
                    )
            team_prior = [
                candidate for candidate in team_history_by_id.get(target["provider_team_id"], [])
                if candidate["kickoff_time"] < target_time
                and candidate["provider_match_id"] != target["provider_match_id"]
            ]
            record["team_prior_matches_count"] = len(team_prior)
            for feature in TEAM_A_FEATURES + TEAM_B_FEATURES:
                for window in (3, 5):
                    sample = team_prior[-window:]
                    values = [item["own_stats"].get(feature) for item in sample
                              if item["own_stats"].get(feature) is not None]
                    record[f"team_{feature}_prior_{window}_avg"] = (
                        sum(values) / len(values) if values else None
                    )
            for feature in OPPONENT_ALLOWED_FEATURES:
                for window in (3, 5):
                    sample = team_prior[-window:]
                    values = [item["opponent_stats"].get(feature) for item in sample
                              if item["opponent_stats"].get(feature) is not None]
                    record[f"opponent_{feature}_allowed_prior_{window}_avg"] = (
                        sum(values) / len(values) if values else None
                    )

            for feature in FEATURES:
                for window in (3, 5):
                    sample = prior[-window:]
                    values = [candidate[feature] for candidate in sample if candidate[feature] is not None]
                    record[f"{feature}_prior_{window}_avg"] = (
                        sum(values) / len(values) if values else None
                    )
                    per90_values = [
                        candidate[feature] * 90.0 / candidate["fpl_minutes"]
                        for candidate in sample
                        if candidate[feature] is not None
                        and candidate["fpl_minutes"] is not None
                        and candidate["fpl_minutes"] > 0
                    ]
                    record[f"{feature}_per90_prior_{window}_avg"] = (
                        sum(per90_values) / len(per90_values) if per90_values else None
                    )
                all_values = [candidate[feature] for candidate in prior if candidate[feature] is not None]
                record[f"{feature}_prior_season_total"] = sum(all_values) if all_values else None
            lagged.append(record)
    lagged.sort(key=lambda row: (row["fpl_element_id"], row["kickoff_time_utc"], row["fixture_id"]))
    counts["panel_rows"] = len(panel)
    counts["lagged_rows"] = len(lagged)
    counts["unique_verified_fpl_players"] = len({row["fpl_element_id"] for row in panel})
    counts["rows_with_prior_history"] = sum(row["prior_matches_count"] > 0 for row in lagged)
    counts["rows_with_prior_team_context"] = sum(row["team_prior_matches_count"] > 0 for row in lagged)
    counts["team_context_team_match_rows"] = sum(len(rows) for rows in team_history_by_id.values())
    report = {
        "status": "PASS_VERIFIED_WYSCOUT_FPL_PANEL_BUILT" if panel else "NO_VERIFIED_PANEL_ROWS",
        "season": "2017/18",
        "provider": "Wyscout",
        "verified_identity_count": len(identity),
        "match_fixture_map_count": len(match_to_fixture),
        **dict(counts),
        "team_context_policy": (
            "Team-match aggregates use all Wyscout player event rows, including players without a verified FPL identity, "
            "only for team-level context. Player-specific rows remain restricted to verified identities; team and opponent "
            "context is lagged strictly before the target FPL kickoff."
        ),
        "predictor_policy": (
            "Lagged features use only earlier player-match rows whose mapped FPL kickoff_time is "
            "strictly earlier than the target fixture kickoff_time. Same-match provider metrics are "
            "kept in the research panel and excluded from that match's predictor row."
        ),
        "validation_status": "PREDICTIVE_VALIDATION_NOT_YET_RUN",
        "limitations": [
            "One historical EPL season only; this is a research bridge, not current-season coverage.",
            "Wyscout public events have no receiver IDs or xG; event-count and geometric threat proxies are not calibrated CTA scores.",
            "Historical FPL records may contain retrospective corrections and are not a point-in-time archive.",
            "11footy was used only as independent identity corroboration; its CC BY-NC 4.0 terms require non-commercial use.",
            "No CTA composite or FPL points uplift is claimed by this panel build."
        ],
        "attribution": (
            "Wyscout: Pappalardo and Massucco (2019), CC BY 4.0. "
            "Historical FPL data remains subject to Fantasy Premier League rights."
        ),
    }
    return panel, lagged, report


def write_csv(path, rows, fallback_fields):
    fields = list(rows[0]) if rows else fallback_fields
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wyscout-player-match", type=Path, required=True)
    parser.add_argument("--cross-provider-crosswalk", type=Path, required=True)
    parser.add_argument("--fpl-gameweek-history", type=Path, required=True)
    parser.add_argument("--fpl-team-list", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    player_match = read_csv(args.wyscout_player_match)
    crosswalk = read_csv(args.cross_provider_crosswalk)
    fpl_history = read_csv(args.fpl_gameweek_history)
    team_names = build_fpl_team_names(read_csv(args.fpl_team_list))
    fixture_index, _ = build_fixture_index(fpl_history, team_names)
    match_to_fixture, fixture_statuses, _ = build_wyscout_match_fixture_map(player_match, fixture_index)
    panel, lagged, report = build_verified_panel(player_match, crosswalk, fpl_history, match_to_fixture)
    report["fixture_mapping_statuses"] = dict(fixture_statuses)
    report["source_hashes"] = {
        "wyscout_player_match_sha256": hashlib.sha256(args.wyscout_player_match.read_bytes()).hexdigest(),
        "cross_provider_crosswalk_sha256": hashlib.sha256(args.cross_provider_crosswalk.read_bytes()).hexdigest(),
        "historical_fpl_gameweek_history_sha256": hashlib.sha256(args.fpl_gameweek_history.read_bytes()).hexdigest(),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "wyscout_verified_fpl_player_match_panel.csv", panel, [
        "season", "provider", "provider_player_id", "provider_match_id", "fpl_element_id",
        "fixture_id", "kickoff_time_utc", "fpl_total_points",
    ])
    write_csv(args.out_dir / "wyscout_lagged_fpl_research_features.csv", lagged, [
        "fpl_element_id", "fixture_id", "kickoff_time_utc", "target_fpl_total_points",
        "target_fpl_minutes", "prior_matches_count",
    ])
    (args.out_dir / "wyscout_verified_fpl_panel_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
