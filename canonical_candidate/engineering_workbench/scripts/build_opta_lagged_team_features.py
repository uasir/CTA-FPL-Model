#!/usr/bin/env python3
"""Build leakage-safe Opta/PulseLive team features and a numeric FPL identity crosswalk.

The source repository's 2026/27 player table uses the same numeric player ID as
FPL's player_code. This adapter verifies exact ID equality and current team-ID
agreement; it never uses fuzzy names. Team-match features are strictly lagged
to before each target fixture kickoff.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROVIDER_COMMIT = "f0f3d40f803c69bc7fac48d0748b49175e2d08ce"
PROVIDER_REPO = "imadeddine-belkat/Premier-League-Stats"
PLAYER_SOURCE_PATH = "pl_stats/_merged/players/2026-27_players_stats.csv"
TEAM_SOURCE_PATH = "pl_stats/_merged/events/2026-27_events_stats.csv"
METRIC_CANDIDATES = (
    "expectedGoals", "expectedAssists", "accuratePass", "possessionPercentage",
    "finalThirdEntries", "attemptsIbox", "ballRecovery", "interception",
    "duelWon", "tacklesWon", "recoveries", "totalPasses", "touches",
    "totalFoulsWon", "cornersWon", "successfulDribbles",
)
CROSSWALK_FIELDS = [
    "season", "competition_id", "competition_name", "provider_player_id",
    "provider_player_name", "fpl_element_id", "fpl_player_code",
    "fpl_player_name", "provider_team_id", "provider_team_name", "fpl_team_id",
    "fpl_team_name", "verification_status", "match_method", "evidence_source",
    "evidence_url", "verified_by", "verified_at",
]


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def as_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def as_float(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        result = float(value)
        return result if result == result and abs(result) != float("inf") else None
    except (TypeError, ValueError):
        return None


def parse_time(value: str) -> datetime:
    if not value:
        raise ValueError("Missing kickoff timestamp; refusing a non-time-safe join")
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_crosswalk(elements: list[dict], teams: list[dict], provider_players: list[dict],
                    source_commit: str = PROVIDER_COMMIT, verified_at: str | None = None):
    """Exact provider playerId == FPL code plus team-ID verification."""
    verified_at = verified_at or datetime.now(timezone.utc).isoformat()
    team_names = {str(t.get("id")): t.get("name", "") for t in teams}
    fpl_by_code = defaultdict(list)
    for element in elements:
        fpl_by_code[str(element.get("code", ""))].append(element)
    provider_by_id = defaultdict(list)
    for player in provider_players:
        provider_by_id[str(player.get("playerId", ""))].append(player)

    rows, errors = [], []
    verified = 0
    for player_id, provider_matches in sorted(provider_by_id.items()):
        status, fpl, provider = "pending", None, provider_matches[0]
        candidates = fpl_by_code.get(player_id, [])
        if len(provider_matches) != 1 or len(candidates) != 1:
            status = "ambiguous"
            errors.append({"provider_player_id": player_id, "reason": "non_unique_numeric_id",
                           "provider_rows": len(provider_matches), "fpl_rows": len(candidates)})
        elif str(provider.get("team_id", "")) != str(candidates[0].get("team", "")):
            status = "ambiguous"
            errors.append({"provider_player_id": player_id, "reason": "team_id_mismatch",
                           "provider_team_id": provider.get("team_id"),
                           "fpl_team_id": candidates[0].get("team")})
        else:
            status = "verified"
            fpl = candidates[0]
            verified += 1
        team_id = str(provider.get("team_id", ""))
        fpl_team_id = str(fpl.get("team", "")) if fpl else ""
        rows.append({
            "season": str(provider.get("season", "2026-27")),
            "competition_id": "PL",
            "competition_name": "English Premier League",
            "provider_player_id": player_id,
            "provider_player_name": provider.get("playerName", ""),
            "fpl_element_id": str(fpl.get("id", "")) if fpl else "",
            "fpl_player_code": player_id if fpl else "",
            "fpl_player_name": " ".join(x for x in ((fpl or {}).get("first_name", ""),
                                               (fpl or {}).get("second_name", "")) if x),
            "provider_team_id": team_id,
            "provider_team_name": provider.get("team_name", ""),
            "fpl_team_id": fpl_team_id,
            "fpl_team_name": team_names.get(fpl_team_id, ""),
            "verification_status": status,
            "match_method": "provider_id_crosswalk",
            "evidence_source": f"{PROVIDER_REPO}@{source_commit}; official FPL bootstrap-static",
            "evidence_url": f"https://github.com/{PROVIDER_REPO}/blob/{source_commit}/{PLAYER_SOURCE_PATH}",
            "verified_by": "automated_numeric_id_and_team_id_check",
            "verified_at": verified_at,
        })
    fpl_codes = set(fpl_by_code)
    provider_codes = set(provider_by_id)
    report = {
        "provider": "opta_pulselive", "season": "2026-27",
        "source_commit": source_commit, "fpl_unique_codes": len(fpl_codes),
        "provider_unique_player_ids": len(provider_codes),
        "exact_shared_numeric_ids": len(fpl_codes & provider_codes),
        "verified_id_and_team_matches": verified,
        "team_mismatches_or_duplicate_ids": len(errors),
        "fpl_players_without_provider_season_row": len(fpl_codes - provider_codes),
        "provider_players_without_fpl_code": len(provider_codes - fpl_codes),
        "status": "PASS" if verified and not errors else "PARTIAL",
        "identity_policy": "Exact provider playerId == FPL code and exact current team ID; no name matching",
        "errors": errors,
    }
    return rows, report


def build_team_features(fixtures: list[dict], bootstrap: dict, provider_rows: list[dict],
                        season: str = "2026-27", max_history: int = 3):
    """Produce fixture-team and FPL player-fixture rows using strictly prior team matches."""
    elements = bootstrap.get("elements", [])
    teams = {str(t["id"]): t.get("name", "") for t in bootstrap.get("teams", [])}
    metrics = [m for m in METRIC_CANDIDATES if any(m in row for row in provider_rows)]
    source = []
    for row in provider_rows:
        if str(row.get("season", season)) != season:
            continue
        kickoff = parse_time(row.get("kickoff", ""))
        team_id = str(row.get("team_id", ""))
        if not team_id:
            continue
        source.append({**row, "_kickoff": kickoff, "_team_id": team_id})
    by_team = defaultdict(list)
    for row in source:
        by_team[row["_team_id"]].append(row)
    for rows in by_team.values():
        rows.sort(key=lambda r: (r["_kickoff"], str(r.get("matchId", ""))))

    team_output, player_output = [], []
    excluded_same_or_future = 0
    for fixture in fixtures:
        fixture_id = str(fixture.get("id", ""))
        kickoff_value = fixture.get("kickoff_time", "")
        target_kickoff = parse_time(kickoff_value) if kickoff_value else None
        event = fixture.get("event")
        sides = (("home", str(fixture.get("team_h", ""))),
                 ("away", str(fixture.get("team_a", ""))))
        for side, team_id in sides:
            team_source = by_team.get(team_id, [])
            prior = ([r for r in team_source
                      if r["_kickoff"] < target_kickoff and str(r.get("matchId", "")) != fixture_id]
                     if target_kickoff else [])
            if target_kickoff:
                excluded_same_or_future += sum(
                    1 for r in team_source
                    if r["_kickoff"] >= target_kickoff or str(r.get("matchId", "")) == fixture_id
                )
            prior = prior[-max_history:]
            row = {
                "season": season, "fixture_id": fixture_id, "gameweek": event or "",
                "kickoff_time": target_kickoff.isoformat() if target_kickoff else "",
                "side": side, "team_id": team_id, "team_name": teams.get(team_id, ""),
                "opta_prior_matches_count": len(prior),
                "features_as_of": target_kickoff.isoformat() if target_kickoff else "",
            }
            for metric in metrics:
                values = [as_float(r.get(metric)) for r in prior]
                values = [v for v in values if v is not None]
                row[f"opta_prior{max_history}_{metric}_avg"] = (
                    round(sum(values) / len(values), 6) if values else ""
                )
            team_output.append(row)

        team_for_side = {team_id: side for side, team_id in sides}
        for element in elements:
            team_id = str(element.get("team", ""))
            if team_id not in team_for_side:
                continue
            side = team_for_side[team_id]
            feature = next(r for r in team_output
                           if r["fixture_id"] == fixture_id and r["team_id"] == team_id)
            player_output.append({
                "season": season, "fpl_element_id": element.get("id", ""),
                "fpl_player_code": element.get("code", ""),
                "fpl_player_name": " ".join(x for x in
                    (element.get("first_name", ""), element.get("second_name", "")) if x),
                "fixture_id": fixture_id, "gameweek": event or "",
                "kickoff_time": target_kickoff.isoformat(), "team_id": team_id,
                "side": side, **{k: v for k, v in feature.items()
                                 if k.startswith("opta_") or k == "features_as_of"},
            })
    team_keys = [(r["fixture_id"], r["team_id"]) for r in team_output]
    player_keys = [(r["fpl_element_id"], r["fixture_id"]) for r in player_output]
    if len(team_keys) != len(set(team_keys)):
        raise ValueError("Duplicate fixture-team keys")
    if len(player_keys) != len(set(player_keys)):
        raise ValueError("Duplicate player-fixture keys")
    report = {
        "season": season, "fixtures": len(fixtures),
        "fixtures_without_kickoff": sum(not bool(f.get("kickoff_time")) for f in fixtures),
        "team_fixture_rows": len(team_output), "player_fixture_rows": len(player_output),
        "provider_team_match_rows": len(source), "metrics_used": metrics,
        "max_prior_matches": max_history,
        "same_or_future_rows_excluded": excluded_same_or_future,
        "leakage_policy": "Only same-season provider team rows with kickoff strictly earlier than target fixture kickoff are used; current fixture matchId is excluded.",
        "point_in_time_status": "NOT_VERIFIED",
        "point_in_time_caveat": "Provider snapshot vintage must be archived at each deadline before strict historical backtests are claimed.",
        "status": "PASS_STRUCTURAL_ONLY",
    }
    return team_output, player_output, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--opta-players", type=Path, required=True)
    parser.add_argument("--opta-team-events", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--season", default="2026-27")
    parser.add_argument("--source-commit", default=PROVIDER_COMMIT)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    bootstrap = json.loads(args.bootstrap.read_text(encoding="utf-8"))
    fixtures = json.loads(args.fixtures.read_text(encoding="utf-8"))
    crosswalk, identity_report = build_crosswalk(
        bootstrap.get("elements", []), bootstrap.get("teams", []),
        read_csv(args.opta_players), args.source_commit,
    )
    team_rows, player_rows, feature_report = build_team_features(
        fixtures, bootstrap, read_csv(args.opta_team_events), args.season,
    )
    write_csv(args.out_dir / "opta_pulselive_fpl_identity_crosswalk.csv",
              crosswalk, CROSSWALK_FIELDS)
    write_csv(args.out_dir / "opta_lagged_team_fixture_features.csv", team_rows,
              list(team_rows[0]) if team_rows else [])
    write_csv(args.out_dir / "opta_lagged_player_fixture_features.csv", player_rows,
              list(player_rows[0]) if player_rows else [])
    report = {"identity": identity_report, "team_features": feature_report}
    (args.out_dir / "opta_fpl_integration_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
