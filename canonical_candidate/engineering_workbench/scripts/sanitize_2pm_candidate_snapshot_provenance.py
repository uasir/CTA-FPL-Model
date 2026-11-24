"""Fail closed on projection/signal/market snapshots too close to official deadlines."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

SNAPSHOT_GROUPS = {
    "ep_next_snapshot_at": ("ar_ep_next",),
    "signals_snapshot_at": ("sig_status_risk", "sig_chance_playing", "sig_has_news"),
    "market_snapshot_at": ("value", "selected", "transfers_balance"),
}


def sanitize_candidate_frame(
    frame: pd.DataFrame, *, safety_buffer_minutes: int = 5
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if safety_buffer_minutes < 0:
        raise ValueError("safety_buffer_minutes must be non-negative")
    required = {"deadline_time", *SNAPSHOT_GROUPS}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Candidate frame missing snapshot provenance columns: {missing}")

    out = frame.copy()
    deadline = pd.to_datetime(out["deadline_time"], utc=True, errors="coerce")
    if deadline.isna().any():
        raise ValueError("deadline_time contains missing or invalid values")

    buffer = pd.Timedelta(minutes=safety_buffer_minutes)
    report: dict[str, Any] = {
        "status": "SNAPSHOT_PROVENANCE_SANITIZED",
        "safety_buffer_minutes": safety_buffer_minutes,
        "groups": {},
        "policy": (
            "A snapshot captured less than the required safety buffer before the "
            "official deadline, at/after the deadline, or with missing/invalid "
            "capture provenance is invalidated. Its associated features become "
            "the explicit -1 missing-snapshot sentinel."
        ),
    }

    for timestamp_column, value_columns in SNAPSHOT_GROUPS.items():
        absent_values = sorted(set(value_columns) - set(out.columns))
        if absent_values:
            raise ValueError(
                f"{timestamp_column} is missing associated feature columns: {absent_values}"
            )
        captured = pd.to_datetime(out[timestamp_column], utc=True, errors="coerce")
        age = deadline - captured
        unsafe = captured.isna() | age.lt(buffer)
        # Missing capture provenance cannot authorize retaining real feature values.
        out.loc[unsafe, list(value_columns)] = -1.0
        out.loc[unsafe, timestamp_column] = pd.NaT
        report["groups"][timestamp_column] = {
            "rows_total": int(len(out)),
            "rows_invalidated": int(unsafe.sum()),
            "rows_retained": int((~unsafe).sum()),
            "feature_columns_sentinelized": list(value_columns),
        }

    return out, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--safety-buffer-minutes", type=int, default=5)
    args = parser.parse_args()

    frame = pd.read_parquet(args.input)
    clean, report = sanitize_candidate_frame(
        frame, safety_buffer_minutes=args.safety_buffer_minutes
    )
    clean.to_parquet(args.input, index=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
