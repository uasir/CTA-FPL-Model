#!/usr/bin/env python3
"""Build a pending-only Wyscout↔historical-FPL identity review queue.

Exact names, team history and match-level FPL statistics are evidence only.
No identity is automatically verified and candidate-level rows remain local.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


TEAM_ALIASES = {
    "afc bournemouth": "bournemouth",
    "brighton": "brighton and hove albion",
    "brighton hove albion": "brighton and hove albion",
    "brighton and hove albion": "brighton and hove albion",
    "burnley": "burnley",
    "chelsea": "chelsea",
    "crystal palace": "crystal palace",
    "everton": "everton",
    "huddersfield": "huddersfield town",
    "huddersfield town": "huddersfield town",
    "leicester": "leicester city",
    "leicester city": "leicester city",
    "liverpool": "liverpool",
    "man city": "manchester city",
    "manchester city": "manchester city",
    "man utd": "manchester united",
    "manchester united": "manchester united",
    "newcastle": "newcastle united",
    "newcastle united": "newcastle united",
    "southampton": "southampton",
    "stoke": "stoke city",
    "stoke city": "stoke city",
    "swansea": "swansea city",
    "swansea city": "swansea city",
    "spurs": "tottenham hotspur",
    "tottenham": "tottenham hotspur",
    "tottenham hotspur": "tottenham hotspur",
    "watford": "watford",
    "west brom": "west bromwich albion",
    "west bromwich albion": "west bromwich albion",
    "west ham": "west ham united",
    "west ham united": "west ham united",
}


def normalize_text(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text).split())


def normalize_team(value):
    normalized = normalize_text(value)
    return TEAM_ALIASES.get(normalized, normalized)


def read_csv(path):
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))
    except UnicodeDecodeError:
        # The historical FPL archive includes legacy Windows-1252 accents.
        with path.open(newline="", encoding="cp1252") as handle:
            return list(csv.DictReader(handle))


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def as_int(value):
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def as_number(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def build_fpl_team_names(team_rows):
    result = {}
    for row in team_rows:
        if str(row.get("season") or "") != "2017-18":
            continue
        team_id = as_int(row.get("team"))
        name = str(row.get("team_name") or "").strip()
        if team_id is None or not name:
            continue
        if team_id in result and result[team_id] != name:
            raise ValueError(f"Conflicting FPL team names for team {team_id}")
        result[team_id] = name
    if len(result) != 20:
        raise ValueError(f"Expected 20 historical FPL teams, found {len(result)}")
    return result


def build_fpl_player_maps(players, idlist, team_names):
    idlist_by_id = {}
    for row in idlist:
        player_id = as_int(row.get("id"))
        if player_id is not None:
            idlist_by_id[player_id] = row
    by_name = defaultdict(list)
    by_id = {}
    for row in players:
        element_id = as_int(row.get("id"))
        if element_id is None:
            continue
        name = " ".join(x for x in (row.get("first_name"), row.get("second_name")) if x).strip()
        norm_name = normalize_text(name)
        if not norm_name:
            continue
        team_id = as_int(row.get("team"))
        id_row = idlist_by_id.get(element_id)
        idlist_name = " ".join(x for x in (
            (id_row or {}).get("first_name"), (id_row or {}).get("second_name")
        ) if x).strip()
        if id_row and normalize_text(idlist_name) != norm_name:
            raise ValueError(f"Historical FPL player ID/name conflict for element {element_id}")
        record = {
            "fpl_element_id": element_id,
            "fpl_player_code": str(row.get("code") or ""),
            "fpl_player_name": name,
            "fpl_team_id": team_id if team_id is not None else "",
            "fpl_team_name": team_names.get(team_id, "") if team_id is not None else "",
            "fpl_birth_date": "",
            "fpl_season_goals": as_int(row.get("goals_scored")) or 0,
            "fpl_season_assists": as_int(row.get("assists")) or 0,
            "fpl_season_minutes": as_int(row.get("minutes")) or 0,
        }
        by_name[norm_name].append(record)
        by_id[element_id] = record
    return by_name, by_id


def build_fixture_index(fpl_history, fpl_team_names):
    by_key = defaultdict(set)
    by_id = {}
    for row in fpl_history:
        fixture_id = as_int(row.get("fixture"))
        opponent_id = as_int(row.get("opponent_team"))
        kickoff = str(row.get("kickoff_time") or "")
        was_home = str(row.get("was_home") or "").strip().lower() in {"true", "1"}
        if fixture_id is None or opponent_id is None or not kickoff:
            continue
        opponent_name = fpl_team_names.get(opponent_id, "")
        if not opponent_name:
            continue
        key = (kickoff[:10], was_home, normalize_team(opponent_name))
        by_key[key].add(fixture_id)
        by_id[fixture_id] = {
            "date": kickoff[:10],
            "opponent_team_id": opponent_id,
            "opponent_team_name": opponent_name,
            "was_home": was_home,
        }
    return by_key, by_id


def build_wyscout_match_fixture_map(player_match_rows, fixture_index):
    match_context = {}
    for row in player_match_rows:
        match_id = as_int(row.get("provider_match_id"))
        if match_id is None:
            continue
        context = {
            "date": str(row.get("match_date") or "")[:10],
            "home_team": str(row.get("provider_team_name") or "") if row.get("home_away") == "home" else str(row.get("opponent_team_name") or ""),
            "away_team": str(row.get("opponent_team_name") or "") if row.get("home_away") == "home" else str(row.get("provider_team_name") or ""),
        }
        prior = match_context.get(match_id)
        if prior and prior != context:
            raise ValueError(f"Inconsistent Wyscout match metadata for {match_id}")
        match_context[match_id] = context

    resolved = {}
    statuses = Counter()
    for match_id, context in match_context.items():
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
    return resolved, statuses, match_context


def build_candidate_review_queue(player_match_rows, players_json, fpl_players,
                                 fpl_idlist, fpl_history, fpl_team_rows):
    team_names = build_fpl_team_names(fpl_team_rows)
    fpl_by_name, fpl_by_id = build_fpl_player_maps(fpl_players, fpl_idlist, team_names)
    fixture_index, fixture_by_id = build_fixture_index(fpl_history, team_names)
    match_to_fixture, fixture_statuses, match_context = build_wyscout_match_fixture_map(
        player_match_rows, fixture_index
    )

    fpl_history_by_key = {}
    duplicate_fpl_keys = set()
    for row in fpl_history:
        element_id = as_int(row.get("element"))
        fixture_id = as_int(row.get("fixture"))
        if element_id is None or fixture_id is None:
            continue
        key = (element_id, fixture_id)
        if key in fpl_history_by_key:
            duplicate_fpl_keys.add(key)
        fpl_history_by_key[key] = row

    provider_names = {}
    provider_birth_dates = {}
    for player in players_json:
        player_id = as_int(player.get("wyId"))
        if player_id is None:
            continue
        full_name = " ".join(x for x in (
            player.get("firstName"), player.get("middleName"), player.get("lastName")
        ) if x).strip()
        provider_names[player_id] = full_name or str(player.get("shortName") or "")
        provider_birth_dates[player_id] = str(player.get("birthDate") or "")

    rows_by_provider = defaultdict(list)
    for row in player_match_rows:
        provider_id = as_int(row.get("provider_player_id"))
        if provider_id is not None:
            rows_by_provider[provider_id].append(row)

    candidates = []
    priority_counts = Counter()
    player_match_rows_with_name_candidate = 0
    player_match_rows_with_fpl_history = 0
    for provider_id, provider_rows in sorted(rows_by_provider.items()):
        provider_name = provider_names.get(provider_id) or str(provider_rows[0].get("provider_player_name") or "")
        norm_name = normalize_text(provider_name)
        matches = fpl_by_name.get(norm_name, [])
        if len(matches) == 1:
            candidate = matches[0]
            match_method = "EXACT_NORMALIZED_FULL_NAME_UNIQUE"
            candidate_status = "PENDING"
        elif len(matches) > 1:
            candidate = None
            match_method = "EXACT_NORMALIZED_FULL_NAME_AMBIGUOUS"
            candidate_status = "AMBIGUOUS"
        else:
            candidate = None
            match_method = "NO_EXACT_FULL_NAME_MATCH"
            candidate_status = "UNMATCHED"

        provider_teams = sorted({
            str(row.get("provider_team_name") or "").strip()
            for row in provider_rows if row.get("provider_team_name")
        })
        candidate_team = normalize_team(candidate["fpl_team_name"]) if candidate else ""
        provider_team_keys = {normalize_team(team) for team in provider_teams}
        team_match = bool(candidate_team and candidate_team in provider_team_keys)
        team_mismatch = bool(candidate and provider_team_keys and not team_match)

        fixture_rows = 0
        history_missing = 0
        history_ambiguous = 0
        positive_minutes = 0
        goals_exact = 0
        own_goals_exact = 0
        assists_exact = 0
        goal_assist_signature_exact = 0
        goal_assist_signature_zero_only = 0
        team_context_exact = 0
        provider_goal_sum = 0
        provider_own_goal_sum = 0
        provider_assist_sum = 0
        fpl_goal_sum = 0
        fpl_own_goal_sum = 0
        fpl_assist_sum = 0
        if candidate:
            player_match_rows_with_name_candidate += len(provider_rows)
            for row in provider_rows:
                fixture_id = match_to_fixture.get(as_int(row.get("provider_match_id")))
                if fixture_id is None:
                    continue
                fixture_rows += 1
                history_key = (candidate["fpl_element_id"], fixture_id)
                if history_key in duplicate_fpl_keys:
                    history_ambiguous += 1
                    continue
                history = fpl_history_by_key.get(history_key)
                if history is None:
                    history_missing += 1
                    continue
                player_match_rows_with_fpl_history += 1
                minutes = as_int(history.get("minutes")) or 0
                positive_minutes += int(minutes > 0)
                w_goals = as_int(row.get("goals")) or 0
                w_own = as_int(row.get("own_goals")) or 0
                w_assists = as_int(row.get("assists")) or 0
                f_goals = as_int(history.get("goals_scored")) or 0
                f_own = as_int(history.get("own_goals")) or 0
                f_assists = as_int(history.get("assists")) or 0
                goals_exact += int(w_goals == f_goals)
                own_goals_exact += int(w_own == f_own)
                assists_exact += int(w_assists == f_assists)
                signature = (w_goals, w_own, w_assists) == (f_goals, f_own, f_assists)
                if signature and (w_goals + w_own + w_assists + f_goals + f_own + f_assists) > 0:
                    goal_assist_signature_exact += 1
                elif signature:
                    goal_assist_signature_zero_only += 1
                provider_goal_sum += w_goals
                provider_own_goal_sum += w_own
                provider_assist_sum += w_assists
                fpl_goal_sum += f_goals
                fpl_own_goal_sum += f_own
                fpl_assist_sum += f_assists
                expected_opponent = (
                    match_context[as_int(row.get("provider_match_id"))]["away_team"]
                    if row.get("home_away") == "home"
                    else match_context[as_int(row.get("provider_match_id"))]["home_team"]
                )
                fixture = fixture_by_id.get(fixture_id, {})
                if normalize_team(expected_opponent) == normalize_team(fixture.get("opponent_team_name")):
                    team_context_exact += 1

        if candidate and goal_assist_signature_exact >= 3 and team_match and not team_mismatch and positive_minutes > 0:
            priority = "P1_MULTI_MATCH_TEAM_CORROBORATION"
        elif candidate and goal_assist_signature_exact > 0 and team_match and not team_mismatch:
            priority = "P2_TEAM_AND_STAT_CROSSCHECK"
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
            "provider": "Wyscout",
            "provider_player_id": provider_id,
            "provider_player_name": provider_name,
            "provider_birth_date": provider_birth_dates.get(provider_id, ""),
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
            "provider_match_rows": len(provider_rows),
            "fixture_mapped_rows": fixture_rows,
            "fpl_history_overlap_rows": fixture_rows - history_missing - history_ambiguous,
            "fpl_history_missing_rows": history_missing,
            "fpl_history_ambiguous_rows": history_ambiguous,
            "fpl_positive_minutes_rows": positive_minutes,
            "goals_exact_rows": goals_exact,
            "own_goals_exact_rows": own_goals_exact,
            "assists_exact_rows": assists_exact,
            "goal_assist_signature_exact_rows": goal_assist_signature_exact,
            "goal_assist_signature_zero_only_rows": goal_assist_signature_zero_only,
            "team_context_exact_rows": team_context_exact,
            "provider_goals_sum": provider_goal_sum,
            "provider_own_goals_sum": provider_own_goal_sum,
            "provider_assists_sum": provider_assist_sum,
            "fpl_goals_sum": fpl_goal_sum,
            "fpl_own_goals_sum": fpl_own_goal_sum,
            "fpl_assists_sum": fpl_assist_sum,
            "review_priority": priority,
            "review_note": (
                "Automated candidate evidence only. Exact names, team history and match-stat agreement "
                "are not proof; this identity remains PENDING until independent source verification."
            ),
        })

    priority_order = {
        "P1_MULTI_MATCH_TEAM_CORROBORATION": 0,
        "P2_TEAM_AND_STAT_CROSSCHECK": 1,
        "P3_HISTORY_REVIEW": 2,
        "P4_IDENTITY_REVIEW": 3,
        "P5_UNMATCHED_OR_AMBIGUOUS": 4,
    }
    candidates.sort(key=lambda row: (
        priority_order[row["review_priority"]],
        -int(row["goal_assist_signature_exact_rows"]),
        -int(row["fpl_history_overlap_rows"]),
        int(row["provider_player_id"]),
    ))
    report = {
        "provider": "Wyscout",
        "season": "2017/18",
        "competition": "English Premier League",
        "wyscout_players_with_match_rows": len(rows_by_provider),
        "historical_fpl_players": len(fpl_by_id),
        "exact_name_unique_candidate_count": sum(row["candidate_status"] == "PENDING" for row in candidates),
        "ambiguous_name_candidate_count": sum(row["candidate_status"] == "AMBIGUOUS" for row in candidates),
        "unmatched_name_count": sum(row["candidate_status"] == "UNMATCHED" for row in candidates),
        "player_match_rows_with_name_candidate": player_match_rows_with_name_candidate,
        "player_match_rows_with_fpl_history": player_match_rows_with_fpl_history,
        "fpl_fixture_rows": len(fpl_history),
        "wyscout_matches_with_fixture_status": dict(fixture_statuses),
        "candidate_review_priority_counts": dict(priority_counts),
        "duplicate_fpl_player_fixture_keys": len(duplicate_fpl_keys),
        "identity_policy": "Exact normalized full names only; team and FPL match statistics are corroboration; no fuzzy matching and no automatic verification.",
        "verification_status": "NO_CANDIDATE_AUTO_VERIFIED",
        "candidate_publication_policy": "Candidate-level rows remain local to the workflow runner; only aggregate counts are published.",
        "prediction_validation": "NOT_EVALUATED",
        "source_attribution": (
            "Wyscout event dataset: Pappalardo and Massucco (2019), CC BY 4.0. "
            "Historical FPL archive: Vaastav Anand, Fantasy-Premier-League repository; underlying FPL data remains property of Fantasy Premier League."
        ),
        "limitations": [
            "Historical FPL archive is unofficial and its underlying data is owned by Fantasy Premier League; applicable source terms must be respected.",
            "The FPL archive contains no player birth date, so birth-date corroboration is unavailable.",
            "Wyscout does not provide pass-recipient IDs or xG in this public event schema.",
            "The FPL archive may contain historical corrections; it is used for identity corroboration only, not point-in-time prediction training.",
            "Player team in players_raw is a season-end team; transfers can create legitimate within-season team changes.",
            "Match fixture mapping uses exact UTC date, opponent and home/away context; unmatched and ambiguous matches remain isolated.",
        ],
    }
    return candidates, report


def main():
    parser = argparse.ArgumentParser(description="Build pending-only Wyscout to historical FPL identity candidates")
    parser.add_argument("--wyscout-player-match", type=Path, required=True)
    parser.add_argument("--wyscout-players", type=Path, required=True)
    parser.add_argument("--fpl-players", type=Path, required=True)
    parser.add_argument("--fpl-player-idlist", type=Path, required=True)
    parser.add_argument("--fpl-gameweek-history", type=Path, required=True)
    parser.add_argument("--fpl-team-list", type=Path, required=True)
    parser.add_argument("--fpl-source-commit", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    with args.wyscout_players.open(encoding="utf-8") as handle:
        wyscout_players = json.load(handle)
    candidates, report = build_candidate_review_queue(
        read_csv(args.wyscout_player_match),
        wyscout_players,
        read_csv(args.fpl_players),
        read_csv(args.fpl_player_idlist),
        read_csv(args.fpl_gameweek_history),
        read_csv(args.fpl_team_list),
    )
    report["historical_fpl_source_commit"] = args.fpl_source_commit
    report["source_hashes"] = {
        "wyscout_player_match_sha256": sha256(args.wyscout_player_match),
        "wyscout_players_sha256": sha256(args.wyscout_players),
        "historical_fpl_players_sha256": sha256(args.fpl_players),
        "historical_fpl_player_idlist_sha256": sha256(args.fpl_player_idlist),
        "historical_fpl_gameweek_history_sha256": sha256(args.fpl_gameweek_history),
        "historical_fpl_team_list_sha256": sha256(args.fpl_team_list),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    fields = list(candidates[0]) if candidates else [
        "season", "competition", "provider", "provider_player_id", "provider_player_name",
        "candidate_fpl_element_id", "candidate_fpl_player_name", "verification_status",
        "review_priority", "review_note",
    ]
    with (args.out_dir / "wyscout_fpl_identity_candidates.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(candidates)
    with (args.out_dir / "wyscout_fpl_identity_review_queue.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(candidates)
    (args.out_dir / "wyscout_fpl_identity_candidate_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        key: report[key] for key in (
            "wyscout_players_with_match_rows", "historical_fpl_players",
            "exact_name_unique_candidate_count", "ambiguous_name_candidate_count",
            "unmatched_name_count", "player_match_rows_with_fpl_history",
            "wyscout_matches_with_fixture_status", "candidate_review_priority_counts",
            "verification_status", "prediction_validation",
        )
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
