#!/usr/bin/env python3
"""Prepare existing verified cross-provider evidence for the historical 11footy panel builder."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def read_csv(path):
    # The pinned Vaastav historical CSV archive includes legacy CP1252 names.
    # Prefer UTF-8, then decode the legacy bytes without dropping identity text.
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            with Path(path).open(newline="", encoding=encoding) as handle:
                return list(csv.DictReader(handle))
        except UnicodeDecodeError:
            continue
    raise UnicodeError(f"Could not decode historical CSV: {path}")


def write_csv(path, rows, fallback_fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else fallback_fields
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def truth(value):
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def id_text(value):
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        number = float(text)
        if number.is_integer():
            return str(int(number))
    except (TypeError, ValueError):
        pass
    return text


def prepare(candidates, crosswalk, raw_history, raw_players, teams):
    team_names = {}
    for row in teams:
        season = str(row.get("season") or "").strip().replace("/", "-")
        if season and season != "2017-18":
            continue
        # Vaastav master_team_list.csv uses season, team, team_name.
        team_id = id_text(row.get("team") or row.get("id") or row.get("team_id"))
        name = str(row.get("team_name") or row.get("name") or "").strip()
        if team_id and name:
            team_names[team_id] = name

    history = []
    for row in raw_history:
        element = id_text(row.get("element") or row.get("fpl_element_id"))
        fixture = id_text(row.get("fixture") or row.get("fixture_id"))
        if not element or not fixture:
            continue
        history.append({
            "fpl_element_id": element,
            "fixture_id": fixture,
            "kickoff_time": row.get("kickoff_time", ""),
            "gameweek": row.get("round") or row.get("gameweek") or "",
            "minutes": row.get("minutes", ""),
            "total_points": row.get("total_points", ""),
            "goals_scored": row.get("goals_scored", ""),
            "assists": row.get("assists", ""),
            "was_home": row.get("was_home", ""),
            "team": id_text(row.get("team")),
            "opponent_team": row.get("opponent_team", ""),
        })

    fixture_parts = defaultdict(dict)
    for row in history:
        fixture = str(row["fixture_id"])
        side = "h" if truth(row.get("was_home")) else "a"
        fixture_parts[fixture].update({
            "fixture_id": fixture,
            "kickoff_time": row.get("kickoff_time", ""),
            "gameweek": row.get("gameweek", ""),
            f"team_{side}_id": row.get("team", ""),
            f"team_{side}_name": team_names.get(id_text(row.get("team")), ""),
        })
    fixtures = [
        item for _, item in sorted(fixture_parts.items())
        if item.get("team_h_name") and item.get("team_a_name") and item.get("kickoff_time")
    ]

    normalized_players = []
    for row in raw_players:
        element = row.get("id") or row.get("fpl_element_id")
        if element:
            normalized_players.append({
                "fpl_element_id": element,
                "fpl_player_code": row.get("code") or row.get("fpl_player_code") or "",
                "web_name": row.get("web_name") or row.get("web_name", ""),
            })

    candidate_out = []
    for row in candidates:
        item = dict(row)
        item["fpl_element_id"] = row.get("candidate_fpl_element_id", "")
        candidate_out.append(item)

    verified_out = []
    for row in crosswalk:
        if not str(row.get("verification_status") or "").startswith("VERIFIED_CROSS_PROVIDER"):
            continue
        item = {
            "season": row.get("season", "2017/18"),
            "competition_id": "1",
            "provider": "11footy",
            "provider_player_id": row.get("corroborating_provider_player_id", ""),
            "provider_player_name": row.get("corroborating_provider_player_name", ""),
            "provider_birth_date": row.get("corroborating_provider_birth_date", ""),
            "fpl_element_id": row.get("fpl_element_id", ""),
            "fpl_player_code": row.get("fpl_player_code", ""),
            "verification_status": "verified",
            "verification_method": row.get("verification_method", ""),
            "source_crosswalk_status": row.get("verification_status", ""),
        }
        if item["provider_player_id"] and item["fpl_element_id"]:
            verified_out.append(item)

    validation = {
        "status": "PASS" if verified_out else "NO_VERIFIED_MAPPINGS",
        "diagnostics": {
            "historical_team_name_rows": len(team_names),
            "historical_team_ids": sorted(team_names)[:25],
            "fpl_history_rows_with_kickoff": sum(bool(str(row.get("kickoff_time") or "").strip()) for row in history),
            "fpl_history_rows_with_team_name_match": sum(
                id_text(row.get("team")) in team_names for row in history
            ),
            "unique_fpl_history_fixtures": len(fixture_parts),
            "fixtures_with_both_team_names": sum(
                bool(item.get("team_h_name")) and bool(item.get("team_a_name"))
                for item in fixture_parts.values()
            ),
        },
        "verified_crosswalk_rows": len(verified_out),
        "verified_unique_11footy_players": len({r["provider_player_id"] for r in verified_out}),
        "verified_unique_fpl_elements": len({r["fpl_element_id"] for r in verified_out}),
        "source": "Existing strict Wyscout–11footy–FPL cross-provider verified bridge",
        "transformation": "Cross-provider corroborating 11footy player IDs mapped into the existing 11footy builder's provider-player crosswalk contract",
    }
    return candidate_out, verified_out, fixtures, normalized_players, history, validation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--crosswalk", type=Path, required=True)
    parser.add_argument("--fpl-history", type=Path, required=True)
    parser.add_argument("--fpl-players", type=Path, required=True)
    parser.add_argument("--team-list", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    candidates, crosswalk, fixtures, players, history, validation = prepare(
        read_csv(args.candidates), read_csv(args.crosswalk),
        read_csv(args.fpl_history), read_csv(args.fpl_players), read_csv(args.team_list),
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "11footy_builder_candidates.csv", candidates,
              ["season", "provider_player_id", "fpl_element_id"])
    write_csv(args.out_dir / "11footy_builder_verified_crosswalk.csv", crosswalk,
              ["season", "competition_id", "provider", "provider_player_id", "fpl_element_id", "verification_status"])
    write_csv(args.out_dir / "historical_fpl_fixtures.csv", fixtures,
              ["fixture_id", "kickoff_time", "gameweek", "team_h_id", "team_h_name", "team_a_id", "team_a_name"])
    write_csv(args.out_dir / "historical_fpl_players.csv", players,
              ["fpl_element_id", "fpl_player_code", "web_name"])
    write_csv(args.out_dir / "historical_fpl_player_fixture.csv", history,
              ["fpl_element_id", "fixture_id", "minutes", "total_points", "goals_scored", "assists", "was_home"])
    (args.out_dir / "11footy_crosswalk_validation.json").write_text(
        json.dumps(validation, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        **validation, "candidate_rows": len(candidates), "fixture_rows": len(fixtures),
        "fpl_player_rows": len(players), "fpl_player_fixture_rows": len(history),
    }, indent=2))
    return 0 if fixtures and validation["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
