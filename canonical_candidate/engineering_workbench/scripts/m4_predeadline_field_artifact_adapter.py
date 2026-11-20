#!/usr/bin/env python3
"""Adapt a genuine pre-deadline provisional field-EO artifact to M4 contract input."""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


class PredeadlineArtifactError(ValueError):
    pass


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise PredeadlineArtifactError(f"{label} is required")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PredeadlineArtifactError(f"{label} must be ISO-8601") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise PredeadlineArtifactError(f"{label} must include timezone")
    return result


def load_predeadline_field_artifact(csv_path: str | Path, report_path: str | Path,
                                    *, season: str, source_url: str) -> dict[str, Any]:
    csv_path, report_path = Path(csv_path), Path(report_path)
    raw_csv = csv_path.read_bytes()
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PredeadlineArtifactError("pre-deadline field report missing or invalid") from exc

    if report.get("status") != "CAPTURED_PRE_DEADLINE_CURRENT_PICKS":
        raise PredeadlineArtifactError("artifact is not a successful pre-deadline current-picks capture")
    if report.get("evidence_role") != "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE":
        raise PredeadlineArtifactError("artifact evidence role is not pre-deadline provisional")
    if report.get("picks_lock_verified") is not False or report.get("provisional_picks") is not True:
        raise PredeadlineArtifactError("pre-deadline artifact must be explicitly provisional and not lock-verified")
    if not season.strip() or not source_url.strip():
        raise PredeadlineArtifactError("season and source_url are required")

    deadline = _time(report.get("deadline_time_utc"), "deadline_time_utc")
    cohort_at = _time(report.get("rank_cohort_captured_at_utc"), "rank_cohort_captured_at_utc")
    captured_at = _time(report.get("picks_captured_at_utc"), "picks_captured_at_utc")
    if not cohort_at < deadline or not captured_at < deadline:
        raise PredeadlineArtifactError("cohort and picks capture must both precede deadline")
    if captured_at < cohort_at:
        raise PredeadlineArtifactError("picks capture cannot precede rank cohort capture")
    if _time(report.get("capture_started_at_utc"), "capture_started_at_utc") > cohort_at:
        raise PredeadlineArtifactError("capture start cannot follow completed cohort capture")

    digest = hashlib.sha256(raw_csv).hexdigest()
    if report.get("csv_sha256") != digest:
        raise PredeadlineArtifactError("CSV SHA-256 does not match the capture report")
    if report.get("gameweek") is None or report.get("sample_size_captured") != report.get("sample_managers"):
        raise PredeadlineArtifactError("report Gameweek or sample count is inconsistent")
    manager_count = report.get("sample_managers")
    effective_n = report.get("effective_sample_size")
    if isinstance(manager_count, bool) or not isinstance(manager_count, int) or manager_count < 1:
        raise PredeadlineArtifactError("sample_managers must be a positive integer")
    if isinstance(effective_n, bool) or not isinstance(effective_n, (int, float)) or not 0 < effective_n <= manager_count:
        raise PredeadlineArtifactError("effective_sample_size must be positive and no greater than manager count")

    rank_limit, rank_min, rank_max = report.get("rank_limit"), report.get("rank_min"), report.get("rank_max")
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (rank_limit, rank_min, rank_max)):
        raise PredeadlineArtifactError("rank limit and observed bounds must be integers")
    if not 1 <= rank_min <= rank_max <= rank_limit:
        raise PredeadlineArtifactError("observed rank bounds are inconsistent")

    required = {
        "gameweek", "fpl_element_id", "sample_managers", "sample_weight",
        "owned_by_pct", "starting_pct", "captain_pct", "triple_captain_pct",
        "effective_ownership_pct", "scoring_exposure_pct",
        "effective_ownership_pct_ci95_low", "effective_ownership_pct_ci95_high",
    }
    try:
        reader = csv.DictReader(raw_csv.decode("utf-8").splitlines())
    except UnicodeDecodeError as exc:
        raise PredeadlineArtifactError("EO CSV must be UTF-8") from exc
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise PredeadlineArtifactError("CSV columns do not match the EO estimator contract")
    rows, seen = [], set()
    for line_number, row in enumerate(reader, start=2):
        if str(row.get("gameweek")) != str(report["gameweek"]):
            raise PredeadlineArtifactError(f"CSV row {line_number} belongs to another Gameweek")
        if str(row.get("sample_managers")) != str(manager_count):
            raise PredeadlineArtifactError(f"CSV row {line_number} sample count differs from report")
        player_id = str(row.get("fpl_element_id", "")).strip()
        if not player_id or player_id in seen:
            raise PredeadlineArtifactError(f"CSV row {line_number} has missing or duplicate player ID")
        seen.add(player_id)
        normalized = {"gameweek": str(report["gameweek"]), "fpl_element_id": player_id}
        numeric = [
            "owned_by_pct", "effective_ownership_pct", "starting_pct", "captain_pct",
            "triple_captain_pct", "scoring_exposure_pct",
            "effective_ownership_pct_ci95_low", "effective_ownership_pct_ci95_high",
        ]
        for key in numeric:
            value = row.get(key)
            if value in (None, ""):
                normalized[key] = None
                continue
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise PredeadlineArtifactError(f"{player_id}.{key} must be numeric or blank") from exc
            if number != number or number in (float("inf"), float("-inf")) or number < 0:
                raise PredeadlineArtifactError(f"{player_id}.{key} must be finite and non-negative")
            normalized[key] = number
        rows.append(normalized)
    if not rows:
        raise PredeadlineArtifactError("EO CSV contains no player rows")

    return {
        "snapshot": {
            "snapshot_id": f"cta-predeadline-gw{report['gameweek']}-{digest[:16]}",
            "season": season,
            "target_gameweek": int(report["gameweek"]),
            "deadline_utc": deadline.isoformat(),
            "captured_at_utc": captured_at.isoformat(),
            "cohort": {
                "name": str(report.get("cohort") or "unspecified"),
                "rank_min": rank_min, "rank_max": rank_max, "rank_limit": rank_limit,
                "rank_strata_count": report.get("rank_strata_count"),
            },
            "sample": {
                "manager_count": manager_count,
                "effective_sample_size": float(effective_n),
                "weighting": "equal_weighted_rank_stratified_sample",
                "sample_weight": report.get("sample_weight"),
            },
            "coverage": {"covered_player_ids": sorted(seen), "missing_player_ids": []},
            "source": {"source_url": source_url, "artifact_sha256": digest,
                       "capture_report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest()},
        },
        "field_eo_rows": rows,
        "evidence_role": "PRE_DEADLINE_PROVISIONAL_FIELD_ESTIMATE",
        "picks_lock_verified": False,
        "provisional_picks": True,
        "release_eligible": False,
    }
