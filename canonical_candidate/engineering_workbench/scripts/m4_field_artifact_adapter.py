#!/usr/bin/env python3
"""Adapt the real post-lock EO capture artifact without leaking it into pre-deadline decisions.

The existing capture freezes the rank cohort before deadline, then fetches final
manager picks after lock. Therefore its EO values are retrospective evidence.
This adapter normalizes provenance and schema but deliberately does not create
an M4 pre-deadline comparison binding.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


class FieldArtifactAdapterError(ValueError):
    pass


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise FieldArtifactAdapterError(f"{label} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FieldArtifactAdapterError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FieldArtifactAdapterError(f"{label} must include a timezone")
    return parsed


def _number(value: Any, label: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise FieldArtifactAdapterError(f"{label} must be numeric or blank") from exc
    if result != result or result in (float("inf"), float("-inf")) or result < 0:
        raise FieldArtifactAdapterError(f"{label} must be finite and non-negative")
    return result


def load_post_lock_field_artifact(
    csv_path: str | Path,
    report_path: str | Path,
    *,
    season: str,
    source_url: str,
) -> dict[str, Any]:
    csv_path, report_path = Path(csv_path), Path(report_path)
    raw_csv = csv_path.read_bytes()
    try:
        metadata = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FieldArtifactAdapterError("EO capture report is missing or invalid JSON") from exc
    if metadata.get("status") != "CAPTURED_POST_DEADLINE_PICKS" or metadata.get("picks_lock_verified") is not True:
        raise FieldArtifactAdapterError("only verified CAPTURED_POST_DEADLINE_PICKS artifacts are supported")

    deadline = _time(metadata.get("deadline_time_utc"), "deadline_time_utc")
    cohort_at = _time(metadata.get("rank_cohort_captured_at_utc"), "rank_cohort_captured_at_utc")
    picks_at = _time(metadata.get("picks_captured_at_utc"), "picks_captured_at_utc")
    grace = metadata.get("lock_grace_seconds")
    if isinstance(grace, bool) or not isinstance(grace, int) or grace < 0:
        raise FieldArtifactAdapterError("lock_grace_seconds must be a non-negative integer")
    if not cohort_at < deadline:
        raise FieldArtifactAdapterError("rank cohort must be frozen before the target deadline")
    if picks_at.timestamp() < deadline.timestamp() + grace:
        raise FieldArtifactAdapterError("manager picks were not captured after the full lock grace period")
    if not season.strip() or not source_url.strip():
        raise FieldArtifactAdapterError("season and source_url are required")

    expected_count = metadata.get("sample_size_captured")
    if isinstance(expected_count, bool) or not isinstance(expected_count, int) or expected_count < 1:
        raise FieldArtifactAdapterError("sample_size_captured must be a positive integer")
    effective_n = _number(metadata.get("effective_sample_size"), "effective_sample_size")
    if effective_n is None or effective_n <= 0:
        raise FieldArtifactAdapterError("effective_sample_size must be positive")

    try:
        text = raw_csv.decode("utf-8")
        reader = csv.DictReader(text.splitlines())
        required = {
            "gameweek", "fpl_element_id", "sample_managers", "sample_weight",
            "owned_by_pct", "starting_pct", "captain_pct", "triple_captain_pct",
            "effective_ownership_pct", "scoring_exposure_pct",
            "effective_ownership_pct_ci95_low", "effective_ownership_pct_ci95_high",
        }
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise FieldArtifactAdapterError("EO CSV columns do not match the estimator contract")
        raw_rows = list(reader)
    except UnicodeDecodeError as exc:
        raise FieldArtifactAdapterError("EO CSV must be UTF-8") from exc
    if not raw_rows:
        raise FieldArtifactAdapterError("EO CSV contains no player rows")

    rows = []
    seen = set()
    gw = str(metadata.get("gameweek"))
    for index, row in enumerate(raw_rows, start=2):
        if str(row.get("gameweek")) != gw:
            raise FieldArtifactAdapterError(f"CSV row {index} belongs to another Gameweek")
        player_id = str(row.get("fpl_element_id", "")).strip()
        if not player_id or player_id in seen:
            raise FieldArtifactAdapterError(f"CSV row {index} has a missing or duplicate FPL element ID")
        seen.add(player_id)
        normalized = {"gameweek": gw, "fpl_element_id": player_id}
        for key in (
            "owned_by_pct", "effective_ownership_pct", "starting_pct",
            "captain_pct", "triple_captain_pct", "scoring_exposure_pct",
            "effective_ownership_pct_ci95_low", "effective_ownership_pct_ci95_high",
        ):
            normalized[key] = _number(row.get(key), f"{player_id}.{key}")
        rows.append(normalized)

    rank_limit = metadata.get("rank_limit")
    rank_min, rank_max = metadata.get("rank_min"), metadata.get("rank_max")
    if not all(isinstance(x, int) and not isinstance(x, bool) and x >= 1 for x in (rank_limit, rank_min, rank_max)):
        raise FieldArtifactAdapterError("rank_limit and observed rank bounds are required")
    if rank_min > rank_max or rank_max > rank_limit:
        raise FieldArtifactAdapterError("observed rank bounds are inconsistent with rank_limit")

    return {
        "artifact_contract_version": "1.0.0",
        "snapshot": {
            "snapshot_id": f"cta-eo-gw{gw}-{hashlib.sha256(raw_csv).hexdigest()[:16]}",
            "season": season,
            "target_gameweek": int(gw),
            "deadline_utc": deadline.isoformat(),
            "cohort_captured_at_utc": cohort_at.isoformat(),
            "captured_at_utc": picks_at.isoformat(),
            "cohort": {
                "name": str(metadata.get("cohort") or "unspecified"),
                "rank_min": rank_min,
                "rank_max": rank_max,
                "rank_limit": rank_limit,
                "rank_strata_count": metadata.get("rank_strata_count"),
            },
            "sample": {
                "manager_count": expected_count,
                "effective_sample_size": effective_n,
                "weighting": "equal_weighted_rank_stratified_sample",
                "sample_weight": metadata.get("sample_weight"),
            },
            "coverage": {
                "covered_player_ids": sorted(seen, key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x)),
                "missing_player_ids": [],
                "row_count": len(rows),
            },
            "source": {
                "source_url": source_url,
                "artifact_sha256": hashlib.sha256(raw_csv).hexdigest(),
                "capture_report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
            },
            "field_eo_rows": rows,
        },
        "evidence_role": "RETROSPECTIVE_POST_LOCK",
        "comparison_admission": "NOT_VALID_FOR_PREDEADLINE_DECISION",
        "timing_note": (
            "Rank cohort was frozen before deadline, but EO values derive from manager picks "
            "captured after deadline and lock grace. This artifact is retrospective only."
        ),
        "release_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = load_post_lock_field_artifact(
        args.csv, args.report, season=args.season, source_url=args.source_url
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
                           encoding="utf-8")
    print(json.dumps({
        "snapshot_id": result["snapshot"]["snapshot_id"],
        "gameweek": result["snapshot"]["target_gameweek"],
        "player_rows": len(result["snapshot"]["field_eo_rows"]),
        "evidence_role": result["evidence_role"],
        "comparison_admission": result["comparison_admission"],
        "release_eligible": result["release_eligible"],
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
