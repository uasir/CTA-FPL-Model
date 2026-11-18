#!/usr/bin/env python3
"""Audit the 11footy Premier League SQLite release without publishing raw data."""
from __future__ import annotations

import argparse
import hashlib
import json
import lzma
import shutil
import sqlite3
import tempfile
from pathlib import Path


REQUIRED_TABLES = {
    "format_version", "competitions", "seasons", "matches", "teams", "players",
    "match_events", "shots", "match_players", "player_match_statistics",
    "player_match_event_counts", "match_team_statistics",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _materialize_sqlite(source: Path, temp_dir: Path) -> Path:
    if source.suffix.lower() != ".xz":
        return source
    target = temp_dir / "11footy-premier-league.db"
    with lzma.open(source, "rb") as compressed, target.open("wb") as output:
        shutil.copyfileobj(compressed, output)
    return target


def _tables(connection):
    return {
        row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def audit_database(connection, source_release: str, source_sha256: str,\n                   players_connection=None, players_sha256: str | None = None):
    tables = _tables(connection)
    missing_tables = sorted(REQUIRED_TABLES - tables)
    if missing_tables:
        raise ValueError("11footy database is missing required tables: " + ", ".join(missing_tables))

    format_rows = [
        dict(zip([column[0] for column in cursor.description], row))
        for cursor in [connection.execute("SELECT * FROM format_version")]
        for row in cursor.fetchall()
    ]
    if not format_rows:
        raise ValueError("format_version table is empty")

    competitions = [
        dict(zip([column[0] for column in cursor.description], row))
        for cursor in [connection.execute(
            "SELECT competition_id, code, name, country, kind, time_zone "
            "FROM competitions WHERE lower(name) LIKE '%premier league%' OR code='PL'"
        )]
        for row in cursor.fetchall()
    ]
    if not competitions:
        raise ValueError("No Premier League competition found in the dataset")

    comp_ids = [int(row["competition_id"]) for row in competitions]
    placeholders = ",".join("?" for _ in comp_ids)

    season_query = (
        "SELECT s.season_id, s.season, s.name AS season_name, s.status AS season_status, "
        "COUNT(m.match_id) AS match_rows, "
        "SUM(CASE WHEN m.status IN ('played','awarded') THEN 1 ELSE 0 END) AS completed_matches, "
        "SUM(CASE WHEN m.status IN ('scheduled','postponed') THEN 1 ELSE 0 END) AS future_or_postponed, "
        "MAX(CASE WHEN m.status IN ('played','awarded') THEN m.kickoff_utc END) AS latest_completed_kickoff_utc, "
        "MAX(m.kickoff_utc) AS latest_kickoff_utc, MAX(m.matchday) AS max_matchday "
        "FROM seasons s JOIN competitions c ON c.competition_id=s.competition_id "
        "LEFT JOIN matches m ON m.season_id=s.season_id "
        "WHERE c.competition_id IN (" + placeholders + ") "
        "GROUP BY s.season_id, s.season, s.name, s.status ORDER BY s.season"
    )
    season_rows = [
        dict(zip([column[0] for column in cursor.description], row))
        for cursor in [connection.execute(season_query, comp_ids)]
        for row in cursor.fetchall()
    ]
    season_ids = [int(row["season_id"]) for row in season_rows]
    if not season_ids:
        raise ValueError("Premier League competition has no season rows")
    season_placeholders = ",".join("?" for _ in season_ids)

    def grouped(query, params):
        cursor = connection.execute(query, params)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    event_layers = grouped(
        "SELECT e.layer, e.kind, COUNT(*) AS rows "
        "FROM match_events e JOIN matches m ON m.match_id=e.match_id "
        "WHERE m.season_id IN (" + season_placeholders + ") "
        "GROUP BY e.layer, e.kind ORDER BY e.layer, e.kind",
        season_ids,
    )
    shot_layers = grouped(
        "SELECT sh.layer, COUNT(*) AS shot_rows, "
        "SUM(CASE WHEN sh.xg IS NOT NULL THEN 1 ELSE 0 END) AS rows_with_xg, "
        "SUM(CASE WHEN sh.x_m IS NOT NULL AND sh.y_m IS NOT NULL THEN 1 ELSE 0 END) AS rows_with_location "
        "FROM shots sh JOIN matches m ON m.match_id=sh.match_id "
        "WHERE m.season_id IN (" + season_placeholders + ") "
        "GROUP BY sh.layer ORDER BY sh.layer",
        season_ids,
    )
    player_match = grouped(
        "SELECT COUNT(*) AS rows, "
        "SUM(CASE WHEN p.minutes_played IS NOT NULL THEN 1 ELSE 0 END) AS rows_with_minutes, "
        "SUM(CASE WHEN p.key_passes IS NOT NULL THEN 1 ELSE 0 END) AS rows_with_key_passes, "
        "SUM(CASE WHEN p.goals IS NOT NULL THEN 1 ELSE 0 END) AS rows_with_goals "
        "FROM player_match_statistics p JOIN matches m ON m.match_id=p.match_id "
        "WHERE m.season_id IN (" + season_placeholders + ")",
        season_ids,
    )[0]
    player_match_events = grouped(
        "SELECT COUNT(*) AS rows, "
        "SUM(CASE WHEN e.attempts IS NOT NULL THEN 1 ELSE 0 END) AS rows_with_attempts, "
        "SUM(CASE WHEN e.big_chances IS NOT NULL THEN 1 ELSE 0 END) AS rows_with_big_chances "
        "FROM player_match_event_counts e JOIN matches m ON m.match_id=e.match_id "
        "WHERE m.season_id IN (" + season_placeholders + ")",
        season_ids,
    )[0]
    lineups = grouped(
        "SELECT COUNT(*) AS rows, "
        "SUM(CASE WHEN p.started=1 THEN 1 ELSE 0 END) AS starters, "
        "SUM(CASE WHEN p.minutes_played IS NOT NULL THEN 1 ELSE 0 END) AS rows_with_minutes "
        "FROM match_players p JOIN matches m ON m.match_id=p.match_id "
        "WHERE m.season_id IN (" + season_placeholders + ")",
        season_ids,
    )[0]
    team_match = grouped(
        "SELECT COUNT(*) AS rows, COUNT(DISTINCT s.match_id) AS matches "
        "FROM match_team_statistics s JOIN matches m ON m.match_id=s.match_id "
        "WHERE m.season_id IN (" + season_placeholders + ")",
        season_ids,
    )[0]

    licence_values = sorted({str(row.get("licence") or "") for row in format_rows})
    player_catalogue = {"available": False, "players": None, "player_merges": None}
    if players_connection is not None:
        player_tables = _tables(players_connection)
        if "players" not in player_tables:
            raise ValueError("Separate 11footy player catalogue is missing the players table")
        player_catalogue = {
            "available": True,
            "players": players_connection.execute("SELECT COUNT(*) FROM players").fetchone()[0],
            "player_merges": (
                players_connection.execute("SELECT COUNT(*) FROM player_merges").fetchone()[0]
                if "player_merges" in player_tables else None
            ),
            "sha256": players_sha256,
        }
    report = {
        "provider": "11footy",
        "source_release": source_release,
        "source_sha256": source_sha256,
        "player_catalogue": player_catalogue,
        "licence": licence_values,
        "attribution": "Credit 11footy; CC BY-NC 4.0; non-commercial use only.",
        "competitions": competitions,
        "season_coverage": season_rows,
        "match_event_layers_and_kinds": event_layers,
        "shot_layers": shot_layers,
        "player_match_statistics": player_match,
        "player_match_event_counts": player_match_events,
        "lineups": lineups,
        "team_match_statistics": team_match,
        "missing_required_tables": missing_tables,
        "status": "PASS_STRUCTURAL_ONLY",
        "prediction_validation": "NOT_EVALUATED",
        "identity_mapping": "NOT_ATTEMPTED",
        "limitations": [
            "The dataset README describes summary and play-by-play match events, not a full StatsBomb-style every-pass event stream.",
            "Shot-level locations and xG are available in the tracked shots layer; this is not player tracking or 360 freeze-frame data.",
            "Player IDs are 11footy IDs and are not FPL element IDs; a season-scoped verified crosswalk is required.",
            "The public release is a snapshot, not a live API; check the release date and latest completed match before use.",
            "The README does not identify every upstream source for its event and statistics layers; reconcile against official FPL and other sources.",
            "No source data or player-level rows are included in the report artifact."
        ],
    }
    return report


def main():
    parser = argparse.ArgumentParser(description="Audit an 11footy Premier League SQLite or .db.xz release")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--players-input", type=Path)
    parser.add_argument("--players-expected-sha256")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    actual_sha = sha256(args.input)
    expected_sha = args.expected_sha256.lower().removeprefix("sha256:")
    if actual_sha != expected_sha:
        raise SystemExit("Source SHA-256 mismatch: expected " + expected_sha + ", got " + actual_sha)

    if bool(args.players_input) != bool(args.players_expected_sha256):
        raise SystemExit("--players-input and --players-expected-sha256 must be supplied together")
    players_sha = None
    if args.players_input:
        players_sha = sha256(args.players_input)
        expected_players_sha = args.players_expected_sha256.lower().removeprefix("sha256:")
        if players_sha != expected_players_sha:
            raise SystemExit("Player catalogue SHA-256 mismatch: expected " + expected_players_sha + ", got " + players_sha)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cta-11footy-") as temp:
        temp_path = Path(temp)
        database_path = _materialize_sqlite(args.input, temp_path)
        connection = sqlite3.connect("file:" + str(database_path.resolve()) + "?mode=ro", uri=True)
        players_connection = None
        try:
            if args.players_input:
                players_path = _materialize_sqlite(args.players_input, temp_path)
                players_connection = sqlite3.connect("file:" + str(players_path.resolve()) + "?mode=ro", uri=True)
            report = audit_database(connection, args.release, actual_sha, players_connection, players_sha)
        finally:
            connection.close()
            if players_connection is not None:
                players_connection.close()

    (args.out_dir / "11footy_premier_league_data_audit.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps({
        "provider": report["provider"],
        "release": report["source_release"],
        "status": report["status"],
        "seasons": len(report["season_coverage"]),
        "player_match_rows": report["player_match_statistics"]["rows"],\n        "player_catalogue": report["player_catalogue"],
        "shot_layers": report["shot_layers"],
        "prediction_validation": report["prediction_validation"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
