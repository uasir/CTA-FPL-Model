#!/usr/bin/env python3
"""Build player-match contextual-threat features from the public Wyscout EPL 2017/18 events.

This is a provider-native research layer. It does not assign FPL identities,
receiver identities, xG, or model-ready status.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ACCURATE_TAG = 1801
GOAL_TAG = 101
OWN_GOAL_TAG = 102
ASSIST_TAG = 301
KEY_PASS_TAG = 302
OPPORTUNITY_TAG = 201
THROUGH_TAG = 901
DANGEROUS_LOSS_TAG = 2001

FIELDS = [
    "season", "competition", "provider", "provider_match_id", "match_date",
    "gameweek", "provider_player_id", "provider_player_name",
    "provider_team_id", "provider_team_name", "opponent_team_id",
    "opponent_team_name", "home_away", "event_rows",
    "pass_attempts", "pass_completions", "key_pass_attempts",
    "smart_pass_attempts", "through_pass_attempts", "opportunity_pass_attempts",
    "progressive_pass_attempts", "progressive_pass_completions",
    "final_third_entry_pass_attempts", "danger_zone_entry_pass_attempts",
    "threat_creation_pass_attempts", "threat_creation_pass_completions",
    "progressive_carry_attempts", "shot_attempts", "accurate_shot_attempts",
    "goals", "own_goals", "assists", "shot_opportunity_attempts", "dangerous_ball_losses",
    "goals_raw", "shot_attempts_raw", "accurate_shot_attempts_raw",
    "manual_correction_count", "manual_correction_sources",
    "offside_events", "duel_events", "duels_won", "duels_lost",
    "ground_defensive_duel_events", "ground_defensive_duels_won",
    "ground_defensive_duels_lost", "aerial_duel_events",
    "aerial_duels_won", "aerial_duels_lost", "clearance_events",
    "foul_events", "interception_events",
    "receiver_identity_status", "xg_status", "feature_scope",
]


def _json_from_zip(path: Path, prefix: str):
    with zipfile.ZipFile(path) as archive:
        matches = [n for n in archive.namelist() if Path(n).name.lower().startswith(prefix.lower())]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one {prefix} JSON in {path}; found {matches[:10]}")
        with archive.open(matches[0]) as handle:
            return json.load(handle)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tags(event):
    return {
        int(tag["id"])
        for tag in (event.get("tags") or [])
        if isinstance(tag, dict) and tag.get("id") is not None
    }


def _position(event):
    positions = event.get("positions") or []
    if not positions or not isinstance(positions[0], dict):
        return None, None
    start = positions[0]
    end = positions[1] if len(positions) > 1 and isinstance(positions[1], dict) else None
    try:
        sx, sy = float(start["x"]), float(start["y"])
        ex, ey = (float(end["x"]), float(end["y"])) if end else (None, None)
    except (KeyError, TypeError, ValueError):
        return None, None
    values = [sx, sy] + ([ex, ey] if ex is not None else [])
    if not all(math.isfinite(v) and 0 <= v <= 100 for v in values):
        return None, None
    return (sx, sy), ((ex, ey) if ex is not None else None)


def _match_context(matches, teams):
    team_names = {int(t["wyId"]): str(t.get("name") or t.get("officialName") or "") for t in teams if t.get("wyId") is not None}
    result = {}
    for match in matches:
        match_id = int(match["wyId"])
        sides = {}
        for key, item in (match.get("teamsData") or {}).items():
            if not isinstance(item, dict):
                continue
            team_id = item.get("teamId", key)
            try:
                team_id = int(team_id)
            except (TypeError, ValueError):
                continue
            side = str(item.get("side") or "").lower()
            if side in {"home", "away"}:
                sides[team_id] = side
        result[match_id] = {
            "date": str(match.get("dateutc") or match.get("date") or "")[:10],
            "gameweek": match.get("gameweek", ""),
            "teams": sides,
            "label": str(match.get("label") or ""),
            "team_names": team_names,
        }
    return result


def apply_manual_corrections(rows, corrections):
    allowed_fields = ("goals", "shot_attempts", "accurate_shot_attempts")
    rows_by_key = {
        (str(row["provider_match_id"]), str(row["provider_player_id"])): row
        for row in rows
    }
    if len(rows_by_key) != len(rows):
        raise ValueError("Player-match rows are not unique by match/player key")
    for row in rows:
        for field in allowed_fields:
            row[f"{field}_raw"] = int(row[field] or 0)
        row["manual_correction_count"] = 0
        row["manual_correction_sources"] = ""
    seen = set()
    applied = []
    for correction in corrections or []:
        key = (str(correction.get("provider_match_id", "")).strip(),
               str(correction.get("provider_player_id", "")).strip())
        if not all(key):
            raise ValueError("Manual correction requires provider_match_id and provider_player_id")
        if key in seen:
            raise ValueError(f"Duplicate manual correction for match/player {key}")
        seen.add(key)
        if key not in rows_by_key:
            raise ValueError(f"Manual correction does not match a player-match row: {key}")
        source_name = str(correction.get("source_name", "")).strip()
        source_url = str(correction.get("source_url", "")).strip()
        reason = str(correction.get("reason", "")).strip()
        if not source_name or not source_url.startswith("https://") or not reason:
            raise ValueError("Manual correction requires source_name, https source_url and reason")
        deltas = {}
        for field in allowed_fields:
            raw = correction.get(f"{field}_delta", 0)
            try:
                delta = int(raw or 0)
            except (TypeError, ValueError):
                raise ValueError(f"Manual correction {field}_delta must be an integer")
            if delta:
                deltas[field] = delta
        if not deltas:
            raise ValueError(f"Manual correction for {key} has no non-zero field deltas")
        row = rows_by_key[key]
        for field, delta in deltas.items():
            updated = int(row[field] or 0) + delta
            if updated < 0:
                raise ValueError(f"Manual correction would make {field} negative for {key}")
            row[field] = updated
        row["manual_correction_count"] += 1
        row["manual_correction_sources"] = source_name
        applied.append({
            "provider_match_id": key[0],
            "provider_player_id": key[1],
            "field_deltas": deltas,
            "source_name": source_name,
            "source_url": source_url,
            "reason": reason,
        })
    return applied


def build_player_match_features(events, matches, players, teams, manual_corrections=None):
    player_names = {
        int(p["wyId"]): str(p.get("shortName") or p.get("shortName2") or " ".join(
            x for x in (p.get("firstName"), p.get("middleName"), p.get("lastName")) if x
        ))
        for p in players if p.get("wyId") is not None
    }
    team_names = {
        int(t["wyId"]): str(t.get("name") or t.get("officialName") or "")
        for t in teams if t.get("wyId") is not None
    }
    match_context = _match_context(matches, teams)
    interception_subtype_observed = any(
        str(event.get("eventName") or "").strip().casefold() == "others on the ball"
        and str(event.get("subEventName") or "").strip().casefold() == "interception"
        for event in events
    )
    grouped = defaultdict(list)
    missing_player_rows = 0
    unmatched_match_rows = 0

    for event in events:
        try:
            match_id = int(event["matchId"])
            team_id = int(event["teamId"])
            player_id = int(event["playerId"])
        except (KeyError, TypeError, ValueError):
            if event.get("playerId") is None:
                missing_player_rows += 1
            continue
        if match_id not in match_context:
            unmatched_match_rows += 1
            continue
        grouped[(match_id, team_id, player_id)].append(event)

    output = []
    totals = Counter()
    for (match_id, team_id, player_id), rows in sorted(grouped.items()):
        counts = Counter()
        for event in rows:
            event_name = str(event.get("eventName") or "").strip().casefold()
            subevent = str(event.get("subEventName") or "").strip().casefold()
            tags = _tags(event)
            start, end = _position(event)
            accurate = ACCURATE_TAG in tags

            if event_name == "pass":
                counts["pass_attempts"] += 1
                counts["pass_completions"] += int(accurate)
                counts["key_pass_attempts"] += int(KEY_PASS_TAG in tags)
                counts["smart_pass_attempts"] += int("smart pass" in subevent)
                counts["through_pass_attempts"] += int(THROUGH_TAG in tags or "through pass" in subevent)
                counts["opportunity_pass_attempts"] += int(OPPORTUNITY_TAG in tags)

                progressive = bool(start and end and end[0] - start[0] >= 10.0)
                final_third = bool(start and end and start[0] < (200 / 3) <= end[0])
                danger_zone = bool(end and end[0] >= 80.0 and 20.0 <= end[1] <= 80.0)
                counts["progressive_pass_attempts"] += int(progressive)
                counts["progressive_pass_completions"] += int(progressive and accurate)
                counts["final_third_entry_pass_attempts"] += int(final_third)
                counts["danger_zone_entry_pass_attempts"] += int(danger_zone)
                creation = (
                    progressive or final_third or danger_zone
                    or KEY_PASS_TAG in tags or "smart pass" in subevent
                    or THROUGH_TAG in tags or "through pass" in subevent
                    or OPPORTUNITY_TAG in tags
                )
                counts["threat_creation_pass_attempts"] += int(creation)
                counts["threat_creation_pass_completions"] += int(creation and accurate)

            if event_name == "shot":
                counts["shot_attempts"] += 1
                counts["accurate_shot_attempts"] += int(accurate)
                counts["shot_opportunity_attempts"] += int(OPPORTUNITY_TAG in tags)
            if event_name in {"shot", "free kick"}:
                counts["goals"] += int(GOAL_TAG in tags)
            counts["own_goals"] += int(OWN_GOAL_TAG in tags)
            counts["assists"] += int(ASSIST_TAG in tags)
            if DANGEROUS_LOSS_TAG in tags:
                counts["dangerous_ball_losses"] += 1
            if event_name == "offside":
                counts["offside_events"] += 1
            if event_name == "duel":
                counts["duel_events"] += 1
                won = int(703 in tags)
                lost = int(701 in tags)
                counts["duels_won"] += won
                counts["duels_lost"] += lost
                if "ground defending duel" in subevent:
                    counts["ground_defensive_duel_events"] += 1
                    counts["ground_defensive_duels_won"] += won
                    counts["ground_defensive_duels_lost"] += lost
                if "air duel" in subevent:
                    counts["aerial_duel_events"] += 1
                    counts["aerial_duels_won"] += won
                    counts["aerial_duels_lost"] += lost
            if event_name == "others on the ball":
                counts["clearance_events"] += int(subevent == "clearance")
                counts["interception_events"] += int(subevent == "interception")
            if event_name == "foul":
                counts["foul_events"] += 1
            if event_name == "others on the ball" and "acceleration" in subevent:
                counts["progressive_carry_attempts"] += int(bool(start and end and end[0] - start[0] >= 10.0))

        context = match_context[match_id]
        side = context["teams"].get(team_id, "")
        opponent_id = next((tid for tid in context["teams"] if tid != team_id), None)
        row = {
            "season": "2017/18",
            "competition": "English Premier League",
            "provider": "Wyscout",
            "provider_match_id": match_id,
            "match_date": context["date"],
            "gameweek": context["gameweek"],
            "provider_player_id": player_id,
            "provider_player_name": player_names.get(player_id, ""),
            "provider_team_id": team_id,
            "provider_team_name": team_names.get(team_id, ""),
            "opponent_team_id": opponent_id if opponent_id is not None else "",
            "opponent_team_name": team_names.get(opponent_id, "") if opponent_id is not None else "",
            "home_away": side,
            "event_rows": len(rows),
            **{field: counts[field] for field in (
                "pass_attempts", "pass_completions", "key_pass_attempts",
                "smart_pass_attempts", "through_pass_attempts", "opportunity_pass_attempts",
                "progressive_pass_attempts", "progressive_pass_completions",
                "final_third_entry_pass_attempts", "danger_zone_entry_pass_attempts",
                "threat_creation_pass_attempts", "threat_creation_pass_completions",
                "progressive_carry_attempts", "shot_attempts", "accurate_shot_attempts",
                "goals", "own_goals", "assists", "shot_opportunity_attempts", "dangerous_ball_losses",
                "offside_events", "duel_events", "duels_won", "duels_lost",
                "ground_defensive_duel_events", "ground_defensive_duels_won",
                "ground_defensive_duels_lost", "aerial_duel_events",
                "aerial_duels_won", "aerial_duels_lost", "clearance_events",
                "foul_events", "interception_events",
            )},
            "receiver_identity_status": "NOT_AVAILABLE_IN_PUBLIC_WYSCOUT_EVENT_SCHEMA",
            "xg_status": "NOT_AVAILABLE_IN_PUBLIC_WYSCOUT_EVENT_SCHEMA",
            "feature_scope": "EVENT_LEVEL_PLAYER_MATCH_COUNTS_NOT_TRACKING",
        }
        if not interception_subtype_observed:
            row["interception_events"] = None
        output.append(row)
        totals.update(counts)
    raw_aggregate_features = dict(totals)
    applied_corrections = apply_manual_corrections(output, manual_corrections)
    for correction in applied_corrections:
        for field, delta in correction["field_deltas"].items():
            totals[field] += delta

    manual_goal_correction_total = sum(c["field_deltas"].get("goals", 0) for c in applied_corrections)
    corrections_by_match = defaultdict(list)
    for correction in applied_corrections:
        corrections_by_match[str(correction["provider_match_id"])].append(correction)

    match_metadata_goals = 0
    matches_with_score = 0
    metadata_goals_by_match = {}
    match_context_by_id = {}
    for match in matches:
        match_id = str(match.get("wyId"))
        teams_data = match.get("teamsData") or {}
        scores = []
        team_context = []
        for team_data in teams_data.values():
            if not isinstance(team_data, dict) or team_data.get("score") is None:
                continue
            try:
                score = int(team_data["score"])
            except (TypeError, ValueError):
                continue
            scores.append(score)
            try:
                team_id = int(team_data.get("teamId"))
            except (TypeError, ValueError):
                team_id = None
            side = str(team_data.get("side") or "")
            team_context.append({
                "team_id": team_id,
                "team_name": team_names.get(team_id, "") if team_id is not None else "",
                "side": side,
                "score": score,
            })
        if len(scores) == 2:
            matches_with_score += 1
            metadata_goals_by_match[match_id] = sum(scores)
            match_metadata_goals += sum(scores)
            match_context_by_id[match_id] = sorted(team_context, key=lambda row: row["side"])

    event_goals_by_match = defaultdict(Counter)
    for event in events:
        match_id = str(event.get("matchId"))
        event_name = str(event.get("eventName") or "UNKNOWN")
        tags = _tags(event)
        if GOAL_TAG in tags and event_name == "Shot":
            event_goals_by_match[match_id]["shot_goal_tags"] += 1
        elif GOAL_TAG in tags and event_name == "Free Kick":
            event_goals_by_match[match_id]["free_kick_goal_tags"] += 1
        if OWN_GOAL_TAG in tags:
            event_goals_by_match[match_id]["own_goal_tags"] += 1

    mismatched_matches = []
    for match_id, metadata_total in sorted(metadata_goals_by_match.items()):
        counts = event_goals_by_match[match_id]
        attributed_total = (
            counts["shot_goal_tags"] + counts["free_kick_goal_tags"] + counts["own_goal_tags"]
        )
        if attributed_total != metadata_total:
            diagnostic_events = []
            for event in events:
                if str(event.get("matchId")) != match_id:
                    continue
                event_name = str(event.get("eventName") or "UNKNOWN")
                tags = _tags(event)
                if event_name not in {"Shot", "Free Kick", "Save attempt"} and not ({GOAL_TAG, OWN_GOAL_TAG} & tags):
                    continue
                diagnostic_events.append({
                    "event_id": event.get("id"),
                    "player_id": event.get("playerId"),
                    "team_id": event.get("teamId"),
                    "event_name": event_name,
                    "sub_event_name": event.get("subEventName"),
                    "match_period": event.get("matchPeriod"),
                    "event_sec": event.get("eventSec"),
                    "tags": sorted(tags),
                    "positions": event.get("positions") or [],
                })
            mismatched_matches.append({
                "match_id": match_id,
                "teams": match_context_by_id.get(match_id, []),
                "metadata_goals": metadata_total,
                "shot_goal_tags": counts["shot_goal_tags"],
                "free_kick_goal_tags": counts["free_kick_goal_tags"],
                "own_goal_tags": counts["own_goal_tags"],
                "player_attributed_goal_total": attributed_total,
                "delta": attributed_total - metadata_total,
                "manual_goal_correction_total": sum(x["field_deltas"].get("goals", 0) for x in corrections_by_match[match_id]),
                "corrected_player_attributed_goal_total": attributed_total + sum(x["field_deltas"].get("goals", 0) for x in corrections_by_match[match_id]),
                "corrected_delta": attributed_total + sum(x["field_deltas"].get("goals", 0) for x in corrections_by_match[match_id]) - metadata_total,
                "manual_correction_sources": [x["source_name"] for x in corrections_by_match[match_id]],
                "diagnostic_events": diagnostic_events,
            })
    goal_tag_types = Counter(
        str(event.get("eventName") or "UNKNOWN")
        for event in events if GOAL_TAG in _tags(event)
    )
    own_goal_tag_types = Counter(
        str(event.get("eventName") or "UNKNOWN")
        for event in events if OWN_GOAL_TAG in _tags(event)
    )
    shot_tagged_goals = goal_tag_types.get("Shot", 0)
    free_kick_tagged_goals = goal_tag_types.get("Free Kick", 0)
    shot_tagged_own_goals = own_goal_tag_types.get("Shot", 0)
    all_goal_tag_events = sum(goal_tag_types.values())
    all_own_goal_tag_events = sum(own_goal_tag_types.values())
    player_attributed_goals = shot_tagged_goals + free_kick_tagged_goals
    player_attributed_own_goals = all_own_goal_tag_events
    mismatched_match_ids = {row["match_id"] for row in mismatched_matches}
    for correction in applied_corrections:
        if correction["provider_match_id"] not in mismatched_match_ids:
            raise ValueError(f"Manual correction must target a raw goal-mismatched match: {correction['provider_match_id']}")

    report = {
        "provider": "Wyscout",
        "season": "2017/18",
        "competition": "English Premier League",
        "player_match_rows": len(output),
        "unique_players": len({r["provider_player_id"] for r in output}),
        "unique_matches": len({r["provider_match_id"] for r in output}),
        "event_rows_with_player_and_team_match": sum(r["event_rows"] for r in output),
        "events_missing_player_id": missing_player_rows,
        "events_with_unmatched_match_metadata": unmatched_match_rows,
        "goal_reconciliation": {
            "matches_with_two_team_scores": matches_with_score,
            "match_metadata_goals": match_metadata_goals,
            "all_event_goal_tag_events": all_goal_tag_events,
            "all_event_own_goal_tag_events": all_own_goal_tag_events,
            "goal_tag_events_by_event_type": dict(goal_tag_types),
            "own_goal_tag_events_by_event_type": dict(own_goal_tag_types),
            "shot_event_goal_tag_count": shot_tagged_goals,
            "free_kick_event_goal_tag_count": free_kick_tagged_goals,
            "shot_event_own_goal_tag_count": shot_tagged_own_goals,
            "player_attributed_goal_events": player_attributed_goals,
            "player_attributed_own_goal_events": player_attributed_own_goals,
            "player_attributed_goal_total": player_attributed_goals + player_attributed_own_goals,
            "player_attributed_minus_metadata_goal_delta": player_attributed_goals + player_attributed_own_goals - match_metadata_goals,
            "raw_player_attributed_goal_total": player_attributed_goals + player_attributed_own_goals,
            "manual_goal_correction_total": manual_goal_correction_total,
            "corrected_player_attributed_goal_total": player_attributed_goals + player_attributed_own_goals + manual_goal_correction_total,
            "corrected_minus_metadata_goal_delta": player_attributed_goals + player_attributed_own_goals + manual_goal_correction_total - match_metadata_goals,
            "manual_corrections": applied_corrections,
            "mismatched_match_count": len(mismatched_matches),
            "mismatched_matches": mismatched_matches,
            "status": (
                "PASS_EXACT"
                if matches_with_score == len(matches) and not mismatched_matches and not applied_corrections
                else "PASS_EXACT_WITH_MANUAL_CORRECTIONS"
                if matches_with_score == len(matches) and applied_corrections and all(x["corrected_delta"] == 0 for x in mismatched_matches)
                else "REVIEW_REQUIRED"
            ),
        },
        "aggregate_features": dict(totals),
        "raw_aggregate_features": raw_aggregate_features,
        "manual_correction_count": len(applied_corrections),
        "identity_mapping_status": "NOT_MAPPED_TO_FPL",
        "receiver_identity_status": "NOT_AVAILABLE_IN_PUBLIC_WYSCOUT_EVENT_SCHEMA",
        "xg_status": "NOT_AVAILABLE_IN_PUBLIC_WYSCOUT_EVENT_SCHEMA",
        "interception_subtype_observed": interception_subtype_observed,
        "coordinate_basis": "Wyscout event coordinates are attacking-team-relative percentages; x increases toward opponent goal.",
        "feature_definitions": {
            "progressive_pass": "Pass end x minus start x is at least 10 percentage points.",
            "final_third_entry": "Pass starts below x=66.67 and ends at or above x=66.67.",
            "danger_zone_entry": "Pass endpoint x>=80 and y in [20,80]; provisional geometric proxy, not a calibrated box or xG measure.",
            "threat_creation_pass": "Union of progressive, final-third-entry, danger-zone-entry, key, smart, through and opportunity pass indicators; one count per pass attempt.",
            "progressive_carry": "Others on the ball / Acceleration event with end x minus start x at least 10 percentage points.",
        },
        "prediction_validation": "NOT_EVALUATED",
        "publication_policy": "Player-match feature rows stay in the workflow runner; publish aggregate counts and source hashes only.",
        "attribution": "Pappalardo and Massucco (2019), Wyscout event collection; CC BY 4.0. DOI: 10.1038/s41597-019-0247-7",
        "limitations": [
            "This is one historical EPL season (2017/18), not a current-season feed.",
            "Events are on-ball logs, not continuous tracking or 360 freeze frames.",
            "No pass-recipient ID is provided; receipt/player involvement cannot be inferred from an event actor alone.",
            "No xG is present; shot and opportunity indicators are not xG.",
            "The danger-zone entry geometry is provisional and must be sensitivity-tested.",
            "FPL identity crosswalk is not yet available.",
        ],
    }
    return output, report


def main():
    parser = argparse.ArgumentParser(description="Build Wyscout EPL 2017/18 player-match CTA features")
    parser.add_argument("--events-zip", type=Path, required=True)
    parser.add_argument("--matches-zip", type=Path, required=True)
    parser.add_argument("--players-json", type=Path, required=True)
    parser.add_argument("--teams-json", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--manual-corrections", type=Path, default=None)
    args = parser.parse_args()
    events = _json_from_zip(args.events_zip, "events_England")
    matches = _json_from_zip(args.matches_zip, "matches_England")
    players = _read_json(args.players_json)
    teams = _read_json(args.teams_json)
    manual_corrections = []
    if args.manual_corrections:
        with args.manual_corrections.open(newline="", encoding="utf-8-sig") as handle:
            manual_corrections = list(csv.DictReader(handle))
    rows, report = build_player_match_features(events, matches, players, teams, manual_corrections=manual_corrections)
    report["source_hashes"] = {
        "events_zip_sha256": _sha256(args.events_zip),
        "matches_zip_sha256": _sha256(args.matches_zip),
        "players_json_sha256": _sha256(args.players_json),
        "teams_json_sha256": _sha256(args.teams_json),
        "manual_corrections_sha256": _sha256(args.manual_corrections) if args.manual_corrections else None,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with (args.out_dir / "wyscout_cta_player_match.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (args.out_dir / "wyscout_cta_player_match_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "provider", "season", "player_match_rows", "unique_players", "unique_matches",
        "event_rows_with_player_and_team_match", "events_missing_player_id",
        "events_with_unmatched_match_metadata", "identity_mapping_status",
        "receiver_identity_status", "xg_status", "prediction_validation",
    )}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
