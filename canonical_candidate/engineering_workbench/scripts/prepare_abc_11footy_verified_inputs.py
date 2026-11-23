#!/usr/bin/env python3
"""Prepare the existing cross-provider bridge for the verified 11footy panel builder."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


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


def prepare(candidates, crosswalk, history, teams):
    team_names = {}
    for row in teams:
        team_id = str(row.get("id") or row.get("team_id") or "").strip()
        name = str(row.get("name") or row.get("team_name") or "").strip()
        if team_id and name:
            team_names[team_id] = name

    fixture_parts = defaultdict(dict)
    for row in history:
        fixture = str(row.get("fixture") or row.get("fixture_id") or "").strip()
        if not fixture:
            continue
        side = "home" if truth(row.get("was_home")) else "away"
        fixture_parts[fixture].update({
            "fixture_id": fixture,
            "kickoff_time": row.get("kickoff_time", ""),
            "gameweek": row.get("round") or row.get("gameweek") or "",
            f"team_{side}_id": row.get("team", ""),
            f"team_{side}_name": team_names.get(str(row.get("team") or ""), ""),
        })

    fixtures = []
    for fixture_id, item in sorted(fixture_parts.items()):
        if item.get("team_h_name") and item.get("team_a_name") and item.get("kickoff_time"):
            fixtures.append(item)

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
        "verified_crosswalk_rows": len(verified_out),
        "verified_unique_11footy_players": len({r["provider_player_id"] for r in verified_out}),
        "verified_unique_fpl_elements": len({r["fpl_element_id"] for r in verified_out}),
        "source": "Existing strict Wyscout–11footy–FPL cross-provider verified bridge",
        "transformation": "Cross-provider corroborating 11footy player IDs mapped into the existing 11footy builder's provider-player crosswalk contract",
    }
    return candidate_out, verified_out, fixtures, validation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--crosswalk", type=Path, required=True)
    parser.add_argument("--fpl-history", type=Path, required=True)
    parser.add_argument("--team-list", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    candidates, crosswalk, fixtures, validation = prepare(
        read_csv(args.candidates), read_csv(args.crosswalk),
        read_csv(args.fpl_history), read_csv(args.team_list),
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "11footy_builder_candidates.csv", candidates,
              ["season", "provider_player_id", "fpl_element_id"])
    write_csv(args.out_dir / "11footy_builder_verified_crosswalk.csv", crosswalk,
              ["season", "competition_id", "provider", "provider_player_id", "fpl_element_id", "verification_status"])
    write_csv(args.out_dir / "historical_fpl_fixtures.csv", fixtures,
              ["fixture_id", "kickoff_time", "gameweek", "team_h_id", "team_h_name", "team_a_id", "team_a_name"])
    (args.out_dir / "11footy_crosswalk_validation.json").write_text(
        json.dumps(validation, indent=2), encoding="utf-8"
    )
    print(json.dumps({**validation, "candidate_rows": len(candidates), "fixture_rows": len(fixtures)}, indent=2))
    return 0 if fixtures and validation["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
