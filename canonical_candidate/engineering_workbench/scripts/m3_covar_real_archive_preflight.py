#!/usr/bin/env python3
"""Preflight a real private M3 CoVar archive and run only on eligible matched evidence.

This adapter never synthesizes historical forecasts or outcomes. Missing matched
forecast/outcome evidence and late observed outcome availability produce an
explicit blocked report without emitting scenarios.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from m4_covar_residual_bootstrap import (
    ResidualBootstrapError,
    build_residual_bootstrap_scenarios,
)


class M3CoVarArchivePreflightError(ValueError):
    """The real M3 archive or its provenance is invalid."""


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise M3CoVarArchivePreflightError(f"{label} is not readable JSON") from exc
    if not isinstance(value, dict):
        raise M3CoVarArchivePreflightError(f"{label} must be a JSON object")
    return value


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise M3CoVarArchivePreflightError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise M3CoVarArchivePreflightError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise M3CoVarArchivePreflightError(f"{label} must include a timezone")
    return parsed


def verify_real_m3_archive(bundle_path: Path, manifest_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _read_json(manifest_path, "private M3 archive manifest")
    raw = bundle_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != manifest.get("bundle_sha256"):
        raise M3CoVarArchivePreflightError("private M3 forecast bundle SHA-256 differs from its archive manifest")
    if len(raw) != manifest.get("bundle_bytes"):
        raise M3CoVarArchivePreflightError("private M3 forecast bundle byte count differs from its archive manifest")
    bundle = _read_json(bundle_path, "private M3 forecast bundle")
    expected = {
        "season": bundle.get("season"),
        "target_gameweek": bundle.get("target_gameweek"),
        "forecast_snapshot_id": bundle.get("forecast_snapshot_id"),
        "model_version": bundle.get("model_version"),
        "as_of_utc": bundle.get("as_of_utc"),
        "deadline_utc": bundle.get("deadline_utc"),
        "point_in_time_status": bundle.get("point_in_time_status"),
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise M3CoVarArchivePreflightError(f"archive manifest and M3 bundle disagree on {key}")
    if bundle.get("bundle_type") != "M3_CONVENTIONAL_FORECAST_ONLY_COVAR_INPUT":
        raise M3CoVarArchivePreflightError("archive does not contain the manager-free conventional M3 CoVar input")
    if bundle.get("decision_weight") != 0.0 or bundle.get("production_eligible") is not False:
        raise M3CoVarArchivePreflightError("M3 archive does not preserve research-only safeguards")
    if bundle.get("point_in_time_status") != "M3_SOURCE_TIMESTAMPS_VALIDATED":
        raise M3CoVarArchivePreflightError("M3 archive source timestamps are not validated")
    privacy = bundle.get("privacy")
    required_privacy = {
        "manager_identity_included": False,
        "manager_squad_included": False,
        "bank_or_transfer_state_included": False,
        "frozen_decision_included": False,
    }
    if privacy != required_privacy:
        raise M3CoVarArchivePreflightError("M3 archive is not explicitly manager-free")
    sources = bundle.get("source_archives")
    if not isinstance(sources, list) or len(sources) < 2:
        raise M3CoVarArchivePreflightError("M3 bundle source archives are missing")
    seen = set()
    as_of = _time(bundle.get("as_of_utc"), "M3 as_of_utc")
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping):
            raise M3CoVarArchivePreflightError(f"M3 source archive {index} is malformed")
        kind = source.get("source_type")
        if kind not in {"provider_forecast", "player_metadata"} or kind in seen:
            raise M3CoVarArchivePreflightError("M3 bundle requires unique provider and metadata raw archives")
        seen.add(kind)
        captured = _time(source.get("captured_at_utc"), f"{kind} captured_at_utc")
        if captured > as_of:
            raise M3CoVarArchivePreflightError(f"{kind} was captured after the M3 forecast as-of")
        payload = source.get("raw_payload_base64")
        if not isinstance(payload, str) or not payload:
            raise M3CoVarArchivePreflightError(f"{kind} raw payload is missing")
        try:
            decoded = base64.b64decode(payload, validate=True)
        except (ValueError, TypeError) as exc:
            raise M3CoVarArchivePreflightError(f"{kind} raw payload is invalid base64") from exc
        if hashlib.sha256(decoded).hexdigest() != source.get("raw_sha256"):
            raise M3CoVarArchivePreflightError(f"{kind} raw payload SHA-256 mismatch")
    if seen != {"provider_forecast", "player_metadata"}:
        raise M3CoVarArchivePreflightError("provider and player metadata source archives are both required")
    return manifest, bundle


def inspect_finality_capture(finality_dir: Path, season: str) -> dict[str, Any]:
    report_path = finality_dir / "covar-finality-result" / "finality_batch_report.json"
    report = _read_json(report_path, "official finality batch report")
    if report.get("status") != "PASS_ALL_EVENTS" or report.get("season") != season:
        raise M3CoVarArchivePreflightError("official finality artifact is not a passing audit for the target season")
    captures = sorted((finality_dir / "covar-finality-captures").rglob("capture_manifest.json"))
    observed = []
    for path in captures:
        capture = _read_json(path, "official source capture manifest")
        snapshots = capture.get("source_snapshots")
        if not isinstance(snapshots, list):
            continue
        for snapshot in snapshots:
            if isinstance(snapshot, Mapping) and snapshot.get("source_id") == "event_live":
                timestamp = snapshot.get("available_at_utc") or snapshot.get("retrieved_at_utc")
                if timestamp:
                    observed.append(_time(timestamp, "event_live observed availability"))
    if not observed:
        raise M3CoVarArchivePreflightError("finality artifact has no observed event-live availability timestamps")
    return {
        "status": report.get("status"),
        "events_checked": report.get("events_checked", []),
        "event_count": report.get("event_count", 0),
        "earliest_event_live_available_at_utc": min(observed).isoformat(),
        "latest_event_live_available_at_utc": max(observed).isoformat(),
        "observed_event_live_capture_count": len(observed),
        "point_in_time_status": report.get("point_in_time_status"),
    }


def run_preflight(
    *,
    bundle_path: Path,
    archive_manifest_path: Path,
    finality_dir: Path,
    training_cutoff_utc: str | None = None,
    matched_panel_path: Path | None = None,
    scenario_output_path: Path | None = None,
) -> dict[str, Any]:
    manifest, bundle = verify_real_m3_archive(bundle_path, archive_manifest_path)
    cutoff = _time(training_cutoff_utc or bundle["as_of_utc"], "training_cutoff_utc")
    as_of = _time(bundle["as_of_utc"], "M3 as_of_utc")
    deadline = _time(bundle["deadline_utc"], "M3 deadline_utc")
    if cutoff > as_of or as_of >= deadline:
        raise M3CoVarArchivePreflightError("training cutoff <= M3 as-of < deadline is required")

    finality = inspect_finality_capture(finality_dir, bundle["season"])
    earliest = _time(finality["earliest_event_live_available_at_utc"], "earliest event-live availability")
    latest = _time(finality["latest_event_live_available_at_utc"], "latest event-live availability")
    after_cutoff = earliest >= cutoff

    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "report_type": "M3_COVAR_REAL_ARCHIVE_PREFLIGHT",
        "status": "BLOCKED_NO_REAL_MATCHED_FORECAST_OUTCOME_PANEL",
        "archive_verified": True,
        "archive_type": manifest.get("archive_type"),
        "season": bundle["season"],
        "target_gameweek": bundle["target_gameweek"],
        "forecast_snapshot_id": bundle["forecast_snapshot_id"],
        "model_version": bundle["model_version"],
        "as_of_utc": bundle["as_of_utc"],
        "deadline_utc": bundle["deadline_utc"],
        "training_cutoff_utc": cutoff.isoformat(),
        "finality": finality,
        "outcome_availability_after_training_cutoff": after_cutoff,
        "matched_panel_supplied": matched_panel_path is not None,
        "producer_invoked": False,
        "scenario_count": 0,
        "probability_calibrated": False,
        "decision_weight": 0.0,
        "production_eligible": False,
        "covar_used": False,
    }

    if after_cutoff:
        report["status"] = "BLOCKED_OUTCOME_AVAILABILITY_AFTER_TRAINING_CUTOFF"
        report["blocker"] = (
            "The earliest archived official event-live retrieval is at or after the M3 training cutoff. "
            "Those outcomes cannot be represented as available to this forecast."
        )
        return report

    if matched_panel_path is None:
        report["blocker"] = (
            "A finality-only archive is not a forecast-residual panel. Supply prospectively captured "
            "conventional M3 forecast-to-outcome match archives for prior Gameweeks."
        )
        return report

    panel = _read_json(matched_panel_path, "multi-Gameweek matched forecast/outcome panel")
    report["matched_panel_gameweeks"] = panel.get("gameweeks", [])
    report["matched_panel_gameweek_count"] = panel.get("gameweek_count")
    report["producer_invoked"] = True
    try:
        scenarios = build_residual_bootstrap_scenarios(
            bundle,
            panel,
            training_cutoff_utc=cutoff.isoformat(),
        )
    except ResidualBootstrapError as exc:
        report["status"] = "BLOCKED_RESIDUAL_PRODUCER_REJECTED_PANEL"
        report["blocker"] = str(exc)
        return report

    if scenario_output_path is None:
        raise M3CoVarArchivePreflightError("scenario_output_path is required when a matched panel is supplied")
    scenario_output_path.parent.mkdir(parents=True, exist_ok=True)
    scenario_bytes = (json.dumps(scenarios, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    scenario_output_path.write_bytes(scenario_bytes)
    report.update({
        "status": "PASS_RESEARCH_SCENARIOS_CREATED",
        "scenario_count": scenarios["scenario_count"],
        "complete_historical_gameweeks": scenarios["complete_historical_gameweeks"],
        "excluded_historical_gameweek_count": len(scenarios["excluded_historical_gameweeks"]),
        "scenario_payload_sha256": hashlib.sha256(scenario_bytes).hexdigest(),
        "producer_invoked": True,
    })
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--archive-manifest", type=Path, required=True)
    parser.add_argument("--finality-dir", type=Path, required=True)
    parser.add_argument("--training-cutoff-utc")
    parser.add_argument("--matched-panel", type=Path)
    parser.add_argument("--scenario-output", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = run_preflight(
        bundle_path=args.bundle,
        archive_manifest_path=args.archive_manifest,
        finality_dir=args.finality_dir,
        training_cutoff_utc=args.training_cutoff_utc,
        matched_panel_path=args.matched_panel,
        scenario_output_path=args.scenario_output,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
