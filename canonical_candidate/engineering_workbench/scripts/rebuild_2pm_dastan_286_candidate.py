"""Rebuild a corrected-identity Dastan 286-feature candidate for 2PM.

This reuses the pinned Dastan source acquisition, schema and feature definitions,
never its minutes predictor or weights. All 286 feature families are independently
reconstructed or joined from accepted deadline snapshots. The output remains an
unadmitted candidate because historical source vintages and exact match-completion
times are not fully proven.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from build_2pm_predeadline_market_snapshot import build_market_artifact
from rebuild_2pm_fixture_context import (
    CONTEXT_COLUMNS,
    rebuild_deadline_team_context,
    rebuild_fixture_context,
    rebuild_player_history_features,
)

PINNED_DASTAN_COMMIT = "758db9247e8b3a9a870c991064f74d8339d61cd0"
KEY = ["season", "gameweek", "fpl_code"]
MARKET_FIELDS = ["value", "selected", "transfers_balance"]
OBSERVED_PREFIX = "__observed__"
FRAME_KEY = ["season", "gameweek", "fixture", "fpl_code"]


def _json_default(value):
    """Serialize report metadata without losing timestamp precision or nulls."""
    if value is pd.NaT or value is pd.NA:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def corrected_assignments(
    training_assignments: pd.DataFrame,
    corrected_mapping: pd.DataFrame,
    requested_seasons: Iterable[str],
    completed_seasons: Iterable[str],
) -> pd.DataFrame:
    """Apply the reviewed corrected player IDs to frozen historical GW intervals."""
    requested = set(map(str, requested_seasons))
    completed = set(map(str, completed_seasons))
    historical_seasons = requested & completed
    active_seasons = requested - completed

    history = training_assignments[
        training_assignments["season"].astype(str).isin(historical_seasons)
    ].copy()
    corrected_ids = corrected_mapping.set_index("fpl_code")["understat_id"]
    mapped = history["fpl_code"].map(corrected_ids)
    missing = history.loc[mapped.isna(), "fpl_code"].drop_duplicates().tolist()
    if missing:
        raise ValueError(
            "Corrected historical map is missing frozen assignment FPL codes: "
            f"{missing[:20]}"
        )
    history["understat_id"] = mapped.astype("int64")

    pieces = [history]
    if active_seasons:
        raise ValueError(
            "Active-season assignments must be supplied from the pinned operational "
            "mapping resolver; this function only rewrites completed historical seasons."
        )
    out = pd.concat(pieces, ignore_index=True)
    if out.duplicated(["season", "fpl_code"]).any():
        raise ValueError("Corrected assignments contain duplicate season/player keys")
    return out.sort_values(["season", "fpl_code"], kind="mergesort").reset_index(drop=True)


def load_dastan_package(source_root: Path):
    """Import the exact pinned Dastan source checkout without importing its model."""
    source_root = source_root.resolve()
    if not (source_root / "dastan" / "data.py").exists():
        raise FileNotFoundError(f"Not a Dastan source checkout: {source_root}")
    result = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    )
    actual = result.stdout.strip()
    if actual != PINNED_DASTAN_COMMIT:
        raise RuntimeError(
            f"Dastan source pin mismatch: expected {PINNED_DASTAN_COMMIT}, got {actual}"
        )
    sys.path.insert(0, str(source_root))
    from dastan import data, mappings  # noqa: E402
    from dastan.rebuild import features, fplcache, sources  # noqa: E402

    # The runner's anonymous GitHub API quota is shared and can be exhausted by
    # concurrent CI. Use the workflow's read-only GITHUB_TOKEN for pinned tree
    # endpoints; raw source downloads remain pinned to the same commits.
    def authenticated_get(url: str, timeout: int = 90, retries: int = 4) -> bytes:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise RuntimeError(
                "GITHUB_TOKEN is required to retrieve pinned GitHub source trees "
                "without relying on the shared anonymous API rate limit"
            )
        quoted = urllib.parse.quote(url, safe=":/?&=%")
        last_error = None
        for attempt in range(retries):
            request = urllib.request.Request(
                quoted,
                headers={
                    "User-Agent": "2pm-pinned-data-rebuild/1.0",
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            try:
                return urllib.request.urlopen(request, timeout=timeout).read()
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    raise
                last_error = exc
                if exc.code not in (403, 429, 500, 502, 503, 504):
                    raise
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
        raise RuntimeError(
            f"Authenticated GitHub GET failed after {retries} attempts: "
            f"{quoted} ({last_error})"
        )

    sources._get = authenticated_get
    fplcache._get = authenticated_get
    return data, mappings, features, fplcache, sources


def attach_official_deadlines(
    frame: pd.DataFrame, raw_dir: Path, fplcache_module, seasons: list[str]
) -> pd.DataFrame:
    index = fplcache_module.load_index(raw_dir)
    rows = []
    for season in seasons:
        deadlines = fplcache_module.season_deadlines(raw_dir, index, season)
        rows.extend(
            {
                "season": season,
                "gameweek": int(gameweek),
                "deadline_time": pd.Timestamp(deadline),
            }
            for gameweek, deadline in deadlines.items()
        )
    calendar = pd.DataFrame(rows)
    if calendar.duplicated(KEY[:2]).any():
        raise ValueError("Official deadline calendar has duplicate season/Gameweek keys")
    out = frame.merge(calendar, on=KEY[:2], how="left", validate="many_to_one")
    if out["deadline_time"].isna().any():
        missing = out.loc[out["deadline_time"].isna(), KEY[:2]].drop_duplicates()
        raise ValueError(
            "Official deadline missing for candidate rows: "
            f"{missing.head(10).to_dict('records')}"
        )
    out["kickoff_time"] = pd.to_datetime(out["kickoff_time"], utc=True, errors="coerce")
    out["deadline_time"] = pd.to_datetime(out["deadline_time"], utc=True, errors="coerce")
    if out["kickoff_time"].isna().any() or out["deadline_time"].isna().any():
        raise ValueError("Candidate frame has invalid kickoff/deadline timestamps")

    # Rescheduled historical fixtures can remain attached to their original FPL
    # Gameweek even when their eventual kickoff is at/before that Gameweek's
    # deadline. Such a fixture is not a valid forecast target at that deadline.
    # Exclude it from the target frame, but retain the full player_matches archive
    # separately for post-match history reconstruction.
    already_started = out["kickoff_time"].le(out["deadline_time"])
    excluded = out.loc[
        already_started,
        [
            column for column in (
                "season", "gameweek", "fixture", "fpl_code",
                "kickoff_time", "deadline_time",
            ) if column in out.columns
        ],
    ].copy()
    report = {
        "rows_before": int(len(out)),
        "rows_excluded_started_by_deadline": int(already_started.sum()),
        "rows_after": int((~already_started).sum()),
        "excluded_player_gameweek_groups": int(
            excluded[["season", "gameweek", "fpl_code"]].drop_duplicates().shape[0]
        ) if len(excluded) else 0,
        "excluded_fixture_groups": int(
            excluded[["season", "gameweek", "fixture"]].drop_duplicates().shape[0]
        ) if len(excluded) else 0,
        "excluded_sample": (
            excluded.head(20).astype({
                column: "string" for column in ("season", "fixture", "fpl_code")
                if column in excluded.columns
            }).to_dict("records")
            if len(excluded) else []
        ),
        "policy": "Only fixtures kicking off strictly after the official Gameweek deadline remain forecast targets; the full match archive is retained for history reconstruction.",
    }
    # Keep every fixture row in the historical archive. The downstream dataset
    # builder uses this flag only to select valid forecast targets; post-match
    # sequence tokens still need played fixtures that were rescheduled before
    # their assigned Gameweek deadline.
    out["forecast_target_eligible"] = ~already_started
    out.attrs["deadline_target_eligibility"] = report
    return out



def attach_match_availability_bounds(
    frame: pd.DataFrame,
    raw_dir: Path,
    sources_module,
    seasons: list[str],
    *,
    force: bool = False,
) -> pd.DataFrame:
    """Attach canonical fixture kickoff and its conservative availability bound.

    Vaastav's fixture calendar is the common kickoff-time authority for the
    availability bound and all downstream post-match state checks. Preserve the
    incoming candidate kickoff for discrepancy auditing rather than comparing
    availability derived from one source against kickoff from another.
    """
    fixture_frames = []
    for season in seasons:
        path = raw_dir / "vaastav" / season / "fixtures.csv"
        if force or not path.exists() or path.stat().st_size == 0:
            url = sources_module.VAASTAV_RAW + f"data/{season}/fixtures.csv"
            sources_module._download(url, path, force=force)
        fixtures = pd.read_csv(path, usecols=["id", "kickoff_time", "finished"])
        fixtures = fixtures.rename(columns={"id": "fixture"})
        fixtures["season"] = season
        fixtures["kickoff_time"] = pd.to_datetime(
            fixtures["kickoff_time"], utc=True, errors="coerce"
        )
        if fixtures["kickoff_time"].isna().any():
            raise ValueError(f"{season} fixtures contain invalid kickoff timestamps")
        finished = fixtures["finished"].astype(str).str.lower().eq("true")
        fixtures["match_available_at"] = fixtures["kickoff_time"] + pd.Timedelta(hours=24)
        fixtures.loc[~finished, "match_available_at"] = pd.NaT
        fixtures["completion_time_quality"] = finished.map(
            {
                True: "CONSERVATIVE_24H_UPPER_BOUND",
                False: "NOT_FINISHED",
            }
        )
        fixture_frames.append(
            fixtures[
                [
                    "season", "fixture", "kickoff_time", "match_available_at",
                    "completion_time_quality",
                ]
            ]
        )
    calendar = pd.concat(fixture_frames, ignore_index=True)
    calendar["season"] = calendar["season"].astype(str)
    calendar["fixture"] = calendar["fixture"].astype(str)
    if calendar.duplicated(["season", "fixture"]).any():
        raise ValueError("Fixture availability calendar has duplicate season/fixture keys")
    calendar = calendar.rename(columns={"kickoff_time": "calendar_kickoff_time"})
    out = frame.copy()
    out["season"] = out["season"].astype(str)
    out["fixture"] = out["fixture"].astype(str)
    if "kickoff_time" in out:
        out["candidate_kickoff_time"] = pd.to_datetime(
            out["kickoff_time"], utc=True, errors="coerce"
        )
    else:
        out["candidate_kickoff_time"] = pd.NaT
    out = out.merge(
        calendar,
        on=["season", "fixture"],
        how="left",
        validate="many_to_one",
    )
    if out["completion_time_quality"].isna().any():
        missing = out.loc[
            out["completion_time_quality"].isna(), ["season", "fixture"]
        ].drop_duplicates()
        raise ValueError(
            "Candidate rows lack fixture completion metadata: "
            f"{missing.head(10).to_dict('records')}"
        )
    if out["calendar_kickoff_time"].isna().any():
        raise ValueError("Canonical fixture calendar contains missing kickoff timestamps")
    out["kickoff_time"] = out["calendar_kickoff_time"]
    mismatch = (
        out["candidate_kickoff_time"].notna()
        & out["candidate_kickoff_time"].ne(out["calendar_kickoff_time"])
    )
    report = {
        "calendar_authority": "pinned Vaastav fixture kickoff_time",
        "rows_with_candidate_kickoff_mismatch": int(mismatch.sum()),
        "mismatch_sample": out.loc[
            mismatch,
            ["season", "fixture", "candidate_kickoff_time", "calendar_kickoff_time"],
        ].head(20).astype({"season": "string", "fixture": "string"}).to_dict("records"),
        "availability_rule": "calendar kickoff_time + 24h for fixtures marked finished",
    }
    out.attrs["fixture_kickoff_reconciliation"] = report
    return out


def enforce_snapshot_safety_buffer(path: Path, *, minutes: int = 5) -> dict:
    """Drop otherwise-pre-deadline snapshots captured inside the safety buffer."""
    frame = pd.read_parquet(path)
    captured = pd.to_datetime(frame["snapshot_at"], utc=True, errors="coerce")
    deadline = pd.to_datetime(frame["deadline_time"], utc=True, errors="coerce")
    age = deadline - captured
    unsafe = captured.isna() | deadline.isna() | age.lt(pd.Timedelta(minutes=minutes))
    removed = int(unsafe.sum())
    safe = frame.loc[~unsafe].copy()
    safe.to_parquet(path, index=False)
    return {
        "path": path.name,
        "safety_buffer_minutes": minutes,
        "rows_before": int(len(frame)),
        "rows_removed": removed,
        "rows_after": int(len(safe)),
    }


def audit_market_value_parity(
    player_matches: pd.DataFrame,
    market_path: Path,
) -> dict:
    """Compare archived retrospective FPL fields with accepted deadline snapshots."""
    market = pd.read_parquet(market_path)[KEY + MARKET_FIELDS]
    source_columns = [column for column in MARKET_FIELDS if column in player_matches]
    if len(source_columns) != len(MARKET_FIELDS):
        return {
            "status": "INCOMPLETE_SOURCE_FIELDS",
            "missing_source_fields": sorted(set(MARKET_FIELDS) - set(source_columns)),
        }
    source = player_matches[KEY + MARKET_FIELDS].copy()
    source["season"] = source["season"].astype(str)
    market["season"] = market["season"].astype(str)
    joined = source.merge(
        market, on=KEY, how="inner", suffixes=("_retrospective", "_snapshot"),
        validate="many_to_one",
    )
    report = {"rows_compared": int(len(joined)), "fields": {}}
    for column in MARKET_FIELDS:
        left = pd.to_numeric(joined[f"{column}_retrospective"], errors="coerce")
        right = pd.to_numeric(joined[f"{column}_snapshot"], errors="coerce")
        valid = left.notna() & right.notna()
        difference = (left[valid] - right[valid]).abs()
        def distribution(values: pd.Series) -> dict:
            numeric = pd.to_numeric(values, errors="coerce").dropna()
            if numeric.empty:
                return {"count": 0}
            return {
                "count": int(len(numeric)),
                "min": float(numeric.min()),
                "p05": float(numeric.quantile(0.05)),
                "median": float(numeric.median()),
                "mean": float(numeric.mean()),
                "p95": float(numeric.quantile(0.95)),
                "max": float(numeric.max()),
            }

        paired_left = left[valid]
        paired_right = right[valid]
        report["fields"][column] = {
            "valid_pairs": int(valid.sum()),
            "exact_match_rows": int(np.isclose(left[valid], right[valid], atol=1e-6).sum()),
            "exact_match_rate": (
                float(np.isclose(left[valid], right[valid], atol=1e-6).mean())
                if valid.any() else None
            ),
            "mean_absolute_difference": float(difference.mean()) if len(difference) else None,
            "median_absolute_difference": float(difference.median()) if len(difference) else None,
            "p95_absolute_difference": float(difference.quantile(0.95)) if len(difference) else None,
            "retrospective_distribution": distribution(paired_left),
            "deadline_snapshot_distribution": distribution(paired_right),
            "pearson_correlation": (
                float(paired_left.corr(paired_right))
                if len(paired_left) > 1 and paired_left.nunique() > 1 and paired_right.nunique() > 1
                else None
            ),
            "spearman_correlation": (
                float(paired_left.corr(paired_right, method="spearman"))
                if len(paired_left) > 1 and paired_left.nunique() > 1 and paired_right.nunique() > 1
                else None
            ),
        }
    report["interpretation"] = (
        "Diagnostic comparison only. Retrospective Vaastav player-fixture fields and "
        "deadline-anchored fplcache player-Gameweek snapshots are different source "
        "artifacts and may represent different capture times or semantics. Distribution "
        "and rank-correlation diagnostics help identify scale/definition differences; "
        "neither exact parity nor correlation proves historical point-in-time validity. "
        "Do not normalize or admit a field from this comparison alone."
    )
    return report


def audit_defensive_source_coverage(
    raw_dir: Path,
    seasons: list[str],
    player_matches: pd.DataFrame,
) -> dict:
    """Verify defensive feature availability against each pinned raw season file."""
    source_fields = [
        "defensive_contribution",
        "clearances_blocks_interceptions",
        "recoveries",
        "tackles",
    ]
    report = {}
    for season in seasons:
        source_path = raw_dir / "vaastav" / season / "merged_gw.csv"
        if not source_path.exists() or source_path.stat().st_size == 0:
            raise FileNotFoundError(
                f"Pinned Vaastav merged_gw.csv is missing for {season}: {source_path}"
            )
        source_columns = set(pd.read_csv(source_path, nrows=0).columns)
        rows = player_matches[player_matches["season"].astype(str).eq(str(season))]
        played = rows[pd.to_numeric(rows["minutes"], errors="coerce").gt(0)]
        fields = {}
        for field in source_fields:
            present = field in source_columns
            values = (
                pd.to_numeric(played[field], errors="coerce")
                if present and field in played
                else pd.Series(np.nan, index=played.index, dtype=float)
            )
            fields[field] = {
                "source_column_present": bool(present),
                "played_rows": int(len(played)),
                "finite_values": int(values.notna().sum()),
                "missing_values": int(values.isna().sum()),
                "observed_zero_values": int(values.eq(0.0).sum()),
                "observed_nonzero_values": int((values.notna() & values.ne(0.0)).sum()),
            }
        report[str(season)] = {
            "source_file": str(source_path.name),
            "source_file_sha256": sha256(source_path),
            "source_column_audit": fields,
        }
    return {
        "source_repository": "vaastav/Fantasy-Premier-League",
        "source_commit": "8c97b2adb123863c3dd581e730f1360e89815ac2",
        "source_file": "data/{season}/gws/merged_gw.csv",
        "fields": source_fields,
        "seasons": report,
        "interpretation": (
            "A missing source column is structural source absence for that pinned "
            "season file; a present column with missing row values is incomplete "
            "observation coverage, not an observed zero. Finite zero and nonzero "
            "values are counted separately. This audit establishes column/row "
            "availability only, not historical publication vintage or feature admission."
        ),
    }


def audit_understat_player_coverage(player_matches: pd.DataFrame) -> dict:
    """Measure actual Understat match-row coverage before any missing-value fill."""
    metrics = ["us_minutes", "us_goals", "us_assists", "us_shots", "us_key_passes", "us_xG", "us_xA", "us_npg", "us_npxG", "us_xGChain", "us_xGBuildup"]
    mapped = player_matches["understat_id"].notna()
    played = pd.to_numeric(player_matches["minutes"], errors="coerce").gt(0)
    eligible = player_matches.loc[mapped & played].copy()
    coverage = {}
    for column in metrics:
        if column not in eligible:
            coverage[column] = {"non_missing_rows": 0, "missing_rows": int(len(eligible)), "coverage_rate": 0.0 if len(eligible) else None}
            continue
        observed = pd.to_numeric(eligible[column], errors="coerce").notna()
        coverage[column] = {
            "non_missing_rows": int(observed.sum()),
            "missing_rows": int((~observed).sum()),
            "coverage_rate": float(observed.mean()) if len(observed) else None,
        }
    if len(eligible) and "us_xG" in eligible:
        by_player = eligible.groupby("understat_id")["us_xG"].apply(
            lambda values: pd.to_numeric(values, errors="coerce").notna().any()
        )
        no_history = by_player.index[~by_player].astype(int).tolist()
    else:
        no_history = []
    return {
        "mapped_played_player_fixture_rows": int(len(eligible)),
        "unmapped_played_player_fixture_rows": int((played & ~mapped).sum()),
        "mapped_player_ids_with_played_rows": int(eligible["understat_id"].nunique()) if len(eligible) else 0,
        "mapped_player_ids_with_no_xG_history": int(len(no_history)),
        "mapped_player_ids_with_no_xG_history_sample": no_history[:25],
        "metric_coverage": coverage,
        "policy": "Missing Understat values remain missing; they are not converted to zero and require training-fold-only imputation.",
    }


def expected_reconstruction_feature_map(features_module) -> dict[str, tuple[str, ...]]:
    """Return the exact schema names emitted by each independent builder path.

    The upstream feature maps define the rolling column names. This explicit
    map is compared with the pinned 286-column schema, not merely counted.
    """
    windows = tuple(features_module.WINDOWS)
    player = tuple(
        f"player_{feature}_{window}"
        for feature in features_module.PLAYER_FEATURES.values()
        for window in windows
    ) + tuple(f"player_relevant_fpl_points_{window}" for window in windows)
    availability = tuple(
        f"{prefix}_{window}"
        for prefix in ("p_any", "p60", "e_minutes")
        for window in (3, 5, 10)
    )
    defensive_player = tuple(
        f"ar_{feature}_{window}"
        for feature in ("defensive_contribution", "cbit", "recoveries", "tackles")
        for window in (3, 5, 10, 38)
    ) + tuple(
        f"ar_{kind}_{window}"
        for kind in ("dc_hit_rate", "dc_near_rate", "starts")
        for window in (3, 5, 10)
    ) + ("ar_dc_ppg_5",)
    team = tuple(
        f"team_{feature}_{window}"
        for feature in features_module.TEAM_FEATURES.values()
        for window in windows
    )
    opponent = tuple(name.replace("team_", "opp_", 1) for name in team)
    return {
        "player_rolling": player,
        "availability_history": availability,
        "defensive_player_history": defensive_player,
        "own_team_rolling": team,
        "opponent_rolling": opponent,
        "direct_ranks": ("status_league_rank", "opp_status_league_rank"),
        "fixture_context": tuple(CONTEXT_COLUMNS),
        "home_context": ("is_home_num",),
        "market_snapshot": tuple(MARKET_FIELDS),
        "expected_points_snapshot": ("ar_ep_next",),
        "pre_deadline_signals": (
            "sig_status_risk", "sig_chance_playing", "sig_has_news",
        ),
    }



def expected_reconstruction_source_map(features_module) -> dict[str, str]:
    """Map every schema name to its raw field or explicit derived calculation."""
    result = {}
    windows = tuple(features_module.WINDOWS)
    for source, feature in features_module.PLAYER_FEATURES.items():
        for window in windows:
            result[f"player_{feature}_{window}"] = (
                f"player_matches.{source}; mean of last {window} eligible player fixtures"
            )
    for window in windows:
        result[f"player_relevant_fpl_points_{window}"] = (
            f"player_matches.total_points; same-venue mean of last {window} eligible fixtures"
        )
    for prefix, expression in {
        "p_any": "player_matches.minutes > 0",
        "p60": "player_matches.minutes >= 60",
        "e_minutes": "player_matches.minutes",
    }.items():
        for window in (3, 5, 10):
            result[f"{prefix}_{window}"] = (
                f"{expression}; season-scoped mean of last {window} eligible player fixtures"
            )
    defensive_sources = {
        "defensive_contribution": "player_matches.defensive_contribution",
        "cbit": "player_matches.clearances_blocks_interceptions or player_matches.cbit",
        "recoveries": "player_matches.recoveries",
        "tackles": "player_matches.tackles",
    }
    for feature, source in defensive_sources.items():
        for window in (3, 5, 10, 38):
            result[f"ar_{feature}_{window}"] = (
                f"{source}; mean of last {window} eligible player fixtures"
            )
    for window in (3, 5, 10):
        result[f"ar_dc_hit_rate_{window}"] = (
            "player_matches.defensive_contribution + position-specific DC_THRESHOLD; "
            f"hit rate over last {window} eligible player fixtures"
        )
        result[f"ar_dc_near_rate_{window}"] = (
            "player_matches.defensive_contribution + position-specific DC_THRESHOLD; "
            f"near-threshold rate over last {window} eligible player fixtures"
        )
        result[f"ar_starts_{window}"] = (
            f"player_matches.starts; mean of last {window} eligible player fixtures"
        )
    result["ar_dc_ppg_5"] = "2 * ar_dc_hit_rate_5"
    for source, feature in features_module.TEAM_FEATURES.items():
        if source == "league_rank":
            own_source = (
                "team_matches.scored/missed/pts; standings using only matches with match_available_at strictly before historical kickoff; "
                "own-team standings rank immediately before each historical match"
            )
            opponent_source = (
                "team_matches.scored/missed/pts; standings using only matches with match_available_at strictly before historical kickoff; "
                "historical opponent standings rank immediately before each match"
            )
        elif source == "opp_league_rank":
            own_source = (
                "team_matches.scored/missed/pts; standings using only matches with match_available_at strictly before historical kickoff; "
                "historical opponent-of-team standings rank immediately before each match"
            )
            opponent_source = (
                "team_matches.scored/missed/pts; standings using only matches with match_available_at strictly before historical kickoff; "
                "historical opponent-of-opponent (target-team) standings rank immediately before each match"
            )
        else:
            own_source = f"team_matches.{source}"
            opponent_source = f"opponent team_matches.{source}"
        for window in windows:
            result[f"team_{feature}_{window}"] = (
                f"{own_source}; mean of last {window} eligible team matches"
            )
            result[f"opp_{feature}_{window}"] = (
                f"{opponent_source}; mean of last {window} eligible opponent matches"
            )
    result["status_league_rank"] = (
        "team_matches.scored/missed/pts; deadline standings rank using only matches with match_available_at strictly before deadline, ordered by points, goal difference, goals scored"
    )
    result["opp_status_league_rank"] = (
        "opponent team_matches.scored/missed/pts; same deadline standings calculation using match_available_at strictly before deadline"
    )
    result.update({
        "ar_rest_days": (
            "player_matches.kickoff_time and match_available_at; latest strictly available prior fixture"
        ),
        "ar_team_matches_14d": (
            "known team fixture schedule; count in [target kickoff - 14 days, target kickoff]"
        ),
        "ar_opp_dc_allowed_3": (
            "player_matches.defensive_contribution; opponent-conceded fixture totals, last 3"
        ),
        "ar_opp_dc_allowed_5": (
            "player_matches.defensive_contribution; opponent-conceded fixture totals, last 5"
        ),
        "ar_opp_dc_allowed_10": (
            "player_matches.defensive_contribution; opponent-conceded fixture totals, last 10"
        ),
        "ar_opp_tackles_allowed_5": (
            "player_matches.tackles; opponent-conceded fixture totals, last 5"
        ),
        "is_home_num": "player_matches.is_home",
        "value": "pre_deadline_market.now_cost",
        "selected": "pre_deadline_market.selected_by_percent",
        "transfers_balance": "pre_deadline_market.transfers_in_event - transfers_out_event",
        "ar_ep_next": "pre_deadline_ep_next.ep_next",
        "sig_status_risk": "pre_deadline_signals.sig_status_risk; FPL status mapped a=0,d=1,s=2,i=3,u/n=4",
        "sig_chance_playing": "pre_deadline_signals.sig_chance_playing; FPL chance_of_playing_next_round as float, -1 if null",
        "sig_has_news": "pre_deadline_signals.sig_has_news; FPL news non-empty -> 1.0, empty -> 0.0",
    })
    return result


def validate_reconstruction_coverage(
    ordered_features: list[str],
    player_report: dict,
    team_report: dict,
    fixture_report: dict,
    frame: pd.DataFrame,
    features_module,
) -> dict:
    """Fail closed on exact feature-name, builder-path and mask alignment."""
    if len(ordered_features) != 286 or len(set(ordered_features)) != 286:
        raise RuntimeError("Pinned 2PM schema must contain 286 unique ordered feature names")
    feature_set = set(ordered_features)
    feature_map = expected_reconstruction_feature_map(features_module)
    flattened = [name for names in feature_map.values() for name in names]
    duplicates = sorted({name for name in flattened if flattened.count(name) > 1})
    if duplicates:
        raise RuntimeError(f"Feature builders assign the same schema name more than once: {duplicates}")
    expected_set = set(flattened)
    missing_from_builders = sorted(feature_set - expected_set)
    unexpected_from_builders = sorted(expected_set - feature_set)
    if missing_from_builders or unexpected_from_builders:
        raise RuntimeError(
            "Exact reconstruction/schema feature-name mismatch: "
            f"schema_without_builder={missing_from_builders}; "
            f"builder_without_schema={unexpected_from_builders}"
        )

    missing_columns = [column for column in ordered_features if column not in frame]
    if missing_columns:
        raise RuntimeError(f"Reconstructed frame missing schema columns: {missing_columns}")
    observed_columns = [f"{OBSERVED_PREFIX}{column}" for column in ordered_features]
    missing_masks = [column for column in observed_columns if column not in frame]
    if missing_masks:
        raise RuntimeError(f"Reconstruction paths missing exact observation-mask columns: {missing_masks}")
    invalid_masks = {}
    for feature, mask_column in zip(ordered_features, observed_columns):
        mask = pd.to_numeric(frame[mask_column], errors="coerce")
        if mask.isna().any() or not mask.isin([0, 1]).all():
            invalid_masks[feature] = mask_column
    if invalid_masks:
        raise RuntimeError(f"Observation masks must be complete binary columns: {invalid_masks}")

    expected_counts = {name: len(names) for name, names in feature_map.items()}
    reported_counts = {
        "player_rolling": int(player_report.get("player_rolling_feature_count", 0)),
        "availability_history": int(player_report.get("availability_feature_count", 0)),
        "defensive_player_history": int(player_report.get("defensive_player_history_feature_count", 0)),
        "own_team_rolling": int(team_report.get("team_feature_count", 0)),
        "opponent_rolling": int(team_report.get("opponent_feature_count", 0)),
        "direct_ranks": len(team_report.get("direct_rank_columns", [])),
        "fixture_context": len(fixture_report.get("fixture_context_columns", [])),
        "home_context": 1,
        "market_snapshot": len(MARKET_FIELDS),
        "expected_points_snapshot": 1,
        "pre_deadline_signals": 3,
    }
    if reported_counts != expected_counts:
        raise RuntimeError(
            f"Builder-reported family counts disagree with exact name map: "
            f"expected={expected_counts}, reported={reported_counts}"
        )
    source_family_by_feature = {
        feature: family
        for family, names in feature_map.items()
        for feature in names
    }
    source_field_by_feature = expected_reconstruction_source_map(features_module)
    if set(source_field_by_feature) != feature_set:
        raise RuntimeError(
            "Raw-source/calculation mapping does not cover the exact schema: "
            f"missing={sorted(feature_set - set(source_field_by_feature))}; "
            f"extra={sorted(set(source_field_by_feature) - feature_set)}"
        )
    return {
        "status": "ALL_286_EXACT_FEATURE_NAMES_AND_OBSERVATION_MASKS_RECONCILED",
        "schema_feature_count": len(ordered_features),
        "exact_name_match": True,
        "feature_names_without_builder": [],
        "builder_names_outside_schema": [],
        "observation_mask_name_match": True,
        "observation_mask_values_binary": True,
        "reconstruction_path_counts": expected_counts,
        "reconstruction_path_total": len(flattened),
        "feature_source_family_by_name": source_family_by_feature,
        "feature_source_field_or_calculation_by_name": source_field_by_feature,
        "admission_status": "NOT_ADMITTED_SOURCE_VINTAGE_AND_PARITY_REMAIN_OPEN",
    }

def build_candidate(
    source_root: Path,
    raw_dir: Path,
    output_dir: Path,
    seasons: list[str],
    *,
    workers: int = 12,
    force: bool = False,
    allow_missing_understat: bool = False,
    include_active_season: bool = False,
) -> dict:
    data, mappings, features, fplcache, sources = load_dastan_package(source_root)
    registry = json.loads((data.DATA / "season_registry.json").read_text())
    completed = list(map(str, registry["completed_seasons"]))
    active = sorted(set(seasons) - set(completed))
    if active and not include_active_season:
        raise ValueError(
            f"Active seasons {active} require explicit --include-active-season"
        )

    # Preserve Dastan's operational resolver for active-season rows, but replace
    # immutable historical IDs with the evidence-backed corrected mapping.
    original_resolver = mappings.assignments_for_seasons
    training_assignments = mappings.load_training_assignments()
    corrected_mapping = mappings.load()
    corrected_map_sha = sha256(mappings.CORRECTED_MAPPING)

    def resolver(requested_seasons: list[str]) -> pd.DataFrame:
        requested = set(map(str, requested_seasons))
        hist = corrected_assignments(
            training_assignments,
            corrected_mapping,
            requested & set(completed),
            completed,
        )
        if active:
            active_rows = original_resolver(sorted(requested - set(completed)))
            result = pd.concat([hist, active_rows], ignore_index=True)
        else:
            result = hist
        result = result[result["season"].astype(str).isin(requested)]
        if result.duplicated(["season", "fpl_code"]).any():
            raise ValueError("Resolved identity assignments are not unique")
        return result.sort_values(["season", "fpl_code"], kind="mergesort").reset_index(drop=True)

    mappings.assignments_for_seasons = resolver
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Downloading pinned FPL/Understat source inputs", flush=True)
    sources.download_sources(
        raw_dir,
        seasons,
        workers=workers,
        force=force,
        allow_missing_understat=allow_missing_understat,
    )
    print("Rebuilding canonical player/team histories with corrected identities", flush=True)
    player_matches, team_matches, player_lookup = sources.build_canonical_matches(
        raw_dir, seasons
    )
    understat_player_coverage = audit_understat_player_coverage(player_matches)
    defensive_source_coverage = audit_defensive_source_coverage(
        raw_dir, seasons, player_matches
    )
    feature_frame = features.build_feature_frame(player_matches, team_matches)
    feature_path = output_dir / "features.parquet"
    feature_frame.to_parquet(feature_path, index=False)
    player_lookup.to_csv(output_dir / "players.csv", index=False)

    print("Rebuilding provenance-checked pre-deadline FPL snapshots", flush=True)
    fplcache.build_predeadline_artifacts(raw_dir, output_dir, seasons)
    ep_safety = enforce_snapshot_safety_buffer(
        output_dir / "pre_deadline_ep_next.parquet", minutes=5
    )
    signals_safety = enforce_snapshot_safety_buffer(
        output_dir / "pre_deadline_signals.parquet", minutes=5
    )
    market_path, market_report = build_market_artifact(
        raw_dir, output_dir, seasons, fplcache, safety_buffer_minutes=5
    )
    market_parity_report = audit_market_value_parity(player_matches, market_path)
    market_report["retrospective_field_parity_audit"] = market_parity_report
    sources.write_download_manifest(raw_dir, seasons)

    # Reuse only Dastan's documented snapshot joins and missing-snapshot sentinel;
    # no Dastan model preprocessing or prediction head is imported.
    loaded = data.load(
        candidates=("availability",),
        check_rows=False,
        data_dir=output_dir,
    )
    market = pd.read_parquet(market_path)[
        KEY + MARKET_FIELDS + ["snapshot_at"]
    ].rename(columns={"snapshot_at": "market_snapshot_at"})
    loaded = loaded.drop(columns=MARKET_FIELDS, errors="ignore").merge(
        market, on=KEY, how="left", validate="many_to_one"
    )
    for column in MARKET_FIELDS:
        loaded[column] = pd.to_numeric(loaded[column], errors="coerce").fillna(-1.0)
    ordered_features = data.shipped_features(loaded)
    if len(ordered_features) != 286:
        raise RuntimeError(f"Expected 286 Dastan inputs, found {len(ordered_features)}")
    loaded = attach_official_deadlines(loaded, raw_dir, fplcache, seasons)
    deadline_target_eligibility = loaded.attrs.get("deadline_target_eligibility", {})
    loaded = attach_match_availability_bounds(
        loaded, raw_dir, sources, seasons, force=force
    )
    fixture_kickoff_reconciliation = loaded.attrs.get(
        "fixture_kickoff_reconciliation", {}
    )
    # Re-evaluate target eligibility against the same canonical fixture kickoff
    # used to derive match_available_at; never mix kickoff timestamps from sources.
    loaded["deadline_time"] = pd.to_datetime(loaded["deadline_time"], utc=True)
    loaded["forecast_target_eligible"] = loaded["kickoff_time"].gt(
        loaded["deadline_time"]
    )
    deadline_target_eligibility = {
        "rows_before": int(len(loaded)),
        "rows_excluded_started_by_deadline": int(
            (~loaded["forecast_target_eligible"]).sum()
        ),
        "rows_after": int(loaded["forecast_target_eligible"].sum()),
        "kickoff_authority": "pinned Vaastav fixture calendar",
        "kickoff_reconciliation": fixture_kickoff_reconciliation,
        "policy": "Only fixtures kicking off strictly after the official Gameweek deadline remain forecast targets; all fixtures remain available for historical state reconstruction.",
    }
    # Restore canonical fixture identity/context from the raw player-match table.
    # The upstream release frame may have anchored ar_* values across a DGW;
    # rebuild the six fixture-specific context fields after that anchor.
    context_matches = player_matches.copy()
    for key_frame in (loaded, context_matches):
        key_frame["season"] = key_frame["season"].astype(str)
        key_frame["fixture"] = key_frame["fixture"].astype(str)
        key_frame["fpl_code"] = pd.to_numeric(
            key_frame["fpl_code"], errors="raise"
        ).astype("int64")
    fixture_context = context_matches[
        ["season", "fixture", "fpl_code", "team_name", "opponent_team_name"]
    ].copy()
    if fixture_context.duplicated(["season", "fixture", "fpl_code"]).any():
        raise ValueError("Canonical player fixture context contains duplicate keys")
    loaded = loaded.drop(
        columns=["team_name", "opponent_team_name"], errors="ignore"
    ).merge(
        fixture_context,
        on=["season", "fixture", "fpl_code"],
        how="left",
        validate="one_to_one",
    )
    fixture_availability = loaded[
        ["season", "fixture", "kickoff_time", "match_available_at"]
    ].drop_duplicates(["season", "fixture"])
    fixture_availability = fixture_availability.rename(
        columns={"kickoff_time": "calendar_kickoff_time"}
    )
    history_matches = context_matches.drop(columns=["kickoff_time"], errors="ignore").merge(
        fixture_availability,
        on=["season", "fixture"],
        how="left",
        validate="many_to_one",
    ).rename(columns={"calendar_kickoff_time": "kickoff_time"})
    # Preserve reconstruction inputs for the post-match sequence stage.
    history_matches.to_parquet(
        output_dir / "player_matches_with_availability.parquet", index=False
    )
    team_matches.to_parquet(output_dir / "team_matches.parquet", index=False)
    loaded, player_history_report = rebuild_player_history_features(
        loaded, history_matches, features
    )
    loaded, team_context_report = rebuild_deadline_team_context(
        loaded, team_matches, features
    )
    loaded, fixture_context_report = rebuild_fixture_context(
        loaded, history_matches
    )
    # The rebuilders emit raw-source observation sidecars for rolling features.
    # Retained context/snapshot columns are classified here, before candidate export.
    retained_observed_features = [
        "is_home_num", "value", "selected", "transfers_balance",
        "ar_ep_next", "sig_status_risk", "sig_chance_playing", "sig_has_news",
    ]
    for feature in retained_observed_features:
        if feature not in loaded:
            raise ValueError(f"Retained feature missing before observation-mask build: {feature}")
        numeric = pd.to_numeric(loaded[feature], errors="coerce")
        observed = np.isfinite(numeric.to_numpy(dtype=float))
        if feature != "is_home_num":
            observed &= numeric.to_numpy(dtype=float) != -1.0
        loaded[f"{OBSERVED_PREFIX}{feature}"] = observed.astype(np.uint8)
    observed_columns = [f"{OBSERVED_PREFIX}{feature}" for feature in ordered_features]
    missing_observation_columns = [
        column for column in observed_columns if column not in loaded
    ]
    if missing_observation_columns:
        raise ValueError(
            "Raw-source observation reconstruction did not cover all 286 features: "
            f"{missing_observation_columns[:20]}"
        )
    reconstruction_coverage = validate_reconstruction_coverage(
        ordered_features,
        player_history_report,
        team_context_report,
        fixture_context_report,
        loaded,
        features,
    )
    # Rehash after adding fixture calendars so the manifest covers every input.
    sources.write_download_manifest(raw_dir, seasons)
    loaded["feature_cutoff_time"] = loaded["deadline_time"]
    loaded["source_vintage_status"] = "RETROSPECTIVE_SOURCE_VINTAGE_NOT_VERIFIED"

    ep_path = output_dir / "pre_deadline_ep_next.parquet"
    signal_path = output_dir / "pre_deadline_signals.parquet"
    ep_meta = pd.read_parquet(ep_path)[KEY + ["snapshot_at"]].rename(
        columns={"snapshot_at": "ep_next_snapshot_at"}
    )
    signal_meta = pd.read_parquet(signal_path)[KEY + ["snapshot_at"]].rename(
        columns={"snapshot_at": "signals_snapshot_at"}
    )
    loaded = loaded.merge(ep_meta, on=KEY, how="left", validate="many_to_one")
    loaded = loaded.merge(signal_meta, on=KEY, how="left", validate="many_to_one")

    metadata = [
        "season", "gameweek", "fixture", "fpl_code", "position",
        "team_name", "opponent_team_name", "kickoff_time", "deadline_time", "feature_cutoff_time",
        "forecast_target_eligible",
        "match_available_at", "completion_time_quality", "source_vintage_status",
        "minutes", "target_points", "ep_next_snapshot_at", "signals_snapshot_at",
        "market_snapshot_at",
    ]
    absent = [column for column in metadata if column not in loaded.columns]
    if absent:
        raise RuntimeError(f"Candidate output is missing metadata columns: {absent}")
    candidate = loaded[metadata + ordered_features + observed_columns].copy()
    # The pinned Dastan contract is one player-fixture row and target_points is
    # the points scored in that fixture. The 2PM dataset later sums these once
    # to obtain the single player-Gameweek training label.
    candidate["target_label_grain"] = "player_fixture"
    candidate["target_points_semantics"] = "FPL_POINTS_SCORED_IN_THIS_FIXTURE"
    candidate["identity_mapping_sha256"] = corrected_map_sha
    candidate["source_manifest_sha256"] = sha256(raw_dir / "downloads.json")
    candidate["source_vintage_status"] = "RETROSPECTIVE_SOURCE_VINTAGE_NOT_VERIFIED"
    candidate["deadline_status"] = "INDEPENDENT_286_FEATURE_RECONSTRUCTION_NOT_SOURCE_VINTAGE_ADMITTED"
    candidate["admission_status"] = "NOT_ADMITTED"
    candidate_path = output_dir / "features_286_candidate.parquet"
    candidate.to_parquet(candidate_path, index=False)

    source_pins = json.loads((data.DATA / "source_pins.json").read_text())
    report = {
        "status": "DASTAN_286_CANDIDATE_REBUILT",
        "source_pins_reviewed_at": source_pins.get("reviewed_at"),
        "source_pins": {
            "vaastav": source_pins.get("vaastav"),
            "fplcache": source_pins.get("fplcache"),
        },
        "admission_status": "NOT_ADMITTED",
        "model": "2PM",
        "upstream_repository": "qazybekb/smartplayfpl-dastan",
        "upstream_commit": PINNED_DASTAN_COMMIT,
        "seasons": seasons,
        "candidate_rows": len(candidate),
        "candidate_feature_count": len(ordered_features),
        "raw_source_observation_sidecar_count": len(observed_columns),
        "target_label_grain": "player_fixture",
        "target_points_semantics": "FPL_POINTS_SCORED_IN_THIS_FIXTURE",
        "feature_order_sha256": hashlib.sha256(
            "\n".join(ordered_features).encode("utf-8")
        ).hexdigest(),
        "identity_mapping_sha256": corrected_map_sha,
        "source_manifest_sha256": sha256(raw_dir / "downloads.json"),
        "candidate_sha256": sha256(candidate_path),
        "deadline_calendar_rows": int(candidate[KEY[:2]].drop_duplicates().shape[0]),
        "deadline_target_eligibility": deadline_target_eligibility,
        "pre_deadline_snapshot_rows": {
            "ep_next": len(pd.read_parquet(ep_path)),
            "signals": len(pd.read_parquet(signal_path)),
            "market": len(pd.read_parquet(market_path)),
        },
        "market_snapshot_report": market_report,
        "market_value_parity_audit": market_parity_report,
        "fixture_context_reconstruction": fixture_context_report,
        "understat_player_coverage": understat_player_coverage,
        "defensive_source_coverage": defensive_source_coverage,
        "player_history_reconstruction": player_history_report,
        "deadline_team_context_reconstruction": team_context_report,
        "reconstruction_coverage": reconstruction_coverage,
        "snapshot_safety_buffer": {
            "ep_next": ep_safety,
            "signals": signals_safety,
            "market": market_report.get("safety_buffer"),
        },
        "limitations": [
            "The reconstruction uses corrected historical FPL-to-Understat assignments.",
            "The upstream deadline assertion is not treated as proof; all 286 feature families are independently reconstructed or joined from accepted pre-deadline snapshots, but historical source vintages and exact completion timestamps remain unadmitted.",
            "Opponent rolling features and direct ranks are rebuilt from Understat team matches using a conservative 24-hour availability bound; source-vintage and value-parity checks remain open.",
            "Player rolling, availability and defensive-history features are independently recomputed using only fixtures available before each target deadline; source-vintage and value-parity checks remain open.",
            "Fixture-specific rest, team congestion and opponent defensive-allowance context are reconstructed after the upstream deadline anchor; their source-vintage and value-parity checks remain open.",
            "Historical source-vintage revisions are not proven by reconstructing from current archived source files.",
            "value, selected and transfers_balance are sourced from pre-deadline snapshots; retrospective-field parity is reported as a diagnostic, not treated as proof of historical snapshot vintage.",
            "Defensive-stat structural absence before 2025/26 remains subject to season-level coverage admission.",
            "The output is a candidate data artifact only; no training or M3/M4 integration is performed.",
        ],
    }
    report_path = output_dir / "2pm_dastan_286_candidate_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=_json_default) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dastan-root", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seasons", required=True, help="Comma-separated season labels")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--allow-missing-understat", action="store_true")
    parser.add_argument("--include-active-season", action="store_true")
    args = parser.parse_args()
    seasons = [value.strip() for value in args.seasons.split(",") if value.strip()]
    if not seasons or len(set(seasons)) != len(seasons):
        parser.error("--seasons must contain unique comma-separated season labels")
    report = build_candidate(
        args.dastan_root,
        args.raw_dir,
        args.output_dir,
        seasons,
        workers=args.workers,
        force=args.force,
        allow_missing_understat=args.allow_missing_understat,
        include_active_season=args.include_active_season,
    )
    print(json.dumps(report, indent=2, default=_json_default))


if __name__ == "__main__":
    main()
