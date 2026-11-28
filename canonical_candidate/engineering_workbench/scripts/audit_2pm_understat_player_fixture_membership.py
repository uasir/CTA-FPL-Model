"""Verify each pinned Understat player row against Dastan's FPL assignment and FPL fixture row.

This is structural identity evidence only; it does not establish Understat publication
vintage or admit features. Team-row fixture reconciliation remains in the companion
understat deadline-visibility audit.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_2pm_understat_deadline_visibility import (
    _fixture_match,
    load_fixture_calendars,
)

DASTAN = "qazybekb/smartplayfpl-dastan"
DASTAN_COMMIT = "758db9247e8b3a9a870c991064f74d8339d61cd0"
POSITION_VALUES = {"GK", "GKP", "DEF", "MID", "FWD"}


def fetch_pinned_file(session: requests.Session, repository: str, commit: str,
                      source_path: str, cache_root: Path) -> Path:
    local = cache_root / commit / source_path
    if local.is_file() and local.stat().st_size:
        return local
    response = session.get(
        f"https://raw.githubusercontent.com/{repository}/{commit}/{source_path}", timeout=90
    )
    response.raise_for_status()
    if not response.content:
        raise RuntimeError(f"Pinned source file is empty: {source_path}")
    local.parent.mkdir(parents=True, exist_ok=True)
    temp = local.with_name(local.name + ".tmp")
    temp.write_bytes(response.content)
    temp.replace(local)
    return local


def load_player_fixture_membership(seasons: list[str], vaastav_commit: str,
                                   dastan_commit: str, cache_root: Path) -> pd.DataFrame:
    session = requests.Session()
    assignment_path = fetch_pinned_file(
        session, DASTAN, dastan_commit,
        "data/mappings/fpl_understat_training_assignments.csv", cache_root,
    )
    assignments = pd.read_csv(assignment_path)
    required = {"season", "fpl_code", "understat_id", "first_gameweek", "last_gameweek"}
    if required - set(assignments.columns):
        raise ValueError(f"Dastan assignments lack {sorted(required - set(assignments.columns))}")
    assignments["season"] = assignments["season"].astype(str)
    for column in required - {"season"}:
        assignments[column] = pd.to_numeric(assignments[column], errors="raise").astype("int64")
    # Mark every season/Understat ID with overlapping FPL assignment intervals.
    # Such IDs remain ambiguous even if only one conflicting FPL code happens to
    # appear in a particular fixture's merged player rows.
    assignments["identity_conflict"] = False
    for (_, understat_id), group in assignments.groupby(["season", "understat_id"]):
        indices = list(group.index)
        for i, left_idx in enumerate(indices):
            left = assignments.loc[left_idx]
            for right_idx in indices[i + 1:]:
                right = assignments.loc[right_idx]
                if left.fpl_code != right.fpl_code and max(left.first_gameweek, right.first_gameweek) <= min(left.last_gameweek, right.last_gameweek):
                    assignments.loc[[left_idx, right_idx], "identity_conflict"] = True
    if assignments.duplicated(["season", "fpl_code"]).any():
        raise ValueError("Dastan assignments contain duplicate season/fpl_code rows")

    pieces = []
    for season in seasons:
        merged_path = fetch_pinned_file(
            session, "vaastav/Fantasy-Premier-League", vaastav_commit,
            f"data/{season}/gws/merged_gw.csv", cache_root,
        )
        players_path = fetch_pinned_file(
            session, "vaastav/Fantasy-Premier-League", vaastav_commit,
            f"data/{season}/players_raw.csv", cache_root,
        )
        merged = pd.read_csv(merged_path, low_memory=False)
        players = pd.read_csv(players_path, usecols=["id", "code"])
        gw_col = "GW" if "GW" in merged else "round" if "round" in merged else None
        needed = {"fixture", "element", "position"}
        if gw_col is None or needed - set(merged.columns):
            raise ValueError(f"{season} merged_gw lacks required columns {sorted(needed - set(merged.columns))} or GW/round")
        if players.id.duplicated().any() or players.code.duplicated().any():
            raise ValueError(f"{season} players_raw IDs/codes are not unique")
        element_to_code = dict(zip(players.id.astype(int), players.code.astype(int)))
        rows = merged.loc[merged.position.isin(POSITION_VALUES)].copy()
        rows["season"] = season
        rows["gameweek"] = pd.to_numeric(rows[gw_col], errors="raise").astype(int)
        rows["fixture_id"] = pd.to_numeric(rows.fixture, errors="raise").astype(int)
        rows["element_id"] = pd.to_numeric(rows.element, errors="raise").astype(int)
        rows["fpl_code"] = rows.element_id.map(element_to_code)
        if rows.fpl_code.isna().any():
            raise ValueError(f"{season} merged_gw has rows without stable FPL player codes")
        rows["fpl_code"] = rows.fpl_code.astype(int)
        season_assignments = assignments.loc[assignments.season.eq(season)]
        rows = rows.merge(season_assignments, on=["season", "fpl_code"], how="left", validate="many_to_one")
        active = rows.gameweek.between(rows.first_gameweek, rows.last_gameweek)
        rows["understat_id"] = pd.to_numeric(rows.understat_id.where(active), errors="coerce")
        rows = rows.dropna(subset=["understat_id"])
        rows["identity_conflict"] = rows.identity_conflict.fillna(False).astype(bool)
        rows = rows.drop_duplicates(["season", "fixture_id", "fpl_code"], keep="last")
        pieces.append(rows[["season", "fixture_id", "gameweek", "fpl_code", "element_id", "understat_id", "identity_conflict"]])
    if not pieces:
        return pd.DataFrame(columns=["season", "fixture_id", "gameweek", "fpl_code", "element_id", "understat_id", "identity_conflict"])
    result = pd.concat(pieces, ignore_index=True)
    if result.duplicated(["season", "fixture_id", "understat_id", "fpl_code"]).any():
        raise ValueError("Dastan assignment produced duplicate player-fixture links")
    return result


def _signature(history: dict[str, Any]) -> dict[str, Any]:
    raw = history.get("first_value_signature") or history.get("latest_value_signature")
    try:
        return json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return {}


def reconcile_player_rows(history_report: dict[str, Any], calendars: dict[str, pd.DataFrame],
                           membership: pd.DataFrame) -> dict[str, Any]:
    output = []
    for file_result in history_report.get("results", []):
        if file_result.get("source_kind") != "pinned_player_csv":
            continue
        source_path = file_result.get("source_path", "")
        match = re.search(r"_(\d+)\.csv$", source_path)
        if not match:
            raise ValueError(f"Cannot extract Understat player ID from {source_path}")
        understat_id = int(match.group(1))
        for row_key, row_history in file_result.get("row_history", {}).items():
            source = _signature(row_history)
            try:
                year = int(float(str(source.get("season", "")).strip()))
                season = f"{year}-{str(year + 1)[-2:]}"
            except (TypeError, ValueError):
                season = ""
            status = "INVALID_SOURCE_SEASON"
            fixture_id = None
            fpl_code = None
            element_id = None
            candidate_count = 0
            if season in calendars:
                fixture, fixture_status = _fixture_match(source, "player", source_path, calendars)
                if fixture is None:
                    status = "AMBIGUOUS_FIXTURE" if fixture_status == "ambiguous_fixture_match" else "NO_CANONICAL_FIXTURE"
                else:
                    candidate_count = 1
                    source_date = pd.to_datetime(source.get("date"), errors="coerce")
                    fixture_date = fixture["kickoff_time"].date()
                    if pd.isna(source_date) or source_date.date() != fixture_date:
                        status = "PLAYER_DATE_TOLERANCE_CANDIDATE"
                    else:
                        fixture_id = int(fixture["fixture_id"])
                        links = membership.loc[
                            membership.season.eq(season)
                            & membership.fixture_id.eq(fixture_id)
                            & membership.understat_id.eq(understat_id)
                        ]
                        if len(links) and links.identity_conflict.fillna(False).any():
                            status = "AMBIGUOUS_PLAYER_ASSIGNMENT"
                            fixture_id = None
                        elif len(links) == 1:
                            status = "MATCHED_PLAYER_FIXTURE"
                            fpl_code = int(links.fpl_code.iloc[0])
                            element_id = int(links.element_id.iloc[0])
                        elif len(links) > 1:
                            status = "AMBIGUOUS_PLAYER_ASSIGNMENT"
                            fixture_id = None
                        else:
                            status = "PLAYER_NOT_IN_FPL_FIXTURE_ROWS"
                            fixture_id = None
            elif season:
                status = "OUTSIDE_AUDITED_SEASONS"
            output.append({
                "source_path": source_path,
                "row_key": row_key,
                "understat_id": understat_id,
                "season": season,
                "source_date": source.get("date"),
                "home_team": source.get("h_team"),
                "away_team": source.get("a_team"),
                "reconciliation_status": status,
                "fixture_id": fixture_id,
                "fpl_code": fpl_code,
                "element_id": element_id,
                "candidate_count": candidate_count,
                "present_in_latest_revision": row_history.get("present_in_latest_revision"),
                "first_seen_at": row_history.get("first_seen_at"),
                "latest_at": row_history.get("latest_at"),
                "value_revision_count": row_history.get("value_revision_count", 0),
                "missing_revision_count": row_history.get("missing_revision_count", 0),
                "reappearance_count": row_history.get("reappearance_count", 0),
            })
    counts: dict[str, int] = {}
    for row in output:
        counts[row["reconciliation_status"]] = counts.get(row["reconciliation_status"], 0) + 1
    return {
        "schema_version": 1,
        "audit_type": "understat_player_row_to_fpl_fixture_membership",
        "vaastav_commit": history_report.get("pinned_commit"),
        "dastan_assignments_commit": history_report.get("dastan_assignments_commit", DASTAN_COMMIT),
        "player_rows_reconciled": len(output),
        "status_counts": counts,
        "admission_decision": "NO_FEATURES_ADMITTED",
        "training_authorized": False,
        "limitations": [
            "A match is accepted only when the Understat match date exactly equals the pinned FPL UTC kickoff date.",
            "Player identity must be unique under the pinned Dastan season/Gameweek assignment interval and appear in the pinned FPL player-fixture rows.",
            "One-day date matches are candidates only; they are not silently accepted as corrections.",
            "This audit does not establish when Understat first published a row or value.",
        ],
        "rows": output,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-report", type=Path, required=True)
    parser.add_argument("--seasons", default="2020-21,2021-22,2022-23,2023-24,2024-25")
    parser.add_argument("--vaastav-commit", required=True)
    parser.add_argument("--dastan-commit", default=DASTAN_COMMIT)
    parser.add_argument("--fixture-cache-root", type=Path, required=True)
    parser.add_argument("--player-cache-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--detail-output", type=Path, required=True)
    args = parser.parse_args()
    seasons = [value for value in args.seasons.split(",") if value]
    history = json.loads(args.history_report.read_text(encoding="utf-8"))
    calendars = load_fixture_calendars(seasons, args.vaastav_commit, args.fixture_cache_root)
    membership = load_player_fixture_membership(seasons, args.vaastav_commit, args.dastan_commit, args.player_cache_root)
    history["dastan_assignments_commit"] = args.dastan_commit
    report = reconcile_player_rows(history, calendars, membership)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.detail_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({k:v for k,v in report.items() if k != "rows"}, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame(report["rows"]).to_csv(args.detail_output, index=False)
    print(json.dumps({k:v for k,v in report.items() if k != "rows"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
