#!/usr/bin/env python3
"""Build a verified-only 11footy/FPL player-match panel and candidate evidence report.

Pending identity candidates are checked against independent FPL match history but
never enter the model-ready panel. Player-level outputs stay inside the workflow
runner; publish aggregate reports only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import lzma
import shutil
import sqlite3
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from audit_11footy_fpl_identity_candidates import normalize_team

PANEL_FIELDS = [
    "season", "competition_id", "provider", "provider_match_id", "fpl_fixture_id",
    "gameweek", "match_date", "provider_player_id", "provider_player_name",
    "provider_team_id", "provider_team_name", "fpl_element_id", "fpl_player_code",
    "fpl_player_name", "fpl_team_id_at_fixture", "minutes_played", "goals",
    "assists", "own_goals", "shots", "shots_on_target", "key_passes",
    "attempts", "attempts_inside_box", "attempts_outside_box", "big_chances",
    "offsides", "fouls_suffered", "fouls_committed", "tracked_shots",
    "tracked_shots_with_xg", "tracked_xg_sum", "fpl_minutes", "fpl_total_points",
    "fpl_goals", "fpl_assists", "join_status",
]

EVIDENCE_FIELDS = [
    "season", "competition_id", "provider_player_id", "provider_player_name",
    "candidate_fpl_element_id", "candidate_fpl_player_name", "confidence_level",
    "verification_status", "provider_player_match_rows", "fixture_matched_rows",
    "fpl_history_overlap_rows", "fpl_history_missing_rows", "team_match_rows",
    "minutes_exact_rows", "goals_exact_rows", "assists_exact_rows",
    "full_signature_exact_rows", "full_signature_match_rate",
    "statistical_corroboration_level", "review_note",
]


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def materialize_sqlite(source: Path, directory: Path):
    if source.suffix.lower() != ".xz":
        return source
    target = directory / source.name[:-3]
    with lzma.open(source, "rb") as compressed, target.open("wb") as output:
        shutil.copyfileobj(compressed, output)
    return target


def as_int(value):
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def as_bool(value):
    return str(value).strip().lower() in {"true", "1", "yes"}


def resolve_player_id(player_id, merge_map):
    current = int(player_id)
    visited = set()
    while current in merge_map:
        if current in visited:
            raise ValueError("Cycle detected in 11footy player_merges at player_id " + str(current))
        visited.add(current)
        current = merge_map[current]
    return current


def load_identity_maps(candidate_rows, crosswalk_rows, season, competition_id):
    candidates = defaultdict(list)
    verified = {}
    errors = []
    crosswalk_season = str(season).replace("-", "/")
    for row in candidate_rows:
        if str(row.get("season") or "") != crosswalk_season:
            continue
        provider_id = as_int(row.get("provider_player_id"))
        element_id = as_int(row.get("fpl_element_id"))
        if provider_id is not None and element_id is not None:
            candidates[provider_id].append(row)

    for row in crosswalk_rows:
        if (
            str(row.get("season") or "") != crosswalk_season
            or str(row.get("competition_id") or "") != str(competition_id)
            or str(row.get("verification_status") or "").lower() != "verified"
        ):
            continue
        provider_id = as_int(row.get("provider_player_id"))
        element_id = as_int(row.get("fpl_element_id"))
        if provider_id is None or element_id is None:
            errors.append({"error": "verified_crosswalk_missing_numeric_identity"})
            continue
        prior = verified.get(provider_id)
        if prior and as_int(prior.get("fpl_element_id")) != element_id:
            errors.append({"error": "conflicting_verified_provider_identity", "provider_player_id": provider_id})
        else:
            verified[provider_id] = row
    return candidates, verified, errors

def build_fixture_map(fpl_fixtures):
    by_key = defaultdict(list)
    fixture_by_id = {}
    for row in fpl_fixtures:
        fixture_id = as_int(row.get("fixture_id"))
        kickoff = str(row.get("kickoff_time") or "")
        home = normalize_team(row.get("team_h_name"))
        away = normalize_team(row.get("team_a_name"))
        if fixture_id is None:
            continue
        fixture_by_id[fixture_id] = row
        if kickoff and home and away:
            by_key[(kickoff[:10], home, away)].append(row)
    return by_key, fixture_by_id


def _player_merge_map(players_connection):
    tables = {
        row[0] for row in players_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if "player_merges" not in tables:
        return {}
    result = {}
    for retired_id, kept_id in players_connection.execute(
        "SELECT retired_id, kept_id FROM player_merges"
    ):
        retired_id, kept_id = int(retired_id), int(kept_id)
        if retired_id in result and result[retired_id] != kept_id:
            raise ValueError("Conflicting player_merges rows for " + str(retired_id))
        result[retired_id] = kept_id
    return result


def _provider_player_names(players_connection):
    columns = {
        row[1] for row in players_connection.execute("PRAGMA table_info(players)")
    }
    required = {"player_id", "name"}
    if not required.issubset(columns):
        raise ValueError("11footy players catalogue is missing player_id or name")
    return {
        int(player_id): str(name or "")
        for player_id, name in players_connection.execute("SELECT player_id, name FROM players")
    }


def _load_player_match_rows(connection, season_id):
    shot_query = """
        SELECT match_id, team_id, player_id,
               COUNT(*) AS tracked_shots,
               SUM(CASE WHEN xg IS NOT NULL THEN 1 ELSE 0 END) AS tracked_shots_with_xg,
               SUM(CASE WHEN xg IS NOT NULL THEN xg ELSE 0 END) AS tracked_xg_sum
        FROM shots
        WHERE layer = 'tracked'
        GROUP BY match_id, team_id, player_id
    """
    query = """
        WITH tracked_shots AS (
            SELECT match_id, team_id, player_id,
                   COUNT(*) AS tracked_shots,
                   SUM(CASE WHEN xg IS NOT NULL THEN 1 ELSE 0 END) AS tracked_shots_with_xg,
                   SUM(CASE WHEN xg IS NOT NULL THEN xg ELSE 0 END) AS tracked_xg_sum
            FROM shots
            WHERE layer = 'tracked'
            GROUP BY match_id, team_id, player_id
        )
        SELECT
            p.match_id, p.team_id, p.player_id, p.minutes_played,
            p.goals, p.assists, p.own_goals, p.shots, p.shots_on_target,
            p.key_passes, p.fouls_committed, p.fouls_suffered,
            p.offsides, ec.attempts, ec.attempts_inside_box,
            ec.attempts_outside_box, ec.big_chances,
            COALESCE(ts.tracked_shots, 0) AS tracked_shots,
            COALESCE(ts.tracked_shots_with_xg, 0) AS tracked_shots_with_xg,
            COALESCE(ts.tracked_xg_sum, 0.0) AS tracked_xg_sum,
            m.kickoff_utc, m.local_date, m.status, m.home_team_id, m.away_team_id,
            ht.name AS home_team_name, at.name AS away_team_name, pt.name AS player_team_name
        FROM player_match_statistics p
        JOIN matches m ON m.match_id = p.match_id
        JOIN teams ht ON ht.team_id = m.home_team_id
        JOIN teams at ON at.team_id = m.away_team_id
        JOIN teams pt ON pt.team_id = p.team_id
        LEFT JOIN player_match_event_counts ec
          ON ec.match_id = p.match_id AND ec.team_id = p.team_id AND ec.player_id = p.player_id
        LEFT JOIN tracked_shots ts
          ON ts.match_id = p.match_id AND ts.team_id = p.team_id AND ts.player_id = p.player_id
        WHERE m.season_id = ? AND m.status IN ('played', 'awarded')
        ORDER BY m.kickoff_utc, p.match_id, p.player_id
    """
    cursor = connection.execute(query, (season_id,))
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _match_date(row):
    kickoff = str(row.get("kickoff_utc") or "")
    if kickoff:
        return kickoff[:10]
    return str(row.get("local_date") or "")[:10]


def _history_team_id(history_row, fixture_row):
    if as_bool(history_row.get("was_home")):
        return as_int(fixture_row.get("team_h_id"))
    return as_int(fixture_row.get("team_a_id"))


def _candidate_evidence_template(candidate):
    return {
        "season": candidate.get("season", ""),
        "competition_id": candidate.get("competition_id", ""),
        "provider_player_id": candidate.get("provider_player_id", ""),
        "provider_player_name": candidate.get("provider_player_name", ""),
        "candidate_fpl_element_id": candidate.get("fpl_element_id", ""),
        "candidate_fpl_player_name": candidate.get("fpl_player_name", ""),
        "confidence_level": candidate.get("confidence_level", ""),
        "verification_status": candidate.get("verification_status", ""),
        "provider_player_match_rows": 0,
        "fixture_matched_rows": 0,
        "fpl_history_overlap_rows": 0,
        "fpl_history_missing_rows": 0,
        "team_match_rows": 0,
        "minutes_exact_rows": 0,
        "goals_exact_rows": 0,
        "assists_exact_rows": 0,
        "full_signature_exact_rows": 0,
        "full_signature_match_rate": "",
        "statistical_corroboration_level": "NO_MATCH_DATA",
        "review_note": "Cross-source match statistics are corroboration only; no candidate is auto-verified.",
    }


def build_panel(
    connection, players_connection, fpl_fixtures, fpl_players, fpl_history,
    candidate_rows, crosswalk_rows, season, competition_id, crosswalk_validation_report=None,
):
    season_start = int(str(season).replace("/", "-").split("-")[0])
    season_rows = connection.execute(
        "SELECT season_id, season FROM seasons WHERE competition_id = ? AND season = ?",
        (int(competition_id), season_start),
    ).fetchall()
    if len(season_rows) != 1:
        raise ValueError(
            "Expected exactly one 11footy season for competition "
            + str(competition_id) + " and season " + str(season_start)
        )
    season_id = int(season_rows[0][0])
    format_row = connection.execute(
        "SELECT built_at, licence FROM format_version LIMIT 1"
    ).fetchone()
    latest_completed = connection.execute(
        "SELECT MAX(kickoff_utc) FROM matches WHERE season_id = ? AND status IN ('played', 'awarded')",
        (season_id,),
    ).fetchone()

    fixture_by_key, _fixture_by_id = build_fixture_map(fpl_fixtures)
    candidates, verified, identity_errors = load_identity_maps(
        candidate_rows, crosswalk_rows, season, competition_id
    )
    validation_status = (
        str(crosswalk_validation_report.get("status") or "")
        if isinstance(crosswalk_validation_report, dict) else "VALIDATION_REPORT_MISSING"
    )
    if validation_status in {"BLOCKED", "VALIDATION_REPORT_MISSING"}:
        identity_errors.append({"error": "crosswalk_validation_" + validation_status.lower()})
        verified = {}
    merge_map = _player_merge_map(players_connection)
    player_names = _provider_player_names(players_connection)

    match_query = """
        SELECT m.match_id, m.kickoff_utc, m.local_date, m.status,
               ht.name AS home_team_name, at.name AS away_team_name
        FROM matches m
        JOIN teams ht ON ht.team_id = m.home_team_id
        JOIN teams at ON at.team_id = m.away_team_id
        WHERE m.season_id = ? AND m.status IN ('played', 'awarded')
        ORDER BY m.kickoff_utc, m.match_id
    """
    match_cursor = connection.execute(match_query, (season_id,))
    match_columns = [item[0] for item in match_cursor.description]
    provider_matches = [dict(zip(match_columns, row)) for row in match_cursor.fetchall()]
    match_map = {}
    match_resolution_status = {}
    match_status_counts = Counter()
    for match in provider_matches:
        match_id = as_int(match["match_id"])
        key = (
            _match_date(match),
            normalize_team(match.get("home_team_name")),
            normalize_team(match.get("away_team_name")),
        )
        matches = fixture_by_key.get(key, [])
        if len(matches) == 1:
            match_map[match_id] = matches[0]
            match_resolution_status[match_id] = "matched"
        elif len(matches) > 1:
            match_resolution_status[match_id] = "ambiguous"
        else:
            match_resolution_status[match_id] = "unmatched"
        match_status_counts[match_resolution_status[match_id]] += 1

    source_rows = _load_player_match_rows(connection, season_id)
    history_by_key = {}
    duplicate_history_keys = []
    for row in fpl_history:
        key = (as_int(row.get("fpl_element_id")), as_int(row.get("fixture_id")))
        if None in key:
            continue
        if key in history_by_key:
            duplicate_history_keys.append(key)
        history_by_key[key] = row

    fpl_player_by_id = {
        as_int(row.get("fpl_element_id")): row
        for row in fpl_players if as_int(row.get("fpl_element_id")) is not None
    }
    evidence_by_provider = {}
    for provider_id, rows in candidates.items():
        candidate_ids = {as_int(row.get("fpl_element_id")) for row in rows}
        if len(candidate_ids) == 1:
            evidence_by_provider[provider_id] = _candidate_evidence_template(rows[0])

    panel_rows = []
    candidate_player_rows = Counter()
    candidate_fixture_rows = Counter()
    candidate_history_rows = Counter()
    candidate_history_missing = Counter()
    candidate_team_matches = Counter()
    candidate_team_mismatches = Counter()
    candidate_minutes_exact = Counter()
    candidate_goals_exact = Counter()
    candidate_assists_exact = Counter()
    candidate_signature_exact = Counter()
    player_match_rows_with_candidate = 0
    player_match_rows_with_verified = 0
    player_match_rows_with_fixture = 0
    player_match_rows_unmatched_fixture = 0
    player_match_rows_ambiguous_fixture = 0
    verified_team_mismatch_rows = 0
    verified_history_missing = 0
    verified_fpl_player_missing = 0

    for source in source_rows:
        provider_id = resolve_player_id(source["player_id"], merge_map)
        match_id = as_int(source["match_id"])
        fixture = match_map.get(match_id)
        fixture_id = as_int(fixture.get("fixture_id")) if fixture else None
        if fixture:
            player_match_rows_with_fixture += 1
        elif match_resolution_status.get(match_id) == "ambiguous":
            player_match_rows_ambiguous_fixture += 1
        else:
            player_match_rows_unmatched_fixture += 1

        candidate_rows_for_id = candidates.get(provider_id, [])
        candidate = candidate_rows_for_id[0] if len(candidate_rows_for_id) == 1 else None
        verified_mapping = verified.get(provider_id)
        verified_element_id = as_int(verified_mapping.get("fpl_element_id")) if verified_mapping else None
        candidate_element_id = as_int(candidate.get("fpl_element_id")) if candidate else None

        if candidate:
            player_match_rows_with_candidate += 1
            candidate_player_rows[provider_id] += 1
        if candidate and fixture and candidate_element_id is not None:
            candidate_fixture_rows[provider_id] += 1
            history = history_by_key.get((candidate_element_id, fixture_id))
            if history is None:
                candidate_history_missing[provider_id] += 1
            else:
                candidate_history_rows[provider_id] += 1
                expected_team_name = (
                    fixture.get("team_h_name") if as_bool(history.get("was_home"))
                    else fixture.get("team_a_name")
                )
                team_match = normalize_team(source.get("player_team_name")) == normalize_team(expected_team_name)
                if team_match:
                    candidate_team_matches[provider_id] += 1
                else:
                    candidate_team_mismatches[provider_id] += 1

                provider_minutes = as_int(source.get("minutes_played"))
                fpl_minutes = as_int(history.get("minutes"))
                provider_goals = as_int(source.get("goals"))
                fpl_goals = as_int(history.get("goals_scored"))
                provider_assists = as_int(source.get("assists"))
                fpl_assists = as_int(history.get("assists"))
                minutes_exact = provider_minutes is not None and provider_minutes == fpl_minutes
                goals_exact = provider_goals is not None and provider_goals == fpl_goals
                assists_exact = provider_assists is not None and provider_assists == fpl_assists
                if minutes_exact:
                    candidate_minutes_exact[provider_id] += 1
                if goals_exact:
                    candidate_goals_exact[provider_id] += 1
                if assists_exact:
                    candidate_assists_exact[provider_id] += 1
                if team_match and minutes_exact and goals_exact and assists_exact:
                    candidate_signature_exact[provider_id] += 1

        if verified_element_id is None:
            continue
        player_match_rows_with_verified += 1
        if fixture is None:
            continue
        history = history_by_key.get((verified_element_id, fixture_id))
        if history is None:
            verified_history_missing += 1
            continue
        expected_team_name = (
            fixture.get("team_h_name") if as_bool(history.get("was_home"))
            else fixture.get("team_a_name")
        )
        if normalize_team(source.get("player_team_name")) != normalize_team(expected_team_name):
            verified_team_mismatch_rows += 1
            continue
        fpl_player = fpl_player_by_id.get(verified_element_id)
        if fpl_player is None:
            verified_fpl_player_missing += 1
            continue
        if str(fpl_player.get("fpl_player_code") or "") != str(verified_mapping.get("fpl_player_code") or ""):
            identity_errors.append({
                "error": "verified_crosswalk_fpl_code_mismatch",
                "provider_player_id": provider_id,
                "fpl_element_id": verified_element_id,
            })
            continue

        panel_rows.append({
            "season": season,
            "competition_id": competition_id,
            "provider": "11footy",
            "provider_match_id": match_id,
            "fpl_fixture_id": fixture_id,
            "gameweek": fixture.get("gameweek", ""),
            "match_date": _match_date(source),
            "provider_player_id": provider_id,
            "provider_player_name": player_names.get(provider_id, ""),
            "provider_team_id": as_int(source.get("team_id")),
            "provider_team_name": source.get("player_team_name", ""),
            "fpl_element_id": verified_element_id,
            "fpl_player_code": fpl_player.get("fpl_player_code", ""),
            "fpl_player_name": fpl_player.get("web_name", ""),
            "fpl_team_id_at_fixture": (
                as_int(fixture.get("team_h_id")) if as_bool(history.get("was_home"))
                else as_int(fixture.get("team_a_id"))
            ),
            "minutes_played": source.get("minutes_played", ""),
            "goals": source.get("goals", ""),
            "assists": source.get("assists", ""),
            "own_goals": source.get("own_goals", ""),
            "shots": source.get("shots", ""),
            "shots_on_target": source.get("shots_on_target", ""),
            "key_passes": source.get("key_passes", ""),
            "attempts": source.get("attempts", ""),
            "attempts_inside_box": source.get("attempts_inside_box", ""),
            "attempts_outside_box": source.get("attempts_outside_box", ""),
            "big_chances": source.get("big_chances", ""),
            "offsides": source.get("offsides", ""),
            "fouls_suffered": source.get("fouls_suffered", ""),
            "fouls_committed": source.get("fouls_committed", ""),
            "tracked_shots": source.get("tracked_shots", 0),
            "tracked_shots_with_xg": source.get("tracked_shots_with_xg", 0),
            "tracked_xg_sum": source.get("tracked_xg_sum", 0),
            "fpl_minutes": history.get("minutes", ""),
            "fpl_total_points": history.get("total_points", ""),
            "fpl_goals": history.get("goals_scored", ""),
            "fpl_assists": history.get("assists", ""),
            "join_status": "VERIFIED_IDENTITY_AND_FIXTURE",
        })

    evidence_rows = []
    for provider_id, evidence in sorted(evidence_by_provider.items()):
        evidence["provider_player_match_rows"] = candidate_player_rows[provider_id]
        evidence["fixture_matched_rows"] = candidate_fixture_rows[provider_id]
        evidence["fpl_history_overlap_rows"] = candidate_history_rows[provider_id]
        evidence["fpl_history_missing_rows"] = candidate_history_missing[provider_id]
        evidence["team_match_rows"] = candidate_team_matches[provider_id]
        evidence["team_mismatch_rows"] = candidate_team_mismatches[provider_id]
        evidence["minutes_exact_rows"] = candidate_minutes_exact[provider_id]
        evidence["goals_exact_rows"] = candidate_goals_exact[provider_id]
        evidence["assists_exact_rows"] = candidate_assists_exact[provider_id]
        evidence["full_signature_exact_rows"] = candidate_signature_exact[provider_id]
        overlaps = candidate_history_rows[provider_id]
        exact = candidate_signature_exact[provider_id]
        evidence["full_signature_match_rate"] = round(exact / overlaps, 6) if overlaps else ""
        if overlaps >= 3 and exact == overlaps:
            evidence["statistical_corroboration_level"] = "STRONG_MULTI_MATCH_CONSISTENCY_REVIEW"
        elif overlaps >= 1 and exact == overlaps:
            evidence["statistical_corroboration_level"] = "LIMITED_MATCH_CONSISTENCY_REVIEW"
        elif overlaps:
            evidence["statistical_corroboration_level"] = "PARTIAL_OR_CONFLICTING_MATCH_EVIDENCE"
        evidence_rows.append(evidence)

    fixture_ids_mapped = {
        as_int(row.get("fixture_id"))
        for row in match_map.values()
        if as_int(row.get("fixture_id")) is not None
    }
    provider_team_ids_invalid = sum(
        1 for row in source_rows
        if as_int(row.get("team_id")) is not None
        and as_int(row.get("team_id")) not in {
            as_int(row.get("home_team_id")), as_int(row.get("away_team_id"))
        }
    )
    join_ready = (
        bool(verified)
        and len(panel_rows) > 0
        and not identity_errors
        and verified_team_mismatch_rows == 0
        and verified_history_missing == 0
        and verified_fpl_player_missing == 0
        and not duplicate_history_keys
        and provider_team_ids_invalid == 0
        and len(match_map) == len(provider_matches)
        and player_match_rows_unmatched_fixture == 0
        and player_match_rows_ambiguous_fixture == 0
    )
    report = {
        "provider": "11footy",
        "source_release": "11footy-2026-11-10",
        "season": season,
        "competition_id": str(competition_id),
        "11footy_season_id": season_id,
        "source_built_at": format_row[0] if format_row else None,
        "source_licence": format_row[1] if format_row else None,
        "latest_completed_match_kickoff_utc": latest_completed[0] if latest_completed else None,
        "source_match_count": len(provider_matches),
        "provider_matches_with_fixture_match": len(match_map),
        "unique_fpl_fixture_ids_matched": len(fixture_ids_mapped),
        "fixture_match_status_counts": dict(match_status_counts),
        "player_match_rows": len(source_rows),
        "player_match_rows_with_fpl_fixture": player_match_rows_with_fixture,
        "player_match_rows_unmatched_fixture": player_match_rows_unmatched_fixture,
        "player_match_rows_ambiguous_fixture": player_match_rows_ambiguous_fixture,
        "player_match_rows_with_candidate_identity": player_match_rows_with_candidate,
        "candidate_identity_count": len(evidence_rows),
        "candidate_high_confidence_count": sum(row["confidence_level"] == "high" for row in evidence_rows),
        "candidate_rows_with_multi_match_consistency": sum(
            row["statistical_corroboration_level"] == "STRONG_MULTI_MATCH_CONSISTENCY_REVIEW"
            for row in evidence_rows
        ),
        "candidate_rows_with_any_match_conflict": sum(row["team_mismatch_rows"] > 0 for row in evidence_rows),
        "verified_crosswalk_rows": len(verified),
        "crosswalk_validation_status": validation_status,
        "player_match_rows_with_verified_identity": player_match_rows_with_verified,
        "verified_player_match_panel_rows": len(panel_rows),
        "verified_identity_history_missing_rows": verified_history_missing,
        "verified_team_mismatch_rows": verified_team_mismatch_rows,
        "verified_fpl_player_missing_rows": verified_fpl_player_missing,
        "provider_team_ids_not_in_match_teams": provider_team_ids_invalid,
        "duplicate_fpl_player_fixture_keys": len(duplicate_history_keys),
        "identity_errors": identity_errors,
        "identity_policy": "Only verified season/competition-scoped crosswalk rows enter the player-match panel; pending candidates are evidence-only.",
        "candidate_evidence_policy": "Exact match-level minutes, goals, assists and team agreement are corroboration only; no automated candidate is promoted to verified.",
        "feature_scope": "11footy player-match statistics, event counts and tracked-shot xG; not continuous tracking or full event-level CTA.",
        "prediction_validation": "NOT_EVALUATED",
        "join_ready": join_ready,
        "status": (
            "PASS_JOIN_READY" if join_ready
            else "BLOCKED" if identity_errors or duplicate_history_keys or provider_team_ids_invalid or not provider_matches
            else "PARTIAL_FIXTURE_OR_IDENTITY_RECONCILIATION" if len(match_map) != len(provider_matches)
                or player_match_rows_unmatched_fixture or player_match_rows_ambiguous_fixture
                or verified_team_mismatch_rows or verified_history_missing or verified_fpl_player_missing
            else "CANDIDATE_REVIEW_READY_NOT_MODEL_JOIN_READY"
        ),
    }
    return panel_rows, evidence_rows, report

def main():
    parser = argparse.ArgumentParser(description="Build verified-only 11footy/FPL player-match features")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--players-database", type=Path, required=True)
    parser.add_argument("--fpl-fixtures", type=Path, required=True)
    parser.add_argument("--fpl-players", type=Path, required=True)
    parser.add_argument("--fpl-player-fixture", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--crosswalk", type=Path, required=True)
    parser.add_argument("--crosswalk-validation", type=Path, required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument("--release", default="11footy-2026-11-10")
    parser.add_argument("--competition-id", default="1")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    candidates = read_csv(args.candidates)
    crosswalk = read_csv(args.crosswalk)
    validation_report = (
        json.loads(args.crosswalk_validation.read_text(encoding="utf-8"))
        if args.crosswalk_validation.exists() else None
    )
    fixtures = read_csv(args.fpl_fixtures)
    fpl_players = read_csv(args.fpl_players)
    fpl_history = read_csv(args.fpl_player_fixture)

    with tempfile.TemporaryDirectory(prefix="cta-11footy-panel-") as temp:
        temp_path = Path(temp)
        database_path = materialize_sqlite(args.database, temp_path)
        players_path = materialize_sqlite(args.players_database, temp_path)
        connection = sqlite3.connect("file:" + str(database_path.resolve()) + "?mode=ro", uri=True)
        players_connection = sqlite3.connect("file:" + str(players_path.resolve()) + "?mode=ro", uri=True)
        try:
            panel_rows, evidence_rows, report = build_panel(
                connection, players_connection, fixtures, fpl_players, fpl_history,
                candidates, crosswalk, args.season, args.competition_id,
                crosswalk_validation_report=validation_report,
            )
        finally:
            connection.close()
            players_connection.close()

    report["source_release"] = args.release
    report["attribution"] = "11footy; CC BY-NC 4.0; non-commercial use only."
    report["source_hashes"] = {
        "11footy_match_database_sha256": sha256(args.database),
        "11footy_player_catalogue_sha256": sha256(args.players_database),
        "official_fpl_fixtures_sha256": sha256(args.fpl_fixtures),
        "official_fpl_players_sha256": sha256(args.fpl_players),
        "official_fpl_player_fixture_history_sha256": sha256(args.fpl_player_fixture),
        "identity_candidate_snapshot_sha256": sha256(args.candidates),
        "verified_crosswalk_snapshot_sha256": sha256(args.crosswalk),
    }
    write_csv(args.out_dir / "verified_player_match_panel.csv", PANEL_FIELDS, panel_rows)
    write_csv(args.out_dir / "candidate_match_evidence.csv", EVIDENCE_FIELDS, evidence_rows)
    (args.out_dir / "11footy_fpl_player_match_integration.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 2 if report["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
