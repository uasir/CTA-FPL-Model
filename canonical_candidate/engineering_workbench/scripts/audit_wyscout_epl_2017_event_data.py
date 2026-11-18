#!/usr/bin/env python3
"""Audit the public Wyscout 2017/18 English Premier League event dataset."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_from_zip(path, filename_prefix):
    with zipfile.ZipFile(path) as archive:
        candidates = [
            name for name in archive.namelist()
            if Path(name).name.lower().startswith(filename_prefix.lower())
        ]
        if len(candidates) != 1:
            raise ValueError(
                "Expected one " + filename_prefix + " JSON in " + str(path)
                + "; found " + repr(candidates[:10])
            )
        with archive.open(candidates[0]) as handle:
            return json.load(handle), candidates[0]


def _json_file(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def audit_wyscout(events_zip, matches_zip, players_file, teams_file):
    events, event_member = _json_from_zip(events_zip, "events_England")
    matches, match_member = _json_from_zip(matches_zip, "matches_England")
    players = _json_file(players_file)
    teams = _json_file(teams_file)

    event_types = Counter()
    subevent_types = Counter()
    tag_counts = Counter()
    event_match_ids = set()
    event_player_ids = set()
    event_team_ids = set()
    events_with_start = 0
    events_with_end = 0
    events_with_both_positions = 0
    events_with_player = 0
    events_with_tags = 0
    event_periods = Counter()

    for event in events:
        event_types[str(event.get("eventName") or "UNKNOWN")] += 1
        subevent_types[str(event.get("subEventName") or "UNKNOWN")] += 1
        if event.get("matchId") is not None:
            event_match_ids.add(int(event["matchId"]))
        if event.get("playerId") is not None:
            event_player_ids.add(int(event["playerId"]))
            events_with_player += 1
        if event.get("teamId") is not None:
            event_team_ids.add(int(event["teamId"]))
        if event.get("matchPeriod"):
            event_periods[str(event["matchPeriod"])] += 1
        positions = event.get("positions") or []
        if len(positions) >= 1 and positions[0] is not None:
            events_with_start += 1
        if len(positions) >= 2 and positions[1] is not None:
            events_with_end += 1
        if len(positions) >= 2 and positions[0] is not None and positions[1] is not None:
            events_with_both_positions += 1
        tags = event.get("tags") or []
        if tags:
            events_with_tags += 1
        for tag in tags:
            if tag.get("id") is not None:
                tag_counts[str(tag["id"])] += 1

    match_ids = {
        int(match.get("wyId")) for match in matches if match.get("wyId") is not None
    }
    player_ids = {
        int(player.get("wyId")) for player in players if player.get("wyId") is not None
    }
    team_ids = {
        int(team.get("wyId")) for team in teams if team.get("wyId") is not None
    }

    report = {
        "provider": "Wyscout",
        "dataset": "Pappalardo and Massucco Soccer Match Event Dataset",
        "competition": "English Premier League",
        "season": "2017/18",
        "license": "CC BY 4.0",
        "attribution": "Pappalardo, L. and Massucco, E. (2019), Soccer match event dataset; Wyscout event collection.",
        "source_file_ids": {
            "events": "figshare:14464685",
            "matches": "figshare:14464622",
            "players": "figshare:15073721",
            "teams": "figshare:15073697",
        },
        "source_file_sha256": {
            "events_zip": sha256(events_zip),
            "matches_zip": sha256(matches_zip),
            "players_json": sha256(players_file),
            "teams_json": sha256(teams_file),
        },
        "archive_members": {"events": event_member, "matches": match_member},
        "events": {
            "rows": len(events),
            "unique_matches": len(event_match_ids),
            "unique_players": len(event_player_ids),
            "unique_teams": len(event_team_ids),
            "rows_with_player_id": events_with_player,
            "rows_with_start_position": events_with_start,
            "rows_with_end_position": events_with_end,
            "rows_with_both_positions": events_with_both_positions,
            "rows_with_tags": events_with_tags,
            "event_types": dict(event_types.most_common(30)),
            "subevent_types": dict(subevent_types.most_common(40)),
            "match_periods": dict(event_periods),
            "top_tag_ids": dict(tag_counts.most_common(30)),
        },
        "matches": {
            "rows": len(matches),
            "unique_match_ids": len(match_ids),
            "event_match_ids_missing_from_metadata": len(event_match_ids - match_ids),
            "metadata_match_ids_without_events": len(match_ids - event_match_ids),
        },
        "player_metadata": {
            "rows": len(players),
            "event_player_ids_missing_from_metadata": len(event_player_ids - player_ids),
        },
        "team_metadata": {
            "rows": len(teams),
            "event_team_ids_missing_from_metadata": len(event_team_ids - team_ids),
        },
        "status": "PASS_STRUCTURAL_ONLY",
        "prediction_validation": "NOT_EVALUATED",
        "fpl_identity_mapping": "NOT_ATTEMPTED",
        "limitations": [
            "This is one historical EPL season (2017/18), not a current-season feed.",
            "Wyscout player IDs are provider-specific; a season-scoped FPL crosswalk is required.",
            "Event locations are on-ball event coordinates, not continuous player tracking or 360 freeze frames.",
            "No raw provider rows or player-level outputs are uploaded.",
        ],
    }
    return report


def main():
    parser = argparse.ArgumentParser(description="Audit Wyscout EPL 2017/18 event data")
    parser.add_argument("--events-zip", type=Path, required=True)
    parser.add_argument("--matches-zip", type=Path, required=True)
    parser.add_argument("--players-json", type=Path, required=True)
    parser.add_argument("--teams-json", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    report = audit_wyscout(args.events_zip, args.matches_zip, args.players_json, args.teams_json)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    output = args.out_dir / "wyscout_epl_2017_event_data_audit.json"
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({
        "provider": report["provider"],
        "season": report["season"],
        "events": report["events"]["rows"],
        "event_types": report["events"]["event_types"],
        "unique_players": report["events"]["unique_players"],
        "matches": report["matches"],
        "player_metadata": report["player_metadata"],
        "team_metadata": report["team_metadata"],
        "position_coverage": {
            "start": report["events"]["rows_with_start_position"],
            "end": report["events"]["rows_with_end_position"],
            "both": report["events"]["rows_with_both_positions"],
        },
        "status": report["status"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
