#!/usr/bin/env python3
"""Build a pending-only 11footy↔historical-FPL identity review queue for 2017/18."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import lzma
import sqlite3
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from build_11footy_player_match_features import (
    _load_player_match_rows,
    _player_merge_map,
    _provider_player_names,
)
from build_wyscout_fpl_identity_candidates import (
    as_int,
    build_fixture_index,
    build_fpl_player_maps,
    build_fpl_team_names,
    normalize_team,
    normalize_text,
    read_csv,
)


def materialize_sqlite(source: Path, directory: Path):
    if source.suffix.lower() != ".xz":
        return source
    target = directory / source.name[:-3]
    with lzma.open(source, "rb") as compressed, target.open("wb") as output:
        import shutil
        shutil.copyfileobj(compressed, output)
    return target


def sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _provider_birth_dates(players_connection):
    columns = {row[1] for row in players_connection.execute("PRAGMA table_info(players)")}
    if "birth_date" not in columns:
        return {}
    return {
        int(player_id): str(birth_date or "")
        for player_id, birth_date in players_connection.execute(
            "SELECT player_id, birth_date FROM players"
        )
    }


def _canonical_player_match_rows(rows, merge_map, player_names):
    grouped = {}
    duplicate_merge_keys = set()
    sum_fields = (
        "minutes_played", "goals", "own_goals", "assists", "shots",
        "shots_on_target", "key_passes", "attempts", "attempts_inside_box",
        "attempts_outside_box", "big_chances", "offsides", "fouls_suffered",
        "fouls_committed", "tracked_shots", "tracked_shots_with_xg",
    )
    for source in rows:
        provider_id = as_int(source.get("player_id"))
        if provider_id is None:
            continue
        canonical_id = merge_map.get(provider_id, provider_id)
        key = (as_int(source.get("match_id")), as_int(source.get("team_id")), canonical_id)
        if key not in grouped:
            row = dict(source)
            row["provider_player_id"] = canonical_id
            row["provider_player_name"] = player_names.get(canonical_id) or player_names.get(provider_id, "")
            for field in sum_fields:
                row[field] = as_int(row.get(field)) or 0
            grouped[key] = row
        else:
            duplicate_merge_keys.add(key)
            row = grouped[key]
            for field in sum_fields:
                row[field] += as_int(source.get(field)) or 0
    return list(grouped.values()), duplicate_merge_keys


def _match_fixture_map(provider_rows, fixture_index):
    matches = {}
    for row in provider_rows:
        match_id = as_int(row.get("match_id"))
        if match_id is None:
            continue
        context = {
            "date": str(row.get("kickoff_utc") or row.get("local_date") or "")[:10],
            "home_team": str(row.get("home_team_name") or ""),
            "away_team": str(row.get("away_team_name") or ""),
        }
        prior = matches.get(match_id)
        if prior and prior != context:
            raise ValueError(f"Inconsistent 11footy match metadata for {match_id}")
        matches[match_id] = context

    resolved = {}
    statuses = Counter()
    for match_id, context in matches.items():
        home_key = (context["date"], True, normalize_team(context["away_team"]))
        away_key = (context["date"], False, normalize_team(context["home_team"]))
        home_ids = fixture_index.get(home_key, set())
        away_ids = fixture_index.get(away_key, set())
        if len(home_ids) == 1 and home_ids == away_ids:
            resolved[match_id] = next(iter(home_ids))
            statuses["matched"] += 1
        elif home_ids or away_ids:
            statuses["ambiguous_or_inconsistent"] += 1
        else:
            statuses["unmatched"] += 1
    return resolved, statuses


def build_identity_review_queue(provider_rows, player_names, birth_dates, fpl_players,
                                fpl_idlist, fpl_history, fpl_team_rows, merge_duplicate_keys=None):
    team_names = build_fpl_team_names(fpl_team_rows)
    fpl_by_name, fpl_by_id = build_fpl_player_maps(fpl_players, fpl_idlist, team_names)
    fixture_index, fixture_by_id = build_fixture_index(fpl_history, team_names)
    match_to_fixture, fixture_statuses = _match_fixture_map(provider_rows, fixture_index)

    history_by_key = {}
    duplicate_history_keys = set()
    for row in fpl_history:
        element_id = as_int(row.get("element"))
        fixture_id = as_int(row.get("fixture"))
        if element_id is None or fixture_id is None:
            continue
        key = (element_id, fixture_id)
        if key in history_by_key:
            duplicate_history_keys.add(key)
        history_by_key[key] = row

    rows_by_provider = defaultdict(list)
    for row in provider_rows:
        provider_id = as_int(row.get("provider_player_id"))
        if provider_id is not None:
            rows_by_provider[provider_id].append(row)

    candidates = []
    priority_counts = Counter()
    player_match_rows_with_name_candidate = 0
    player_match_rows_with_fpl_history = 0
    for provider_id, player_rows in sorted(rows_by_provider.items()):
        provider_name = player_names.get(provider_id) or str(player_rows[0].get("provider_player_name") or "")
        fpl_matches = fpl_by_name.get(normalize_text(provider_name), [])
        if len(fpl_matches) == 1:
            candidate = fpl_matches[0]
            match_method = "EXACT_NORMALIZED_FULL_NAME_UNIQUE"
            candidate_status = "PENDING"
        elif len(fpl_matches) > 1:
            candidate = None
            match_method = "EXACT_NORMALIZED_FULL_NAME_AMBIGUOUS"
            candidate_status = "AMBIGUOUS"
        else:
            candidate = None
            match_method = "NO_EXACT_FULL_NAME_MATCH"
            candidate_status = "UNMATCHED"

        provider_teams = sorted({
            str(row.get("player_team_name") or "").strip()
            for row in player_rows if row.get("player_team_name")
        })
        candidate_team = normalize_team(candidate["fpl_team_name"]) if candidate else ""
        team_keys = {normalize_team(team) for team in provider_teams}
        team_match = bool(candidate_team and candidate_team in team_keys)
        team_mismatch = bool(candidate and team_keys and not team_match)

        fixture_rows = 0
        history_missing = 0
        history_ambiguous = 0
        positive_minutes = 0
        minutes_exact = 0
        goals_exact = 0
        own_goals_exact = 0
        assists_exact = 0
        signature_exact = 0
        signature_zero_only = 0
        provider_totals = Counter()
        fpl_totals = Counter()
        if candidate:
            player_match_rows_with_name_candidate += len(player_rows)
            for row in player_rows:
                fixture_id = match_to_fixture.get(as_int(row.get("match_id")))
                if fixture_id is None:
                    continue
                fixture_rows += 1
                history_key = (candidate["fpl_element_id"], fixture_id)
                if history_key in duplicate_history_keys:
                    history_ambiguous += 1
                    continue
                history = history_by_key.get(history_key)
                if history is None:
                    history_missing += 1
                    continue
                player_match_rows_with_fpl_history += 1
                provider_minutes = as_int(row.get("minutes_played")) or 0
                fpl_minutes = as_int(history.get("minutes")) or 0
                provider_goals = as_int(row.get("goals")) or 0
                provider_own_goals = as_int(row.get("own_goals")) or 0
                provider_assists = as_int(row.get("assists")) or 0
                fpl_goals = as_int(history.get("goals_scored")) or 0
                fpl_own_goals = as_int(history.get("own_goals")) or 0
                fpl_assists = as_int(history.get("assists")) or 0
                minutes_exact += int(provider_minutes == fpl_minutes)
                goals_exact += int(provider_goals == fpl_goals)
                own_goals_exact += int(provider_own_goals == fpl_own_goals)
                assists_exact += int(provider_assists == fpl_assists)
                signature = (
                    provider_minutes, provider_goals, provider_own_goals, provider_assists
                ) == (fpl_minutes, fpl_goals, fpl_own_goals, fpl_assists)
                if signature and provider_minutes > 0:
                    signature_exact += 1
                elif signature:
                    signature_zero_only += 1
                positive_minutes += int(fpl_minutes > 0)
                provider_totals.update({
                    "minutes": provider_minutes,
                    "goals": provider_goals,
                    "own_goals": provider_own_goals,
                    "assists": provider_assists,
                })
                fpl_totals.update({
                    "minutes": fpl_minutes,
                    "goals": fpl_goals,
                    "own_goals": fpl_own_goals,
                    "assists": fpl_assists,
                })

        if candidate and signature_exact >= 3 and team_match and not team_mismatch and positive_minutes > 0:
            priority = "P1_MULTI_MATCH_TEAM_SIGNATURE"
        elif candidate and signature_exact > 0 and team_match and not team_mismatch:
            priority = "P2_TEAM_AND_FULL_SIGNATURE"
        elif candidate and fixture_rows > 0:
            priority = "P3_HISTORY_REVIEW"
        elif candidate:
            priority = "P4_IDENTITY_REVIEW"
        else:
            priority = "P5_UNMATCHED_OR_AMBIGUOUS"
        priority_counts[priority] += 1
        candidates.append({
            "season": "2017/18",
            "competition": "English Premier League",
            "provider": "11footy",
            "provider_player_id": provider_id,
            "provider_player_name": provider_name,
            "provider_birth_date": birth_dates.get(provider_id, ""),
            "provider_team_names_seen": ";".join(provider_teams),
            "candidate_fpl_element_id": candidate["fpl_element_id"] if candidate else "",
            "candidate_fpl_player_code": candidate["fpl_player_code"] if candidate else "",
            "candidate_fpl_player_name": candidate["fpl_player_name"] if candidate else "",
            "candidate_fpl_team_id": candidate["fpl_team_id"] if candidate else "",
            "candidate_fpl_team_name": candidate["fpl_team_name"] if candidate else "",
            "candidate_fpl_birth_date": "",
            "candidate_status": candidate_status,
            "verification_status": "PENDING" if candidate else candidate_status,
            "match_method": match_method,
            "team_match_to_season_end_team": team_match,
            "team_mismatch_to_season_end_team": team_mismatch,
            "provider_player_match_rows": len(player_rows),
            "fixture_mapped_rows": fixture_rows,
            "fpl_history_overlap_rows": fixture_rows - history_missing - history_ambiguous,
            "fpl_history_missing_rows": history_missing,
            "fpl_history_ambiguous_rows": history_ambiguous,
            "fpl_positive_minutes_rows": positive_minutes,
            "minutes_exact_rows": minutes_exact,
            "goals_exact_rows": goals_exact,
            "own_goals_exact_rows": own_goals_exact,
            "assists_exact_rows": assists_exact,
            "full_signature_exact_rows": signature_exact,
            "full_signature_zero_only_rows": signature_zero_only,
            "provider_minutes_sum": provider_totals["minutes"],
            "provider_goals_sum": provider_totals["goals"],
            "provider_own_goals_sum": provider_totals["own_goals"],
            "provider_assists_sum": provider_totals["assists"],
            "fpl_minutes_sum": fpl_totals["minutes"],
            "fpl_goals_sum": fpl_totals["goals"],
            "fpl_own_goals_sum": fpl_totals["own_goals"],
            "fpl_assists_sum": fpl_totals["assists"],
            "review_priority": priority,
            "review_note": (
                "Automated historical corroboration only. Exact names, team history and per-match "
                "minutes/goals/own-goals/assists agreement are evidence, not proof; identity remains PENDING."
            ),
        })

    priority_order = {
        "P1_MULTI_MATCH_TEAM_SIGNATURE": 0,
        "P2_TEAM_AND_FULL_SIGNATURE": 1,
        "P3_HISTORY_REVIEW": 2,
        "P4_IDENTITY_REVIEW": 3,
        "P5_UNMATCHED_OR_AMBIGUOUS": 4,
    }
    candidates.sort(key=lambda row: (
        priority_order[row["review_priority"]],
        -int(row["full_signature_exact_rows"]),
        -int(row["fpl_history_overlap_rows"]),
        int(row["provider_player_id"]),
    ))
    report = {
        "provider": "11footy",
        "season": "2017/18",
        "competition": "English Premier League",
        "provider_players_with_match_rows": len(rows_by_provider),
        "historical_fpl_players": len(fpl_by_id),
        "exact_name_unique_candidate_count": sum(row["candidate_status"] == "PENDING" for row in candidates),
        "ambiguous_name_candidate_count": sum(row["candidate_status"] == "AMBIGUOUS" for row in candidates),
        "unmatched_name_count": sum(row["candidate_status"] == "UNMATCHED" for row in candidates),
        "player_match_rows_with_name_candidate": player_match_rows_with_name_candidate,
        "player_match_rows_with_fpl_history": player_match_rows_with_fpl_history,
        "fpl_fixture_rows": len(fpl_history),
        "provider_matches_with_fixture_status": dict(fixture_statuses),
        "candidate_review_priority_counts": dict(priority_counts),
        "duplicate_fpl_player_fixture_keys": len(duplicate_history_keys),
        "duplicate_player_merge_match_keys": len(merge_duplicate_keys or []),
        "identity_policy": "Exact normalized full names only; team and per-match minutes/goals/own-goals/assists are corroboration; no fuzzy matching and no automatic verification.",
        "verification_status": "NO_CANDIDATE_AUTO_VERIFIED",
        "candidate_publication_policy": "Candidate-level rows remain local to the workflow runner; only aggregate counts are published.",
        "prediction_validation": "NOT_EVALUATED",
        "source_attribution": "11footy EPL dataset, CC BY-NC 4.0 (non-commercial use only); historical FPL archive by Vaastav Anand, with underlying FPL data owned by Fantasy Premier League.",
        "limitations": [
            "The historical FPL archive has no player birth date; 11footy birth dates cannot be independently cross-checked against FPL.",
            "The historical FPL archive may contain corrections and is used for identity corroboration only, not point-in-time prediction training.",
            "Player team in the FPL season-end player file may differ from the team at a specific fixture; team mismatch is a review signal, not automatic rejection.",
            "Fixture mapping uses exact UTC date, opponent and home/away context; unmatched and ambiguous fixtures remain isolated.",
        ],
    }
    return candidates, report


def attach_current_candidates(historical_candidates, current_candidates):
    current_by_provider = defaultdict(list)
    for row in current_candidates:
        provider_id = as_int(row.get("provider_player_id"))
        if provider_id is not None:
            current_by_provider[provider_id].append(row)

    priority_counts = Counter()
    current_overlap = 0
    current_high_overlap = 0
    for row in historical_candidates:
        matches = current_by_provider.get(as_int(row["provider_player_id"]), [])
        if len(matches) == 1:
            current = matches[0]
            current_overlap += 1
            confidence = str(current.get("confidence_level") or "").lower()
            if confidence == "high":
                current_high_overlap += 1
                current_status = "HIGH_CONFIDENCE_PENDING"
            else:
                current_status = "REVIEW_REQUIRED_PENDING"
            row["current_fpl_element_id"] = current.get("fpl_element_id", "")
            row["current_fpl_player_code"] = current.get("fpl_player_code", "")
            row["current_fpl_player_name"] = current.get("fpl_player_name", "")
            row["current_fpl_team_id"] = current.get("fpl_team_id", "")
            row["current_fpl_team_name"] = current.get("fpl_team_name", "")
            row["current_fpl_birth_date"] = current.get("fpl_birth_date", "")
            row["current_candidate_confidence"] = current.get("confidence_level", "")
            row["current_candidate_verification_status"] = current.get("verification_status", "")
            row["current_candidate_status"] = current_status
        elif len(matches) > 1:
            row["current_fpl_element_id"] = ""
            row["current_fpl_player_code"] = ""
            row["current_fpl_player_name"] = ""
            row["current_fpl_team_id"] = ""
            row["current_fpl_team_name"] = ""
            row["current_fpl_birth_date"] = ""
            row["current_candidate_confidence"] = ""
            row["current_candidate_verification_status"] = "AMBIGUOUS"
            row["current_candidate_status"] = "AMBIGUOUS"
        else:
            row["current_fpl_element_id"] = ""
            row["current_fpl_player_code"] = ""
            row["current_fpl_player_name"] = ""
            row["current_fpl_team_id"] = ""
            row["current_fpl_team_name"] = ""
            row["current_fpl_birth_date"] = ""
            row["current_candidate_confidence"] = ""
            row["current_candidate_verification_status"] = ""
            row["current_candidate_status"] = "NO_CURRENT_CANDIDATE"

        if row["current_candidate_status"] == "HIGH_CONFIDENCE_PENDING":
            if row["review_priority"] == "P1_MULTI_MATCH_TEAM_SIGNATURE":
                cross_priority = "P1_HISTORICAL_AND_CURRENT_HIGH"
            elif row["review_priority"] == "P2_TEAM_AND_FULL_SIGNATURE":
                cross_priority = "P2_HISTORICAL_AND_CURRENT_HIGH"
            else:
                cross_priority = "P3_CURRENT_HIGH_HISTORICAL_REVIEW"
        elif row["current_candidate_status"] == "REVIEW_REQUIRED_PENDING":
            if row["review_priority"] == "P1_MULTI_MATCH_TEAM_SIGNATURE":
                cross_priority = "P2_HISTORICAL_P1_CURRENT_REVIEW"
            elif row["review_priority"] == "P2_TEAM_AND_FULL_SIGNATURE":
                cross_priority = "P3_HISTORICAL_P2_CURRENT_REVIEW"
            else:
                cross_priority = "P4_HISTORICAL_AND_CURRENT_REVIEW"
        elif row["review_priority"] == "P1_MULTI_MATCH_TEAM_SIGNATURE":
            cross_priority = "P2_HISTORICAL_P1_CURRENT_NOT_HIGH"
        elif row["current_candidate_status"] == "AMBIGUOUS":
            cross_priority = "P4_CURRENT_IDENTITY_AMBIGUOUS"
        elif row["candidate_status"] == "PENDING":
            cross_priority = "P4_HISTORICAL_ONLY_REVIEW"
        else:
            cross_priority = "P5_UNMATCHED_OR_NO_CURRENT_CANDIDATE"
        row["cross_season_review_priority"] = cross_priority
        priority_counts[cross_priority] += 1

    report = {
        "current_fpl_candidate_provider_ids": len(current_by_provider),
        "historical_current_provider_id_overlap": current_overlap,
        "historical_current_high_confidence_overlap": current_high_overlap,
        "current_candidate_provider_ids_without_historical_rows": len(
            set(current_by_provider) - {as_int(row["provider_player_id"]) for row in historical_candidates}
        ),
        "cross_season_review_priority_counts": dict(priority_counts),
    }
    return historical_candidates, report


def build_from_databases(database_path, players_database_path, fpl_players, fpl_idlist,
                         fpl_history, fpl_team_rows, season=2017, competition_id=1):
    with tempfile.TemporaryDirectory(prefix="cta-11footy-historical-") as temp:
        temp_path = Path(temp)
        db_path = materialize_sqlite(database_path, temp_path)
        players_path = materialize_sqlite(players_database_path, temp_path)
        connection = sqlite3.connect("file:" + str(db_path.resolve()) + "?mode=ro", uri=True)
        players_connection = sqlite3.connect("file:" + str(players_path.resolve()) + "?mode=ro", uri=True)
        try:
            season_rows = connection.execute(
                "SELECT season_id FROM seasons WHERE competition_id = ? AND season = ?",
                (int(competition_id), int(season)),
            ).fetchall()
            if len(season_rows) != 1:
                raise ValueError(f"Expected one 11footy season row for {competition_id}/{season}; found {len(season_rows)}")
            season_id = int(season_rows[0][0])
            raw_rows = _load_player_match_rows(connection, season_id)
            merge_map = _player_merge_map(players_connection)
            names = _provider_player_names(players_connection)
            birth_dates = _provider_birth_dates(players_connection)
            provider_rows, merge_duplicate_keys = _canonical_player_match_rows(raw_rows, merge_map, names)
            candidates, report = build_identity_review_queue(
                provider_rows, names, birth_dates, fpl_players, fpl_idlist,
                fpl_history, fpl_team_rows, merge_duplicate_keys,
            )
            report["11footy_season_id"] = season_id
            report["source_player_match_rows"] = len(raw_rows)
            report["canonical_player_match_rows"] = len(provider_rows)
            report["player_merge_rows"] = len(merge_map)
            report["latest_completed_match_kickoff_utc"] = max(
                (str(row.get("kickoff_utc") or "") for row in raw_rows), default=""
            )
            return candidates, report
        finally:
            connection.close()
            players_connection.close()


def main():
    parser = argparse.ArgumentParser(description="Build pending-only 11footy 2017/18 FPL identity candidates")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--players-database", type=Path, required=True)
    parser.add_argument("--fpl-players", type=Path, required=True)
    parser.add_argument("--fpl-player-idlist", type=Path, required=True)
    parser.add_argument("--fpl-gameweek-history", type=Path, required=True)
    parser.add_argument("--fpl-team-list", type=Path, required=True)
    parser.add_argument("--fpl-source-commit", required=True)
    parser.add_argument("--11footy-release", dest="footy_release", required=True)
    parser.add_argument("--current-candidates", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    candidates, report = build_from_databases(
        args.database, args.players_database,
        read_csv(args.fpl_players), read_csv(args.fpl_player_idlist),
        read_csv(args.fpl_gameweek_history), read_csv(args.fpl_team_list),
    )
    report["historical_fpl_source_commit"] = args.fpl_source_commit
    report["11footy_source_release"] = args.footy_release
    if args.current_candidates:
        candidates, current_report = attach_current_candidates(candidates, read_csv(args.current_candidates))
        report.update(current_report)
        report["current_candidate_csv_sha256"] = sha256(args.current_candidates)
    report["source_hashes"] = {
        "11footy_match_database_sha256": sha256(args.database),
        "11footy_player_catalogue_sha256": sha256(args.players_database),
        "historical_fpl_players_sha256": sha256(args.fpl_players),
        "historical_fpl_player_idlist_sha256": sha256(args.fpl_player_idlist),
        "historical_fpl_gameweek_history_sha256": sha256(args.fpl_gameweek_history),
        "historical_fpl_team_list_sha256": sha256(args.fpl_team_list),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    fields = list(candidates[0]) if candidates else [
        "season", "competition", "provider", "provider_player_id",
        "provider_player_name", "candidate_fpl_element_id",
        "candidate_fpl_player_name", "verification_status",
        "review_priority", "review_note",
    ]
    for name in ("11footy_fpl_identity_candidates.csv", "11footy_fpl_identity_review_queue.csv"):
        with (args.out_dir / name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(candidates)
    (args.out_dir / "11footy_historical_fpl_identity_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        key: report[key] for key in (
            "provider_players_with_match_rows", "historical_fpl_players",
            "exact_name_unique_candidate_count", "ambiguous_name_candidate_count",
            "unmatched_name_count", "player_match_rows_with_fpl_history",
            "provider_matches_with_fixture_status", "candidate_review_priority_counts",
            "verification_status", "prediction_validation",
        )
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
