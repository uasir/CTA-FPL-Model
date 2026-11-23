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
import subprocess
import sys
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from build_2pm_predeadline_market_snapshot import build_market_artifact
from rebuild_2pm_fixture_context import (
    rebuild_deadline_team_context,
    rebuild_fixture_context,
    rebuild_player_history_features,
)

PINNED_DASTAN_COMMIT = "758db9247e8b3a9a870c991064f74d8339d61cd0"
KEY = ["season", "gameweek", "fpl_code"]
MARKET_FIELDS = ["value", "selected", "transfers_balance"]
FRAME_KEY = ["season", "gameweek", "fixture", "fpl_code"]


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
    if out["deadline_time"].ge(out["kickoff_time"]).any():
        raise ValueError("Official deadline is not before every target fixture kickoff")
    return out



def attach_match_availability_bounds(
    frame: pd.DataFrame,
    raw_dir: Path,
    sources_module,
    seasons: list[str],
    *,
    force: bool = False,
) -> pd.DataFrame:
    """Attach a conservative 24-hour post-kickoff availability upper bound.

    Vaastav fixture archives expose kickoff and finished status, not an exact
    completion timestamp. The bound intentionally excludes borderline matches
    rather than inventing an exact finish time.
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
                    "season", "fixture", "match_available_at",
                    "completion_time_quality",
                ]
            ]
        )
    calendar = pd.concat(fixture_frames, ignore_index=True)
    if calendar.duplicated(["season", "fixture"]).any():
        raise ValueError("Fixture availability calendar has duplicate season/fixture keys")
    out = frame.merge(
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
        }
    report["interpretation"] = (
        "Comparison only; retrospective Vaastav values are not treated as deadline-safe truth. "
        "Use differences to detect unit mismatches and snapshot-vintage drift."
    )
    return report

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
    loaded = attach_match_availability_bounds(
        loaded, raw_dir, sources, seasons, force=force
    )
    # Restore canonical fixture identity/context from the raw player-match table.
    # The upstream release frame may have anchored ar_* values across a DGW;
    # rebuild the six fixture-specific context fields after that anchor.
    fixture_context = player_matches[
        ["season", "fixture", "fpl_code", "team_name", "opponent_team_name"]
    ].copy()
    fixture_context["season"] = fixture_context["season"].astype(str)
    fixture_context["fixture"] = fixture_context["fixture"].astype(str)
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
        ["season", "fixture", "match_available_at"]
    ].drop_duplicates(["season", "fixture"])
    history_matches = player_matches.merge(
        fixture_availability,
        on=["season", "fixture"],
        how="left",
        validate="many_to_one",
    )
    loaded, player_history_report = rebuild_player_history_features(
        loaded, history_matches, features
    )
    loaded, team_context_report = rebuild_deadline_team_context(
        loaded, team_matches, features
    )
    loaded, fixture_context_report = rebuild_fixture_context(
        loaded, history_matches
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
        "team_name", "kickoff_time", "deadline_time", "feature_cutoff_time",
        "match_available_at", "completion_time_quality", "source_vintage_status",
        "minutes", "target_points", "ep_next_snapshot_at", "signals_snapshot_at",
        "market_snapshot_at",
    ]
    absent = [column for column in metadata if column not in loaded.columns]
    if absent:
        raise RuntimeError(f"Candidate output is missing metadata columns: {absent}")
    candidate = loaded[metadata + ordered_features].copy()
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
        "feature_order_sha256": hashlib.sha256(
            "\n".join(ordered_features).encode("utf-8")
        ).hexdigest(),
        "identity_mapping_sha256": corrected_map_sha,
        "source_manifest_sha256": sha256(raw_dir / "downloads.json"),
        "candidate_sha256": sha256(candidate_path),
        "deadline_calendar_rows": int(candidate[KEY[:2]].drop_duplicates().shape[0]),
        "pre_deadline_snapshot_rows": {
            "ep_next": len(pd.read_parquet(ep_path)),
            "signals": len(pd.read_parquet(signal_path)),
            "market": len(pd.read_parquet(market_path)),
        },
        "market_snapshot_report": market_report,
        "market_value_parity_audit": market_parity_report,
        "fixture_context_reconstruction": fixture_context_report,
        "player_history_reconstruction": player_history_report,
        "deadline_team_context_reconstruction": team_context_report,
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
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
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
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
