#!/usr/bin/env python3
"""Audit exact-name/team/birth-date candidates between 11footy and official FPL."""
from __future__ import annotations

import argparse
import json
import lzma
import re
import shutil
import sqlite3
import tempfile
import unicodedata
from collections import defaultdict
from pathlib import Path


TEAM_ALIASES = {
    "afc bournemouth": "bournemouth",
    "bournemouth": "bournemouth",
    "brighton": "brighton and hove albion",
    "brighton hove albion": "brighton and hove albion",
    "brighton and hove albion": "brighton and hove albion",
    "leeds": "leeds united",
    "leeds united": "leeds united",
    "man city": "manchester city",
    "manchester city": "manchester city",
    "man utd": "manchester united",
    "manchester united": "manchester united",
    "newcastle": "newcastle united",
    "newcastle united": "newcastle united",
    "nottm forest": "nottingham forest",
    "nott m forest": "nottingham forest",
    "nott forest": "nottingham forest",
    "nottingham forest": "nottingham forest",
    "sheffield utd": "sheffield united",
    "sheffield united": "sheffield united",
    "spurs": "tottenham hotspur",
    "tottenham": "tottenham hotspur",
    "tottenham hotspur": "tottenham hotspur",
    "west ham": "west ham united",
    "west ham united": "west ham united",
    "wolves": "wolverhampton wanderers",
    "wolverhampton": "wolverhampton wanderers",
    "wolverhampton wanderers": "wolverhampton wanderers",
}


def normalize_text(value):
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_team(value):
    key = normalize_text(value)
    return TEAM_ALIASES.get(key, key)


def _materialize_sqlite(source: Path, temp_dir: Path):
    if source.suffix.lower() != ".xz":
        return source
    target = temp_dir / source.name[:-3]
    with lzma.open(source, "rb") as compressed, target.open("wb") as output:
        shutil.copyfileobj(compressed, output)
    return target


def audit_identity_candidates(players_connection, fpl_bootstrap):
    tables = {
        row[0] for row in players_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if "players" not in tables:
        raise ValueError("11footy player catalogue is missing its players table")

    columns = {
        row[1] for row in players_connection.execute("PRAGMA table_info(players)")
    }
    required_columns = {"player_id", "name", "current_team_name", "birth_date"}
    missing = sorted(required_columns - columns)
    if missing:
        raise ValueError("11footy players table is missing columns: " + ", ".join(missing))

    provider_rows = players_connection.execute(
        "SELECT player_id, name, current_team_name, birth_date FROM players"
    ).fetchall()
    provider_by_name_team = defaultdict(list)
    provider_by_name = defaultdict(list)
    for player_id, name, team, birth_date in provider_rows:
        norm_name = normalize_text(name)
        if not norm_name:
            continue
        row = {
            "provider_player_id": int(player_id),
            "provider_name": str(name or ""),
            "provider_team": str(team or ""),
            "norm_team": normalize_team(team),
            "birth_date": str(birth_date or ""),
        }
        provider_by_name[norm_name].append(row)
        if row["norm_team"]:
            provider_by_name_team[(norm_name, row["norm_team"])].append(row)

    fpl_teams = {
        int(team["id"]): str(team.get("name") or "")
        for team in fpl_bootstrap.get("teams", [])
        if team.get("id") is not None
    }
    fpl_rows = []
    for element in fpl_bootstrap.get("elements", []):
        full_name = " ".join(
            part for part in (element.get("first_name"), element.get("second_name")) if part
        ).strip()
        team_name = fpl_teams.get(int(element.get("team") or 0), "")
        norm_name = normalize_text(full_name)
        if not norm_name:
            continue
        fpl_rows.append({
            "fpl_element_id": int(element["id"]),
            "fpl_code": element.get("code"),
            "fpl_name": full_name,
            "fpl_team": team_name,
            "norm_name": norm_name,
            "norm_team": normalize_team(team_name),
            "birth_date": str(element.get("birth_date") or ""),
        })

    fpl_by_name = defaultdict(list)
    fpl_by_name_team = defaultdict(list)
    for row in fpl_rows:
        fpl_by_name[row["norm_name"]].append(row)
        if row["norm_team"]:
            fpl_by_name_team[(row["norm_name"], row["norm_team"])].append(row)

    exact_name_team = 0
    high_confidence_dob_matches = 0
    missing_birthdate_candidates = 0
    birthdate_conflicts = 0
    unique_name_only = 0
    team_mismatch = 0
    ambiguous = 0
    unmatched = 0
    candidate_rows = []
    for row in fpl_rows:
        key = (row["norm_name"], row["norm_team"])
        same_name_team = provider_by_name_team.get(key, [])
        same_name = provider_by_name.get(row["norm_name"], [])
        same_fpl_name_team = fpl_by_name_team.get(key, [])

        if len(same_name_team) == 1 and len(same_fpl_name_team) == 1:
            provider_player = same_name_team[0]
            provider_dob = provider_player["birth_date"]
            fpl_dob = row["birth_date"]
            if provider_dob and fpl_dob and provider_dob != fpl_dob:
                birthdate_conflicts += 1
                continue
            exact_name_team += 1
            if provider_dob and fpl_dob:
                high_confidence_dob_matches += 1
                verification_status = "HIGH_CONFIDENCE_AUTOMATED_CANDIDATE"
                match_method = "EXACT_NAME_TEAM_AND_BIRTH_DATE"
            else:
                missing_birthdate_candidates += 1
                verification_status = "CANDIDATE_REQUIRES_REVIEW"
                match_method = "EXACT_NAME_AND_TEAM_BIRTH_DATE_UNAVAILABLE"
            candidate_rows.append({
                "season": "2026/27",
                "source_release": "11footy-2026-11-10",
                "fpl_element_id": row["fpl_element_id"],
                "fpl_player_code": row["fpl_code"],
                "fpl_player_name": row["fpl_name"],
                "fpl_team_name": row["fpl_team"],
                "fpl_birth_date": fpl_dob,
                "provider_player_id": provider_player["provider_player_id"],
                "provider_player_name": provider_player["provider_name"],
                "provider_team_name": provider_player["provider_team"],
                "provider_birth_date": provider_dob,
                "match_method": (
                    "exact_name_team_birth_date" if provider_dob and fpl_dob
                    else "exact_name_team_birth_date_missing"
                ),
                "confidence_level": (
                    "high" if provider_dob and fpl_dob else "review_required"
                ),
                "verification_status": "pending",
                "verification_reason": (
                    "Exact normalized full name, team and matching birth date; "
                    "awaiting independent identity review"
                    if provider_dob and fpl_dob
                    else "Exact normalized full name and team; one or both birth dates unavailable"
                ),
                "evidence_source": "11footy player catalogue and official FPL bootstrap-static",
                "provider_release_url": "https://github.com/fm-devlab/11footy-dataset/releases/tag/11footy-2026-11-10",
                "fpl_source_url": "https://fantasy.premierleague.com/api/bootstrap-static/",
            })
        elif len(same_name) == 1 and not same_name_team and not same_name[0]["norm_team"]:
            unique_name_only += 1
        elif same_name and (len(same_name) > 1 or len(same_fpl_name_team) > 1):
            ambiguous += 1
        elif same_name:
            team_mismatch += 1
        else:
            unmatched += 1

    provider_to_fpl = defaultdict(list)
    for row in candidate_rows:
        provider_to_fpl[row["provider_player_id"]].append(row["fpl_element_id"])
    collisions = {
        provider_id for provider_id, element_ids in provider_to_fpl.items()
        if len(element_ids) > 1
    }
    if collisions:
        candidate_rows = [
            row for row in candidate_rows if row["provider_player_id"] not in collisions
        ]
        exact_name_team -= sum(len(provider_to_fpl[provider_id]) for provider_id in collisions)
        high_confidence_dob_matches = sum(
            row["match_method"] == "EXACT_NAME_TEAM_AND_BIRTH_DATE" for row in candidate_rows
        )
        missing_birthdate_candidates = sum(
            row["match_method"] == "EXACT_NAME_AND_TEAM_BIRTH_DATE_UNAVAILABLE"
            for row in candidate_rows
        )

    return {
        "provider": "11footy",
        "comparison_source": "Official FPL bootstrap-static",
        "fpl_player_count": len(fpl_rows),
        "provider_player_catalogue_count": len(provider_rows),
        "exact_normalized_name_and_team_candidates": exact_name_team,
        "high_confidence_name_team_birth_date_candidates": high_confidence_dob_matches,
        "name_team_candidates_missing_birth_date": missing_birthdate_candidates,
        "birth_date_conflicts_excluded": birthdate_conflicts,
        "unique_name_only_unverified": unique_name_only,
        "same_name_team_mismatch": team_mismatch,
        "ambiguous_name_or_duplicate_identity": ambiguous,
        "unmatched_fpl_players": unmatched,
        "provider_id_collisions_removed": len(collisions),
        "candidate_rows_remaining": len(candidate_rows),
        "matching_policy": "Exact normalized full name plus normalized current team; when both birth dates exist they must match. No fuzzy matching.",
        "verification_status": "CANDIDATES_ONLY_NOT_VERIFIED",
        "candidate_export": "identity_candidates.csv",
        "candidate_policy": "All exported rows remain pending; high confidence is an automated evidence grade, not human verification.",
        "birth_date_policy": "Birth-date mismatches are excluded; missing birth dates remain review candidates.",
        "prediction_validation": "NOT_EVALUATED",
    }, candidate_rows


def main():
    parser = argparse.ArgumentParser(description="Audit 11footy-to-FPL current-player identity candidates")
    parser.add_argument("--players-input", type=Path, required=True)
    parser.add_argument("--fpl-bootstrap", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    bootstrap = json.loads(args.fpl_bootstrap.read_text(encoding="utf-8"))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cta-11footy-identities-") as temp:
        db_path = _materialize_sqlite(args.players_input, Path(temp))
        connection = sqlite3.connect("file:" + str(db_path.resolve()) + "?mode=ro", uri=True)
        try:
            report, candidate_rows = audit_identity_candidates(connection, bootstrap)
        finally:
            connection.close()

    (args.out_dir / "identity_candidate_summary.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    with (args.out_dir / "identity_candidates.csv").open("w", encoding="utf-8", newline="") as handle:
        import csv
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "season", "source_release", "fpl_element_id", "fpl_player_code",
                "fpl_player_name", "fpl_team_name", "fpl_birth_date",
                "provider_player_id", "provider_player_name", "provider_team_name",
                "provider_birth_date", "match_method", "confidence_level",
                "verification_status", "verification_reason", "evidence_source",
                "provider_release_url", "fpl_source_url",
            ],
        )
        writer.writeheader()
        writer.writerows(candidate_rows)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
